
import gevent.monkey
gevent.monkey.patch_all(subprocess=True)

from gtools import backdoor
backdoor(2201)

import sys

from .main import main

ret = main(*sys.argv[1:])
sys.exit(ret)
