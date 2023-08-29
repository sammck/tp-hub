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
from io import StringIO
import json
from copy import deepcopy
from ruamel.yaml import YAML, MappingNode, ScalarNode, SequenceNode
from functools import cache
from .internal_types import *
from threading import Lock
import tomlkit
from tomlkit import TOMLDocument, key as toml_key, container as toml_container
from tomlkit.container import Container as TOMLContainer
from tomlkit.items import Item as TOMLItem, Key as TOMLKey
from .internal_types import *
from .util import deep_update_mutable, deep_copy_mutable
from .proj_dirs import get_project_dir

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")

TKey = Union[str, List[str], TOMLKey]
TValue = Any

class TOMLData(MutableMapping[str, Any]):
    """
    Container for the TOML data that can be merged etc.
    """
    _toml_doc: Optional[TOMLDocument] = None

    def __init__(self, /, data: Optional[Mapping[str, Any]]=None):
        self.set_top_node(data)

    def set_top_node(self, data: Optional[Mapping]) -> None:
        if data is None:
            self._toml_doc = None
        elif isinstance(data, TOMLDocument):
            self._toml_doc = deepcopy(data)
        else:
            self._toml_doc = tomlkit.document()
            self._toml_doc.update(deep_copy_mutable(data))

    def get_toml_doc(self) -> TOMLDocument:
        if self._toml_doc is None:
            self._toml_doc = tomlkit.document()
        return self._toml_doc
    
    def resolve_key(
            self,
            key: TKey,
            start_container: Optional[TOMLContainer]=None,
            create_containers: bool=False
          ) -> Tuple[TOMLContainer, str]:
        """
        Resolve a potentially multi-part key into a container and a key name.
        """
        key_names: List[str]
        if start_container is None:
            start_container = self.get_toml_doc() if create_containers else self._toml_doc
            if start_container is None:
                raise KeyError("<empty key>")
        if isinstance(key, TOMLKey):
            key_names = [str(x) for x in key]
        elif isinstance(key, str):
            key_names = [ key ]
        elif isinstance(key, list):
            key_names = list(key)
        else:
            raise TypeError(f"key must be a TOMLKey, str, or list of str, not {type(key)}")
        if len(key_names) == 0:
            raise ValueError("Multi-part key must not be empty")
        
        for i, key_name in enumerate(key_names[:-1]):
            if key_name not in start_container:
                if create_containers:
                    start_container.add(key_name, tomlkit.co)
                else:
                    if i == 0:
                        raise KeyError(key_name)
                    else:
                        raise KeyError(str(key_names[:i]))
            start_container = start_container[key_name]
        return start_container, key_names[-1]

    def __getitem__(self, key: TKey) -> TOMLItem:
        if self._toml_doc is None:
            raise KeyError(key)
        
        container, key_name = self.resolve_key(key, create_containers=False)
        return container[key_name]
    
    def __setitem__(self, key: TKey, value: Any) -> None:
        container, key_name = self.resolve_key(key, create_containers=True)
        container[key_name] = value

    def __delitem__(self, key: TKey) -> None:
        container, key_name = self.resolve_key(key, create_containers=False)
        del container[key_name]

    def __contains__(self, key: TKey) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False
    
    def __iter__(self) -> Iterator[str]:
        if self._toml_doc is None:
            return iter([])
        return iter(self._toml_doc)
    
    def __len__(self) -> int:
        if self._toml_doc is None:
            return 0
        return len(self._toml_doc)
    
    def __repr__(self) -> str:
        if self._toml_doc is None:
            return "TomlData()"
        return f"TomlData({repr(self._toml_doc)})"
    
    def __str__(self) -> str:
        if self._toml_doc is None:
            return "TomlData()"
        return f"Tomldata({str(self._toml_doc)})"
    
    def __deepcopy__(self, memo: Dict[int, Any]) -> TomlData:
        result = TomlData(self._toml_doc)
        memo[id(self)] = result
        return result
    
    def __copy__(self) -> TomlData:
        return TomlData(self._toml_doc)
    
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, TomlData):
            return self._toml_doc == other._toml_doc
        return False
    
    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)
    
    def keys(self) -> KeysView[str]:
        if self._toml_doc is None:
            return []
        return self._toml_doc.keys()
    
    def values(self) -> ValuesView[Any]:
        if self._toml_doc is None:
            return []
        return self._toml_doc.values()

    def items(self) -> ItemsView[str, Any]:
        if self._toml_doc is None:
            return []
        return self._toml_doc.values()

    def unwrap(self) -> JsonableDict:
        if self._toml_doc is None:
            return {}
        return json.loads(json.dumps(self._toml_doc.value))

    @overload
    def update(self, other: SupportsKeysAndGetItem[TKey, Any], **kwargs: Any) -> None: ...

    @overload
    def update(self, other: Iterable[Tuple[TKey, Any]], **kwargs: Any) -> None: ...

    @overload
    def update(self, **kwargs: Any) -> None: ...

    def update(self, other=None, **kwargs):
        if other is None:
            self.get_toml_doc().update(**kwargs)
        else:
            self.get_toml_doc().update(other, **kwargs)

    @overload
    def deep_update(self, other: SupportsKeysAndGetItem[TKey, Any], **kwargs: Any) -> None: ...

    @overload
    def deep_update(self, other: Iterable[Tuple[TKey, Any]], **kwargs: Any) -> None: ...

    def deep_update(self, other=None, **kwargs) -> None:
        deep_update_mutable(self.get_toml_doc(), other, **kwargs)

    def deep_update_from_str(self, content: str) -> None:
        self.deep_update(tomlkit.parse(content))

    def deep_update_from_stream(self, fp: IO) -> None:
        self.deep_update(tomlkit.load(fp))

    def deep_update_from_file(self, filename: str) -> None:
        with open(filename, "r") as fp:
            self.deep_update_from_stream(fp)

    def clear(self) -> None:
        self._toml_doc = None

    def loads(self, content: str) -> None:
        self._toml_doc = tomlkit.parse(content)

    def dumps(self) -> str:
        return tomlkit.dumps(self._toml_doc)
    
    def dump(self, fp: StringIO) -> None:
        fp.write(self.dumps())

    def save_file(self, filename: str) -> None:
        with open(filename, "w") as fp:
            self.dump(fp)

    def load(self, fp: IO) -> None:
        self._toml_doc = tomlkit.load(fp)

    def load_file(self, filename: str) -> None:
        with open(filename, "r") as fp:
            self.load(fp)


    def to_jsonable(self) -> JsonableDict:
        return self.unwrap()
    
    def to_json(self) -> str:
        return json.dumps(self.to_jsonable(), indent=2, sort_keys=True)

