
import gpippy
from classtricks import HasLogger


class PippyBot(HasLogger):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		super(PippyBot, self).__init__(logger=logger)
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config
		# TODO on conn close, stop()
		self.pippy = gpippy.Client(sock=pip_sock, on_update=self.on_pip_update)
		self._init_features()
		self.say("Connecting...")

	def _init_features(self):
		pass # TODO iterate through loaded features, if enabled then register callback

	def recv_chat(self, text, sender, sender_rank):
		pass # TODO

	def on_pip_update(self, updates):
		pass #TODO

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)

	def stop(self):
		"""Stop the bot and disconnect from the pip boy"""
		# TODO stop pippy if pippy not stopping
		# TODO for each feature with a stop handler, call it
		# TODO close stream if ipc not stopping
