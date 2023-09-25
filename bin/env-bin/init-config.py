#!/usr/bin/env python3

#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Initialize the config.yml file interactively.
"""

from __future__ import annotations

import os
import sys
import dotenv
import argparse
import json
import logging
import getpass

from tp_hub import (
    Jsonable, JsonableDict, JsonableList,
    get_project_dir,
    logger,
    get_config_yml,
    set_config_yml_property,
    unindent_string_literal as usl,
    hash_username_password,
    hash_password,
    is_valid_email_address,
    is_valid_dns_name,
  )

from tp_hub.internal_types import *

from project_init_tools import get_git_user_email

def prompt_value(prompt: str, default: Optional[str]=None) -> str:
    prompt = prompt.strip()
    if default is None:
        prompt = f"{prompt}: "
    else:
        prompt = f"{prompt} [{default}]: "

    print("", file=sys.stderr)
    while True:
        value = input(prompt)
        if value == "":
            if default is None:
                print("A value is required; please try again")
            else:
                value = default
        return value
    
def prompt_verify_password(prompt: str) -> str:
    prompt = prompt.strip()
    print("", file=sys.stderr)
    while True:
        password = getpass.getpass(prompt=f"{prompt}: ")
        password2 = getpass.getpass(prompt="Please enter again to confirm: ")
        if password != password2:
            print("Passwords do not match; please try again", file=sys.stderr)
        else:
            return password

def prompt_yes_no(prompt: str, default: Optional[bool]=None) -> bool:
    while True:
        answer = prompt_value(prompt, default=None if default is None else ("Y" if default else "N")).lower()
        if answer in [ "y", "yes", "true", "t", "1" ]:
            return True
        elif answer in [ "n", "no", "false", "f", "0" ]:
            return False
        print("Please answer 'y' or 'n'", file=sys.stderr)

def expand_dns_name(name: str, parent_dns_domain: str) -> str:
    if '.' in name:
        return name
    return f"{name}.{parent_dns_domain}"

def shrink_dns_name(name: str, parent_dns_domain: str) -> str:
    if name.endswith(f".{parent_dns_domain}"):
        return name[:-len(f".{parent_dns_domain}")]
    return name

def main() -> int:
    parser = argparse.ArgumentParser(description="Install prerequisites for this project")

    parser.add_argument( '--loglevel', type=str.lower, default='warning',
                choices=['debug', 'info', 'warning', 'error', 'critical'],
                help='Provide logging level. Default="warning"' )
    parser.add_argument("--force", "-f", action="store_true", help="Force config of all required values, even if already set")

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())

    force: bool = args.force

    config_yml = get_config_yml()

    data = config_yml.get("hub", {})

    portainer_agent_secret = data.get("portainer_agent_secret")
    if force or portainer_agent_secret is None or len(portainer_agent_secret) < 16:
        print("Generating new portainer_agent_secret...", file=sys.stderr)
        portainer_agent_secret = os.urandom(32).hex()
        set_config_yml_property("hub.portainer_agent_secret", portainer_agent_secret)

    traefik_password_hash = data.get("traefik_dashboard_htpasswd")
    if force or traefik_password_hash is None:
        need_reset = traefik_password_hash is None or prompt_yes_no(usl(
                """A Traefik dashboard password has already been set...
                   Reset traefik dashboard password?
                """), default=False)
        if need_reset:
            new_password = prompt_verify_password(usl(
                """The Traefik reverse-proxy provides a dashboard Web UI. It
                   will only be exposed on the local LAN, and it will be protected
                   with basic HTTP authenthication using a bcrypt password hash. This
                   is a good, time-consuming hash but a strong password should be selected
                   to defend against dictionary attacks on the hash.
                   Enter a new Traefik dashboard password for user 'admin'"""
              ))
            hashed = hash_username_password('admin', new_password)
            set_config_yml_property(f"hub.traefik_dashboard_htpasswd", hashed)
            print("Traefik dashboard password reset successfully!", file=sys.stderr)

    portainer_password_hash = data.get("portainer_initial_password_hash")
    if force or portainer_password_hash is None:
        need_reset = portainer_password_hash is None or prompt_yes_no(usl(
                """A Portainer initial password has already been set...
                   Reset Portainer initial password?
                """), default=False)
        if need_reset:
            new_password = prompt_verify_password(usl(
                """Portainer provides a rich web UI. It will only be exposed on the local LAN.
                   Nonetheless, Portainer is protected by its own username/hashed-password
                   database. The first time the Portainer web UI is used, the only login account
                   is 'admin', and the password is an initial password that must be configured
                   before Portainer is started for the first time. It is meant to be temporary;
                   it should never be a re-use of a durable password.

                   The first time you log into Portainer, you will log in with username 'admin'
                   and the configured initial password. At that time, you should immediately
                   change the password to a durable hard-to-guess password.
                   After you have changed the password, the initial password is no longer used,
                   unless you wipe Portainer state by recreating the 'portainer_data' volume.

                   Enter a Portainer initial password for user 'admin'"""
              ))
            hashed = hash_password(new_password)
            set_config_yml_property(f"hub.portainer_initial_password_hash", hashed)
            print("Poratiner initial admin password reset successfully!", file=sys.stderr)

    parent_dns_domain = data.get("parent_dns_domain")
    if force or parent_dns_domain is None:
        while True:
            parent_dns_domain = prompt_value(usl(
                """A registered public "parent" DNS domain that you administer is required.
                   The hub will need CNAME records in this domain that resolve to the
                   public IP address of your network, for each HTTPS hostname
                   it serves.
                   Enter a registered parent DNS domain that you control
                """), default=parent_dns_domain)
            if not is_valid_dns_name(parent_dns_domain):
                print("Invalid domain name; please try again", file=sys.stderr)
                continue
            break
        set_config_yml_property("hub.parent_dns_domain", parent_dns_domain)

    admin_parent_dns_domain = data.get("admin_parent_dns_domain")
    if admin_parent_dns_domain is None:
        admin_parent_dns_domain = parent_dns_domain

    stable_public_dns_name = data.get("stable_public_dns_name")
    if force or stable_public_dns_name is None:
        while True:
            stable_public_dns_name = prompt_value(usl(
                 f"""The hub requires a permanent DNS name (e.g., ddns.{admin_parent_dns_domain}) that has been configured to always
                    resolve to the current public IP address of your network's gateway router. Since typical
                    residential ISPs may change your public IP address periodically, it is usually necessary to
                    involve Dynamic DNS (DDNS) to make this work. Some gateway routers (e.g., eero) have DDNS
                    support built-in. Otherwise, you can run a DDNS client agent on any host inside your network,
                    and use a DDNS provider such as noip.com.
                    Your DDNS provider will provide you with an obscure but unique and stable (as long as you stay
                    with the DDNS provider) DNS name for your gateway's public IP address; e.g.,
                    "g1234567.eero.online". You should then create a permanent CNAME entry (e.g., ddns.{admin_parent_dns_domain})
                    that points at the obscure DDNS name. That additional level of indirection makes an
                    easy-to-remember DNS name for your network's public IP address, and ensures that if your
                    provided obscure name ever changes, you will only have to update this one CNAME record to
                    be back in business.
                    All DNS names created by this project will be CNAME records that point to this DNS name.
                    As a convenience, if this value is a sinple subdomain name with no dots, it will be
                    automatically prepended to {admin_parent_dns_domain} to form the full DNS name.
                    The default, recommended value is "ddns".
                    Please enter a permanent DNS name that will forever resolve to your
                    network's public IP address
                """), default=stable_public_dns_name or "ddns")
            if '.' in stable_public_dns_name and not is_valid_dns_name(stable_public_dns_name):
                print("Invalid domain name; please try again", file=sys.stderr)
                continue
            break
        set_config_yml_property("hub.stable_public_dns_name", stable_public_dns_name)

    spdn = expand_dns_name(stable_public_dns_name, admin_parent_dns_domain)
    
    traefik_dns_name = expand_dns_name(data.get("traefik_dashboard_dns_name") or 'traefik', admin_parent_dns_domain)
    portainer_dns_name = expand_dns_name(data.get("portainer_dns_name") or 'portainer', admin_parent_dns_domain)
    shared_app_dns_name = expand_dns_name(data.get("shared_app_dns_name") or 'hub', parent_dns_domain)
    whoami_dns_name = f"whoami.{parent_dns_domain}"

    print("\n============================================================", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print("Local project config in config.yml initialized successfully!", file=sys.stderr)

    if parent_dns_domain == admin_parent_dns_domain:
        print(f"\nNOTE: in addition to the above, you will need to create the following DNS records in domain {parent_dns_domain}", file=sys.stderr)
    else:
        print(f"\nNOTE: in addition to the above, you will need to create the following DNS records in domains {parent_dns_domain} and {admin_parent_dns_domain}", file=sys.stderr)
    alias_dns_names: List[str] = [
        traefik_dns_name,
        portainer_dns_name,
        shared_app_dns_name,
        whoami_dns_name,
    ]
    print(f"    {'CNAME':<10} {spdn:<35} ==> <your-obscure-dynamic-dns-name>", file=sys.stderr)
    for alias_dns_name in alias_dns_names:
        print(f"    {'CNAME':<10} {alias_dns_name:<35} ==> {spdn}", file=sys.stderr)

    print("\nIf you are using AWS route53 and have credentials configured in ~/.aws/credentials, you can use the following commands to create these records:\n", file=sys.stderr)
    print(f"    hub cloud dns create-name --target=<your-obscure-dynamic-dns-name> {shrink_dns_name(spdn, parent_dns_domain)}", file=sys.stderr)
    for alias_dns_name in alias_dns_names:
        print(f"    hub cloud dns create-name {shrink_dns_name(alias_dns_name, parent_dns_domain)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)