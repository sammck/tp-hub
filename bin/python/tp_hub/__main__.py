#!/usr/bin/env python3

# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
RPI Home Hub Command-Line Tool
"""
from __future__ import annotations

import os
import sys
import dotenv
import argparse
import json
import logging

from tp_hub.internal_types import *

from tp_hub import (
    __version__ as pkg_version,
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
    HubSettings,
    get_config_yml_property,
    set_config_yml_property,
  )

from tp_hub.route53_dns_name import create_route53_dns_name, get_aws, AwsContext

PROGNAME = "hub"

class CmdExitError(RuntimeError):
    exit_code: int

    def __init__(self, exit_code: int, msg: Optional[str]=None):
        if msg is None:
            msg = f"Command exited with return code {exit_code}"
        super().__init__(msg)
        self.exit_code = exit_code

class ArgparseExitError(CmdExitError):
    pass

class NoExitArgumentParser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stderr)
        raise ArgparseExitError(status, message)

class CommandHandler:
    _parser: argparse.ArgumentParser
    _args: argparse.Namespace
    _provide_traceback: bool = True
    _project_dir: Optional[str] = None
    _config: Optional[HubSettings] = None
    _aws: Optional[AwsContext] = None
    _hub_settings_params: Dict[str, Any]
    _hub_settings: Optional[HubSettings] = None

    def __init__(self, argv: Optional[Sequence[str]]=None):
        self._argv = argv
        self._hub_settings_params = {}

    def get_settings(self) -> HubSettings:
        if self._hub_settings is None:
            params = {} if self._hub_settings_params is None else self._hub_settings_params
            self._hub_settings = HubSettings(**params)
        return self._hub_settings
    
    def get_settings_schema(self) -> JsonableDict:
        return HubSettings.model_json_schema()

    def get_project_dir(self) -> str:
        if self._project_dir is None:
            self._project_dir = get_project_dir()
        return self._project_dir
    
    def get_build_dir(self) -> str:
        return os.path.join(self.get_project_dir(), "build")

    def get_aws(self) -> AwsContext:
        if self._aws is None:
            self._aws = get_aws()
        return self._aws


    def rebuild_traefik_env(self) -> None:
        traefik_compose_file = os.path.join(self.get_project_dir(), "traefik", "docker-compose.yml")
        traefik_build_dir = os.path.join(self.get_build_dir(), "traefik")
        output_file = os.path


    def cmd_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._parser.print_help(sys.stderr)
        return 1

    def cmd_version(self) -> int:
        print(pkg_version)
        return 0

    def cmd_config_bare(self) -> int:
        # import pprint
        # settings = self.get_settings()
        # pp = pprint.PrettyPrinter(depth=2)
        # pp.pprint(settings.model_dump())
        jsonable = json.loads(self.get_settings().model_dump_json())
        print(json.dumps(jsonable, indent=2, sort_keys=True))
        return 0

    def cmd_config_get_yml(self) -> int:
        property_name: Optional[str] = self._args.property_name
        raw: bool = self._args.raw
        yml_property_name = "hub" if property_name is None else f"hub.{property_name}"
        value = get_config_yml_property(yml_property_name)
        if raw and isinstance(value, str):
            print(value, end='')
        else:
            print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    
    def cmd_config_get(self) -> int:
        property_name: Optional[str] = self._args.property_name
        raw: bool = self._args.raw
        property_name_parts = [] if property_name is None else property_name.split('.')
        data = json.loads(self.get_settings().model_dump_json())
        for name in property_name_parts:
            if not name in data:
                raise ValueError(f"Property name {property_name} does not exist")
            data = data[name]

        if raw and isinstance(data, str):
            print(data, end='')
        else:
            print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    
    def cmd_config_set(self) -> int:
        property_name: str = self._args.property_name
        property_value_str: str = self._args.property_value
        is_json: bool = self._args.json
        property_converter: Callable[[str], Jsonable] = str
        property_name_parts = property_name.split('.')
        if len(property_name_parts) > 2:
            raise ValueError(f"Property name {property_name} is not valid")
        schema = self.get_settings_schema()
        property = schema.get('properties', {}).get(property_name_parts[0])
        if property is None:
            raise ValueError(f"Property name {property_name} is not valid")
        is_dict = False
        has_default = "default" in property
        default_value = property["default"] if has_default else None
        is_dict = isinstance(default_value, dict)
        nullable = False
        if is_dict:
            if len(property_name_parts) != 2:
                raise ValueError(f"Property name {property_name} is a dict; cannot be set directly")
            property_converter = str
        else:
            if len(property_name_parts) != 1:
                raise ValueError(f"Property name {property_name} is not a dict; cannot be dotted")
            allowed_types: Set[str] = set()
            if "type" in property:
                allowed_types.add(property["type"])
            if "anyOf" in property:
                allowed_types.update(property["anyOf"])
            nullable = 'null' in allowed_types
            if nullable:
                allowed_types.remove('null')
            if len(allowed_types) == 0:
                raise ValueError(f"Property name {property_name} must be null; cannot be set")
            if len(allowed_types) > 1:
                raise ValueError(f"Property name {property_name} has multiple allowed types: {allowed_types}; cannot be set")
            allowed_type = allowed_types.pop()
            if allowed_type == 'string':
                property_converter = str
            elif allowed_type == 'integer':
                property_converter = int
            elif allowed_type == 'number':
                property_converter = float
            elif allowed_type == 'boolean':
                property_converter = bool
            else:
                raise ValueError(f"Property name {property_name} has unknown type {allowed_type}; cannot be set")
        if is_json:
            property_value = json.loads(property_value_str)
        elif nullable and property_value_str == 'null':
            property_value = None
        else:
            property_value = property_converter(property_value_str)
        set_config_yml_property(f"hub.{property_name}", property_value)
        return 0

    def cmd_config_schema(self) -> int:
        schema = self.get_settings_schema()
        print(json.dumps(schema, indent=2, sort_keys=True))
        return 0

    def cmd_create_dns_name(self) -> int:
        dns_name: str = self._args.dns_name
        dns_target: Optional[str] = self._args.dns_target
        if dns_target is None:
            dns_target = self.get_config().stable_public_dns_name

        if not '.' in dns_name:
            dns_name = f"{dns_name}.{self.get_config().parent_dns_domain}"

        create_route53_dns_name(get_aws(), dns_name, dns_target, verify_public_ip=False)
        return 0
    
    def cmd_install_prereqs(self) -> int:
        force: bool = self._args.force

        username = os.environ["USER"]

        # Install docker
        if not docker_is_installed() or force:
            install_docker(force=force)

        # Install docker-compose
        if not docker_compose_is_installed() or force:
            install_docker_compose(force=force)

        # Install aws-cli
        if not aws_cli_is_installed() or force:
            install_aws_cli(force=force)

        # Create the "traefik" network if it doesn't exist:
        create_docker_network("traefik")

        # Create The "traefik_acme" volume if it doesn't exist:
        create_docker_volume("traefik_acme")

        # Create the "portainer_data" volume if it doesn't exist:
        create_docker_volume("portainer_data")

        public_ip_addr = get_public_ip_address()
        gateway_lan_ip_addr = get_gateway_lan_ip_address()
        lan_ip_addr = get_lan_ip_address()
        default_interface = get_default_interface()

        print(file=sys.stderr)
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


    def run(self) -> int:
        """Run the command-line tool with provided arguments

        Args:
            argv (Optional[Sequence[str]], optional):
                A list of commandline arguments (NOT including the program as argv[0]!),
                or None to use sys.argv[1:]. Defaults to None.

        Returns:
            int: The exit code that would be returned if this were run as a standalone command.
        """
        import argparse

        parser = argparse.ArgumentParser(
            prog=PROGNAME,
            description="Install and manage a Docker webservice hub based on Traefik and Portainer."
          )


        # ======================= Main command

        self._parser = parser
        parser.add_argument('--traceback', "--tb", action='store_true', default=False,
                            help='Display detailed exception information')
        parser.add_argument('--log-level', '-l', type=str.lower, dest='log_level', default='warning',
                            choices=['debug', 'infos', 'warning', 'error', 'critical'],
                            help='''The logging level to use. Default: warning''')
        parser.set_defaults(func=self.cmd_bare)

        subparsers = parser.add_subparsers(
                            title='Commands',
                            description='Valid commands',
                            help='Additional help available with "<command-name> -h"')

        # ======================= create-dns-name
        sp = subparsers.add_parser('create-dns-name',
                            help='''Use AWS Route53 to create a new DNS name.''')
        sp.add_argument('--target,', '-t', dest='dns_target',
                            help='''The resolved target value for a 'CNAME' or 'A' DNS record to create. '''
                                 '''If a valid IPV4 address, an 'A' record will be created. Otherwise, '''
                                 '''a 'CNAME' record is created.  If a simple subdomain, f"{value}.{new_dns_name_parent}" '''
                                 '''will be used. By default, config.stable_public_dns_name is used.''')
        sp.add_argument('dns_name',
                            help='''The DNS name to create. If a simple subdomain, '''
                                 '''f"{value}.{config.parent_dns_name}" will be used''')
        sp.set_defaults(func=self.cmd_create_dns_name)

        # ======================= config

        sp = subparsers.add_parser('config',
                                description='''Display or set the project configuration.''')
        sp.set_defaults(func=self.cmd_config_bare)
        config_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help='Additional help available with "config <subcommand-name> -h"')

        # ======================= config get-yml

        sp = config_subparsers.add_parser('get-yml',
                                description='''Get the value of a configuration property as set in config.yml.''')
        sp.add_argument('--raw', "-r", action='store_true', default=False,
                            help='If the value is a string, output it in raw form without encoding as JSON, and without appending a newline. No effect if not a string.')
        sp.add_argument('property_name', default=None, nargs='?',
                            help='''The property name to get; may be dotted to access sub-properties. By default, the entire hub configuration is displayed.''')
        sp.set_defaults(func=self.cmd_config_get_yml)

        # ======================= config get

        sp = config_subparsers.add_parser('get',
                                description='''Get the resolved value of a configuration property.''')
        sp.add_argument('--raw', "-r", action='store_true', default=False,
                            help='If the value is a string, output it in raw form without encoding as JSON, and without appending a newline. No effect if not a string.')
        sp.add_argument('property_name', default=None, nargs='?',
                            help='''The property name to get; may be dotted to access sub-properties. By default, the entire hub configuration is displayed.''')
        sp.set_defaults(func=self.cmd_config_get)

        # ======================= config set

        sp = config_subparsers.add_parser('set',
                                description='''Set the value of a configuration property in config.yml.''')
        parser.add_argument('--json', "--j", action='store_true', default=False,
                            help='Interpret the property value as JSON. Allows setting null values.')
        sp.add_argument('property_name',
                            help='''The property name to set; may be dotted to access sub-properties.''')
        sp.add_argument('property_value',
                            help='''The new value for the property. If the property is nullable, "<^null>" will set it to null. To escape this, use "<<^null>".''')
        sp.set_defaults(func=self.cmd_config_set)

        # ======================= config schema

        sp = config_subparsers.add_parser('schema',
                                description='''Display the configuration schema in JSON.''')
        sp.set_defaults(func=self.cmd_config_schema)

        # ======================= install-prereqs

        sp = subparsers.add_parser('install-prereqs',
                                description='''Install system prerequisites for launching the hub.''')
        sp.add_argument("--force", "-f", action="store_true",
                            help="Force clean installation of prerequisites")
        sp.set_defaults(func=self.cmd_install_prereqs)


        # ======================= version

        sp = subparsers.add_parser('version',
                                description='''Display version information.''')
        sp.set_defaults(func=self.cmd_version)

        # =========================================================

        try:
            args = parser.parse_args(self._argv)
        except ArgparseExitError as ex:
            return ex.exit_code
        traceback: bool = args.traceback
        self._provide_traceback = traceback

        try:
            logging.basicConfig(
                level=logging.getLevelName(args.log_level.upper()),
            )
            self._args = args
            func: Callable[[], int] = args.func
            logging.debug(f"Running command {func.__name__}, tb = {traceback}")
            rc = func()
            logging.debug(f"Command {func.__name__} returned {rc}")
        except Exception as ex:
            if isinstance(ex, CmdExitError):
                rc = ex.exit_code
            else:
                rc = 1
            if rc != 0:
                if traceback:
                    raise
            ex_desc = str(ex)
            if len(ex_desc) == 0:
                ex_desc = ex.__class__.__name__
            print(f"{PROGNAME}: error: {ex_desc}", file=sys.stderr)
        except BaseException as ex:
            print(f"{PROGNAME}: Unhandled exception {ex.__class__.__name__}: {ex}", file=sys.stderr)
            raise

        return rc

def run(argv: Optional[Sequence[str]]=None) -> int:
    try:
        rc = CommandHandler(argv).run()
    except CmdExitError as ex:
        rc = ex.exit_code
    return rc

# allow running with "python3 -m", or as a standalone script
if __name__ == "__main__":
    sys.exit(run())
