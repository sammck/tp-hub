#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Common type definitions meant to be imported with "import *".
"""

from __future__ import annotations

from typing import (
    Dict, List, Optional, Union, Any, TypeVar, Tuple,
    Callable, Iterable, Iterator, Generator, cast, TYPE_CHECKING,
    Mapping, ParamSpec, Concatenate, Sequence,
  )

from types import TracebackType
from typing_extensions import Self

from project_init_tools.internal_types import Jsonable, JsonableDict, JsonableList

class HubError(Exception):
    """
    Base class for exceptions in this module
    """
    pass

HostAndPort = Tuple[str, int]

# mypy really struggles with this
if TYPE_CHECKING:
  from subprocess import _CMD, _FILE, _ENV
  from _typeshed import StrOrBytesPath
else:
  _CMD = Any
  _FILE = Any
  _ENV = Any
  StrOrBytesPath = Any

