
from uuid import uuid4
from socket import AF_UNIX, AF_INET, SOCK_STREAM
import json
import random
import socket
import subprocess
import sys

from gevent.pool import Group
import gevent

from classtricks import HasLogger
from gclient import GSocketClient
from gtools import gmap, send_fd, recv_fd

from .bot import PippyBot


class IPCServer(HasLogger):
	WORKER_RESPAWN_INTERVAL = 1

	stopping = False

	def __init__(self, main, num_workers, logger=None):
		super(IPCServer, self).__init__(logger=logger)
		self.sock_path = '/tmp/{}.sock'.format(uuid4())
		self.main = main
		self.group = Group()
		self.listener = socket.socket(AF_UNIX, SOCK_STREAM)
		self.listener.bind(self.sock_path)
		self.listener.listen(128)
		self._accept_loop = self.group.spawn(self.run)
		self.conns = {}
		for i in range(num_workers):
			self.group.spawn(self._worker_proc_watchdog)

	def run(self):
		while not self.stopping:
			sock, addr = self.listener.accept()
			self.logger.debug("Accepted sock fd {} from address {}".format(sock.fileno(), addr))
			IPCMasterConnection(self, sock, logger=self.logger).start()
			# will insert itself into conns once it knows its name

	def _worker_proc_watchdog(self):
		while True:
			proc = None
			self.logger.info("Starting worker process")
			try:
				proc = subprocess.Popen([
					sys.executable,
					'-m', 'pipirc.worker',
					self.main.config.filepath, self.sock_path,
				])
				proc.wait()
			except Exception:
				self.logger.exception("Error starting or waiting on subprocess")
			else:
				if proc.returncode == 0:
					self.logger.info("Worker cleanly shut down")
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
	def streams_to_conns(self):
		ret = {}
		for conn in self.conns.values():
			for stream in conn.streams:
				assert stream not in ret
				ret[stream] = conn
		return ret

	@property
	def streams(self):
		"""Set of all connected streams"""
		return set(self.streams_to_conns.keys())

	def _choose_conn(self):
		"""Pick a conn to be given a new stream."""
		# approximate least loaded as least streams
		return min(self.conns.values(), key=lambda conn: len(conn.streams))

	def open_stream(self, stream, pip_sock):
		conn = self._choose_conn()
		conn.open_stream(stream, pip_sock)
		self.logger.debug("Opening new stream {} onto conn {} with sock {}".format(stream, conn, pip_sock))

	def recv_chat(self, stream, text, sender, sender_rank):
		conn = self.streams_to_conns.get(stream)
		self.logger.debug("Got chat message for stream {} (conn {}): {}({}) says {!r}".format(
			stream, conn, sender, sender_rank, text
		))
		if not conn:
			return
		conn.recv_chat(stream, text, sender, sender_rank)

	def stop(self):
		"""Gracefully stop all workers. Blocks until all workers have completely stopped."""
		self.stopping = True
		self._accept_loop.kill(block=False)
		self.logger.debug("Waiting for workers to stop")
		gmap(lambda conn: conn.stop(), self.conns.values())
		self.group.join()


class IPCConnection(HasLogger, GSocketClient):
	name = None

	def __init__(self, socket, logger=None):
		self._socket = socket
		super(IPCConnection, self).__init__(logger=logger)

	def __repr__(self):
		return "<{cls.__name__} {self.name}>".format(self=self, cls=type(self))
	__str__ = __repr__

	def send(self, type, block=False, **data):
		"""Send message of given type, with other args.
		Set 'fd' to an integer fd to send that fd over the wire."""
		data['type'] = type
		self.logger.debug("Enqueuing {} to be sent".format(data))
		return super(IPCConnection, self).send(data, block=block)

	def _send(self, msg):
		self.logger.debug("Sending {}".format(msg))
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
		self.logger.debug("Recieved {}".format(msg))
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
		self.streams = set() # set of streams handled by the worker we're connected to
		self._handle_map = {
			'chat message': self._send_chat,
			'close stream': self._close_stream,
			'init': self._init,
		}

	def _stop(self, ex=None):
		super(IPCMasterConnection, self)._stop()
		for stream in self.streams:
			self._send_chat(stream, "Something went wrong. Attempting to reconnect...")
		if self.name is not None:
			assert self.server.conns.pop(self.name) is self
		self.server.main.sync_streams()

	def _init(self, name):
		if self.server.stopping:
			self.stop()
		else:
			self.name = name
			self.server.conns[name] = self

	def open_stream(self, stream, pip_fd):
		"""Send stream info and pip protocol fd for given stream to worker process,
		assigning the stream to this process."""
		self.streams.add(stream)
		self.server.main.sync_streams()
		self.send('open stream', stream=stream, fd=pip_fd)

	def _close_stream(self, stream):
		self.streams.remove(stream)
		self.server.main.sync_streams()

	def _send_chat(self, stream, text):
		self.server.main.send_chat(stream, text)

	def recv_chat(self, stream, text, sender, sender_rank):
		self.send('chat message', stream=stream, text=text, sender=sender, sender_rank=sender_rank)


class IPCWorkerConnection(IPCConnection):
	def __init__(self, name, sock_path, config, logger=None):
		self.name = name
		self.streams = {} # {stream: PippyBot}
		self.config = config
		self._handle_map = {
			'open stream': self._open_stream,
			'chat message': self._recv_chat,
		}

		sock = socket.socket(AF_UNIX, SOCK_STREAM)
		sock.connect(sock_path)
		super(IPCWorkerConnection, self).__init__(sock, logger=logger)

		self.init(self.name)

	def init(self, name):
		self.send('init', name=name)

	def _open_stream(self, stream, fd):
		pip_sock = socket.fromfd(fd, AF_INET, SOCK_STREAM)
		try:
			self.streams[stream] = PippyBot(self, pip_sock, stream, self.config.streams[stream], logger=self.logger)
		except Exception:
			self.logger.exception("Failed to init stream {}".format(stream))
			self.send('close stream', stream=stream)

	def close_stream(self, stream):
		if stream in self.streams:
			self.streams.pop(stream)
			self.send('close stream', stream=stream)

	def send_chat(self, stream, text):
		self.send('chat message', stream=stream, text=text)

	def _recv_chat(self, stream, text, sender, sender_rank):
		if stream in self.streams:
			self.streams[stream].recv_chat(text, sender, sender_rank)

	def _stop(self, ex=None):
		super(IPCWorkerConnection, self)._stop()

		# since our connection is gone, treat the expected master state as having no streams
		# this ensures we don't try to send any closes, etc.
		self.streams = {}

		for bot in self.streams.values():
			bot.stop()

