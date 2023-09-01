#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Read and write config.yml
"""

import os
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap as YAMLContainer
from project_init_tools import atomic_mv
import yaml
from copy import deepcopy
from threading import Lock
from io import StringIO

from .impl import HubSettings
from .config_yaml_generator import generate_settings_yaml
from ..util import unindent_string_literal as usl, unindent_text
from ..pkg_logging import logger

from ..internal_types import *
from ..version import __version__ as pkg_version
from ..proj_dirs import get_project_dir

_config_yml: Optional[JsonableDict] = None
_roundtrip_config_yml: Optional[YAMLContainer] = None
_cache_lock = Lock()

def _clear_config_yml_cache_no_lock() -> None:
    global _config_yml
    global _roundtrip_config_yml
    _config_yml = None
    _roundtrip_config_yml = None

def clear_config_yml_cache() -> None:
    with _cache_lock:
        _clear_config_yml_cache_no_lock()

def get_config_yml_pathname() -> str:
    return os.path.join(get_project_dir(), "config.yml")

def get_config_yml() -> JsonableDict:
    global _config_yml
    pathname = get_config_yml_pathname()
    with _cache_lock:
        if _config_yml is None:
            if os.path.exists(pathname):
                with open(pathname, 'r', encoding="utf-8") as fd:
                    data: JsonableDict = yaml.safe_load(fd)
                assert isinstance(data, dict)
            else:
                logger.debug("get_config_yml: Generating default config.yml")
                content = generate_settings_yaml()
                _write_config_yml_content_no_lock(content)
                data = yaml.safe_load(content)
                assert isinstance(data, dict)
            _config_yml = data
        result = _config_yml

    return deepcopy(result)

def get_roundtrip_config_yml() -> YAMLContainer:
    global _roundtrip_config_yml
    pathname = get_config_yml_pathname()
    with _cache_lock:
        if _roundtrip_config_yml is None:
            if os.path.exists(pathname):
                with open(get_config_yml_pathname(), 'r', encoding="utf-8") as fd:
                    content = fd.read()
            else:
                logger.debug("get_roundtrip_config_yml: Generating default config.yml")
                content = generate_settings_yaml()
                _write_config_yml_content_no_lock(content)
            data: YAMLContainer = YAML().load(content)
            assert isinstance(data, YAMLContainer)
            _roundtrip_config_yml = data
        result = _roundtrip_config_yml
    return deepcopy(result)

_null_representer = lambda dumper, data: dumper.represent_scalar('tag:yaml.org,2002:null', 'null')

def _ryaml_dumps(ryaml: YAML, data: Any, **options) -> str:
    ss = StringIO()
    try:
        ryaml.dump(data, ss, **options)
        return ss.getvalue()
    finally:
        ss.close()

def _write_config_yml_content_no_lock(content: str) -> None:
    pathname = get_config_yml_pathname()
    tmp_pathname = pathname + '.tmp'
    if os.path.exists(tmp_pathname):
        os.unlink(tmp_pathname)
    try:
        # Create with only this user having access, since secrets may be contained
        with open(
                os.open(tmp_pathname, os.O_CREAT | os.O_WRONLY, 0o600),
                'w',
                encoding='utf-8',
              ) as fd:
            fd.write(content)
        _clear_config_yml_cache_no_lock()
        atomic_mv(tmp_pathname, pathname)
    finally:
        if os.path.exists(tmp_pathname):
            os.unlink(tmp_pathname)

def write_config_yml_content(content: str) -> None:
    with _cache_lock:
        _write_config_yml_content_no_lock(content)
    
    
def save_roundtrip_config_yml(data: YAMLContainer) -> None:
    ryaml = YAML()
    ryaml.representer.add_representer(type(None), _null_representer)
    content = _ryaml_dumps(ryaml, data)
    write_config_yml_content(content)

def get_config_yml_property(name: str) -> Jsonable:
    names = name.split('.')
    data = get_config_yml()
    for name in names[:-1]:
        data = data[name]
    return data[names[-1]]

def set_config_yml_property(name: str, value: Jsonable) -> None:
    names = name.split('.')
    root = get_roundtrip_config_yml()
    data = root
    for name in names[:-1]:
        if name not in data or data[name] is None:
            data[name] = {}
        data = data[name]
    data[names[-1]] = value
    save_roundtrip_config_yml(root)
