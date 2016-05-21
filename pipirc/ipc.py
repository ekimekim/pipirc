
from uuid import uuid4
from socket import AF_UNIX, AF_INET, SOCK_STREAM
import json
import socket

from gevent.pool import Group

from gclient import GSocketClient
from gtools import send_fd, recv_fd

from .bot import PippyBot


class IPCServer(object):
	def __init__(self, main):
		self.sock_path = '/tmp/{}.sock'.format(uuid4())
		self.main = main
		self.group = Group()
		self.listener = socket.socket(AF_UNIX, SOCK_STREAM)
		self.listener.listen(128)
		self.listener.bind(self.sock_path)
		self.group.spawn(self.run)
		self.conns = {}

	def run(self):
		while True:
			sock, addr = self.listener.accept()
			name = uuid4()
			self.conns[name] = IPCMasterConnection(self, name, sock)

	@property
	def channels_to_conns(self):
		ret = {}
		for conn in self.conns.values():
			for channel in conn.channels:
				assert channel not in ret
				ret[channel] = conn
		return ret

	@property
	def channels(self):
		"""Set of all connected channels"""
		return set(self.channels_to_conns.keys())

	def _choose_conn(self):
		"""Pick a conn to be given a new channel."""
		# approximate least loaded as least channels
		return min(self.conns.values(), key=lambda conn: len(conn.channels))

	def open_channel(self, channel, pip_sock, **options):
		self._choose_conn().open_channel(channel, pip_sock, **options)

	def recv_chat(self, channel, text, sender, sender_rank):
		conn = self.channels_to_conns.get(channel)
		if not conn:
			return
		conn.recv_chat(channel, text, sender, sender_rank)


class IPCConnection(GSocketClient):
	def __init__(self, socket):
		super(IPCConnection, self).__init__()
		self._socket = socket

	def send(self, type, block=False, **data):
		"""Send message of given type, with other args.
		Set 'fd' to an integer fd to send that fd over the wire."""
		data['type'] = type
		return super(IPCConnection, self).send(data, block=block)

	def _send(self, msg):
		super(IPCConnection, self)._send(msg)
		if msg.get('fd') is not None:
			send_fd(self._socket, msg['fd'])

	def _encode(self, msg):
		return json.dumps(msg) + '\n'

	def _handle(self, msg):
		msg = json.loads(msg)
		if 'fd' in msg:
			msg['fd'] = recv_fd(self._socket)
		msg_type = msg.pop('type')
		if msg_type in self._handle_map:
			try:
				self._handle_map[msg_type](**msg)
			except Exception:
				# TODO log
				pass


class IPCMasterConnection(IPCConnection):
	def __init__(self, server, name, socket):
		super(IPCMasterConnection, self).__init__(socket)
		self.server = server
		self.name = name
		self.channels = set() # set of channels handled by the worker we're connected to
		self.send('init', name=name)
		self._handle_map = {
			'chat message': self._send_chat,
			'close channel': self._close_channel,
		}
		self.start()

	def _stop(self, ex=None):
		super(IPCMasterConnection, self)._stop()
		for channel in self.channels:
			self._send_chat(channel, "Something went wrong. Please reconnect.")
		assert self.server.conns.pop(self.name) is self
		self.server.main.sync_channels()

	def open_channel(self, channel, pip_fd, **options):
		"""Send channel info and pip protocol fd for given channel to worker process,
		assigning the channel to this process."""
		self.channels.add(channel)
		self.server.main.sync_channels()
		self.send('open channel', channel=channel, fd=pip_fd, **options)

	def _close_channel(self, channel):
		self.channels.remove(channel)
		self.server.main.sync_channels()

	def _send_chat(self, channel, text):
		self.server.main.send_chat(channel, text)

	def recv_chat(self, channel, text, sender, sender_rank):
		self.send('chat message', channel=channel, text=text, sender=sender, sender_rank=sender_rank)


class IPCWorkerConnection(IPCConnection):
	def __init__(self, sock_path):
		sock = socket.socket(AF_UNIX, SOCK_STREAM)
		sock.connect(sock_path)
		super(IPCWorkerConnection, self).__init__(sock)
		self.channels = {} # {channel: PippyBot}
		self._handle_map = {
			'init': self._init,
			'open channel': self._open_channel,
			'chat message': self._recv_chat,
		}
		self.start()

	def _init(self, name):
		self.name = name

	def _open_channel(self, channel, fd, **options):
		pip_sock = socket.fromfd(fd, AF_INET, SOCK_STREAM)
		self.channels[channel] = PippyBot(self, pip_sock, options)

	def close_channel(self, channel):
		del self.channels[channel]
		self.send('close channel', channel=channel)

	def send_chat(self, channel, text):
		self.send('chat message', channel=channel, text=text)

	def _recv_chat(self, channel, text, sender, sender_rank):
		if channel in self.channels:
			self.channels[channel].recv_chat(text, sender, sender_rank)
