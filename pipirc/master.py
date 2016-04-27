

class MasterServer(object):
	def __init__(self):
		self.sock_path = '/tmp/{}.sock'.format(uuid4())
		self.group = Group()
		self.listener = socket.socket(AF_UNIX, SOCK_DGRAM)
		self.listener.listen(128)
		self.listener.bind(self.sock_path)
		self.group.spawn(self.run)
		self.conns = {}

	def run(self):
		while True:
			sock, addr = self.listener.accept()
			name = uuid4()
			self.conns[name] = SubConnection(name, sock)
			self.group.spawn(self.conns[name].run)


class SubConnection(object):
	def __init__(self, name, sock):
		self.name = name
		self.socket = sock
		self.group = Group()
		self.queue = Queue()
		self.send(name, {'type': 'init', 'name': name})

	def run(self):
		# TODO spawn both and wait on either to error or exit, error handlng etc

		# TODO braindump
		# each conn has associated (host:channel)s
		# we keep track of channel set based on read commands
		# we send and recv messages for channel
		# on sock close, remove all channels for conn
		# also be able to send fd

	def send(self, msg, fd=None):
		self.queue.append(msg, fd)

	def send_loop(self):
		for msg, fd in self.queue:
			if fd is not None:
				# TODO
			else:
				content = json.dumps(msg)
				self.sendall(content)

	def recv_loop(self):
		while True:
			msg = self.socket.recv(4096)
			msg = json.loads(msg)
