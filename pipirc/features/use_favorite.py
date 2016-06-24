
from ..feature import Feature, UserError, command


class UseFavorite(Feature):
	"""Adds the use command to use/equip an item in your favorites"""

	@command('use')
	def use(self, sender, sender_rank, index, *args):
		"""Equip or use the item in the given favorite slot (1 to 12)"""
		try:
			index = int(index) - 1 # user interface is 1-indexed
		except ValueError:
			raise UserError("Favorite slot must be a number, not {!r}".format(index))
		use_favorite_slot(self.bot, index)


def use_favorite_slot(bot, index):
	with bot.use_item_lock:
		items = [item for item in bot.inventory.items if item.favorite_slot == index]
		if not items:
			raise UserError("No item attached to that favorite slot")
		if len(items) > 1:
			first_item = items[0]
			# special case: sometimes we get duplicates with the same name? they're the same item.
			if not all(item.name == first_item.name for item in items[1:]):
				raise UserError("More than one item attached to that favorite slot somehow?")
			items = [first_item]
		item, = items
		if item.equipped:
			raise UserError("Sorry, you can't equip something that's already equipped")
		bot.use_item(item)
