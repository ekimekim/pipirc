
import gevent.monkey
gevent.monkey.patch_all(subprocess=True)

import sys

from .main import main

ret = main(*sys.argv[1:])
sys.exit(ret)
