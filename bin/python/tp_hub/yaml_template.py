#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
expand environment variables in YAML
"""

from __future__ import annotations

import os
import yaml
import string

from .internal_types import *
from .internal_types import _CMD, _FILE, _ENV
from .pkg_logging import logger

def load_yaml_template_str(template_str: str, env: Optional[Dict[str, str]]= None) -> JsonableDict:
    if env is None:
        env = dict(os.environ)
    expanded = string.Template(template_str).substitute(env)
    result = yaml.safe_load(expanded)
    return result

def load_yaml_template_file(template_file: str, env: Optional[Dict[str, str]]= None) -> JsonableDict:
    with open(template_file, encoding='utf-8') as f:
        template_str = f.read()

    return load_yaml_template_str(template_str, env=env)
