import logging
import sys
from pipirc.main import main

logging.basicConfig(level=logging.DEBUG)
ret = main(*sys.argv[1:])
sys.exit(ret)
