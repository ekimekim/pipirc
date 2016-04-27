

class IPCServer(object):
	def __init__(self, main):
		self.sock_path = '/tmp/{}.sock'.format(uuid4())
		self.main = main
		self.group = Group()
		self.listener = socket.socket(AF_UNIX, SOCK_STREAM)
		self.listener.listen(128)
		self.listener.bind(self.sock_path)
		self.group.spawn(self.run)
		self.conns = {}

	def run(self):
		while True:
			sock, addr = self.listener.accept()
			name = uuid4()
			self.conns[name] = IPCMasterConnection(self, name, sock)

	@property
	def channels(self):
		ret = {}
		for conn in self.conns.values():
			for host, channel in conn.channels:
				ret.setdefault(host, set()).add(channel)
		return ret


class IPCConnection(GSocketClient):
	def __init__(self, socket):
		super(SubConnection, self).__init__()
		self._socket = socket

	def send(self, type, block=False, **data):
		"""Send message of given type, with other args.
		Set 'fd' to an integer fd to send that fd over the wire."""
		data['type'] = type
		return super(SubConnection, self).send(data, block=block)

	def _send(self, msg):
		super(SubConnection, self)._send(msg)
		if msg.get('fd') is not None:
			send_fd(self._socket, msg['fd'])

	def _encode(self, msg):
		return json.dumps(msg) + '\n'

	def _handle(self, msg):
		msg = json.loads(msg)
		if 'fd' in msg:
			msg['fd'] = recv_fd(self._socket)
		msg_type = msg.pop('type')
		if msg_type in self._handle_map:
			self._handle_map[msg_type](**msg)


class IPCMasterConnection(IPCConnection):
	def __init__(self, server, name, socket):
		super(IPCMasterConnection, self).__init__(socket)
		self.server = server
		self.name = name
		self.channels = set() # set of (host, channel)
		self.send('init', name=name)
		self._handle_map = {
			'chat message': self._send_chat
			'close channel': self._close_channel,
		}
		self.start()

	def _stop(self):
		super(IPCMasterConnection, self)._stop()
		assert self.server.conns.pop(name) is self
		self.server.main.sync_open_channels()

	def open_channel(self, host, channel, pip_fd, **options):
		"""Send channel info and pip protocol fd for given channel to worker process,
		assigning the channel to this process."""
		self.channels.add((host, channel))
		self.server.main.sync_open_channels()
		self.send('open channel', host=host, channel=channel, fd=pip_fd, **options)

	def _close_channel(self, host, channel):
		self.channels.remove((host, channel))
		self.server.main.sync_open_channels()

	def _send_chat(self, host, channel, text):
		self.server.main.send_chat(host, channel, text)

	def recv_chat(self, host, channel, text, sender, sender_rank)
		self.send('chat message', host=host, channel=channel, text=text, sender=sender, sender_rank=sender_rank)


class IPCWorkerConnection(IPCConnection):
	def __init__(self, sock_path):
		sock = socket.socket(AF_UNIX, SOCK_STREAM)
		sock.connect(sock_path)
		super(IPCWorkerConnection, self).__init__(sock)
		self.channels = {} # {(host, channel): PippyBot}
		self._handle_map = {
			'init': self._init,
			'open channel': self._open_channel,
			'chat message': self._recv_chat,
		}
		self.start()

	def _init(self, name):
		self.name = name

	def _open_channel(self, host, channel, fd, **options):
		pip_sock = socket.fromfd(fd, AF_INET, SOCK_STREAM)
		self.channels[host, channel] = PippyBot(self, pip_sock, host, channel, options)

	def close_channel(self, host, channel):
		del self.channels[host, channel]
		self.send('close channel', host=host, channel=channel)

	def send_chat(self, host, channel, text):
		self.send('chat message', host=host, channel=channel, text=text)

	def _recv_chat(self, host, channel, text, sender, sender_rank):
		if (host, channel) in self.channels:
			self.channels[host, channel].recv_chat(text, sender, sender_rank)
