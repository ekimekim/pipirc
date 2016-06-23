
from contextlib import closing
from select import select
import socket
import json
import time


def patrick(s1, s2):

	buf_1_to_2 = ''
	buf_2_to_1 = ''

	while True:
		to_write = []
		if buf_1_to_2:
			to_write.append(s2)
		if buf_2_to_1:
			to_write.append(s1)
		r, w, x = select([s1, s2], to_write, [])
		if s1 in r:
			c = s1.recv(4096)
			if not c:
				return
			buf_1_to_2 += c
		if s2 in r:
			c = s2.recv(4096)
			if not c:
				return
			buf_2_to_1 += c
		if s1 in w:
			n = s1.send(buf_2_to_1[:4096])
			buf_2_to_1 = buf_2_to_1[n:]
		if s2 in w:
			n = s2.send(buf_1_to_2[:4096])
			buf_1_to_2 = buf_1_to_2[n:]


def do_connection(pip_key, game_host):
	pip_host = 'misterpippy.xyz'
	pip_port = 27000
	game_port = 27000

	pip_sock = None
	game_sock = None

	try:
		print "Connecting to Mister Pippy at {}:{}".format(pip_host, pip_port)
		pip_sock = socket.socket()

		try:
			pip_sock.connect((pip_host, pip_port))
		except (socket.error, OSError):
			print "Failed to connect to Mister Pippy"
			return

		try:
			pip_sock.sendall(pip_key)
			response = ''
			while True:
				part = pip_sock.recv(1)
				if not part:
					raise EOFError
				if part == '\n':
					break
				response += part
		except (socket.error, OSError, EOFError):
			print "Failed to handshake with Mister Pippy"
			return

		if response != 'OK':
			print "Server responded: {}".format(response)
			return

		print "Connecting to game at {}:{}".format(game_host, game_port)
		game_sock = socket.socket()

		try:
			game_sock.connect((game_host, game_port))
		except (socket.error, OSError):
			print "Failed to connect to game"
			return

		patrick(pip_sock, game_sock)

	finally:
		if pip_sock:
			pip_sock.close()
		if game_sock:
			game_sock.close()


def discover(timeout=1, repeats=5, port=28000):
	"""Uses UDP broadcast to find pip boy app hosts on the local network.
	Returns a set of (ip, machine_type, busy).
	if allow_busy=True, also include replies that indicated server was present but busy.
	timeout is how long to wait for responses.
	repeats is how many broadcast packets to send. This makes the message (and replies) more likely
	to make it through despite packet loss."""
	with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)) as sock:
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
		for x in range(repeats):
			sock.sendto(json.dumps({'cmd': 'autodiscover'}), ('255.255.255.255', 28000))
		results = {}
		start = time.time()
		while True:
			time_left = start + timeout - time.time()
			if time_left <= 0:
				break
			r, w, x = select([sock], [], [], time_left)
			if r:
				assert r == [sock]
				message, addr = sock.recvfrom(1024)
				try:
					message = json.loads(message)
				except (ValueError, UnicodeDecodeError):
					continue # malformed message, ignore it
				if not isinstance(message, dict):
					continue # not a json object, ignore it
				if any(key not in message for key in ['MachineType', 'addr', 'IsBusy']):
					continue # missing required keys, ignore it
				if message['IsBusy'] and not allow_busy:
					continue # server is busy, ignore it
				results[message['addr'], message['MachineType']] = message['IsBusy']
	return set((a, t, b) for (a, t), b in results.items())


def pick_game():
	games = discover()
	if not games:
		print "No games found. Check the game is running and the pip boy app is enabled in settings."
		return
	print "Found running game(s):"
	for i, (ip, machine_type, busy) in enumerate(games):
		print "{}. {} game at {}{}".format(i+1, machine_type, ip, ' (currently busy)' if busy else '')
	if len(games) == 1:
		(ip, machine_type, busy), = games
		return ip
	while True:
		selection_str = raw_input("Please choose which number to connect to")
		try:
			selection = int(selection_str)
		except ValueError:
			selection = 0
		if 0 < selection <= len(games):
			ip, machine_type, busy = games[selection - 1]
			return ip
		print "{!r} is not an option. Please enter a number between 1 and {}.".format(selection_str, len(games))


def load_config():
	CONF_FILE = 'pip_key.txt'
	try:
		with open(CONF_FILE) as f:
			return f.read().strip()
	except (IOError, OSError):
		pass
	while True:
		pip_key = raw_input("Please enter your pip key (don't show this window on stream): ").strip()
		if len(pip_key) == 32:
			break
		print "That doesn't look right. A pip key should be exactly 32 characters."
	if raw_input("Should I save this for next time? (y/N) > ").lower().startwith('y'):
		try:
			with open(CONF_FILE, 'w') as f:
				f.write(pip_key + '\n')
		except (IOError, OSError):
			print "Oops, I couldn't save for some reason. Ignoring."

def main():
	RETRY_INTERVAL = 10

	pip_key = load_config()
	ip = pick_game()
	if not ip:
		return 1

	while True:
		do_connection(pip_key, ip)
		print "Connection failed. Trying again in {} seconds.".format(RETRY_INTERVAL)
		time.sleep(RETRY_INTERVAL)


if __name__ == '__main__':
	import sys
	import traceback

	try:
		exit_code = main(*sys.argv[1:])
	except Exception:
		print "Something went wrong. Copy-paste the following and tell the developer:"
		traceback.print_exc()
		exit_code = 1

	raw_input("Press enter to finish.")
	sys.exit(exit_code)
