#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
A Pydantic settings source that reads a YAML file.
"""

import sys
import yaml
import os
from copy import deepcopy

from pydantic.fields import FieldInfo

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
  )

from ..proj_dirs import get_project_dir

from ..internal_types import *

class YAMLConfigSettingsSource(PydanticBaseSettingsSource):
    """
    A settings source class that loads variables from a config.yml file
    """

    config_file: str
    cached_jsonable: Optional[JsonableDict] = None

    def __init__(
            self,
            settings_cls: type[BaseSettings],
            config_file: str = 'config.yml'
          ):
        self.config_file = config_file
        super().__init__(settings_cls)

    def get_jsonable(self) -> JsonableDict:
        if self.cached_jsonable is None:
            project_dir = get_project_dir()
            file_path = os.path.join(project_dir, self.config_file)
            if os.path.exists(file_path):
                encoding = self.config.get('env_file_encoding')
                with open(file_path, 'r', encoding=encoding) as f:
                    parent_jsonable = yaml.safe_load(f)
                    if not isinstance(parent_jsonable, dict):
                        raise TypeError(
                            f"YAML config file {file_path} must contain a dictionary"
                        )
                    if 'hub' in parent_jsonable and isinstance(parent_jsonable['hub'], dict):
                        self.cached_jsonable = parent_jsonable['hub']
                    else:
                        print(f"WARNING: YAML config file {file_path} does not contain a 'hub' section", file=sys.stderr)
                        self.cached_jsonable = {}
            else:
                self.cached_jsonable = {}
        return self.cached_jsonable

    # @override
    def get_field_value(
            self,
            field: FieldInfo,
            field_name: str
          ) -> Tuple[Any, str, bool]:
        """
        Gets the value, the key for model creation, and a flag to determine whether value is complex.

        This is an abstract method that should be overridden in every settings source classes.

        Args:
            field: The field.
            field_name: The field name.

        Returns:
            A tuple contains the key, value and a flag to determine whether value is complex.
        """
        jsonable = self.get_jsonable()
        field_value = jsonable.get(field_name)
        return field_value, field_name, False

    # @override
    def prepare_field_value(
            self,
            field_name: str,
            field: FieldInfo,
            value: Any,
            value_is_complex: bool
          ) -> Any:
        """
        Prepares the value of a field.

        Args:
            field_name: The field name.
            field: The field.
            value: The value of the field that has to be prepared.
            value_is_complex: A flag to determine whether value is complex.

        Returns:
            The prepared value.
        """
        return value

    def __call__(self) -> Dict[str, Any]:
        """Return a deep dictionary of settings initializer values from this source"""

        d: Dict[str, Any] = deepcopy(self.get_jsonable())

        #d: Dict[str, Any] = {}
        # for field_name, field in self.settings_cls.model_fields.items():
        #     field_value, field_key, value_is_complex = self.get_field_value(
        #         field, field_name
        #     )
        #     field_value = self.prepare_field_value(
        #         field_name, field, field_value, value_is_complex
        #     )
        #     if field_value is not None:
        #         d[field_key] = field_value

        return d

