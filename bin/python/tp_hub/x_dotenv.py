#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
dotenv-compatible extensions utilities
"""

from __future__ import annotations

import os
import sys
import re
import dotenv
from dotenv import dotenv_values, get_key, set_key
from collections import OrderedDict
from io import StringIO

from .internal_types import *
from .internal_types import _CMD, _FILE, _ENV
from .pkg_logging import logger
from project_init_tools import atomic_mv

def x_dotenv_loads(content: str) -> OrderedDict[str, str]:
    """
    Load content of .env (as a string) into an OrderedDict
    """
    with StringIO(content) as fd:
        return dotenv.dotenv_values(stream=fd)

def x_dotenv_load_file(pathname: str) -> OrderedDict[str, str]:
    """
    Load content of .env (as a file) into an OrderedDict
    """
    with open(pathname, 'r', encoding="utf-8") as fd:
        return dotenv.dotenv_values(stream=fd)

_unquoted_safe_re = re.compile(r'^[a-zA-Z0-9_.:\-]+$')
def _x_dotenv_encode_name_value(name: str, value: str) -> str:
    """
    Encode a name/value pair into a string suitable for .env
    """
    encoded_value: str
    if _unquoted_safe_re.match(value):
        encoded_value = value
    else:
        encoded_value = "'" + value.replace('\\', '\\\\').replace("'", "'\\''") + "'"
    return f"{name}={encoded_value}"

def x_dotenv_dumps(data: Dict[str, str]) -> str:
    """
    Serialize a dict into parseable .env content string
    """
    lines = [_x_dotenv_encode_name_value(name, value) for name, value in data.items()]
    return "\n".join(lines)

def x_dotenv_save_file(pathname: str, data: Dict[str, str], mode: int=0o600) -> None:
    """
    Serialize a dict into a .env file
    """
    content = x_dotenv_dumps(data) + "\n"
    tmp_pathname = pathname + ".tmp"
    if os.path.exists(tmp_pathname):
        os.unlink(tmp_pathname)
    try:
        with open(os.open(tmp_pathname, os.O_CREAT | os.O_WRONLY, mode), 'w', encoding="utf-8") as fd:
            fd.write(content)
        atomic_mv(tmp_pathname, pathname)
    finally:
        if os.path.exists(tmp_pathname):
            os.unlink(tmp_pathname)

def x_dotenv_update_file(pathname: str, update_data: Mapping[str, str], mode: int=0o600) -> OrderedDict:
    """
    Update an .env file with new values. If a value already exists, it is not changed.
    """
    data = x_dotenv_load_file(pathname)
    result = data.update(update_data)
    x_dotenv_save_file(pathname, data, mode=mode)
    return result
