from setuptools import setup, find_packages

setup(
	name='pipirc',
	version='0.0.1',
	author='Mike Lang',
	author_email='michael@mixpanel.com',
	description='A twitch irc bot to interact with Fallout 4',
	packages=find_packages(),
	install_requires=[
		'backoff',
		'gclient',
		'gevent',
		'girc',
		'gpippy',
		'gtools',
		'mrpippy',
	],
)
