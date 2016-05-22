
from uuid import uuid4
from socket import AF_UNIX, AF_INET, SOCK_STREAM
import logging
import json
import random
import socket
import subprocess
import sys

from gevent.pool import Group
import gevent

from gclient import GSocketClient
from gtools import send_fd, recv_fd

from .bot import PippyBot


class IPCServer(object):
	WORKER_RESPAWN_INTERVAL = 1

	def __init__(self, main, num_workers, logger=None):
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__)
		self.sock_path = '/tmp/{}.sock'.format(uuid4())
		self.main = main
		self.group = Group()
		self.listener = socket.socket(AF_UNIX, SOCK_STREAM)
		self.listener.bind(self.sock_path)
		self.listener.listen(128)
		self.group.spawn(self.run)
		self.conns = {}
		for i in range(num_workers):
			self.group.spawn(self._worker_proc_watchdog)

	def run(self):
		while True:
			sock, addr = self.listener.accept()
			IPCMasterConnection(self, sock).start()
			# will insert itself into conns once it knows its name

	def _worker_proc_watchdog(self):
		while True:
			proc = None
			try:
				proc = subprocess.Popen([sys.executable, '-m', 'pipirc.ipc', self.sock_path])
				proc.wait()
			except Exception:
				self.logger.exception("Error starting or waiting on subprocess")
			else:
				if proc.returncode == 0:
					return
				self.logger.error("Subprocess died with exit code {}".format(proc.returncode))
			finally:
				if proc and proc.returncode is None:
					try:
						proc.kill()
					except OSError:
						pass
			gevent.sleep(self.WORKER_RESPAWN_INTERVAL * random.uniform(0.9, 1.1))

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

	def open_channel(self, channel, pip_sock):
		self._choose_conn().open_channel(channel, pip_sock)

	def recv_chat(self, channel, text, sender, sender_rank):
		conn = self.channels_to_conns.get(channel)
		if not conn:
			return
		conn.recv_chat(channel, text, sender, sender_rank)


class IPCConnection(GSocketClient):
	name = None

	def __init__(self, socket, logger=None):
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__)
		super(IPCConnection, self).__init__()
		self._socket = socket

	def send(self, type, block=False, **data):
		"""Send message of given type, with other args.
		Set 'fd' to an integer fd to send that fd over the wire."""
		data['type'] = type
		return super(IPCConnection, self).send(data, block=block)

	def _send(self, msg):
		if hasattr(msg.get('fd'), 'fileno'):
			# since we might be the last reference preventing msg['fd'] from closing,
			# we need to hold onto it until after send_fd(). A local var does fine.
			fileobj = msg['fd']
			msg['fd'] = fileobj.fileno()
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
				self.logger.exception("Failed to process IPC request of type {!r} with args {!r}".format(msg_type, msg))


class IPCMasterConnection(IPCConnection):
	def __init__(self, server, socket, logger=None):
		super(IPCMasterConnection, self).__init__(socket, logger=logger)
		self.server = server
		self.channels = set() # set of channels handled by the worker we're connected to
		self._handle_map = {
			'chat message': self._send_chat,
			'close channel': self._close_channel,
			'init': self._init,
		}

	def _stop(self, ex=None):
		super(IPCMasterConnection, self)._stop()
		for channel in self.channels:
			self._send_chat(channel, "Something went wrong. Please reconnect.")
		if self.name is not None:
			assert self.server.conns.pop(self.name) is self
		self.server.main.sync_channels()

	def _init(self, name):
		self.name = name
		self.server.conns[name] = self

	def open_channel(self, channel, pip_fd):
		"""Send channel info and pip protocol fd for given channel to worker process,
		assigning the channel to this process."""
		self.channels.add(channel)
		self.server.main.sync_channels()
		self.send('open channel', channel=channel, fd=pip_fd)

	def _close_channel(self, channel):
		self.channels.remove(channel)
		self.server.main.sync_channels()

	def _send_chat(self, channel, text):
		self.server.main.send_chat(channel, text)

	def recv_chat(self, channel, text, sender, sender_rank):
		self.send('chat message', channel=channel, text=text, sender=sender, sender_rank=sender_rank)


class IPCWorkerConnection(IPCConnection):
	def __init__(self, name, sock_path, config, logger=None):
		self.name = name
		self.channels = {} # {channel: PippyBot}
		self.config = config
		self.parent_logger = logger or logging.getLogger()
		self._handle_map = {
			'open channel': self._open_channel,
			'chat message': self._recv_chat,
			'quit': self._quit,
		}

		sock = socket.socket(AF_UNIX, SOCK_STREAM)
		sock.connect(sock_path)
		super(IPCWorkerConnection, self).__init__(sock, logger=self.parent_logger)

		self.init(self.name)

	def init(self, name):
		self.send('init', name=name)

	def _quit(self):
		self.stop()

	def _open_channel(self, channel, fd):
		pip_sock = socket.fromfd(fd, AF_INET, SOCK_STREAM)
		self.channels[channel] = PippyBot(self, channel, pip_sock, self.config, logger=self.parent_logger)

	def close_channel(self, channel):
		del self.channels[channel]
		self.send('close channel', channel=channel)

	def send_chat(self, channel, text):
		self.send('chat message', channel=channel, text=text)

	def _recv_chat(self, channel, text, sender, sender_rank):
		if channel in self.channels:
			self.channels[channel].recv_chat(text, sender, sender_rank)

