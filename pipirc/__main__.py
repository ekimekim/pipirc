
import gevent.monkey
gevent.monkey.patch_all(subprocess=True)

import logging
import sys

from .main import main

logging.basicConfig(level=logging.DEBUG)
ret = main(*sys.argv[1:])
sys.exit(ret)
