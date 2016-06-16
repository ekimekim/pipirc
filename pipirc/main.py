
import logging
import multiprocessing
import signal

import gevent.event

from classtricks import HasLogger

from .config import ServiceConfig
from .ipc import IPCServer
from .irc import IRCHostsManager
from .pipserver import PipConnectionServer


def constant_time_equal(a, b):
	"""Compare two strings in constant time (if they're the same length)"""
	return len(a) == len(b) and sum(ord(c1) ^ ord(c2) for c1, c2 in zip(a, b)) == 0


class Main(HasLogger):
	"""Ties the main parts of the server together"""
	def __init__(self, config, logger=None):
		super(Main, self).__init__(logger=logger)
		self.config = config
		self.streams = self.config.streams # probably going to change this later
		self.ipc_server = IPCServer(self, multiprocessing.cpu_count())
		self.irc_manager = IRCHostsManager(self.ipc_server.recv_chat)
		self.pip_server = PipConnectionServer(self, self.config.listen)
		self.pip_server.start()
		self.logger.debug("Initialized")

	def send_chat(self, stream_name, text):
		self.irc_manager.send(stream_name, text)

	def sync_streams(self):
		self.irc_manager.update_connections(
			(
				stream_config.name,
				stream_config.irc_host,
				stream_config.irc_user,
				stream_config.irc_oauth,
				stream_config.irc_channel,
			)
			for stream_config in map(self.get_stream_config, self.ipc_server.streams)
			if stream_config
		)

	def open_stream(self, stream_config, pip_sock):
		self.ipc_server.open_stream(stream_config.name, pip_sock)

	def get_stream_config(self, stream_name):
		# will probably change this later
		return self.streams[stream_name]

	def get_stream_by_pip_key_constant_time(self, pip_key):
		self.logger.debug("Trying to find stream for pip key")
		# will probably change this later
		streams = [
			stream for stream in self.streams.values()
			if constant_time_equal(stream.pip_key, pip_key)
		]
		if not streams:
			self.logger.debug("Key did not match")
			return
		assert len(streams) == 1
		stream, = streams
		self.logger.debug("Key matched stream: {}".format(stream))
		return stream

	def stop(self):
		self.logger.info("Gracefully shutting down")
		# stop accepting new streams
		self.pip_server.stop()
		self.logger.debug("Pip server stopped")
		# close existing streams and stop workers
		self.ipc_server.stop()
		self.logger.debug("IPC stopped")
		# finally, we're done with irc
		self.irc_manager.stop()
		self.logger.debug("IRC stopped")


def main(conf_path, *args):

	logger = logging.getLogger("pipirc")

	config = ServiceConfig(conf_path)
	config.configure_logging()

	logger.info("Starting")

	stop = gevent.event.Event()
	signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())

	main = Main(config, logger=logger)
	logger.info("Started")
	stop.wait()
	main.stop()
	logger.info("Exiting cleanly")
