

class IrcManager(object):
	def __init__(self, nick, oauth):
		self.nick = nick
		self.oauth = oauth
		self.clients = {} # {host: client}

	def send(self, host, channel, msg):
		self.clients[host].send(channel, msg)


def main(*args):
	from . import config

	stop = Event()
	signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())

	config.load_all()
	store = Store(...?)
	irc = PipIrc(config, store)
	server = PippyServer(irc)

	stop.wait()
	# TODO stop graceful
