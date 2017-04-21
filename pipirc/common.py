
from collections import OrderedDict

def annotate_config(helps, defaults, values):
	"""Produce an 'annotated' config which has the following form:
		Every key describes a config key that can be set. It may contain any of:
			help: Help text
			default: The default value
			value: The current value set by the stream config
		or it may contain exactly one key, 'subconfig', which maps to another annotated config dict
		which describes config keys that would be nested under that name.
	"""
	result = OrderedDict()
	for key in sorted(helps):
		item = OrderedDict({'help': helps[key]})
		if key in defaults:
			item['default'] = defaults[key]
		if key in values:
			item['value'] = values[key]
		result[key] = item
	return result


def deannotate_config(annotated):
	"""Returns a set of values from an annotated config"""
	result = {}
	for key, annotated_value in annotated.items():
		if 'subconfig' in annotated_value:
			result[key] = deannotate_config(annotated_value['subconfig'])
		elif 'value' in annotated_value:
			result[key] = annotated_value['value']
	return result
