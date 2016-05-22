
from itertools import groupby

from gevent.queue import Queue
from gevent.event import AsyncResult

import girc.message
from backoff import Backoff
from gclient import GClient


def get_sender_rank(channel, tags):
	"""From twitch tags, return a string message sender rank"""
	if tags['display-name'].lower() == channel.lower().lstrip('#'):
		return 'broadcaster'
	for level in ('mod', 'subscriber'):
		if tags.get(level) == '1':
			return level
	return 'viewer'


class IRCHostsManager(object):
	"""An abstraction around a group of irc clients that provide service to different irc servers.
	Takes a set of (host, nick, oauth, channel) tuples and automatically manages one actual client
	per unique (host, nick, oauth).
	Any PrivMsgs received will be passed to the given callback as (stream, text, sender, sender_rank)
	Note we assume stream name = channel_name.lstrip('#')
	"""
	# NOTE on security: We can't re-use a client for the same (host, nick) with differing oauth
	# as we'd have no way of knowing if any oauth but the first was valid, which would potentially
	# let unauthorized users in. In the unusual case where the same nick has more than one oauth
	# provided and both work, it's a pessimization we can live with.

	def __init__(self, callback):
		self.clients = {} # {(host, nick, oauth): client}
		self.callback = callback

	def send(self, host, nick, oauth, channel, msg):
		self.clients[host, nick, oauth].send(channel, msg)

	def _recv(self, client, msg):
		# prefer twitch display-name for correct capitalization
		sender = msg.tags.get('display-name', msg.sender)
		sender_rank = get_sender_rank(msg.target, msg.tags)
		self.callback(msg.target.lstrip('#'), msg.payload, sender, sender_rank)

	def update_connections(self, connections):
		"""Channels should be a set of (host, nick, oauth, channel)"""
		connections = {
			(host, nick, oauth): set(channel for _, _, _, channel in items)
			for (host, nick, oauth), items in groupby(connections, lambda item: item[:3])
		}
		for host, nick, oauth in set(connections.keys()) | set(self.clients.keys()):
			if (host, nick, oauth) not in self.clients:
				# new connection
				self.clients[host, nick, oauth] = IRCClientManager(
					host, nick, self._recv, channels=connections[host, nick, oauth],
					password=oauth, twitch=True,
				)
				self.clients[host, nick, oauth].start()
			elif (host, nick, oauth) in connections:
				# existing connection
				self.clients[host, nick, oauth].update_channels(connections[host, nick, oauth])
			else:
				# dead connection
				self.clients.pop((host, nick, oauth)).stop()
		assert set(self.clients.keys()) == set(connections.keys()), (
			"Mismatch after syncing client managers: {!r} keys don't match {!r}".format(
				self.clients, connections,
			)
		)


class IRCClientManager(GClient):
	"""An abstraction around an irc connection that provides automatic reconnects
	while preserving channel membership and re-enqueuing any messages we know were never sent
	(so messages may still be lost, but it is less likely).
	Takes a generic callback with args (irc_client_manager, msg) for all incoming PrivMsgs.
	"""

	def __init__(self, host, nick, callback, channels=None, **irc_kwargs):
		irc_kwargs.update(hostname=host, nick=nick)
		self.recv_callback = callback
		self.irc_kwargs = irc_kwargs

		self.channels = set() if channels is None else channels
		self._client = AsyncResult()
		self._recv_queue = Queue()

		super(IRCClientManager, self).__init__()

	def _start(self):
		self._client_loop_worker = self.group.spawn(self._client_loop)

	def _client_loop(self):
		try:
			backoff = Backoff(start=0.1, limit=10, rate=5)
			while True:
				client = girc.Client(**self.irc_kwargs)
				for channel in self.channels:
					client.channel(channel).join()
				client.handler(self._client_recv, command=girc.message.Privmsg)
				self._client.set(client)
				try:
					client.start()
					backoff.reset()
					client.wait_for_stop()
				except Exception as ex:
					# clear _client if no-one else has
					if self._client.ready():
						assert self._client.get() is client
						self._client = AsyncResult()
				else:
					self.stop() # graceful exit
					return
		except Exception as ex:
			self.stop(ex)

	def _client_recv(self, client, msg):
		self._recv_queue.put(msg)

	@property
	def client(self):
		while True:
			waiter = self._client
			client = waiter.get()
			if not client._stopping:
				return client
			# clear _client if no-one else has
			if self._client is waiter:
				self._client = AsyncResult()

	def send(self, channel, text):
		super(IRCClientManager, self).send((channel, text))

	def update_channels(self, new_channels):
		self.channels = new_channels
		if not self._client.ready() or self._client.get()._stopping:
			return # no active connection, we're done
		client = self._client.get()
		old_channels = client.joined_channels
		for channel in old_channels - new_channels:
			client.channel(channel).part()
		for channel in new_channels - old_channels:
			client.channel(channel).join()
		assert self.channels == client.joined_channels, "Channel mismatch after sync: {!r} != {!r}".format(self.channels, client.joined_channels)

	def _send(self, msg):
		channel, text = msg
		try:
			girc.message.Privmsg(self.client, channel, text).send(block=True)
		except Exception:
			# we can't be certain the message wasn't sent, so discard it
			# but at least we know all remaining items in the queue have not been.
			pass

	def _receive(self):
		for msg in self._recv_queue:
			try:
				self.recv_callback(self, msg)
			except Exception:
				# TODO log
				pass

	def _stop(self, ex):
		if self._client.ready():
			self._client.get().quit()
