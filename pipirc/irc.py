
from gevent.queue import Queue
from gevent.event import AsyncResult

import girc.message
from backoff import Backoff
from gclient import GClient


class IRCClientManager(GClient):
	"""An abstraction around an irc connection that provides automatic reconnects
	while preserving channel membership and re-enqueuing any messages we know were never sent
	(so messages may still be lost, but it is less likely).
	Takes a generic callback for all incoming messages.
	"""

	def __init__(self, host, nick, callback, **irc_kwargs):
		irc_kwargs.update(hostname=host, nick=nick)
		self.recv_callback = callback
		self.irc_kwargs = irc_kwargs

		self.channels = set()
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
				client.handler(self._client_recv)
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
					break # graceful exit
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
			self.recv_callback(msg)

	def _stop(self, ex):
		if self._client.ready():
			self._client.get().quit()
