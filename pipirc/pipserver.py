
from gevent.server import StreamServer

from classtricks import HasLogger


def recv_all(sock, length):
	"""recv exactly length bytes from (blocking) sock, unless closed first"""
	buf = ''
	while len(buf) < length:
		part = sock.recv(length - len(buf))
		if not part: # socket was closed
			break
		buf += part
	return buf


class PipConnectionServer(HasLogger, StreamServer):
	"""A socket server that accepts connections from a special client,
	does authentication and hands off the socket to main.
	"""
	# TODO SSL

	TOKEN_LENGTH = 32

	def __init__(self, main, listener, logger=None):
		"""listener can be anything that looks like a listen socket or an address
		parsable by gevent.baseserver.parse_address (eg. (host, port))"""
		self.main = main
		super(PipConnectionServer, self).__init__(listener, logger=logger)

	def do_close(self, *args):
		# We don't want to close the connection after handle returns, we want to wait until all references are gone
		pass

	def handle(self, sock, address):
		# The custom protocol here is very simple.
		# The client opens with 32 bytes of pip_key data.
		# Once this is sent, it waits for a response from the server.
		# The response is terminated by a newline and is one of:
		#   "OK": The connection can continue, switch to pip protocol data
		#   otherwise: A human readable error message. The connection will then close.
		self.logger.debug("Accepting new connection fd {} from address {}".format(sock.fileno(), address))
		try:
			pip_key = recv_all(sock, self.TOKEN_LENGTH)
			# for security, some care must be taken here to be constant-time
			stream = self.main.get_stream_by_pip_key_constant_time(pip_key)
			if not stream:
				sock.sendall("Unknown pip key.\n")
				return
			if self.main.is_stream_open(stream):
				sock.sendall(
					"You appear to already be connected.\n"
					"It's possible this is a zombie connection and will disappear soon.\n"
					"Close any other copies of this program, or just try again in a few seconds.\n"
				)
				return
			sock.sendall("OK\n")
		except Exception:
			self.logger.exception("Error in pip_key handshake from address {}".format(address))
			sock.sendall("Internal server error! We'll get this fixed soon.\n")
			return
		try:
			self.main.open_stream(stream, sock)
		except Exception:
			self.logger.exception("Error in opening stream {} from address {}".format(stream, address))
			# since we've already sent the OK, we can't give an error message
		self.logger.debug("Successfully opened stream from address {}".format(address))
