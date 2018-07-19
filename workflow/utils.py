import re
from functools import reduce

try:
    # Python 3
    from itertools import zip_longest
except ImportError:
    # Python 2
    from itertools import izip_longest as zip_longest

from . import mapper


def form_doc(doc, mapping_json_str):
    new_mapper = mapper.DataMapper(mapping_json_str)
    data = new_mapper.form_doc_dict(doc)

    return data


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n

    return zip_longest(*args, fillvalue=fillvalue)


as_list = lambda x: x if isinstance(x, list) else [x]


class RegexRemover:
  """
  Removes predefined regex from given string.
  """

  def __init__(self, regex_list_or_str):
    """
    :in regex_list_or_str either single regex string or a list of regex strings.
    """
    self.regexes = [re.compile(regex) for regex in as_list(regex_list_or_str)]

  def handle(self, string):
    """
    :out string with self.regexes removed
    """
    return reduce(lambda s, r: re.sub(r, "", s), self.regexes, string)
