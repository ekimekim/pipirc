
from ..feature import Feature, UserError, command


class UseChem(Feature):
	"""Adds the use_chem command to use a named chem"""

	@command('usechem')
	def use_chem(self, sender, sender_rank, *name):
		"""Use the named chem"""
		name = ' '.join(name)
		if name.lower() not in self.CHEMS:
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
