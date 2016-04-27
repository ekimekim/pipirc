
from pyconfig import Config

config = Config()

config.register('irc_host', default='irc.twitch.tv')
config.register('nick', default='mister_pippy')
config.register('irc_oauth') # required
