
from ..feature import Feature, command


class ListWeapons(Feature):
	"""Adds weapons command to see list of favorited weapons"""

	@command('weapons')
	def weapons(self, sender, sender_rank, *args):
		"""List all favorited weapon slots"""
		favorites = [item for item in self.bot.inventory.weapons if item.favorite]
		favorites = {item.name: item for item in favorites}.values()
		favorites.sort(key=lambda item: item.favorite_slot)
		self.bot.say("Favorited items:")
		for item in favorites:
			slot_name = item.favorite_slot + 1
			ammo = item.ammo
			if ammo is item:
				# grenades, etc
				ammo_str = " ({}x)".format(item.count)
			elif item.ammo_type:
				# firearms - note ammo is None if we have none of it
				count = ammo.count if ammo else 0
				ammo_str = " ({count}x {item.ammo_type})".format(item=item, count=count)
			else:
				# no ammo: melee, etc
				ammo_str = ""
			self.bot.say("{} - {}{}".format(slot_name, item.name, ammo_str))
