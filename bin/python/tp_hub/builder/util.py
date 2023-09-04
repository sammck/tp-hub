#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Builder tools
"""

import os
import json
import hashlib
from datetime import datetime
from functools import cache

from ..internal_types import *
from ..pkg_logging import logger
from ..config import HubSettings, current_hub_settings
from project_init_tools import atomic_mv

very_old = datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

def timestamp_now() -> datetime.datetime:
    return datetime.utcnow()

def timestamp_to_str(ts: datetime) -> str:
    ts = ts.astimezone(datetime.timezone.utc)
    result = ts.isoformat()
    if result.endswith("+00:00"):
        result = result[:-6] + "Z"
    return result

def str_to_timestamp(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(datetime.timezone.utc)

@cache
def get_config_hash(settings: Optional[HubSettings]=None) -> str:
    """
    Returns a hash of the current configuration settings. Will
    be used to determine if a rebuild is necessary.
    """
    if settings is None:
        settings = current_hub_settings()
    settings_data = json.loads(settings.model_dump_json())
    settings_str = json.dumps(settings_data, separators=(',', ':'), sort_keys=True)
    settings_hash = hashlib.sha256(settings_str.encode('utf-8')).hexdigest()
    return settings_hash
