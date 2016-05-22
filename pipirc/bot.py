

class PippyBot(object):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__).getChild(self.stream_name)
		self.pippy = ClientConnectionFromSocket(pip_sock)
		self.say("Connecting...")

	def recv_chat(self, text, sender, sender_rank):
		pass # TODO

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)
