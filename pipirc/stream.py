
from random import SystemRandom
import logging
import string


class Stream(object):
	# {key: help text}
	ITEMS = {
		'irc_host':
			'Can be a specific chat server, but there should be no reason to use anything but the default.',
		'irc_user':
			'You may specify a custom twitch user for the bot to log in as. Note that if you do so you must '
			'also give a valid IRC OAuth token for irc_oauth. Defaults to "Mister_Pippy".',
		'irc_oauth':
			'If you are specifying a custom twitch user for the bot to speak as in irc_user, you '
			'must provide an oauth token here to allow it to log in and chat. If not, you should '
			'leave this blank.',
		'pip_key':
			'This 32-character string must be entered into the pip-connector client to '
			'authenticate the connection.',
		'command_prefix':
			'The character or phrase that must preceed commands. Default is "!", ie. the "foo" command would be "!foo".',
		'debug':
			'Set True for extra status messages to be sent to IRC.',
	}

	DEFAULTS = {
		'irc_host': 'irc.chat.twitch.tv',
		'irc_user': None,
		'irc_oauth': None,
		'command_prefix': '!',
		'debug': False,
	}

	def __init__(self, name, data, global_config, logger=None):
		self.config = global_config
		self.name = name
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__)

		data = data.copy()
		for key in self.ITEMS:
			value = data.pop(key, self.DEFAULTS[key]) if key in self.DEFAULTS else data.pop(key)
			setattr(self, key, value)
		self.features = data

		# special case defaults
		if not self.irc_user:
			self.irc_user = self.config.default_irc_user
		if not self.irc_oauth:
			self.irc_oauth = self.config.default_irc_oauth

	def __repr__(self):
		return "<{cls.__name__} {self.name}>".format(self=self, cls=type(self))
	__str__ = __repr__

	@property
	def irc_channel(self):
		return '#{}'.format(self.name)

	@classmethod
	def gen_pip_key(cls):
		corpus = string.letters + string.digits
		random = SystemRandom() # use os.urandom as a CPRNG
		return ''.join(random.choice(corpus) for i in range(32))
