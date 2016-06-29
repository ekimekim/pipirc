
import re

from ..feature import Feature, UserError, on_message

from .use_favorite import use_favorite_slot


class DeepbotPollResponse(Feature):
	"""Specialized feature that response to messages like:
		'Poll for <poll> has been closed. Winning option was Slot N'
	by equipping the item in favorite slot N
	"""

	CONFIG = {
		'pattern': '(advanced) Regex to match on. Uses python-flavored regex. Must match exactly one group.',
	}

	DEFAULTS = {
		'pattern': r'^Poll for .* has been closed. Winning option was Slot (\d+)$',
	}

	@on_message
	def respond_to_poll(self, text, sender, sender_rank):
		if sender_rank not in ('mod', 'broadcaster'):
			return
		match = re.match(self.pattern, text)
		if not match:
			return
		slot, = match.groups()
		slot = int(slot)

		try:
			use_favorite_slot(self.bot, slot - 1)
		except UserError as ex:
			self.bot.say("Failed to apply poll result: {}".format(ex))
