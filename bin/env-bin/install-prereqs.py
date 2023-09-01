#!/usr/bin/env python3

#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Install system prerequisites for this project, after the virtualenv has been created.
"""

from __future__ import annotations

import os
import sys
import dotenv
import argparse
import json
import logging

from typing import Dict, List

from tp_hub import (
    Jsonable, JsonableDict, JsonableList,
    install_docker,
    docker_is_installed,
    install_docker_compose,
    docker_compose_is_installed,
    install_aws_cli,
    aws_cli_is_installed,
    create_docker_network,
    create_docker_volume,
    should_run_with_group,
    get_public_ip_address,
    get_gateway_lan_ip_address,
    get_lan_ip_address,
    get_default_interface,
    get_project_dir,
    logger,
  )

from tp_hub.config.config_yaml_generator import generate_settings_yaml

def main() -> int:
    parser = argparse.ArgumentParser(description="Install prerequisites for this project")

    parser.add_argument("--force", "-f", action="store_true", help="Force clean installation of prerequisites")
    parser.add_argument( '--loglevel', type=str.lower, default='warning',
                choices=['debug', 'info', 'warning', 'error', 'critical'],
                help='Provide logging level. Default="warning"' )

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())


    force: bool = args.force

    username = os.environ["USER"]

    # Install docker
    if not docker_is_installed() or args.force:
        install_docker(force=force)

    # Install docker-compose
    if not docker_compose_is_installed() or args.force:
        install_docker_compose(force=force)

    # Install aws-cli
    if not aws_cli_is_installed() or args.force:
        install_aws_cli(force=force)

    # Create the "traefik" network if it doesn't exist:
    create_docker_network("traefik")

    # Create The "traefik_acme" volume if it doesn't exist:
    create_docker_volume("traefik_acme")

    # Create the "portainer_data" volume if it doesn't exist:
    create_docker_volume("portainer_data")

    project_dir = get_project_dir()
    config_yml_file = os.path.join(project_dir, "config.yml")
    if not os.path.exists(config_yml_file):
        print(f"Generating initial local config file {config_yml_file}")
        config_yml_content = generate_settings_yaml()
        with open(config_yml_file, 'w', encoding='utf-8') as fd:
            fd.write(config_yml_content)

    public_ip_addr = get_public_ip_address()
    gateway_lan_ip_addr = get_gateway_lan_ip_address()
    lan_ip_addr = get_lan_ip_address()
    default_interface = get_default_interface()

    print(file=sys.stderr)
    print(f"Local hub config file: {config_yml_file}", file=sys.stderr)
    print(f"Default interface: {default_interface}", file=sys.stderr)
    print(f"Gateway LAN IP address: {gateway_lan_ip_addr}", file=sys.stderr)
    print(f"Public IP address: {public_ip_addr}", file=sys.stderr)
    print(f"LAN IP address: {lan_ip_addr}", file=sys.stderr)


    if should_run_with_group("docker"):
        print("\nWARNING: docker and docker-compose require membership in OS group 'docker', which was newly added for", file=sys.stderr)
        print(f"user \"{username}\", and is not yet effective for the current login session. Please logout", file=sys.stderr)
        print("and log in again, or in the mean time run docker with:\n", file=sys.stderr)
        print(f"      sudo -E -u {username} docker [<arg>...]", file=sys.stderr)

    print("\nPrerequisites installed successfully", file=sys.stderr)

    return 0

if __name__ == "__main__":
    rc = main()
    sys.exit(rc)