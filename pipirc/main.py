

class Main(object):
	"""Ties the main parts of the server together"""
	def __init__(self, listen_address):
		self.ipc_server = IPCServer(self)
		self.irc_manager = IRCHostsManager(self._recv_chat)
		self.pip_server = PipConnectionServer(self, listen_address)
		self.pip_server.start()

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
				channel_config.irc_host,
				channel_config.irc_user,
				channel_config.irc_oauth,
				channel_config.irc_channel,
			)
			for channel_config in map(self.get_channel_config, self.ipc_server.channels)
			if channel_config
		)

	def open_channel(self, channel_config, pip_sock):
		self.ipc_server.open_channel(channel_config.name, pip_sock,
			# TODO per-channel options go here (from channel_config)
		)

	def get_channel_config(self, channel_name):
		return None # TODO

	def get_channel_by_token_constant_time(self, token):
		return None # TODO note to be constant time we need a constant string compare and we can't stop after finding the right answer


def main(*args):
	from . import config

	stop = Event()
	signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())

	config.load_all()
	store = Store(...?)
	irc = PipIrc(config, store)
	server = PippyServer(irc)

	stop.wait()
	# TODO stop graceful
