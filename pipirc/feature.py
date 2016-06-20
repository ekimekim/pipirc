
import gevent.pool

from classtricks import HasLogger, classproperty


def on_message(fn):
	"""Decorate class methods with this to have them called upon any chat message being recieved.
	Wrapped functions should take args (text, sender, sender_rank)"""
	fn._on_message = True
	return fn


def on_update(fn):
	"""Decorate class methods with this to have them called upon any pip data update.
	Wrapped functions should take a list of updated values, though in most cases it's probably better
	to ignore them and just consult pippy directly."""
	fn._on_update = True
	return fn


class UserError(Exception):
	"""Raise UserError(message) inside a command to display an error message to the user.
	This is not considered an error in the bot, and should be used for user input errors, etc.
	"""


class Feature(HasLogger):

	CONFIG = {}
	DEFAULTS = {}

	@classproperty
	def name(cls):
		return cls.__name__

	@classmethod
	def check_config(cls, config):
		return (set(cls.CONFIG.keys()) - set(cls.DEFAULTS.keys())).issubset(set(config.keys()))

	def __init__(self, bot, config):
		self.bot = bot
		self.group = gevent.pool.Group()
		self._message_callbacks = []
		self._update_callbacks = []

		config = config.copy()
		for key in self.CONFIG:
			value = config.pop(key, self.DEFAULTS[key]) if key in self.DEFAULTS else config.pop(key)
			setattr(self, key, value)
		self.config = config # any unknown options

		for attr in dir(self):
			method = getattr(self, attr)
			if not callable(method):
				continue
			if getattr(method, '_on_message', False):
				self._message_callbacks.append(method)
			if getattr(method, '_on_update', False):
				self._update_callbacks.append(method)

		self.init()

	def recv_chat(self, text, sender, sender_rank):
		for callback in self._message_callbacks:
			self.group.spawn(self._log_errors, callback, text, sender, sender_rank)

	def on_pip_update(self, updates):
		for callback in self._update_callbacks:
			self.group.spawn(self._log_errors, callback, updates)

	def _log_errors(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except Exception:
			self.logger.exception("Error calling {} with args {}, {}".format(fn, args, kwargs))

	def stop(self):
		self._stop()
		self.group.kill(block=True)

	def init(self):
		"""Optional feature init hook"""

	def _stop(self):
		"""Optional feature shutdown hook"""


def command(name, **config):
	"""Decorate a method of a Feature to call upon a user running a command.
	A command consists of the configured command char, a command name, and optionally some args.
	Example:
		@command('foo', mod_only=True)
		def foo(self, sender, sender_rank, *args):
			...
	would be triggered by "!foo", but only if the triggerer was a mod.
	The passed *args are the remaining message text split by spaces, and any TypeErrors are assumed to be
	caused by a number of args mismatch and will report an error.
	"""
	def _command(fn):
		return Command(fn, name, **config)
	return _command


class Command(object):
	"""The type that @command returns."""
	_on_message = True

	CONFIG = {
		'mod_only': 'When true, only mods can run the command. Default false.',
		'sub_only': 'When true, only mods or subs can run the command. Default false.',
		'cooldown': 'How long after the command is used before it can be used again. Mods ignore cooldowns. '
		            'Should be a number of seconds.', # TODO
		'point_cost': 'If Deepbot integration is configured, setting this value to a number causes the '
		              'command to cost that much. You may also set this to a map from deepbot user rank numbers '
		              'to a cost for each rank, or omit a rank to disallow that rank from using the command. '
		              'For example, {"2": 10, "3": 0} would indicate that rank 1 users can\'t use the command, '
		              'rank 2 users can use it at a 10 point cost, and rank 3 can use it for free. Mods can '
		              'always use a command, and default to free if omitted.', # TODO
		'help': 'Help text to display to users for the command. You should generally not need to touch this.',
		'fail_message': 'Governs how often to post a failure message, eg. "This command is mod-only.". '
		                'Set to False to never display, True to always display, or a number to display with '
		                'that many seconds of cooldown. Defaults to True.', # TODO
	}

	DEFAULTS = {
		'mod_only': False,
		'sub_only': False,
		'cooldown': 0,
		'point_cost': 0,
		'help': None,
		'fail_message': True,
	}

	def __init__(self, fn, name, **config):
		"""name is the string that triggers this command. All other args are defaults and can be overridden
		by feature config under the name key.
		For example, if you created a command like:
			Command('foo', mod_only=True)
		but the feature has config:
			{"foo": {"mod_only": False}}
		then non-mods could call !foo.
		See CONFIG for docs on options.
		Note as a special case, help defaults to the first line of the wrapped function's docstring.
		Pass help='' to disable this.
		"""
		self.fn = fn
		self.name = name

		if 'help' not in config and self.fn.__doc__:
			config['help'] = self.fn.__doc__.split('\n')[0].strip()

		self.config = self.DEFAULTS.copy()
		self.config.update(config)

	def __get__(self, instance, cls):
		if instance:
			# bind to feature instance
			return BoundCommand(self, instance)
		return self

	def get_config(self, feature):
		config = self.config.copy()
		config.update(feature.config.get(self.name, {}))
		return config

	def full_prefix(self, feature):
		return '{}{}'.format(feature.bot.config.command_prefix, self.name)

	def __call__(self, feature, text, sender, sender_rank):
		prefix = self.full_prefix()
		args = text.strip().split()
		if args[0] != prefix:
			continue
		args = args[1:]

		config = self.get_config(feature)
		is_mod = sender_rank in ('broadcaster', 'mod')

		try:
			if config['mod_only'] and not is_mod:
				raise UserError("This command is mod only.")
			if config['sub_only'] and not (is_mod or sender_rank == 'subscriber'):
				raise UserError("This command is sub only.")

			try:
				self.fn(feature, sender, sender_rank, *args)
			except TypeError:
				raise UserError("Wrong number of args for command.")
			except Exception:
				feature.logger.exception("Error while handling command {} from {}({}): {!r}".format(self.name, sender, sender_rank, text))
				raise UserError("Something went wrong. Try again?")
		except UserError as ex:
			# TODO fail cooldown
			feature.bot.say(str(ex))


class BoundCommand(object):
	"""Wrapper around Command once it has been bound to a parent Feature.
	For convenience, exports fully resolved config as 'config' attr.
	"""
	def __init__(self, command, feature):
		self._command = command
		self._feature = feature

	def __getattr__(self, attr):
		return getattr(self._command, attr)

	def __call__(self, *args, **kwargs):
		return self._command(self._feature, *args, **kwargs)

	@property
	def config(self):
		return self._command.get_config(self._feature)
