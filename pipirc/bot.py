

class PippyBot(object):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__).getChild(self.stream_name)
		self.pippy = gpippy.Client(sock=pip_sock, on_update=on_pip_update)
		self._init_features()
		self.say("Connecting...")

	def _init_features(self):
		# TODO iterate through loaded features, if enabled then register callback

	def recv_chat(self, text, sender, sender_rank):
		pass # TODO

	def on_pip_update(self, updates):
		pass #TODO

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)
