
import random

from ..feature import Feature, UserError, command


class UseBooze(Feature):
	"""Adds the booze command to drink a random alcoholic drink"""

	@command('booze')
	def booze(self, sender, sender_rank, *args):
		"""Use a random booze item"""
		with self.bot.use_item_lock:
			booze = [item for item in self.bot.inventory.aid if item.name.lower() in item.ALCOHOL_NAMES]
			if not booze:
				raise UserError("Sorry, {} is trying to cut back (Not carrying any booze)".format(self.bot.player.name))
			item = random.choice(booze)
			self.bot.use_item(item)
		verb = random.choice([
			"Chugged", "Shotgunned", "Slammed", "Skulled", "Downed", "Quaffed",
			"Guzzled", "Swigged", "Scarfed, glass and all,", "Inhaled", "Crushed", "Daintily sipped",
		])
		text = "{} a bottle of {}".format(verb, item.name)
		if random.random() < 0.05:
			text = "{} like it's 2069!".format(text)
		if 'ice cold' in item.name.lower() and random.random() < 0.5:
			text = '{}. Gah, too cold, ice-cream headache!'.format(text)
		if item.name.lower() == 'dirty wastelander' and random.random() < 0.25:
			text = '{player.name} tastes a {item.name} ;)'.format(player=self.bot.player, item=item)
		self.bot.say(text)
