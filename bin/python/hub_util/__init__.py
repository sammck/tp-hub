#!/usr/bin/env python3

"""
Package hub_util

Handy Python utilities for this project
"""
import os
import sys
import dotenv
import json
import re
import functools
from functools import cache

from .internal_types import *

from .pkg_logging import logger

from .pkg_data import get_pkg_data_dir

from .util import (
    IpRouteInfo,
    get_public_ip_address,
    get_route_info,
    get_internet_route_info,
    get_lan_ip_address,
    get_gateway_lan_ip_address,
    get_default_interface,
    docker_call,
    docker_call_output,
    docker_compose_call,
    docker_compose_call_output,
    loads_ndjson,
    get_docker_networks,
    get_docker_volumes,
    create_docker_network,
    create_docker_volume,
    docker_is_installed,
    install_docker,
    docker_compose_is_installed,
    install_docker_compose,
    docker_compose_is_installed,
    should_run_with_group,
    sudo_check_call_stderr_exception,
    sudo_check_output_stderr_exception,
    download_url_text,
  )

from .docker_compose_stack import DockerComposeStack

from .port_tester import test_whoami_port_connection, test_server_traefik_ports
