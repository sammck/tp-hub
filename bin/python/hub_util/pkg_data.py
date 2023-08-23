#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Access non-python data files in the package
"""

from __future__ import annotations

import os
import socket
from functools import cache

@cache
def get_pkg_data_dir() -> str:
    """
    Get the path to the package data directory
    """
    # This is a bit of a hack, but it works
    # If we eventually make this an installable package, we'll need to do something else.
    return os.path.join(os.path.dirname(__file__), "data")

