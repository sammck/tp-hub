#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Generate config.yaml from pydantic settings schema
"""

import json
from copy import deepcopy

from .impl import HubSettings
from ..util import unindent_string_literal as usl, unindent_text

from ..internal_types import *
from ..version import __version__ as pkg_version

_explicit_default_properties: Set[str] = set([
    "hub_package_version",
  ])
"""Property names that should be explicitly initialized to default values
   in config.yml, rather than placing in a comment."""

def generate_settings_yaml() -> str:
    """Use HubSettings schema to generate default settings.yml content, with comments"""
    schema = HubSettings.model_json_schema()
    lns: List[str] = []
    lns.extend(usl(
        f"""version: 1.2

            # Contains local configuration settings for the hub
            # This file should generally be in .gitignore

            hub:
        """
      ).rstrip().split('\n'))
    properties: Dict[str, JsonableDict] = schema["properties"]
    for name, property in properties.items():
        lns.append("")
        title: Optional[str] = property.get('title')
        description: Optional[str] = property.get('description')
        has_default = 'default' in property
        default = property['default'] if has_default else None

        if title is None:
            lns.append(f"  # {name}")
        else:
            lns.append(f"  # {name} -- {title}")
        lns.append("  #")
        if description is not None:
            description_lines = [f"  # {unindent_text(line)}" for line in description.split('\n')]
            lns.extend(description_lines)
        lns.append("  #")
        if has_default:
            lns.append(f"  {name}: {json.dumps(default)}")
        else:
            lns.append(f"  {name}: null")
    lns.append("")     # End with a newline
    return '\n'.join(lns)
