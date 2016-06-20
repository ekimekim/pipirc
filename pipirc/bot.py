
import gpippy
from classtricks import HasLogger


class PippyBot(HasLogger):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		super(PippyBot, self).__init__(logger=logger)
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config
		self.pippy = gpippy.Client(sock=pip_sock, on_update=self.on_pip_update, on_close=lambda ex: self.stop())
		self._init_features()
		self.say("Connecting...")

	def _init_features(self):
		self.features = []
		pass # TODO iterate through loaded features, if enabled then register callback

	def recv_chat(self, text, sender, sender_rank):
		for feature in self.features:
			feature.recv_chat(text, sender, sender_rank)

	def on_pip_update(self, updates):
		for feature in self.features:
			feature.on_pip_update(updates)

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)

	def stop(self):
		"""Stop the bot and disconnect from the pip boy"""
		if not self.pippy.closing:
			self.pippy.close()
		for feature in self.features:
			feature.stop()
		self.ipc.close_stream(self.stream_name)
