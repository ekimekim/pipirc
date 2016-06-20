
import gpippy
from classtricks import HasLogger, get_all_subclasses

from .features import Feature


class PippyBot(HasLogger):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		super(PippyBot, self).__init__(logger=logger)
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config
		self.pippy = gpippy.Client(sock=pip_sock, on_update=self.on_pip_update, on_close=lambda ex: self.stop())
		self.debug("Starting...")
		self._init_features()
		self.debug("Started")

	def _init_features(self):
		self.features = []
		for feature in get_all_subclasses(Feature):
			if feature.name not in self.config.features:
				continue
			feature_config = self.config.features[feature.name]
			if not feature_config.get('enabled', False):
				continue
			self.features.append(feature(self, feature_config))

	def recv_chat(self, text, sender, sender_rank):
		for feature in self.features:
			feature.recv_chat(text, sender, sender_rank)

	def on_pip_update(self, updates):
		for feature in self.features:
			feature.on_pip_update(updates)

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)

	def debug(self, text):
		"""Say if debug is True"""
		if self.config.debug:
			self.say(text)

	def stop(self):
		"""Stop the bot and disconnect from the pip boy"""
		if not self.pippy.closing:
			self.pippy.close()
		for feature in self.features:
			feature.stop()
		try:
			self.debug("Disconnected")
		except Exception:
			pass
		self.ipc.close_stream(self.stream_name)
