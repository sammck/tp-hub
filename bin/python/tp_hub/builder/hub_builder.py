#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Builder tools for traefik
"""

import os

from ..internal_types import *
from ..pkg_logging import logger
from ..config import HubSettings, current_hub_settings
from .traefik_builder import build_traefik
from .portainer_builder import build_portainer

def build_hub(settings: Optional[HubSettings]=None):
    logger.info("Building Hub")
    build_traefik(settings=settings)
    build_portainer(settings=settings)
    logger.info("Hub build complete")