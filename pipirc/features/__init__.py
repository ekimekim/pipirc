
# we automatically import all modules in our directory so they're loaded

import importlib
import os

for filename in os.listdir(os.path.dirname(__file__)):
	name, ext = os.path.splitext(filename)
	if ext == '.py' and name != '__init__':
		print 'import', name
		print importlib.import_module('.{}'.format(name), __name__)
