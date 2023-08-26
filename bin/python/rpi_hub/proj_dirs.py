#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Access project and package directories
"""

from __future__ import annotations

import os
import socket
from functools import cache
from .internal_types import *
from threading import Lock

_lock = Lock()

@cache
def get_hub_util_package_dir() -> str:
    """
    Get the path to the directory containing this package
    """
    result = os.path.abspath(os.path.dirname(__file__))
    return result

@cache
def get_pkg_data_dir() -> str:
    """
    Get the path to the package data directory
    """
    # This is a bit of a hack, but it works
    # If we eventually make this an installable package, we'll need to do something else.
    return os.path.join(get_hub_util_package_dir(), "data")

_project_dir: Optional[str] = None

def set_project_dir(project_dir: str) -> None:
    """
    Set the project directory
    """
    with _lock:
        global _project_dir
        _project_dir = project_dir

def get_project_dir() -> str:
    """
    Get the path to the project directory
    """
    global _project_dir
    with _lock:
        if _project_dir is None:
            _project_dir = os.path.abspath(os.path.join(get_hub_util_package_dir(), "..", "..", ".."))
        result = _project_dir
    return result

def get_project_bin_dir() -> str:
    """
    Get the path to the project bin directory
    """
    result = os.path.join(get_project_dir(), 'bin')
    return result

def get_project_python_dir() -> str:
    """
    Get the path to the project python directory (added to PYTHONPATH)
    """
    result = os.path.join(get_project_bin_dir(), "python")
    return result

def get_project_bin_data_dir() -> str:
    """
    Get the path to the project bin data directory
    """
    result = os.path.join(get_project_bin_dir(), 'data')
    return result

def get_project_build_dir() -> str:
    """
    Get the path to the project build directory
    """
    result = os.path.join(get_project_dir(), 'build')
    return result

