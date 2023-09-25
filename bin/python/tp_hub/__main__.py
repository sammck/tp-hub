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
import getpass

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
    get_public_ipv4_egress_address,
    get_gateway_lan_ip4_address,
    get_lan_ipv4_address,
    get_default_ipv4_interface,
    get_project_dir,
    logger,
    HubSettings,
    init_current_hub_settings,
    get_config_yml_property,
    set_config_yml_property,
    hash_password,
    check_password,
    hash_username_password,
    check_username_password,
    build_hub,
    build_traefik,
    build_portainer,
    DockerComposeStack,
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
            self._hub_settings = init_current_hub_settings(**params)
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

    def get_traefik_stack(self, **kwargs) -> DockerComposeStack:
        dc_file = os.path.join(self.get_project_dir(), "stacks", "traefik", "docker-compose.yml")
        return DockerComposeStack(dc_file, **kwargs)

    def get_portainer_stack(self, **kwargs) -> DockerComposeStack:
        dc_file = os.path.join(self.get_project_dir(), "stacks", "portainer", "docker-compose.yml")
        return DockerComposeStack(dc_file, **kwargs)
    
    def traefik_up(self, **kwargs) -> None:
        self.get_traefik_stack(**kwargs).up()

    def traefik_down(self, **kwargs) -> None:
        self.get_traefik_stack(**kwargs).down()

    def traefik_logs(self, **kwargs) -> None:
        log_options: Optional[List[str]] = kwargs.pop('log_options', None)
        self.get_traefik_stack(**kwargs).logs(log_options)

    def traefik_ps(self, **kwargs) -> None:
        ps_options: Optional[List[str]] = kwargs.pop('ps_options', None)
        self.get_traefik_stack(**kwargs).ps(ps_options)

    def portainer_up(self, **kwargs) -> None:
        self.get_portainer_stack(**kwargs).up()

    def portainer_down(self, **kwargs) -> None:
        self.get_portainer_stack(**kwargs).down()

    def portainer_logs(self, **kwargs) -> None:
        log_options: Optional[List[str]] = kwargs.pop('log_options', None)
        self.get_portainer_stack(**kwargs).logs(log_options)

    def portainer_ps(self, **kwargs) -> None:
        ps_options: Optional[List[str]] = kwargs.pop('ps_options', None)
        self.get_portainer_stack(**kwargs).ps(ps_options)

    def hub_up(self, **kwargs) -> None:
        self.traefik_up(**kwargs)
        self.portainer_up(**kwargs)

    def hub_down(self, **kwargs) -> None:
        self.portainer_down(**kwargs)
        self.traefik_down(**kwargs)

    def hub_ps(self, **kwargs) -> None:
        self.traefik_ps(**kwargs)
        self.portainer_ps(**kwargs)

    def cmd_traefik_up(self) -> int:
        self.traefik_up()
        return 0

    def cmd_traefik_down(self) -> int:
        self.traefik_down()
        return 0

    def cmd_traefik_logs(self) -> int:
        follow: bool = self._args.follow
        try:
            self.traefik_logs(log_options=["-f"] if follow else None)
        except KeyboardInterrupt:
            return 130
        return 0

    def cmd_traefik_ps(self) -> int:
        self.traefik_ps()
        return 0

    def cmd_portainer_up(self) -> int:
        self.portainer_up()
        return 0

    def cmd_portainer_down(self) -> int:
        self.portainer_down()
        return 0

    def cmd_portainer_logs(self) -> int:
        follow: bool = self._args.follow
        try:
            self.portainer_logs(log_options=["-f"] if follow else None)
        except KeyboardInterrupt:
            return 130
        return 0

    def cmd_portainer_ps(self) -> int:
        self.portainer_ps()
        return 0

    def cmd_up(self) -> int:
        self.hub_up()
        return 0

    def cmd_down(self) -> int:
        self.hub_down()
        return 0

    def cmd_ps(self) -> int:
        self.hub_ps()
        return 0

    def rebuild_traefik_env(self) -> None:
        traefik_compose_file = os.path.join(self.get_project_dir(), "traefik", "docker-compose.yml")
        traefik_build_dir = os.path.join(self.get_build_dir(), "traefik")
        output_file = os.path


    def cmd_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._args.subparser.print_help(sys.stderr)
        return 1

    def cmd_version(self) -> int:
        print(pkg_version)
        return 0

    def cmd_config_bare(self) -> int:
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
                raise CmdExitError(1, f"Property name {property_name} does not exist")
            data = data[name]

        if raw and isinstance(data, str):
            print(data, end='')
        else:
            print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    def cmd_config_set_traefik_password(self) -> int:
        username = self._args.username
        password = self._args.password
        if password is None:
            first = True
            for i in range(5):
                if not first:
                    print("Passwords do not match; try again", file=sys.stderr)
                first = False
                password = getpass.getpass(f"Enter new password for user {username}: ")
                confirm_password = getpass.getpass(f"Confirm new password for user {username}: ")
                if password == confirm_password:
                    break
            else:
                raise CmdExitError(1, "Too many attempts; password not reset")
        hashed = hash_username_password(username, password)
        set_config_yml_property(f"hub.traefik_dashboard_htpasswd", hashed)
        return 0

    def cmd_config_check_traefik_password(self) -> int:
        hashed = get_config_yml_property(f"hub.traefik_dashboard_htpasswd")
        if not ':' in hashed:
            raise HubError(1, "Configured password hash is malformed")
        cfg_username, _ = hashed.split(':', 1)
        username = self._args.username
        username_given = username is not None
        if not username_given:
            username = cfg_username
        password = self._args.password
        if password is None:
            password = getpass.getpass(f"Enter password for user {username}: ")
        if not check_username_password(hashed, username, password):
            if username_given:
                print(f"FAIL: The username and/or the password are incorrect!", file=sys.stderr)
            else:
                print(f"FAIL: The password is incorrect!", file=sys.stderr)
            return 1
        if username_given:
            print(f"SUCCESS: The username and password are correct!", file=sys.stderr)
        else:
            print(f"SUCCESS: The password is correct!", file=sys.stderr)
        return 0

    def cmd_config_set_portainer_initial_password(self) -> int:
        password = self._args.password
        if password is None:
            first = True
            for i in range(5):
                if not first:
                    print("Passwords do not match; try again", file=sys.stderr)
                first = False
                password = getpass.getpass(f"Enter new initial Portainer password for user 'admin': ")
                confirm_password = getpass.getpass(f"Confirm new initial Portainer password for user 'admin': ")
                if password == confirm_password:
                    break
            else:
                raise CmdExitError(1, "Too many attempts; password not reset")
        hashed = hash_password(password)
        set_config_yml_property(f"hub.portainer_initial_password_hash", hashed)
        return 0

    def cmd_config_check_portainer_initial_password(self) -> int:
        hashed = self.get_settings().portainer_initial_password_hash
        if ':' in hashed:
            raise HubError(1, "Configured password hash is malformed")
        password = self._args.password
        if password is None:
            password = getpass.getpass(f"Enter initial Portainer password for user 'admin'': ")
        if not check_password(hashed, password):
            print(f"FAIL: The password is incorrect!", file=sys.stderr)
            return 1
        print(f"SUCCESS: The password is correct!", file=sys.stderr)
        return 0

    def cmd_config_set_portainer_secret(self) -> int:
        secret = self._args.secret
        if secret is None:
            secret = os.urandom(32).hex()
        set_config_yml_property(f"hub.portainer_agent_secret", secret)
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
        nullable = False
        allowed_types: Set[str] = set()
        if "type" in property:
            allowed_types.add(property["type"])
        if "anyOf" in property:
            allowed_types.update(x["type"] for x in property["anyOf"])
        nullable = 'null' in allowed_types
        if nullable:
            allowed_types.remove('null')
        is_dict = isinstance(default_value, dict) or 'object' in allowed_types
        if is_dict:
            if len(property_name_parts) != 2:
                raise ValueError(f"Property name {property_name} is a dict; cannot be set directly")
            if default_value is None:
                default_value = {}
            property_converter = str
        else:
            if len(property_name_parts) != 1:
                raise ValueError(f"Property name {property_name} is not a dict; cannot be dotted")
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
            elif allowed_type == 'array' and 'items' in property and 'type' in property['items'] and property['items']['type'] == 'string':
                property_converter = lambda x: x.split(',')
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

    def cmd_build(self) -> int:
        target: str = self._args.target or "hub"

        if target == 'hub':
            build_hub()
        elif target == 'traefik':
            build_traefik()
        elif target == 'portainer':
            build_portainer()
        else:
            raise ValueError(f"Invalid build target {target}")

        return 0

    def cmd_cloud_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._args.subparser.print_help(sys.stderr)
        return 1

    def cmd_cloud_dns_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._args.subparser.print_help(sys.stderr)
        return 1

    def cmd_cloud_dns_create_name(self) -> int:
        dns_name: str = self._args.dns_name
        dns_target: Optional[str] = self._args.dns_target
        force: bool = self._args.force
        settings = self.get_settings()
        if dns_target is None:
            dns_target = settings.stable_public_dns_name

        if not '.' in dns_name:
            dns_name = f"{dns_name}.{settings.parent_dns_domain}"

        # TODO: Support other DNS providers
        create_route53_dns_name(
            self.get_aws(),
            dns_name,
            dns_target,
            verify_public_ip=False,
            allow_overwrite=force,
          )
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

        public_ip_addr = get_public_ipv4_egress_address()
        gateway_lan_ip_addr = get_gateway_lan_ip4_address()
        lan_ip_addr = get_lan_ipv4_address()
        default_interface = get_default_ipv4_interface()

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
            
    def cmd_traefik_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._args.subparser.print_help(sys.stderr)
        return 1

    def cmd_portainer_bare(self) -> int:
        print("Error: A command is required\n", file=sys.stderr)
        self._args.subparser.print_help(sys.stderr)
        return 1

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
        parser.set_defaults(func=self.cmd_bare, subparser=parser)

        subparsers = parser.add_subparsers(
                            title='Commands',
                            description='Valid commands',
                            help=f'Additional help available with "{PROGNAME} <command-name> -h"')

        # ======================= cloud

        sp = subparsers.add_parser('cloud',
                                description='''Manage DNS and other cloud services.''')
        sp.set_defaults(func=self.cmd_cloud_bare)
        cloud_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help=f'Additional help available with "{PROGNAME} cloud <subcommand-name> -h"')

        # ======================= cloud dns

        sp = cloud_subparsers.add_parser('dns',
                                description='''Manage DNS via Route53 or other cloud services.''')
        sp.set_defaults(func=self.cmd_cloud_dns_bare)
        cloud_dns_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help=f'Additional help available with "{PROGNAME} cloud dns <subcommand-name> -h"')

        # ======================= cloud dns create-name
        sp = cloud_dns_subparsers.add_parser('create-name',
                            help='''Use AWS Route53 or other cloud service to create a new CNAME or A record.
                                    If the record already exists and matches, this command will silently succeed.''')
        sp.add_argument('--force', "-f", action='store_true', default=False,
                            help='Force replacement of the record if it already exists and is not matching.')
        sp.add_argument('--target,', '-t', dest='dns_target',
                            help='''The resolved target value for a 'CNAME' or 'A' DNS record to create. '''
                                 '''If a valid IPV4 address, an 'A' record will be created. Otherwise, '''
                                 '''a 'CNAME' record is created.  If a simple subdomain, f"{value}.{config.parent_dns_domain}" '''
                                 '''will be used. By default, config.stable_public_dns_name is used.''')
        sp.add_argument('dns_name',
                            help='''The DNS name to create. If a simple subdomain, '''
                                 '''f"{value}.{config.parent_dns_domain}" will be used''')
        sp.set_defaults(func=self.cmd_cloud_dns_create_name, subparser=sp)

        # ======================= build

        sp = subparsers.add_parser('build',
                                description='''Build artifacts required to run the hub stacks.''')
        sp.add_argument("--force", "-f", action="store_true",
                            help="Force clean build")
        sp.add_argument("target", nargs='?', default="hub", choices=["hub", "traefik", "portainer"],
                            help="The build target to build. Default: hub")
        sp.set_defaults(func=self.cmd_build, subparser=sp)

        # ======================= config

        sp = subparsers.add_parser('config',
                                description='''Display or set the project configuration.''')
        sp.set_defaults(func=self.cmd_config_bare)
        config_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help=f'Additional help available with "{PROGNAME} config <subcommand-name> -h"')

        # ======================= config get-yml

        sp = config_subparsers.add_parser('get-yml',
                                description='''Get the value of a configuration property as set in config.yml.''')
        sp.add_argument('--raw', "-r", action='store_true', default=False,
                            help='If the value is a string, output it in raw form without encoding as JSON, and without appending a newline. No effect if not a string.')
        sp.add_argument('property_name', default=None, nargs='?',
                            help='''The property name to get; may be dotted to access sub-properties. By default, the entire hub configuration is displayed.''')
        sp.set_defaults(func=self.cmd_config_get_yml, subparser=sp)

        # ======================= config get

        sp = config_subparsers.add_parser('get',
                                description='''Get the resolved value of a configuration property.''')
        sp.add_argument('--raw', "-r", action='store_true', default=False,
                            help='If the value is a string, output it in raw form without encoding as JSON, and without appending a newline. No effect if not a string.')
        sp.add_argument('property_name', default=None, nargs='?',
                            help='''The property name to get; may be dotted to access sub-properties. By default, the entire hub configuration is displayed.''')
        sp.set_defaults(func=self.cmd_config_get, subparser=sp)

        # ======================= config set

        sp = config_subparsers.add_parser('set',
                                description='''Set the value of a configuration property in config.yml.''')
        sp.add_argument('--json', "--j", action='store_true', default=False,
                            help='Interpret the property value as JSON. Allows setting null values.')
        sp.add_argument('property_name',
                            help='''The property name to set; may be dotted to access sub-properties.''')
        sp.add_argument('property_value',
                            help='''The new value for the property. If the property is nullable, "<^null>" will set it to null. To escape this, use "<<^null>".''')
        sp.set_defaults(func=self.cmd_config_set, subparser=sp)

        # ======================= config set-traefik-password

        sp = config_subparsers.add_parser('set-traefik-password',
                                description='''Set the value of property traefik_dashboard_htpasswd in config.yml to a hash of a given username/password.''')
        sp.add_argument('--user', '-u', type=str, dest='username', default='admin',
                            help='''The username to use for logging into the Traefik dashboard. Default: admin''')
        sp.add_argument('password', default=None, nargs='?',
                            help='''The new password. If not provided, you will be prompted for a hidden password.''')
        sp.set_defaults(func=self.cmd_config_set_traefik_password, subparser=sp)

        # ======================= config check-traefik-password

        sp = config_subparsers.add_parser('check-traefik-password',
                                description='''Checks that a given username/password matches the hash in config.traefik_dashboard_htpasswd.''')
        sp.add_argument('--user', '-u', type=str, dest='username', default=None,
                            help='''The username to use for logging into the Traefik dashboard. Default: the username configured in config.traefik_dashboard_htpasswd''')
        sp.add_argument('password', default=None, nargs='?',
                            help='''The password to check. If not provided, you will be prompted for a hidden password.''')
        sp.set_defaults(func=self.cmd_config_check_traefik_password, subparser=sp)

        # ======================= config set-portainer-initial-password

        sp = config_subparsers.add_parser('set-portainer-initial-password',
                                description='''Set the value of property portainer_initial_password_hash in config.yml to a hash of a given password.'''
                                            ''' This is the password that will be used with username 'admin' to log into Portainer for the first time.'''
                                            ''' It is not used after the first time you change the admin password in Portainer.''')
        sp.add_argument('password', default=None, nargs='?',
                            help='''The new password. If not provided, you will be prompted for a hidden password.''')
        sp.set_defaults(func=self.cmd_config_set_portainer_initial_password, subparser=sp)

        # ======================= config check-portainer-initial-password

        sp = config_subparsers.add_parser('check-portainer-initial-password',
                                description='''Checks that a given password matches the hash in config.portainer_initial_password_hash.''')
        sp.add_argument('password', default=None, nargs='?',
                            help='''The password to check. If not provided, you will be prompted for a hidden password.''')
        sp.set_defaults(func=self.cmd_config_check_portainer_initial_password, subparser=sp)

        # ======================= config set-portainer-secret

        sp = config_subparsers.add_parser('set-portainer-secret',
                                description='''Set the value of property portainer_agent_secret in config.yml to a given secret passphrase.''')
        sp.add_argument('secret', default=None, nargs='?',
                            help='''The new secret passphrase. If not provided, a random 64-character hex string will be used.''')
        sp.set_defaults(func=self.cmd_config_set_portainer_secret, subparser=sp)

        # ======================= config schema

        sp = config_subparsers.add_parser('schema',
                                description='''Display the configuration schema in JSON.''')
        sp.set_defaults(func=self.cmd_config_schema, subparser=sp)

        # ======================= install-prereqs

        sp = subparsers.add_parser('install-prereqs',
                                description='''Install system prerequisites for launching the hub.''')
        sp.add_argument("--force", "-f", action="store_true",
                            help="Force clean installation of prerequisites")
        sp.set_defaults(func=self.cmd_install_prereqs, subparser=sp)


        # ======================= traefik

        sp = subparsers.add_parser('traefik',
                                description='''Manage the Traefik reverse-proxy and its stack.''')
        sp.set_defaults(func=self.cmd_traefik_bare, subparser=sp)
        traefik_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help=f'Additional help available with "{PROGNAME} traefik <subcommand-name> -h"')

        # ======================= traefik up

        sp = traefik_subparsers.add_parser('up',
                                description='''Start the Traefik stack.''')
        sp.set_defaults(func=self.cmd_traefik_up, subparser=sp)

        # ======================= traefik down

        sp = traefik_subparsers.add_parser('down',
                                description='''Stop the Traefik stack.''')
        sp.set_defaults(func=self.cmd_traefik_down, subparser=sp)

        # ======================= traefik logs

        sp = traefik_subparsers.add_parser('logs',
                                description='''Display Traefik logs.''')
        sp.add_argument("--follow", "-f", action="store_true",
                            help="Continue monitoring and follow new log messages")
        sp.set_defaults(func=self.cmd_traefik_logs, subparser=sp)

        # ======================= traefik ps

        sp = traefik_subparsers.add_parser('ps',
                                description='''Display list of Traefik docker containers.''')
        sp.set_defaults(func=self.cmd_traefik_ps, subparser=sp)

        # ======================= portainer

        sp = subparsers.add_parser('portainer',
                                description='''Manage Portainer and its stack.''')
        sp.set_defaults(func=self.cmd_portainer_bare, subparser=sp)
        portainer_subparsers = sp.add_subparsers(
                            title='Subcommands',
                            description='Valid subcommands',
                            help=f'Additional help available with "{PROGNAME} portainer <subcommand-name> -h"')
        
        # ======================= portainer up

        sp = portainer_subparsers.add_parser('up',
                                description='''Start the Portainer stack.''')
        sp.set_defaults(func=self.cmd_portainer_up, subparser=sp)

        # ======================= portainer down

        sp = portainer_subparsers.add_parser('down',
                                description='''Stop the Portainer stack.''')
        sp.set_defaults(func=self.cmd_portainer_down, subparser=sp)

        # ======================= portainer logs

        sp = portainer_subparsers.add_parser('logs',
                                description='''Display Portainer logs.''')
        sp.add_argument("--follow", "-f", action="store_true",
                            help="Continue monitoring and follow new log messages")
        sp.set_defaults(func=self.cmd_portainer_logs, subparser=sp)

        # ======================= portainer ps

        sp = portainer_subparsers.add_parser('ps',
                                description='''Display list of Portainer docker containers.''')
        sp.set_defaults(func=self.cmd_portainer_ps, subparser=sp)

        # ======================= up

        sp = subparsers.add_parser('up',
                                description='''Start the hub.''')
        sp.set_defaults(func=self.cmd_up, subparser=sp)

        # ======================= down

        sp = subparsers.add_parser('down',
                                description='''Stop the hub.''')
        sp.set_defaults(func=self.cmd_down, subparser=sp)

        # ======================= ps

        sp = subparsers.add_parser('ps',
                                description='''Display lists of Traefik and Portainer docker containers.''')
        sp.set_defaults(func=self.cmd_ps, subparser=sp)

        # ======================= version

        sp = subparsers.add_parser('version',
                                description='''Display version information.''')
        sp.set_defaults(func=self.cmd_version, subparser=sp)

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
            is_exit_error = isinstance(ex, CmdExitError)
            if is_exit_error:
                rc = ex.exit_code
            else:
                rc = 1
            ex_desc = str(ex)
            ex_classname = ex.__class__.__name__
            if len(ex_desc) == 0:
                print(f"{PROGNAME}: error: {ex_classname}", file=sys.stderr)
            else:
                print(f"{PROGNAME}: error ({ex_classname}): {ex_desc}", file=sys.stderr)
            if traceback:
                raise
        except BaseException as ex:
            print(f"{PROGNAME}: Unhandled exception {ex.__class__.__name__}: {ex}", file=sys.stderr)
            raise

        return rc

def run(argv: Optional[Sequence[str]]=None) -> int:
    rc = CommandHandler(argv).run()
    return rc

# allow running with "python3 -m", or as a standalone script
if __name__ == "__main__":
    sys.exit(run())
