
import time

import requests

from ..feature import Feature, on_update


class WebPippyUpload(Feature):
	"""Integrate with the WebPippy service by periodically uploading a json dump"""
	last_upload = None

	CONFIG = {
		"interval": "How often to upload data. Default 15s.",
	}

	DEFAULTS = {
		"interval": 15,
	}

	@on_update
	def upload(self, updates):
		now = time.time()
		if self.last_upload is None or now - self.last_upload > self.interval:
			self.last_upload = now
			try:
				resp = requests.patch(
					'https://webpippy.firebaseio.com/{}.json'.format(self.bot.stream_name.lower()),
					data=self.bot.pipdata.root.value,
				)
				resp.raise_for_status()
			except Exception:
				self.logger.warning("Failed to upload data", exc_info=True)
			else:
				self.logger.info("Uploaded data")
