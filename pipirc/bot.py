
import gevent.event

from classtricks import HasLogger, get_all_subclasses
from mrpippy.data import Inventory, Player
import deepclient
import gpippy

from .feature import Feature, UserError


class PippyBot(HasLogger):
	def __init__(self, ipc, pip_sock, stream_name, stream_config, logger=None):
		super(PippyBot, self).__init__(logger=logger)
		self.ipc = ipc
		self.stream_name = stream_name
		self.config = stream_config

		self._data_ready = gevent.event.Event()
		self.use_item_lock = UseItemLock(self)
		self._pippy = gevent.spawn(
			gpippy.Client, sock=pip_sock, on_update=self.on_pip_update, on_close=lambda ex: self.stop()
		)
		if self.config['deepbot_url']:
			self._deepbot = gevent.spawn(
				deepclient.DeepClient(self.config['deepbot_url'], self.config['deepbot_secret'])
			)
		else:
			self._deepbot = None

		self.debug("Starting...")
		self._init_features()
		self.debug("Started")

	def _init_features(self):
		self.features = []
		for feature in get_all_subclasses(Feature):
			self.logger.debug("Considering feature {}".format(feature.name))
			if feature.name not in self.config.features:
				continue
			feature_config = self.config.features[feature.name]
			self.logger.debug("Config for feature {}: {}".format(feature.name, feature_config))
			if not feature_config.get('enabled', False):
				continue
			self.logger.debug("Registering feature {}".format(feature.name))
			self.features.append(feature(self, feature_config))

	def recv_chat(self, text, sender, sender_rank):
		for feature in self.features:
			feature.recv_chat(text, sender, sender_rank)

	def on_pip_update(self, updates):

		# unblock things waiting for data
		if self.pippy.pipdata.root is not None:
			self._data_ready.set()

		# unblock things waiting for items to be usable
		self.use_item_lock.check()

		# call feature callbacks
		for feature in self.features:
			feature.on_pip_update(updates)

	def say(self, text):
		self.ipc.send_chat(self.stream_name, text)

	def debug(self, text):
		"""Say if debug is True"""
		if self.config.debug:
			self.say(text)

	def stop(self):
		"""Stop the bot and disconnect from the pip boy"""
		if self._pippy.ready() and not self.pippy.closing:
			self.pippy.close()
		else:
			self._pippy.kill(block=False)
		for feature in self.features:
			feature.stop()
		try:
			self.debug("Disconnected")
		except Exception:
			pass
		self.ipc.close_stream(self.stream_name)

	@property
	def deepbot(self):
		if not self._deepbot:
			return
		return self._deepbot.get()

	@property
	def pippy(self):
		try:
			return self._pippy.get()
		except Exception:
			self.stop()
			raise

	@property
	def pipdata(self):
		self._data_ready.wait()
		return self.pippy.pipdata

	@property
	def player(self):
		return Player(self.pipdata)

	@property
	def inventory(self):
		return Inventory(self.pipdata)

	def use_item(self, item):
		"""Attempt to use an item. May fail if the item has disappeared since you acquired your reference to it.
		(you should acquire self.use_item_lock before checking the inventory to minimise that risk)
		May silently fail in general due to unavoidable race conditions and lack of feedback from the server.
		May raise UserError on failure, which will contain an error message suitable for user display."""
		with self.use_item_lock:
			version = self.inventory.version
			self.use_item_lock.set_last_use_version(version)
			# confirm item is still present
			found_items = [i for i in self.inventory.items if i.handle_id == item.handle_id]
			if len(found_items) > 1:
				self.logger.warning("Got duplicate handle id for multiple items: {}".format(found_items))
				found_items = found_items[:1] # take first one
			if not found_items:
				raise UserError("Failed to use {}: item no longer exists".format(item.name))
			self.pippy.use_item(item.handle_id, version, block=False)


class UseItemReset(Exception):
	pass


class UseItemLock(gevent.lock.RLock):
	"""RLock variant which blocks until we're in a state when we can use an item."""
	_use_item_waiter = None
	_last_use_version = None

	def __init__(self, bot):
		self.bot = bot
		super(UseItemLock, self).__init__()

	def acquire(self):
		super(UseItemLock, self).acquire()
		if self._count == 1:
			# on first acquire, block until we can use item
			self._use_item_waiter = gevent.event.AsyncResult()
			self.check()
			self._use_item_waiter.wait()
			if not self._use_item_waiter.successful():
				self.release()
				self._use_item_waiter.get() # raise

	def reset(self):
		if self._use_item_waiter:
			self._use_item_waiter.set_exception(UseItemReset())
		self._last_use_version = None

	def check(self):
		# check if we're currently in a good state to use an item
		# should be called when we start waiting and every update thereafter
		if (
			self._use_item_waiter and not self._use_item_waiter.ready() # if we are waiting
			and self.bot.inventory.version != self._last_use_version # disallow if we just used an item and haven't got a change in response yet
			and not self.bot.player.locked # actual check, are we in a good player state (not paused, in vats, etc)
		):
			self._use_item_waiter.set(None)

	def set_last_use_version(self, version):
		self._last_use_version = version
