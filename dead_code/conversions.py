#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Mult-format config data files with merging, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import socket
from io import StringIO
import json
from enum import Enum
import copy
from copy import deepcopy
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap as YAMLContainer, CommentedSeq as YAMLSequence
from functools import cache
from ..internal_types import *
from threading import Lock
import tomlkit
from tomlkit import TOMLDocument, key as toml_key, container as toml_container
from tomlkit.container import Container as TOMLContainer
from tomlkit.items import Item as TOMLItem, Key as TOMLKey
from ..util import deep_update_mutable, deep_copy_mutable
from ..proj_dirs import get_project_dir


from ..internal_types import *
from typing import TypeVar

ScalarValue = Union[None, int, float, bool, str, bytes]
InputValue = TypeVar('InputValue')
ConvertedValue = TypeVar('ConvertedValue')
DataKeyType = TypeVar('DataKeyType')

class _NoValue:
    def __eq__(self, value: object) -> bool:
        return value is self
    
    def __ne__(self, value: object) -> bool:
        return value is not self
    
    def __str__(self) -> str:
        return "<NO_VALUE>"
    
    def __repr__(self) -> str:
        return "<NO_VALUE>"

NO_VALUE = _NoValue()
NO_VALUE_TYPE = _NoValue

class ValueConverter(ABC, Generic[InputValue, ConvertedValue, DataKeyType]):
    InputMapping = Mapping[DataKeyType, InputValue]
    InputSequence = Sequence[InputValue]
    InputSet = AbstractSet[InputValue]
    InputContainerValue = Union[InputMapping, InputSequence, InputSet]
    OutputMapping = Mapping[DataKeyType, ConvertedValue]
    OutputSequence = Sequence[ConvertedValue]
    OutputSet = AbstractSet[ConvertedValue]
    OutputContainerValue = Union[OutputMapping, OutputSequence, OutputSet]

    copied_types: Set[Type] = set()
    """The types for which if a value is an instance, that value will be copied rather than converted."""

    copied_exact_types: Set[Type] = set()
    """The types for which if a value is of exactly that type, that value will be copied rather than converted."""

    copy_by_ref_types: Set[Type] = set()
    """The types for which if a value is an instance, that value will be copied by reference rather than converted.
       Useful for known immutable types."""

    copy_by_ref_exact_types: Set[Type] = set()
    """The types for which if a value is of exactly that type, that value will be copied by reference rather than converted.
       Useful for known immutable types."""
    
    scalar_types: Set[Type] = set([NoneType, int, float, bool, str, bytes])
    """The types that are considered scalar values."""
    
    def __init__(self):
        self
        pass

    def is_scalar(self, value: InputValue) -> bool:
        """"""
        return value is None or isinstance(value, (int, float, bool, str, bytes))
    
    def instanceof_copied_type(self, value: InputValue) -> bool:
        """Returns True if the value is matched by copied_types or exact_copied_types."""
        return isinstance(value, self.copied_types) or type(value) in self.copied_exact_types
    
    def instanceof_copy_by_ref_type(self, value: InputValue) -> bool:
        """Returns True if the value is matched by copy_by_ref_types or exact_copy_by_ref_types."""
        return isinstance(value, self.copy_by_ref_types) or type(value) in self.copy_by_ref_exact_types
    
    def convert_scalar(self, value: InputValue) -> Union[NO_VALUE_TYPE, ConvertedValue]:
        """Converts a scalar value into the form provided by this ValueConverter.

        A scalar value is one that is always converted by value, not by reference.
        """

        If the value is not a scalar, then NO_VALUE is returned
        If the value is already in the desired form, then it is returned unchanged.
        Otherwise, the value is converted into the desired form and returned.

        The default implementation converts subclasses of basic scalar types to their
        basic representation, unless they match a configured copyable type.

        Subclasses may override this implementation to pass their own subclasses through
        unchanged.
        """
        
    @abstractmethod
    def shallow_convert(self, value: Any, force_copy: bool=False) -> ConvertedType:
        """Turns a value into the form provided by this ValueConverter, nonrecursively.
        Does not modify the original value, but the return value may reference it in containers.
        
        If force_copy is False, then the original value is returned if it is already in the desired form. This
        includes the case where the original value is a Mapping or Sequence.

        Subclasses of basic types are converted into the basic type. For example, a TOML String is converted into a simple str.
        Implementations of Mapping and Sequence are converted into dict and list, respectively.
        """
        if value is None:
            result = None
        elif isinstance(value, int):
            result = int(value)
        elif isinstance(value, float):
            result = float(value)
        elif isinstance(value, bool):
            result = bool(value)
        elif isinstance(value, str):
            result = str(value)
        elif isinstance(value, Mapping):
            result = dict(value.items())
        elif isinstance(value, Sequence):
            result = [ v for v in value ]
        else:
            raise HubError(f"deep_make_jsonable: Unsupported type {type(value)}")
        return result


def shallow_copy_jsonable(value: Any) -> Jsonable:
    """Turns a value into an independent simple plain-old JSON-able value, nonrecursively.
       Does not modify the original value, but may reference it in containers.

    Subclasses of basic types are converted into the basic type. For example, a TOML String is converted into a simple str.
    Implementations of Mapping and Sequence are converted into dict and list, respectively.
    """
    if value is None:
        result = None
    elif isinstance(value, int):
        result = int(value)
    elif isinstance(value, float):
        result = float(value)
    elif isinstance(value, bool):
        result = bool(value)
    elif isinstance(value, str):
        result = str(value)
    elif isinstance(value, Mapping):
        result = dict(value.items())
    elif isinstance(value, Sequence):
        result = [ v for v in value ]
    else:
        raise HubError(f"deep_make_jsonable: Unsupported type {type(value)}")
    return result

def deep_make_jsonable(value: Any) -> Jsonable:
    """Turns a value into a simple plain-old JSON-able value, recursively. May modify and reference the original value.

    Subclasses of basic types are converted into the basic type. For example, a TOML String is converted into a simple str.
    Implementations of Mapping and Sequence are converted into dict and list, respectively.
    """
    result = shallow_make_jsonable(value)
    if isinstance(result, Mapping):
        for k, v in result.items():
            result[k] = deep_make_jsonable(v)
    elif isinstance(result, Sequence):
        for i, v in enumerate(result):
            result[i] = deep_make_jsonable(v)
    return result

def deep_copy_jsonable(value: Any) -> Jsonable:
    """Turns a value into an independent simple plain-old JSON-able value.
       Does not modify or reference the original value.

    Subclasses of basic types are converted into the basic type. For example, a TOML String is converted into a simple str.
    Implementations of Mapping and Sequence are converted into dict and list, respectively.
    """
    result = shallow_copy_jsonable(value)
    if isinstance(result, Mapping):
        for k, v in result.items():
            result[k] = deep_copy_jsonable(v)
    elif isinstance(result, Sequence):
        for i, v in enumerate(result):
            result[i] = deep_copy_jsonable(v)
    return result
    return result

def shallow_make_yamlable(value: ConfigValue) -> Jsonable:
    if value is None:
        result = None
    elif isinstance(value, int):
        result = int(value)
    elif isinstance(value, float):
        result = float(value)
    elif isinstance(value, bool):
        result = bool(value)
    elif isinstance(value, str):
        result = str(value)
    elif isinstance(value, Mapping):
        if not (type(value) == dict or isinstance(value, YAMLContainer)):
            result = dict(value)
    elif isinstance(value, Sequence):
        if not (type(value) == list or isinstance(value, YAMLSequence)):
            result = list(value)
    else:
        raise HubError(f"shallow_make_yamlable: Unsupported type {type(value)}")
    return result

def deep_make_yamlable(value: ConfigValue) -> ConfigValue:
    if value is None:
        result = None
    elif isinstance(value, int):
        result = int(value)
    elif isinstance(value, float):
        result = float(value)
    elif isinstance(value, bool):
        result = bool(value)
    elif isinstance(value, str):
        result = str(value)
    elif isinstance(value, Mapping):
        if type(value) == dict or isinstance(value, YAMLContainer):
            result = value
            for k, v in result.items():
                result[k] = deep_make_yamlable(v)
        else:
            result = dict((k, deep_make_yamlable(v)) for k, v in value.items())
    elif isinstance(value, Sequence):
        if type(value) == list or isinstance(value, YAMLSequence):
            result = value
            for i, v in enumerate(result):
                result[i] = deep_make_yamlable(v)
        else:
            result = [deep_make_yamlable(v) for v in value]
    else:
        raise HubError(f"deep_make_yamlable: Unsupported type {type(value)}")
    return result

def deep_copy_yamlable(value: ConfigValue) -> Jsonable:
    if value is None:
        result = None
    elif isinstance(value, int):
        result = int(value)
    elif isinstance(value, float):
        result = float(value)
    elif isinstance(value, bool):
        result = bool(value)
    elif isinstance(value, str):
        result = str(value)
    elif isinstance(value, Mapping):
        result = dict((k, deep_copy_yamlable(v)) for k, v in value.items())
    elif isinstance(value, Sequence):
        result = [deep_copy_yamlable(v) for v in value]
    else:
        raise HubError(f"deep_copy_yamlable: Unsupported type {type(value)}")
    return result

def shallow_make_mutable(value: ConfigValue) -> ConfigValue:
    if isinstance(value, (str, bytes)):
        pass
    elif isinstance(value, Mapping) and not isinstance(value, MutableMapping):
        value = dict(value)
    elif isinstance(value, Sequence) and not isinstance(value, MutableSequence):
        value = list(value)
    return value

def shallow_copy_mutable(value: MappingValue) -> MutableMappingValue:
    value = copy.copy(value)
    value = shallow_make_mutable(value)
    return value

def deep_make_mutable(value: MappingValue) -> MutableMappingValue:
    mutable_value = shallow_make_mutable(value)
    if isinstance(mutable_value, (str, bytes)):
        pass
    elif isinstance(mutable_value, Mapping):
        assert isinstance(mutable_value, MutableMapping)
        for k, v in mutable_value.items():
            if ((isinstance(v, Mapping) and not isinstance(v, MutableMapping)) or
                (isinstance(v, Sequence) and not isinstance(v, MutableSequence))):
                mutable_value[k] = deep_make_mutable(v)
    elif isinstance(mutable_value, Sequence):
        assert isinstance(mutable_value, MutableSequence)
        for i, v in enumerate(mutable_value):
            if ((isinstance(v, Mapping) and not isinstance(v, MutableMapping)) or
                (isinstance(v, Sequence) and not isinstance(v, MutableSequence))):
                mutable_value[i] = deep_make_mutable(v)
    return mutable_value


def deep_copy_mutable(value: MappingValue) -> MutableMappingValue:
    result = copy.deepcopy(value)
    result = deep_make_mutable(result)
    return result

def deep_merge_mutable(
        dest: MappingValue,
        source: MappingValue,
        allow_retype_mapping: bool=False,
        content_type: Optional[ContentType]=None,
      ) -> MutableMappingValue:
    result: MutableMappingValue
    if isinstance(dest, Mapping):
        if isinstance(source, Mapping):
            # Merging source map into dest map
            # If dest is not mutable, convert it into a dict
            mutable_dest = shallow_make_mutable(dest)
            #if not mutable_dest is dest:
            #    raise HubError(f"Non-mutable Mapping or Sequence passed to deep_merge_mutable: {type(dest)}")
            assert isinstance(mutable_dest, MutableMapping)
            for k, v in source.items():
                if k in mutable_dest:
                    # key is present; just recurse to update it
                    new_v = deep_merge_mutable(mutable_dest[k], v, allow_retype_mapping=allow_retype_mapping)
                    if mutable_dest[k] != new_v:
                        #del mutable_dest[k]  # delete the old value; tomlkit doesn't allow overwriting
                        # raise HubError(f"Key = '{k}'; Attempt to replace {type(mutable_dest[k])} '''{mutable_dest[k]}'''with {type(new_v)} '''{new_v}'''")
                        mutable_dest[k] = new_v
                else:
                    # key is not present. make a deep mutable copy of source value.
                    new_v = deep_copy_mutable(v)
                    mutable_dest[k] = new_v
            result = mutable_dest
        else:
            # replacing a mapping with something else
            if not allow_retype_mapping:
                raise HubError(
                    f"While merging data, an attempt was made to replace a Mapping type "
                    f"{dest.__class__.__name__} with non-mapping type {source.__class__.__name__}")
            result = deep_copy_mutable(source)
    else:
        result = deep_copy_mutable(source)
    return result

@overload
def normalize_update_args(other: Mapping[_KT, _VT], __m: SupportsKeysAndGetItem[_KT, _VT], **kwargs: _VT) -> List[Tuple[_KT, _VT]]: ...

@overload
def normalize_update_args(other: Iterable[Tuple[_KT, _VT]], **kwargs: _VT) -> List[Tuple[_KT, _VT]]: ...

@overload
def normalize_update_args(other: Mapping[_KT, _VT], **kwargs: _VT) -> List[Tuple[_KT, _VT]]: ...

@overload
def normalize_update_args(other: None, **kwargs: _VT) -> List[Tuple[_KT, _VT]]: ...

def normalize_update_args(other=None, /, **kwargs):
    """
    Normalize the arguments to MutableMapping.update() to be a list of key-value tuples
    """
    result = []
    if not other is None:
        if isinstance(other, Mapping):
            for key in other:
                result.append((key, other[key]))
        elif hasattr(other, "keys"):
            for key in other.keys():
                result.append((key, other[key]))
        else:
            for key, value in other:
                result.append((key, value))
    for key, value in kwargs.items():
        result.append((key, value))
    return result

@overload
def deep_update_mutable(dest: MutableMapping[str, _VT], other: SupportsKeysAndGetItem[_KT, _VT], **kwargs: _VT) -> MutableMapping[_KT, _VT]: ...

@overload
def deep_update_mutable(dest: MutableMapping[str, _VT], other: Iterable[Tuple[_KT, _VT]], **kwargs: _VT) -> MutableMapping[_KT, _VT]: ...

@overload
def deep_update_mutable(dest: MutableMapping[str, _VT], **kwargs: _VT) -> MutableMapping[_KT, _VT]: ...

def deep_update_mutable(
        dest,
        other=None,
        /,
        **kwargs
      ):
    updates = normalize_update_args(other, **kwargs)
    update_mapping = dict(updates)
    mutable_dest = deep_merge_mutable(dest, update_mapping)
    assert isinstance(mutable_dest, MutableMapping)
    return mutable_dest





class ConfigData(MutableConfigMapping):
    """
    Container for YAML, TOML, or raw JSON data that can be merged, etdited etc.
    Supports roud-trip serialization to/from YAML and TOML.
    """
    _root: Optional[MutableConfigMapping] = None
    _name: Optional[str] = None
    _save_filename: Optional[str] = None
    _merged_names: List[str]
    _default_root_content_type: ContentType = ContentType.JSON

    def __init__(
            self,
            data: Optional[ConfigMapping]=None,
            /,
            name: Optional[str]=None,
            default_content_type: ContentType=ContentType.JSON
          ):
        self._name = name
        self._merged_names = []
        self._default_root_content_type = default_content_type
        self.set_root(data)
    
    def clear_merged_names(self) -> None:
        self._merged_names.clear()

    def add_merged_name(self, name: str) -> None:
        self._merged_names.append(name)

    @property
    def save_filename(self) -> Optional[str]:
        return self._save_filename

    @save_filename.setter
    def save_filename(self, filename: Optional[str]) -> None:
        self._save_filename = filename


    def set_root(self, data: Optional[ConfigMapping], content_type: Optional[ContentType]=None) -> None:
        """Replaces the entire root mapping node with the given data."""
        if data is None:
            self._root = None
        else:
            if content_type is None:
                if isinstance(data, TOMLContainer):
                    content_type = ContentType.TOML
                elif isinstance(data, YAMLContainer):
                    content_type = ContentType.YAML
                else:
                    content_type = self._default_root_content_type
            if content_type == ContentType.JSON:
                self._root = deep_copy_mutable(data)
            elif content_type == ContentType.YAML:
                if isinstance(data, YAMLContainer):
                    self._root = deepcopy(data)
                else:
                    self._root = YAML().load("{}")
                    self._root.update(deepcopy(data))
            elif content_type == ContentType.TOML:
                if isinstance(data, TOMLDocument):
                    self._root = deepcopy(data)
                else:
                    self._root = tomlkit.document()
                    self._root.update(deepcopy(data))
            else:
                raise ValueError(f"Unknown content type: {content_type}")

    def get_root(self) -> MutableConfigMapping:
        if self._root is None:
            if self._default_root_content_type == ContentType.JSON:
                self._root = {}
            elif self._default_root_content_type == ContentType.YAML:
                self._root = YAML().load("{}")
            elif self._default_root_content_type == ContentType.TOML:
                 self._root = tomlkit.document()
            else:
                raise ValueError(f"Unknown default root content type: {self._default_root_content_type}")
        return self._root
    
    def resolve_key(
            self,
            key: ConfigKey,
            start_container: Optional[MutableConfigMapping]=None,
            create_containers: bool=False
          ) -> Tuple[MutableConfigMapping, str]:
        """
        Resolve a potentially multi-part key path into a container mapping and a key name.
        """
        key_names: List[str]
        if start_container is None:
            start_container = self.get_root() if create_containers else self._root
            if start_container is None:
                raise KeyError("<empty key>")
        if isinstance(key, KeyPath):
            key_names = [str(x) for x in key]
        elif isinstance(key, str):
            key_names = [ key ]
        elif isinstance(key, list):
            key_names = list(key)
        else:
            raise TypeError(f"key must be a KeyPath, str, or list of str, not {type(key)}")
        if len(key_names) == 0:
            raise ValueError("Multi-part key must not be empty")
        
        for i, key_name in enumerate(key_names[:-1]):
            if key_name not in start_container:
                if create_containers:
                    if isinstance(start_container, TOMLContainer):
                        start_container.add(key_name, TOMLContainer())
                    else:
                        start_container[key_name] = {}
                else:
                    if i == 0:
                        raise KeyError(key_name)
                    else:
                        raise KeyError(f"KeyPath({key_names[:i]})")
            start_container = start_container[key_name]
        return start_container, key_names[-1]

    def __getitem__(self, key: ConfigKey) -> ConfigValue:
        if self._root is None:
            raise KeyError(key)
        
        container, key_name = self.resolve_key(key, create_containers=False)
        return container[key_name]
    
    def __setitem__(self, key: ConfigKey, value: ConfigValue) -> None:
        container, key_name = self.resolve_key(key, create_containers=True)
        #if key_name in container:
        #    if isinstance(container, TOMLContainer):
        #        del container[key_name] # HACK: TOML does not like to replace existing keys
        container[key_name] = value

    def __delitem__(self, key: ConfigKey) -> None:
        container, key_name = self.resolve_key(key, create_containers=False)
        del container[key_name]

    def __contains__(self, key: ConfigKey) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False
    
    def __iter__(self) -> Iterator[str]:
        if self._root is None:
            return iter([])
        return iter(self._root)
    
    def __len__(self) -> int:
        if self._root is None:
            return 0
        return len(self._root)
    
    def __repr__(self) -> str:
        if self._root is None:
            return "ConfigData()"
        return f"ConfigData({repr(self._root)})"
    
    def __str__(self) -> str:
        if self._root is None:
            return "ConfigData()"
        return f"ConfigData({str(self._root)})"
    
    def __deepcopy__(self, memo: Dict[int, ConfigValue]) -> ConfigData:
        result = ConfigData(self._root)
        memo[id(self)] = result
        return result
    
    def __copy__(self) -> ConfigData:
        return ConfigData(self._root)
    
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ConfigData):
            return self._root == other._root
        return False
    
    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)
    
    def keys(self) -> KeysView[ConfigData]:
        if self._root is None:
            return []
        return self._root.keys()
    
    def values(self) -> ValuesView[ConfigData]:
        if self._root is None:
            return []
        return self._root.values()

    def items(self) -> ItemsView[ConfigData]:
        if self._root is None:
            return []
        return self._root.items()

    def unwrap(self) -> JsonableDict:
        if self._root is None:
            return {}
        return json.loads(json.dumps(self._root.value))

    @overload
    def update(self, other: SupportsKeysAndGetItem[ConfigKey, ConfigValue], **kwargs: ConfigValue) -> None: ...

    @overload
    def update(self, other: Iterable[Tuple[ConfigKey, ConfigValue]], **kwargs: ConfigValue) -> None: ...

    @overload
    def update(self, **kwargs: ConfigValue) -> None: ...

    def update(self, other=None, **kwargs):
        if other is None:
            self.get_root().update(**kwargs)
        else:
            self.get_root().update(other, **kwargs)

    @overload
    def deep_update(self, other: SupportsKeysAndGetItem[ConfigKey, ConfigValue], **kwargs: ConfigValue) -> None: ...

    @overload
    def deep_update(self, other: Iterable[Tuple[ConfigKey, ConfigValue]], **kwargs: ConfigValue) -> None: ...

    def deep_update(self, other=None, **kwargs) -> None:
        deep_update_mutable(self.get_root(), other, **kwargs)

    @classmethod
    def _parse_content(cls, content: str, content_type: ContentType) -> MutableConfigMapping:
        parsed_content: MutableConfigMapping
        if content_type == ContentType.JSON:
            parsed_content = json.loads(content)
        elif content_type == ContentType.YAML:
            parsed_content = YAML().load(content)
        elif content_type == ContentType.TOML:
            parsed_content = tomlkit.parse(content)
        else:
            raise ValueError(f"Unknown content type: {content_type}")
        return parsed_content

    def deep_update_from_str(
            self,
            content: str,
            content_type: ContentType=ContentType.JSON,
            merged_name: Optional[str]=None
          ) -> None:
        parsed_content = self._parse_content(content, content_type)
        self.deep_update(parsed_content)
        if merged_name is not None:
            self.add_merged_name(merged_name)

    def deep_update_from_stream(
            self,
            fp: IO,
            content_type: ContentType=ContentType.JSON,
            merged_name: Optional[str]=None
          ) -> None:
        content = fp.read()
        assert isinstance(content, (str, bytes))
        str_content = content.decode("utf-8") if isinstance(content, bytes) else content
        self.deep_update_from_str(str_content, content_type=content_type, merged_name=merged_name)

    def _filename_to_content_type(self, filename: str, default: Union[bool, ContentType]=False) -> ContentType:
        _, ext = os.path.splitext(filename)
        if ext == ".json":
            content_type = ContentType.JSON
        elif ext == ".yaml" or ext == ".yml":
            content_type = ContentType.YAML
        elif ext == ".toml":
            content_type = ContentType.TOML
        else:
            if isinstance(default, bool):
                if default:
                    content_type = self._default_root_content_type
                else:
                    raise ValueError(f"Unable to infer content type from file extension '{ext}': {filename}")
            else:
                content_type = default
        return content_type

    def deep_update_from_file(
            self,
            filename: str,
            content_type: Optional[ContentType]=None,
            merged_name: Optional[Union[str, bool]]=True
          ) -> None:
        filename = os.path.abspath(filename)
        if content_type is None:
            content_type = self._filename_to_content_type(filename)
        if isinstance(merged_name, bool):
            merged_name = filename if merged_name else None
        with open(filename, "r") as fp:
            self.deep_update_from_stream(fp, content_type=content_type, merged_name=merged_name)

    def clear(self) -> None:
        self._root = None

    def dumps(self, content_type: Optional[ContentType]=None) -> str:
        if content_type is None:
            content_type = self.current_content_type
        if content_type == ContentType.JSON:
            data = {} if self._root is None else self._root
            result = json.dumps(data, indent=2, sort_keys=True)
        elif content_type == ContentType.YAML:
            data = deep_copy_yamlable(self._root)
            string_stream = StringIO()
            YAML().dump(data, string_stream)
            result = string_stream.getvalue()
            string_stream.close
        elif content_type == ContentType.TOML:
            data = {} if self._root is None else self._root
            result = tomlkit.dumps(data)
        else:
            raise ValueError(f"Unknown content type: {content_type}")
        return result
     
    def dump(self, fp: StringIO, content_type: Optional[ContentType]=None) -> None:
        fp.write(self.dumps(content_type=content_type))

    def save_file(self, filename: Optional[str]=None, content_type: Optional[ContentType]=None) -> None:
        if filename is None:
            if self.save_filename is None:
                raise ValueError("No save filename provided")
            filename = self.save_filename
        if content_type is None:
            content_type = self._filename_to_content_type(filename, default=self._default_root_content_type)
        with open(filename, "w", encoding='utf-8') as fp:
            self.dump(fp, content_type=content_type)

    def loads(
            self,
            content: str,
            content_type: ContentType=ContentType.JSON,
            merged_name: Optional[str]=None
          ) -> None:
        parsed_content = self._parse_content(content, content_type)
        self.set_root(parsed_content)
        self.save_filename = None
        self.clear_merged_names()
        if merged_name is not None:
            self.add_merged_name(merged_name)

    def load_stream(
            self, fp: IO,
            content_type: Optional[ContentType]=None,
            filename: Optional[str]=None,
            merged_name: Optional[str]=None,
            replace_merged_name: bool=True,
          ) -> None:
        if content_type is None:
            if filename is None:
                raise ValueError("Either filename or content_type must be provided")
            content_type = self._filename_to_content_type(filename)
        if replace_merged_name:
            if merged_name is None:
                merged_name = filename
                if merged_name is None:
                    raise ValueError("Either filename or merged_name must be provided if replace_merged_name is True")
        else:
            merged_name = None
        content = fp.read()
        assert isinstance(content, (str, bytes))
        str_content = content.decode("utf-8") if isinstance(content, bytes) else content
        self.loads(str_content, content_type=content_type, merged_name=merged_name)
        if not filename is None:
            self.save_filename = filename

    def load_file(self, filename: str, content_type: Optional[ContentType]=None, replace_merged_name: bool=True) -> None:
        filename = os.path.abspath(filename)
        merged_name = filename if replace_merged_name else None
        if content_type is None:
            content_type = self._filename_to_content_type(filename)
        with open(filename, "r") as fp:
            self.load_stream(fp, content_type=content_type, merged_name=merged_name)
        if replace_merged_name:
            self.clear_merged_names()
            self.add_merged_name(filename)
        self.save_filename = filename

    @property
    def current_content_type(self) -> ContentType:
        if self._root is None:
            return self._default_root_content_type
        if isinstance(self._root, TOMLContainer):
            return ContentType.TOML
        elif isinstance(self._root, YAMLContainer):
            return ContentType.YAML
        else:
            return ContentType.JSON

    def to_jsonable(self) -> JsonableDict:
        return self.unwrap()
    
    def to_json(self) -> str:
        return self.dumps(content_type=ContentType.JSON)
    
    def to_yaml(self) -> str:
        return self.dumps(content_type=ContentType.YAML)

    def to_toml(self) -> str:
        return self.dumps(content_type=ContentType.TOML)

    def __str__(self) -> str:
        result_parts: List[str] = []
        if self._name is None:
            if not self.save_filename is None:
                result_parts.append(f"filename={self.save_filename}")
            if len(self._merged_names) > 0:
                result_parts.append(f"merged_names={self._merged_names}")
            if len(result_parts) == 0:
                result_parts.append("id={id(self)}")
        else:
            result_parts.append(f"name={self._name}>")
        result_inner = ', '.join(result_parts)
        result = f"ConfigData<{result_inner}>"
        return result

    def __repr__(self) -> str:
        return str(self)
