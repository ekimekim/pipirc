
import random

from ..feature import Feature, command


class ListChems(Feature):
	"""Adds chems command to see list of carried chems"""

	CONFIG = {
		'limit': 'Maximium number of chems to display when the command is run. Default is 5.',
	}

	DEFAULTS = {
		'limit': 5,
	}

	@command('chems')
	def chems(self, sender, sender_rank, *args):
		"""See a selection of chems the player is carrying"""
		chems = [item for item in self.bot.inventory.aid if item.name.lower() in item.CHEMS]
		if len(chems) > self.limit:
			chems = random.sample(chems, self.limit)
		for item in sorted(chems, key=lambda item: item.name):
			description = ', '.join(item.effects_text)
			self.bot.say("{item.count}x {item.name} ({description})".format(
				item=item,
				description=description,
			))
