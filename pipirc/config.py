
import json
import logging

from .stream import Stream


class ServiceConfig(object):
	# {key: help text}
	ITEMS = {
		'listen':
			'The socket address to bind to for accepting incoming Pip Boy connections.\n'
			'Should be a string of form "{ipv4}:{port}", "[{ipv6}:{port}]" or integer port '
			'as a shortcut for "0.0.0.0:{port}".',
		'logging':
			'Options for configuring logging. Should be an object with keys and values as per '
			'logging.basicConfig(), eg. {"level": "INFO", "filename": "foo.log"}',
		'streams':
			'Temporary option, hard-codes channel data. Map from names to objects with keys '
			'as per pipirc.stream:Stream',
		'default_irc_user':
			'Main twitch user to use when not using a custom one.',
		'default_irc_oauth':
			'OAuth token to authenticate as default_irc_user for twitch IRC.',
	}

	def __init__(self, filepath):
		self.filepath = filepath
		with open(self.filepath) as f:
			data = json.loads(f.read())

		for key in self.ITEMS:
			setattr(self, key, data.pop(key))

		self.streams = {name: Stream(name, stream, self) for name, stream in self.streams.items()}

		if data:
			raise ValueError("Config has unknown keys: {}".format(data.keys()))

	def configure_logging(self):
		logging.basicConfig(**self.logging)
