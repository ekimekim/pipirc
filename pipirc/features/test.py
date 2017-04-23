
from ..feature import Feature, on_message


class Test(Feature):
	"""A simple feature to test connectivity. Says hello/goodbye and responds to the word 'pippy'."""

	def init(self):
		self.bot.say("Hello!")

	@on_message
	def echo(self, text, sender, sender_rank):
		if 'pippy' in text:
			self.bot.say("hello {} {}".format(sender_rank, sender))

	def stop(self):
		self.bot.say("Goodbye!")
