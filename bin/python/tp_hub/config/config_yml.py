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
import yaml
from copy import deepcopy
from threading import Lock
from io import StringIO
from functools import cache
from .impl import HubSettings
from .config_yaml_generator import generate_settings_yaml
from ..util import unindent_string_literal as usl, unindent_text, atomic_mv
from ..pkg_logging import logger

from ..internal_types import *
from ..version import __version__ as pkg_version
from ..proj_dirs import get_project_dir

_config_yml: Optional[JsonableDict] = None
_roundtrip_config_yml: Optional[YAMLContainer] = None
_cache_lock = Lock()


@cache
def _get_default_roundtrip_config_yml() -> YAMLContainer:
    content = generate_settings_yaml()
    data = YAML().load(content)
    assert isinstance(data, YAMLContainer)
    return data

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
    with _cache_lock:
        if _config_yml is None:
            rt_data = _get_roundtrip_config_yml_no_lock()
            rt_content = render_roundtrip(rt_data)
            data = yaml.safe_load(rt_content)
            _config_yml = data
        result = _config_yml

    return deepcopy(result)

def _get_roundtrip_config_yml_no_lock() -> YAMLContainer:
    global _roundtrip_config_yml
    pathname = get_config_yml_pathname()
    if _roundtrip_config_yml is None:
        data = deepcopy(_get_default_roundtrip_config_yml())
        hub_data = data['hub']
        assert isinstance(data, YAMLContainer)
        if os.path.exists(pathname):
            with open(get_config_yml_pathname(), 'r', encoding="utf-8") as fd:
                content = fd.read()
            new_data: YAMLContainer = YAML().load(content)
            assert isinstance(new_data, YAMLContainer)
            new_hub_data = new_data.get('hub')
            if not new_hub_data is None:
                for k, v in new_hub_data.items():
                    if not k in hub_data:
                        raise HubError(f"get_roudtrip_config_yml: Unknown setting in config.yml: '{k}'")
                    hub_data[k] = v
        else:
            logger.debug("get_roundtrip_config_yml: Generating default config.yml")
        _roundtrip_config_yml = data
    result = _roundtrip_config_yml
    return deepcopy(result)

def get_roundtrip_config_yml() -> YAMLContainer:
    global _roundtrip_config_yml
    pathname = get_config_yml_pathname()
    with _cache_lock:
        return _get_roundtrip_config_yml_no_lock()

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
        atomic_mv(tmp_pathname, pathname, force=True)
    finally:
        if os.path.exists(tmp_pathname):
            os.unlink(tmp_pathname)

def write_config_yml_content(content: str) -> None:
    with _cache_lock:
        _write_config_yml_content_no_lock(content)
    

def render_roundtrip(data: YAMLContainer) -> str:
    ryaml = YAML()
    ryaml.representer.add_representer(type(None), _null_representer)
    content = _ryaml_dumps(ryaml, data)
    return content

def save_roundtrip_config_yml(data: YAMLContainer) -> None:
    content = render_roundtrip(data)
    write_config_yml_content(content)

def rewrite_roundtrip_config_yml():
    data = get_roundtrip_config_yml()
    save_roundtrip_config_yml(data)

def get_config_yml_property(name: str) -> Jsonable:
    names = name.split('.')
    data = get_config_yml()
    for name in names[:-1]:
        data = data[name]
    return data[names[-1]]

def set_config_yml_property(name: str, value: Jsonable) -> None:
    names = name.split('.')
    root = get_roundtrip_config_yml()
    if names[0] not in root:
        raise HubError(f"set_config_yml_property: Unknown setting in config.yml: '{names[0]}'")
    data = root
    for name in names[:-1]:
        if name not in data or data[name] is None:
            data[name] = {}
        data = data[name]
    data[names[-1]] = value
    save_roundtrip_config_yml(root)
