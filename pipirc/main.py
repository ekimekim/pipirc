
from girc import Client


class PipIrc(object):
	def __init__(self, config, store):
		self.config = config
		self.store = store

		self.stop = Event()
		self.clients = {} # {host: client}
		self.ready = defaultdict(Event) # {host: event for when client for host is ready}
		self.backoffs = defaultdict(lambda: Backoff(start=0.1, limit=10, rate=5)) # {host: backoff for host}

		if not self.config.irc_oauth:
			raise ValueError("oauth token is required to connect to irc")

	def client_stopped(self, client, ex):
		host = client.hostname
		del self.ready[host]
		if ex is None:
			log.info("Client {!r} quit, not reconnecting".format(host))
			del self.clients[host]
			self.ready.pop(host).set()
			return
		log.exception("Client {!r} lost connection, waiting {:.2f}s".format(host, self.backoffs[host].peek()))
		time.sleep(self.backoffs[host].get())
		self.start_client(host)

	def start_client(self, host):
		self.clients[host] = PipIrcClient(host, self.config.nick, password=self.config.irc_oauth,
		                            stop_handler=self.client_stopped, twitch=True)
		self.ready[host].set()
		self.clients[host].start()


# in per-connection init:
#	if host not in irc.clients:
#		irc.start_client(host)
#	irc.ready[host].wait()
#	regsiter(irc.clients[host])
#	irc.clients[host].channel(name).join()


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
