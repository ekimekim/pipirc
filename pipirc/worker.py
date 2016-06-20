
import gevent.monkey
gevent.monkey.patch_all(subprocess=True)

from uuid import uuid4
import logging
import os
import sys

from .config import ServiceConfig
from .ipc import IPCWorkerConnection


def main(conf_path, sock_path):
	"""Entry point for IPC workers"""

	config = ServiceConfig(conf_path)
	config.configure_logging()

	name = "{}:{}".format(os.getpid(), uuid4())
	logger = logging.getLogger('pipirc.worker').getChild(name)

	logger.info("Starting")
	conn = IPCWorkerConnection(name, sock_path, config, logger=logger)
	conn.start()
	logger.info("Started")

	try:
		conn.wait_for_stop()
	except Exception:
		logger.exception("Fatal error in worker")
	else:
		logger.info("Cleanly stopped")


if __name__ == '__main__':
	main(*sys.argv[1:])