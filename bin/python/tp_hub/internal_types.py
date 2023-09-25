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
    Dict, List, Optional, Union, Any, TypeVar, Tuple, overload,
    Callable, Iterable, Iterator, Generator, cast, TYPE_CHECKING,
    Mapping, MutableMapping, ParamSpec, Concatenate, Sequence, MutableSequence, Set, AbstractSet, MutableSet,
    KeysView, ValuesView, ItemsView, Literal, IO, Generic, Type
  )

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem

# mypy really struggles with this
if TYPE_CHECKING:
  from subprocess import _CMD, _FILE, _ENV
  from _typeshed import StrOrBytesPath
else:
  _CMD = Any
  _FILE = Any
  _ENV = Any
  StrOrBytesPath = Any


from ipaddress import IPv4Address, IPv6Address, IPv4Network, IPv6Network
IPAddress = Union[IPv4Address, IPv6Address]
IPv4AddressOrStr = Union[IPv4Address, str, int]
IPv6AddressOrStr = Union[IPv6Address, str]
IPAddressOrStr = Union[IPAddress, str, int]

from enum import Enum
from types import TracebackType, NoneType
from typing_extensions import Self

from project_init_tools.internal_types import Jsonable, JsonableDict, JsonableList

class HubError(Exception):
    """
    Base class for exceptions in this module
    """
    pass

HostAndPort = Tuple[str, int]

class ContentType(Enum):
    YAML = 1
    TOML = 2
    JSON = 3


