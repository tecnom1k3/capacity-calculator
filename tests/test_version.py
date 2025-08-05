import re

from version import VERSION_TUPLE, __version__


def test_version_format_and_tuple():
    assert re.match(r"^\d+\.\d+\.\d+$", __version__)
    assert VERSION_TUPLE == tuple(map(int, __version__.split(".")))
