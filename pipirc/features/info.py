
import time

from ..feature import Feature, command


class Info(Feature):
	"""Adds the health, info and special commands for general info about the character"""

	@command('health')
	def health(self, sender, sender_rank, *args):
		"""See player's health, level and limb conditions"""
		player = self.bot.player
		limbs = {name: condition * 100 for name, condition in player.limbs.items() if condition < 1}
		limbs_str = ", ".join("{} {:.0f}%".format(name, condition) for name, condition in limbs.items())
		if not limbs_str:
			limbs_str = 'all limbs healthy'

		self.bot.say(
			(
				"{player.name} L{level} ({level_percent}% to next), "
				"{player.hp:.0f}/{player.maxhp:.0f}hp ({hp_percent}%), {limbs}"
			).format(
				player = player,
				level = int(player.level),
				level_percent = int(100 * player.level) % 100,
				hp_percent = int(100 * player.hp / player.maxhp),
				limbs = limbs_str,
			)
		)

	@command('info')
	def info(self, sender, sender_rank, *args):
		"""See player's weight, location and other info"""
		player = self.bot.player

	   	weight = int(player.weight)
		maxweight = int(player.maxweight)
		self.bot.say(
			(
				"{player.name} carrying {weight}/{maxweight}lb "
				"in {player.location} at {time}"
			).format(
				player = player,
				time = time.strftime("%H:%M", time.gmtime(player.time)),
				weight = weight,
				maxweight = maxweight,
			)
		)

	@command('special')
	def special(self, sender, sender_rank, *args):
		"""See player's SPECIAL stats and any modifiers"""
		player = self.bot.player
		names = "STR", "PER", "END", "CHA", "INT", "AGL", "LCK"
		display = []
		for name, value, base in zip(names, player.special, player.base_special):
			diff = value - base
			suffix = '({:+d})'.format(diff) if diff else ''
			display.append("{} {}{}".format(name, value, suffix))
		self.bot.say("{}: {}".format(
			player.name,
			", ".join(display),
		))
