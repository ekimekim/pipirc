
from collections import defaultdict
from itertools import groupby

from gevent.event import AsyncResult
from gevent.pool import Group
from gevent.queue import Queue

import girc.message
from classtricks import HasLogger
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


class IRCHostsManager(HasLogger):
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

	def __init__(self, callback, logger=None):
		self.clients = {} # {(host, nick, oauth): client}
		self.streams = {} # {stream name: (host, nick, oauth, channel)}
		self._stopping_clients = Group()
		self.callback = callback
		super(IRCHostsManager, self).__init__(logger=logger)

	def send(self, name, msg):
		if name not in self.streams:
			# shouldn't be able to happen, unless a channel was closed without IPC server knowing?
			self.logger.warning("Tried to send message for unknown stream {!r}: {!r}".format(name, msg))
			return
		host, nick, oauth, channel = self.streams[name]
		self.clients[host, nick, oauth].send(channel, msg)

	def _recv(self, client, msg):
		# prefer twitch display-name for correct capitalization
		sender = msg.tags.get('display-name', msg.sender)
		sender_rank = get_sender_rank(msg.target, msg.tags)
		stream_name = msg.target.lstrip('#') # NOTE: we depend on channel name being #stream-name
		self.callback(stream_name, msg.payload, sender, sender_rank)

	def update_connections(self, connections):
		"""Channels should be a set of (name, host, nick, oauth, channel)"""
		self.logger.debug("Updating streams={} to connections {}".format(self.streams, connections))
		connections = {
			(host, nick, oauth): set(channel for name, _, _, _, channel in items)
			for (host, nick, oauth), items in groupby(connections, lambda item: item[:3])
		}
		self.streams = {name: (host, nick, oauth, channel) for name, host, nick, oauth, channel in connections}
		for host, nick, oauth in set(connections.keys()) | set(self.clients.keys()):
			if (host, nick, oauth) not in self.clients:
				# new connection
				self.logger.info("Starting new irc client for {}@{}".format(nick, host))
				self.clients[host, nick, oauth] = IRCClientManager(
					host, nick, self._recv, channels=connections[host, nick, oauth],
					password=oauth, twitch=True, logger=self.logger,
				)
				self.clients[host, nick, oauth].start()
			elif (host, nick, oauth) in connections:
				# existing connection
				self.logger.debug("Updating channels for {}@{}".format(nick, host))
				self.clients[host, nick, oauth].update_channels(connections[host, nick, oauth])
			else:
				# dead connection
				client = self.clients.pop((host, nick, oauth))
				self.logger.info("Client {}({}@{}) has no more connections, stopping".format(
					client, nick, host
				))
				client.update_channels(set()) # by setting to no channels, ensures client won't call recv callback
				self._stopping_clients.spawn(client.wait_and_stop)
		assert set(self.clients.keys()) == set(connections.keys()), (
			"Mismatch after syncing client managers: {!r} keys don't match {!r}".format(
				self.clients, connections,
			)
		)

	def stop(self):
		"""Block on all clients messages sent and shut down"""
		for client in self.clients.values():
			self._stopping_clients.spawn(client.wait_and_stop)
		self.logger.debug("Waiting for all clients to finish stopping")
		self._stopping_clients.join()


class IRCClientManager(HasLogger, GClient):
	"""An abstraction around an irc connection that provides automatic reconnects
	while preserving channel membership and re-enqueuing any messages we know were never sent
	(so messages may still be lost, but it is less likely).
	Takes a generic callback with args (irc_client_manager, msg) for all incoming PrivMsgs.
	"""

	def __init__(self, host, nick, callback, channels=None, logger=None, **irc_kwargs):
		irc_kwargs.update(hostname=host, nick=nick)
		self.recv_callback = callback
		self.irc_kwargs = irc_kwargs

		self.channels = set() if channels is None else channels
		self.channel_pending = defaultdict(lambda: 0) # {channel: num of pending messages on queue}
		self._client = AsyncResult()
		self._recv_queue = Queue()

		super(IRCClientManager, self).__init__(logger=logger)

	@property
	def all_open_channels(self):
		"""self.channels is desired channels, self.channel_pending tracks any with unsent messages,
		actual open channels is a union of the two."""
		return self.channels | set(self.channel_pending.keys())

	def _start(self):
		self._client_loop_worker = self.group.spawn(self._client_loop)

	def _client_loop(self):
		try:
			backoff = Backoff(start=0.1, limit=10, rate=5)
			while True:
				self.logger.info("Starting new irc connection")
				client = girc.Client(**self.irc_kwargs)
				self.logger.debug("Joining channels: {}".format(self.all_open_channels))
				for channel in self.all_open_channels:
					client.channel(channel).join()
				client.handler(self._client_recv, command=girc.message.Privmsg)
				self._client.set(client)
				try:
					client.start()
					self.logger.debug("Started new irc connection")
					backoff.reset()
					client.wait_for_stop()
				except Exception as ex:
					self.logger.warning("irc connection died", exc_info=True)
					# clear _client if no-one else has
					if self._client.ready():
						assert self._client.get() is client
						self._client = AsyncResult()
				else:
					self.logger.info("irc connection exited gracefully, stopping")
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
		self.channel_pending[channel] += 1
		self.logger.debug("Enqueuing message for channel {} ({} now pending): {!r}".format(
			channel, self.channel_pending[channel], text
		))
		super(IRCClientManager, self).send((channel, text))

	def update_channels(self, new_channels):
		old_channels = self.all_open_channels
		self.channels = new_channels
		if not self._client.ready() or self._client.get()._stopping:
			self.logger.debug("Ignoring channel resync, client not running")
			return # no active connection, we're done
		client = self._client.get()
		self.logger.debug("Updating channels: {} to {}".format(old_channels, self.all_open_channels))
		for channel in old_channels - self.all_open_channels:
			client.channel(channel).part()
		for channel in new_channels - self.all_open_channels:
			client.channel(channel).join()

	def _send(self, msg):
		if msg == 'stop':
			self.logger.debug("Calling graceful stop due to stop message on queue")
			self.stop() # does not return
			assert False
		channel, text = msg
		try:
			girc.message.Privmsg(self.client, channel, text).send(block=True)
		except Exception:
			# we can't be certain the message wasn't sent, so discard it
			# but at least we know all remaining items in the queue have not been.
			pass
		finally:
			self.channel_pending[channel] -= 1
			self.logger.debug("Sent message for channel {} ({} now pending): {!r}".format(
				channel, self.channel_pending[channel], text
			))
			if self.channel_pending[channel] <= 0:
				del self.channel_pending[channel]
				if self._client.ready():
					self._client.get().channel(channel).part()

	def _receive(self):
		for msg in self._recv_queue:
			if msg.target not in self.channels:
				self.logger.debug("Ignoring message {}, not a channel we care about".format(msg))
				# ignore PMs and messages from channels we're only holding open while we finish sending
				return
			try:
				self.recv_callback(self, msg)
			except Exception:
				self.logger.exception("Failed to handle message {}".format(msg))
				pass

	def wait_and_stop(self):
		"""Graceful stop. Waits to send all remaining messages."""
		self.logger.debug("Setting stop message for flushing send queue then stop")
		super(IRCClientManager, self).send('stop')
		self.wait_for_stop()

	def _stop(self, ex):
		if self._client.ready():
			self._client.get().quit()
