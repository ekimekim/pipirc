
import signal

import gevent.event

from .ipc import IPCServer
from .irc import IRCHostsManager
from .pipserver import PipConnectionServer


def constant_time_equal(a, b):
	"""Compare two strings in constant time (if they're the same length)"""
	return len(a) == len(b) and sum(ord(c1) ^ ord(c2) for c1, c2 in zip(a, b)) == 0


class Main(object):
	"""Ties the main parts of the server together"""
	def __init__(self, listen_address, channels):
		self.ipc_server = IPCServer(self)
		self.irc_manager = IRCHostsManager(self._recv_chat)
		self.pip_server = PipConnectionServer(self, listen_address)
		self.pip_server.start()
		# probably going to change this later
		self.channels = channels

	def send_chat(self, channel_name, text):
		channel_config = self.get_channel_config(channel_name)
		if not channel_config:
			return
		self.irc_manager.send(
			channel_config.irc_host,
			channel_config.irc_user,
			channel_config.irc_oauth,
			channel_config.irc_channel,
			text,
		)

	def _recv_chat(self, channel_name, text, sender, sender_rank):
		self.ipc_server.recv_chat(channel_name, text, sender, sender_rank)

	def sync_channels(self):
		self.irc_manager.update_connections(
			(
				channel_config['irc_host'],
				channel_config['irc_user'],
				channel_config['irc_oauth'],
				channel_config['irc_channel'],
			)
			for channel_config in map(self.get_channel_config, self.ipc_server.channels)
			if channel_config
		)

	def open_channel(self, channel_config, pip_sock):
		self.ipc_server.open_channel(channel_config.name, pip_sock,
			# TODO per-channel options go here (from channel_config)
		)

	def get_channel_config(self, channel_name):
		# will probably change this later
		return self.channels.get(channel_name)

	def get_channel_by_token_constant_time(self, token):
		# will probably change this later
		channels = [
			channel for channel in self.channels
			if constant_time_equal(channel['token'], token)
		]
		if not channels:
			return
		assert len(channels) == 1
		channel, = channels
		return channel

	def stop(self):
		return # TODO graceful shutdown


def main(config_file, *args):
	import json

	# hard-coded for now, will replace later
	config = {
		'listen': ('127.0.0.1', 6066),
		'channels': json.loads(open(config_file).read()),
	}

	stop = gevent.event.Event()
	signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())

	main = Main(config['listen'], config['channels'])
	stop.wait()
	main.stop()
