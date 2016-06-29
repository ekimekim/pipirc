
import random

from mrpippy.data import Item

from ..feature import Feature, UserError, command


class UseChem(Feature):
	"""Adds the use_chem command to use a named chem"""

	@command('usechem')
	def use_chem(self, sender, sender_rank, *name):
		"""Use the named chem"""
		name = ' '.join(name)
		if name.lower() not in Item.CHEM_NAMES:
			raise UserError("{} is not a chem we can use".format(name))
		with self.bot.use_item_lock:
			matching = [item for item in self.bot.inventory.aid if item.name.lower() == name.lower()]
			if not matching:
				raise UserError("{} is not carrying any {}".format(self.player.name, name))
			if len(matching) > 1:
				self.logger.warning("Carrying multiple copies of chem named {!r}: {}".format(name, matching))
				matching = matching[0]
			item, = matching
			self.bot.use_item(item)
		fmt = random.choice([
			"Mainlined some {item.name}",
			"Huffed some {item.name}",
			"Slammed some {item.name}",
			"{player.name} can quit {item.name} whenever they want.",
			"{item.name} is {player.name}'s only friend.",
			"{player.name} goes on a wicked {item.name} trip",
			"{item.name}! What could go wrong?",
			"{player.name} replaced some of their blood with {item.name}",
			"Maybe they're born with it. Maybe it's {item.name}.",
			"If {item.name} is wrong, {player.name} doesn't want to be right.",
			"{player.name} gets their sweet fix of {item.name}",
		])
		if item.name.lower() == 'jet fuel' and random.random() < 0.25:
			fmt = "{item.name} can't melt {player.name}'s brain!"
		self.bot.say(fmt.format(player=self.bot.player, item=item))
