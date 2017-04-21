
from .common import annotate_config

import time
from collections import OrderedDict

import gevent.pool

from classtricks import HasLogger, NoOpContext, classproperty, get_all_subclasses
import deepclient


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
		super(Feature, self).__init__()

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

	@classmethod
	def get_annotated_config(cls, values={}):
		# hack to avoid needing to merge subclass CONFIGs with Feature.CONFIG
		CONFIG = dict(enabled='Whether to enable this feature', **cls.CONFIG)
		DEFAULTS = dict(enabled=False, **cls.DEFAULTS)
		config = annotate_config(CONFIG, DEFAULTS, values)
		for attr in sorted(dir(cls)):
			command = getattr(cls, attr)
			if not isinstance(command, Command):
				continue
			config[attr] = {'subconfig': command.get_annotated_config(values.get(attr, {}))}
		return config

	@classmethod
	def get_all_features_annotated_config(cls, values={}):
		result = {
			feature.name: OrderedDict([
				('help', feature.__doc__.strip().split('\n', 1)[0] if isinstance(feature.__doc__, basestring) else 'No help available'),
				('subconfig', feature.get_annotated_config(values.get(feature.name, {}))),
			]) for feature in get_all_subclasses(Feature)
		}
		return OrderedDict(sorted(result.items()))

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
		            'Should be a number of seconds.',
		'point_cost': 'If Deepbot integration is configured, setting this value to a number causes the '
		              'command to cost that much.',
		'help': 'Help text to display to users for the command. You should generally not need to touch this.',
		'fail_message': 'Governs how often to post a failure message, eg. "This command is mod-only.". '
		                'Set to False to never display, True to always display, or a number to display with '
		                'that many seconds of cooldown. Defaults to True.',
	}

	DEFAULTS = {
		'mod_only': False,
		'sub_only': False,
		'cooldown': 0,
		'point_cost': 0,
		'help': None,
		'fail_message': True,
	}

	last_used = None
	last_failed = None

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

	def get_config(self, feature_config):
		config = self.config.copy()
		config.update(feature_config.get(self.name, {}))
		return config

	def get_annotated_config(self, values={}):
		return annotate_config(self.CONFIG, self.config, values)

	def full_prefix(self, feature):
		return '{}{}'.format(feature.bot.config.command_prefix, self.name)

	def __call__(self, feature, text, sender, sender_rank):
		prefix = self.full_prefix(feature)
		args = text.strip().split()
		feature.logger.debug("Considering message {} for command {}".format(args, self))
		if args[0] != prefix:
			return
		args = args[1:]

		config = self.get_config(feature.config)
		is_mod = sender_rank in ('broadcaster', 'mod')
		now = time.time()

		try:
			if config['mod_only'] and not is_mod:
				raise UserError("This command is mod only.")
			if config['sub_only'] and not (is_mod or sender_rank == 'subscriber'):
				raise UserError("This command is sub only.")

			if config['cooldown'] and not is_mod and self.last_used is not None and now - self.last_used < config['cooldown']:
				raise UserError("This command is on cooldown for the next {} seconds".format(int(config['cooldown'] - (now - self.last_used))))

			if config['point_cost'] and feature.bot.deepbot:
				cost_wrapper = feature.bot.deepbot.escrow(sender, config['point_cost'])
			else: # any further bot integrations should go here
				cost_wrapper = NoOpContext()

			try:
				with cost_wrapper:
					self.fn(feature, sender, sender_rank, *args)
			except UserError:
				raise # pass upwards
			except (deepclient.UserNotFound, deepclient.NotEnoughPoints):
				raise UserError("Not enough points for that command (need {})".format(config['point_cost']))
			except TypeError:
				raise UserError("Wrong number of args for command.")
			except Exception:
				feature.logger.exception("Error while handling command {} from {}({}): {!r}".format(self.name, sender, sender_rank, text))
				raise UserError("Something went wrong. Try again?")
			else:
				self.last_used = now
		except UserError as ex:
			fail = config['fail_message']
			if fail is True or self.last_failed is None or now - self.last_failed >= fail or is_mod:
				feature.bot.say(str(ex))
			self.last_failed = now


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
