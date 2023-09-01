#!/usr/bin/env python3

"""
Handy Python utilities for this project
"""

from .version import __version__

from .internal_types import *

from .pkg_logging import logger

from .config import (
    HubSettings,
    clear_config_yml_cache,
    get_config_yml_pathname,
    get_config_yml,
    get_roundtrip_config_yml,
    save_roundtrip_config_yml,
    get_config_yml_property,
    set_config_yml_property,
  )

from .proj_dirs import (
    get_tp_hub_package_dir,
    get_project_python_dir,
    get_project_bin_dir,
    get_project_dir,
    get_pkg_data_dir,
    set_project_dir,
    get_project_bin_data_dir,
    get_project_build_dir,
  )

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
    install_aws_cli,
    aws_cli_is_installed,
    should_run_with_group,
    sudo_check_call_stderr_exception,
    sudo_check_output_stderr_exception,
    download_url_text,
    resolve_public_dns,
    raw_resolve_public_dns,
    unindent_text,
    unindent_string_literal,
  )

from .password_hash import hash_username_password, check_username_password

from .docker_compose_stack import DockerComposeStack
