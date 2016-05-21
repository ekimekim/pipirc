
import logging

from gevent.server import StreamServer


def recv_all(sock, length):
	"""recv exactly length bytes from (blocking) sock, unless closed first"""
	buf = ''
	while len(buf) < length:
		part = sock.recv(length - len(buf))
		if not part: # socket was closed
			break
		buf += part
	return buf


class PipConnectionServer(StreamServer):
	"""A socket server that accepts connections from a special client,
	does authentication and hands off the socket to main.
	"""
	# TODO SSL

	TOKEN_LENGTH = 32

	def __init__(self, main, listener, logger=None):
		"""listener can be anything that looks like a listen socket or an address
		parsable by gevent.baseserver.parse_address (eg. (host, port))"""
		self.logger = (logger or logging.getLogger()).getChild(type(self).__name__)
		self.main = main
		super(PipConnectionServer, self).__init__(listener)

	def handle(self, sock, address):
		# The custom protocol here is very simple.
		# The client opens with 32 bytes of token data.
		# Once this is sent, it waits for a response from the server.
		# The response is terminated by a newline and is one of:
		#   "OK": The connection can continue, switch to pip protocol data
		#   otherwise: A human readable error message. The connection will then close.
		try:
			token = recv_all(sock, self.TOKEN_LENGTH)
			# for security, some care must be taken here to be constant-time
			channel = self.main.get_channel_by_token_constant_time(token)
			if not channel:
				sock.sendall("Unknown token.\n")
				return
			sock.sendall("OK\n")
		except Exception:
			self.logger.exception("Error in token handshake from address {}".format(address))
			sock.sendall("Internal server error! We'll get this fixed soon.\n")
			return
		try:
			self.main.open_channel(channel, sock)
		except Exception:
			self.logger.exception("Error in opening channel {} from address {}".format(channel, address))
			# since we've already sent the OK, we can't give an error message
