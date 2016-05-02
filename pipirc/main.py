
from girc import Client


class IrcManager(object):
	def __init__(self, nick, oauth):
		self.nick = nick
		self.oauth = oauth

		self.group = gevent.pool.Group()
		self.clients = {} # {host: client}
		self.backoffs = defaultdict(lambda: Backoff(start=0.1, limit=10, rate=5)) # {host: backoff for host}
		self.desired_channels = {} # {host: set(channels)}

	def client_stopped(self, client, ex):
		host = client.hostname
		if ex is None:
			log.info("Client {!r} quit, not reconnecting".format(host))
			del self.clients[host]
			return
		log.exception("Client {!r} lost connection, waiting {:.2f}s".format(host, self.backoffs[host].peek()))
		time.sleep(self.backoffs[host].get())
		self.start_client(host)

	def start_client(self, host):
		self.clients[host] = PipIrcClient(host, self.nick, password=self.oauth,
		                                  stop_handler=self.client_stopped, twitch=True)
		for channel in self.desired_channels.get(host, []):
			self.clients[host].channel(channel).join()

		@self.group.spawn
		def _start_client():
			self.clients[host].start()
			self.backoffs[host].reset()

	def sync_open_channels(self, desired):
		"""Takes a set of (host, channel) pairs and JOINs/PARTs to match."""
		self.desired_channels = {
			host: set(channel for host, channel in subset)
			for host, subset in itertools.groupby(desired, lambda (host, channel): host)
		}
		for host, channels in self.desired_channels.items():
			if host in self.clients:
				client = self.clients[host]
				current = set(channel.name for channel in client._channels.values() if channel.joined)
				for channel in channels - current:
					client.channel(channel).join()
				for channel in current - channels:
					client.channel(channel).part()
			else:
				# this will automatically join desired_channels
				irc.start_client(host)
		for host in set(self.clients.keys()) - set(self.desired_channels.keys()):
			self.clients[host].quit("No desired channels on this server")

	def send(self, host, channel, msg):
		self.clients[host


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
