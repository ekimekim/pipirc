
"""Simple module providing a CLI interface to convert between annotated and true stream config"""

import json
import sys

import argh

from .stream import Stream
from .common import deannotate_config

def main(deannotate=False):
	"""Either annotate or deannotate config given on stdin.
	Give no input to annotate from an empty config."""

	from . import features # load Features

	config = sys.stdin.read()
	if config:
		config = json.loads(config)
	else:
		config = {}

	fn = deannotate_config if deannotate else Stream.get_bare_annotated_config
	config = fn(config)

	print json.dumps(config, indent=4)


if __name__ == '__main__':
	argh.dispatch_command(main)
