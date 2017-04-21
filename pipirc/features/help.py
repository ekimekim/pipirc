
from ..feature import Feature, BoundCommand, command


class Help(Feature):
	"""Adds the help command"""

	# XXX option of what command name somehow?
	@command('piphelp')
	def help(self, sender, sender_rank, *args):
		"""Display a list of commands and what they do"""
		commands = [
			method
			for feature in self.bot.features
			for method in feature._message_callbacks
			if isinstance(method, BoundCommand)
		]

		lines = []
		for command in commands:
			config = command.config

			if config['mod_only']:
				continue # hide mod only

			if command.name == self.help.name:
				continue # don't display the help command itself

			points = config['point_cost']
			if isinstance(points, dict):
				sort_points = min(points.values())
				points = '/'.join(str(v) for k, v in sorted(points.items()))
			else:
				sort_points = points
			points = '({} {}) '.format(points, self.bot.config.currency) if points else ''

			line = '{prefix}{name} {points}- {help}'.format(
				prefix = self.bot.config.command_prefix,
				name = command.name,
				points = points,
				help = config['help'] or 'No help available',
			)
			lines.append((sort_points, line))

		lines.sort() # sorts from free to most expensive, then alphabetically
		for points, line in lines:
			self.bot.say(line)
