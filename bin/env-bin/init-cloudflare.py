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
import argparse
import json
import logging
import re
import subprocess
import CloudFlare
import yaml
import urllib3
import time
from CloudFlare.exceptions import CloudFlareAPIError

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
    atomic_mv,
    raw_resolve_public_dns,
  )

from tp_hub.internal_types import *


from project_init_tools import get_git_user_email, sudo_check_output_stderr_exception, sudo_call, sudo_check_call, CalledProcessErrorWithStderrMessage
from project_init_tools.util import sudo_check_call_stderr_exception, command_exists

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

api_key_re = re.compile(r"^[a-f0-9]{37}$")
def is_valid_api_key(api_key: str) -> bool:
    return api_key_re.match(api_key) is not None

'''
def cloudflared_login(cf: CloudFlare.CloudFlare, email: str, api_key: str) -> None:

def get_local_tunnels(cf: CloudFlare.CloudFlare) -> List[JsonableDict]:
    pass
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Install prerequisites for this project")

    parser.add_argument( '--loglevel', type=str.lower, default='warning',
                choices=['debug', 'info', 'warning', 'error', 'critical'],
                help='Provide logging level. Default="warning"' )
    parser.add_argument("--force", "-f", action="store_true", help="Force config of all required values, even if already set")

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel.upper())

    force: bool = args.force

    cloudflare_dir = os.path.join(get_project_dir(), ".cloudflare")
    os.makedirs(cloudflare_dir, exist_ok=True, mode=0o700)

    params_file = os.path.join(cloudflare_dir, "params.json")
    if not os.path.exists(params_file):
        old_params_content = "{}"
    else:
        with open(params_file, "r", encoding='utf-8') as f:
            old_params_content = f.read()

    params: JsonableDict = json.loads(old_params_content)
    assert isinstance(params, dict)

    def flush_params() -> None:
        new_params_content = json.dumps(params, indent=2, sort_keys=True)
        if new_params_content != old_params_content:
            tmp_params_file = params_file + ".tmp"
            if os.path.exists(tmp_params_file):
                os.unlink(tmp_params_file)
            try:
                with open(os.open(tmp_params_file, os.O_CREAT | os.O_WRONLY, 0o600), "w", encoding='utf-8') as f:
                    f.write(new_params_content)
                atomic_mv(tmp_params_file, params_file, force=True)
            finally:
                if os.path.exists(tmp_params_file):
                    os.unlink(tmp_params_file)

    email: Optional[str] = params.get("email")

    force_reauth = force
    while True:
        if force_reauth or email is None:
            default_email = email
            if default_email is None:
                try:
                    default_email = get_git_user_email(cwd=get_project_dir())
                except Exception:
                    pass
            while True:
                email = prompt_value(usl(
                    """Please enter the email address associated with your Cloudflare account"""), default=default_email).strip()
                if not is_valid_email_address(email):
                    print("Invalid email address; please try again", file=sys.stderr)
                    continue
                break
            params["email"] = email

        api_key: Optional[str] = params.get("api_key")
        if force_reauth or api_key is None:
            default_api_key = api_key
            while True:
                api_key = prompt_value(usl(
                    """The Cloudflare Global API Key is required to configure Cloudflare. It can be found by navigating
                    to https://dash.cloudflare.com/profile/api-tokens and clicking on "View" next to "Global API Key".
                    Please enter the Global API Key for your Cloudflare account"""), default=default_api_key).strip()
                if not is_valid_api_key(api_key):
                    print("Invalid api_key format; please try again", file=sys.stderr)
                    continue
                break
            params["api_key"] = api_key

        try:
            cf = CloudFlare.CloudFlare(email=email, key=api_key)
            cf.user.get()
            break
        except CloudFlareAPIError as e:
            if e.code == 9103:
                print("Invalid Cloudflare login email address or API key; please try again", file=sys.stderr)
                force_reauth = True
                continue
            else:
                raise

    print(f"Logged in to Cloudflare API successfully with username {email}", file=sys.stderr)
    flush_params()

    zone_infos: List[JsonableDict] = cf.zones.get()
    zones_by_id = { zone["id"]: zone for zone in zone_infos }
    zones_by_name = { zone["name"]: zone for zone in zone_infos }

    zone_id: Optional[str] = params.get("zone_id")
    zone_info: Optional[JsonableDict] = None if zone_id is None else zones_by_id.get(zone_id)
    zone_name: Optional[str] = None if zone_info is None else zone_info["name"]
    if zone_name is None:
        zone_id = None
        zone_info = None
    if force or zone_name is None:
        default_zone_name = zone_name
        if default_zone_name is None and len(zone_infos) > 0:
            default_zone_name = zone_infos[0]["name"]
        if len(zone_infos) == 0:
            print("No DNS zones found in this this Cloudflare account...", file=sys.stderr)
        else:
            print("DNS zones found in this this Cloudflare account:", file=sys.stderr)
            for zone_name in sorted(zones_by_name.keys()):
                print(f"  {zone_name}", file=sys.stderr)
        while True:
            zone_name = prompt_value(usl(
                """Enter the Parent DNS Domain that will be managed by Cloudflare and under which subdomain names
                   will be created for use by the hub. You must have administrative control of the domain. If the
                   name you enter is not already set up on Cloudflare, it will be created for you."""), default=default_zone_name).strip()
            if not is_valid_dns_name(zone_name):
                print("Invalid DNS name; please try again", file=sys.stderr)
                continue
            if not zone_name in zones_by_name:
                should_create = prompt_yes_no(f"DNS zone '{zone_name}' is not currently configured on Cloudflare. Create it now?", default=True)
                if not should_create:
                    continue
                new_zone_info = cf.zones.post(data={ "name": zone_name, "type": "full" })
                zone_infos.append(new_zone_info)
                zones_by_id[new_zone_info["id"]] = new_zone_info
                zones_by_name[new_zone_info["name"]] = new_zone_info
            break
        zone_id = zones_by_name[zone_name]["id"]
    params["zone_id"] = zone_id
    params["zone_name"] = zone_name

    zone_info = zones_by_id[zone_id]
    logger.debug(f"Zone info: {json.dumps(zone_info, indent=2, sort_keys=True)}")
    print(f"Using DNS zone '{zone_name}' with zone ID '{zone_id}'", file=sys.stderr)
    flush_params()

    name_servers: List[str] = zone_info["name_servers"]
    assert len(name_servers) > 0 and all(isinstance(ns, str) for ns in name_servers)
    name_servers = list(name_servers)
    for i, ns in enumerate(name_servers):
        if not ns.endswith('.'):
            name_servers[i] = f"{ns}."
    correct_ns_set = set(name_servers)

    ns_record_info = raw_resolve_public_dns(zone_name, 'NS')
    logger.debug(f"Current name server record info for this zone: {json.dumps(ns_record_info, indent=2, sort_keys=True)}")
    actual_ns_set : Set[str] = set()
    if 'Answer' in ns_record_info:
        answer_list = ns_record_info['Answer']
        assert isinstance(answer_list, list)
        for answer in answer_list:
            assert isinstance(answer, dict)
            if 'data' in answer and answer.get('type') == 2 and answer.get('name') == zone_name+'.':
                actual_ns_set.add(answer['data'])

    if actual_ns_set != correct_ns_set:
        print(f"The name servers for zone {zone_name} are not yet set for the TLD at the registrar, or are set incorrectly. Please set or correct them and restart this script.", file=sys.stderr)
        if (len(actual_ns_set) > 0):
            print("Current name servers:", file=sys.stderr)
            for ns in sorted(actual_ns_set):
                print(f"  {ns}", file=sys.stderr)
        else:
            print("Current name servers:  <None>", file=sys.stderr)
        print("Correct name servers:", file=sys.stderr)
        for ns in sorted(correct_ns_set):
            print(f"  {ns}", file=sys.stderr)
        return 1
    
    print(f"The name servers for zone {zone_name} are set correctly.", file=sys.stderr)

    if not command_exists("cloudflared"):
        print("'cloudflared' package is not installed.  Run install-prereqs, then restart this script...", file=sys.stderr)
        return 1



    try:
        tunnel_infos_content = sudo_check_output_stderr_exception(["cloudflared", "tunnel", "list", "-o", "json"], use_sudo=False).decode('utf-8')
    except CalledProcessErrorWithStderrMessage as e:
        print(f"\n\nLogging cloudflared tool in to Cloudflare. If prompted, please navigate to the requested URL, select {zone_name} ans the zone, and confirm.", file=sys.stderr)
        subprocess.check_call(["cloudflared", "tunnel", "login"])
        tunnel_infos_content = sudo_check_output_stderr_exception(["cloudflared", "tunnel", "list", "-o", "json"], use_sudo=False).decode('utf-8')

    tunnel_infos: List[JsonableDict] = json.loads(tunnel_infos_content)
    logger.debug(f"tunnel_infos: {json.dumps(tunnel_infos, indent=2, sort_keys=True)}")
    tunnels_by_id = { tunnel["id"]: tunnel for tunnel in tunnel_infos }
    tunnels_by_name = { tunnel["name"]: tunnel for tunnel in tunnel_infos }

    if len(tunnel_infos) == 0:
        print("\nNo Cloudflare tunnels currently exist on this host...", file=sys.stderr)
    else:
        print("\nCloudflare tunnels found on this host:", file=sys.stderr)
        print(f"  {'Name':<40}   ID", file=sys.stderr)
        print(f"  {'----------------------------------------':<40}   ------------------------------------", file=sys.stderr)
        for tunnel in tunnel_infos:
            print(f"  {tunnel['name']:<40}   {tunnel['id']}", file=sys.stderr)
    print(file=sys.stderr)

    tunnel_id: Optional[str] = params.get("tunnel_id")
    tunnel_info: Optional[JsonableDict] = None if tunnel_id is None else tunnels_by_id.get(tunnel_id)
    tunnel_name: Optional[str] = None if tunnel_info is None else tunnel_info["name"]
    if force or tunnel_name is None:
        default_tunnel_info = tunnel_info
        if default_tunnel_info is None and len(tunnel_infos) > 0:
            default_tunnel_info = tunnel_infos[0]
        default_tunnel_name = "tphub" if default_tunnel_info is None else default_tunnel_info["name"]
        while True:
            tunnel_name = prompt_value(usl(
                """Enter the name of the Cloudflare tunnel to use for the hub. If the name you enter is
                   not an existing tunnel, a new tunnel will be created for you"""), default=default_tunnel_name).strip()
            if len(tunnel_name) == 0:
                print("Invalid tunnel name format; please try again", file=sys.stderr)
                continue
            if not tunnel_name in tunnels_by_name:
                should_create = prompt_yes_no(f"Tunnel '{tunnel_name}' is not currently configured on Cloudflare. Create it now?", default=True)
                if not should_create:
                    continue
                sudo_check_call_stderr_exception(["cloudflared", "tunnel", "create", tunnel_name], use_sudo=False).decode('utf-8')
                tunnel_infos_content = sudo_check_output_stderr_exception(["cloudflared", "tunnel", "list", "-o", "json"], use_sudo=False).decode('utf-8')
                tunnel_infos = json.loads(tunnel_infos_content)
                tunnels_by_name = { tunnel["name"]: tunnel for tunnel in tunnel_infos }
                tunnels_by_id = { tunnel["id"]: tunnel for tunnel in tunnel_infos }
                tunnel_info = tunnels_by_name[tunnel_name]
                tunnel_id = tunnel_info["id"]
                print(f"Created Cloudflare tunnel '{tunnel_name}' with ID {tunnel_id}", file=sys.stderr)
            break
    tunnel_info = tunnels_by_name[tunnel_name]
    tunnel_id = tunnel_info["id"]
    params["tunnel_id"] = tunnel_id
    params["tunnel_name"] = tunnel_name

    print(f"Using Cloudflare tunnel '{tunnel_name}' with ID '{tunnel_id}'", file=sys.stderr)
    flush_params()

    wildcard_name = f"*.{zone_name}"
    tunnel_cname = f"{tunnel_id}.cfargotunnel.com"

    need_dns_update = True
    dns_records: List[JsonableDict] = cf.zones.dns_records.get(zone_id, params={ "name": wildcard_name, "type": "CNAME" })
    if len(dns_records) > 0:
        assert len(dns_records) == 1
        dns_record = dns_records[0]
        if dns_record['type'] == 'CNAME' and dns_record['name'] == wildcard_name and dns_record['content'] == tunnel_cname and dns_record['proxied'] == True:
            print(f"DNS wildcard record '{wildcard_name}' is already set to proxy to '{tunnel_cname}' on Cloudflare", file=sys.stderr)
            need_dns_update = False

    if need_dns_update:
        print(f"Updating DNS wildcard record '{wildcard_name}' to proxy to '{tunnel_cname}' on Cloudflare", file=sys.stderr)
        cf.zones.dns_records.post(zone_id, data={ "name": wildcard_name, "type": "CNAME", "content": tunnel_cname, "proxied": True })
        print(f"DNS wildcard record '{wildcard_name}' successfully updated to proxy to '{tunnel_cname}' on Cloudflare", file=sys.stderr)

    home_dir = os.path.expanduser("~")
    home_cloudflared_dir = os.path.join(home_dir, ".cloudflared")
    home_cert_pem = os.path.join(home_cloudflared_dir, "cert.pem")
    creds_filename = f"{tunnel_id}.creds.json"
    home_creds_file = os.path.join(home_cloudflared_dir, creds_filename)

    print(f"Updating cloudflared tunnel credentials file {home_creds_file}", file=sys.stderr)
    if os.path.exists(home_creds_file):
        os.unlink(home_creds_file)
    sudo_check_call_stderr_exception(["cloudflared", "tunnel", "token", "--cred-file", home_creds_file, tunnel_id], use_sudo=False)

    etc_cloudflared_dir = "/etc/cloudflared"
    etc_cert_pem = os.path.join(etc_cloudflared_dir, "cert.pem")
    etc_creds_file = os.path.join(etc_cloudflared_dir, creds_filename)

    if not os.path.exists(etc_cloudflared_dir):
        print(f"creating {etc_cloudflared_dir}", file=sys.stderr)
        sudo_check_call_stderr_exception(["mkdir", "-p", etc_cloudflared_dir], use_sudo=True)

    print(f"Copying cloudflared credentials from '{home_cert_pem}' to '{etc_cert_pem}'", file=sys.stderr)
    sudo_check_call_stderr_exception(["rsync", "-rlptD", "--chmod=F600", home_cert_pem, etc_cert_pem], use_sudo=True)

    print(f"Copying cloudflared tunnel credentials from '{home_creds_file}' to '{etc_creds_file}'", file=sys.stderr)
    sudo_check_call_stderr_exception(["rsync", "-rlptD", "--chmod=F600", home_creds_file, etc_creds_file], use_sudo=True)

    expose_ssh = params.get("expose_ssh")
    if force or expose_ssh is None:
        default_expose_ssh = True if expose_ssh is None else expose_ssh
        expose_ssh = prompt_yes_no(usl(
            f"""Do you want to expose SSH via cloudflared SSH tunnel at ssh.{zone_name}?
            ("cloudflared" must be installed on the client, and SSH keys will still be required to connect)"""), default=default_expose_ssh)
        params["expose_ssh"] = expose_ssh
        flush_params()

    expose_traefik = params.get("expose_traefik")
    if force or expose_traefik is None:
        default_expose_traefik = expose_traefik or False
        expose_traefik = prompt_yes_no(usl(
            f"""Do you want to expose the Traefik dashboard on the public Internet at https://traefik.{zone_name}?
            (It will be somewhat protected with HTTP basic authentication)"""), default=default_expose_traefik)
        params["expose_traefik"] = expose_traefik
        flush_params()

    expose_portainer = params.get("expose_portainer")
    if force or expose_portainer is None:
        default_expose_portainer = expose_portainer or False
        expose_portainer = prompt_yes_no(usl(
            f"""Do you want to expose the Portainer web UI on the public Internet at https://portainer.{zone_name}?
            (It will be somewhat protected with Portainer's integrated username/password authentication)"""), default=default_expose_portainer)
        params["expose_portainer"] = expose_portainer
        flush_params()

    etc_config_yml = os.path.join(etc_cloudflared_dir, "config.yml")
    if os.path.exists(etc_config_yml):
        with open(etc_config_yml, "r", encoding='utf-8') as f:
            old_config_yml_content = f.read()
        old_config: JsonableDict = yaml.safe_load(old_config_yml_content)
        assert isinstance(old_config, dict)
        old_config_json_content = json.dumps(old_config, indent=2, sort_keys=True)
    else:
        old_config_json_content = "{}"

    ingress_rules: List[JsonableDict] = []

    if expose_ssh:
        ingress_rules.append({
            "hostname": f"ssh.{zone_name}",
            "service": "ssh://localhost:22",
        })

    ingress_rules.append({
        "hostname": f"tunnel-test.{zone_name}",
        "service": "hello-world",
      })

    
    if expose_traefik:
        ingress_rules.append({
            "hostname": f"traefik.{zone_name}",
            "service": "http://localhost:8080",
          })

    if expose_portainer:
        ingress_rules.append({
            "hostname": f"portainer.{zone_name}",
            "service": "http://localhost:9000",
          })

    ingress_rules.append({
        "hostname": f"*.{zone_name}",
        "service": "http://localhost:7082",
      })

    ingress_rules.append({
        "service": "http_status:404",
      })

    config: JsonableDict = {
        "tunnel": tunnel_id,
        "credentials-file": etc_creds_file,
        "ingress": ingress_rules,
      }
    
    config_json_content = json.dumps(config, indent=2, sort_keys=True)
    if config_json_content != old_config_json_content:
        print(f"Updating {etc_config_yml}", file=sys.stderr)
        tmp_config_yml = os.path.join(home_cloudflared_dir, "config.yml.tmp")
        if os.path.exists(tmp_config_yml):
            os.unlink(tmp_config_yml)
        try:
            with open(os.open(tmp_config_yml, os.O_CREAT | os.O_WRONLY, 0o600), "w", encoding='utf-8') as f:
                f.write(yaml.dump(config))
            sudo_check_call_stderr_exception(["rsync", "-rlptD", "--chmod=F644", tmp_config_yml, etc_config_yml], use_sudo=True)
        finally:
            if os.path.exists(tmp_config_yml):
                os.unlink(tmp_config_yml)
        print(f"Successfully updated {etc_config_yml}", file=sys.stderr)

    if force or not os.path.exists('/etc/systemd/system/cloudflared.service') or not os.path.exists('/etc/systemd/system/cloudflared-update.service'):
        print("Installing cloudflared systemd service", file=sys.stderr)
        sudo_call(["systemctl", "stop", "cloudflared"], use_sudo=True)
        sudo_call(["cloudflared", "service", "uninstall"], use_sudo=True)
        sudo_check_call(["rm", "-f", "/etc/systemd/system/cloudflared.service", "/etc/systemd/system/cloudflared-update.service"], use_sudo=True)

        sudo_check_call_stderr_exception(["cloudflared", "service", "install"], use_sudo=True)
        print("Successfully installed cloudflared systemd service", file=sys.stderr)
    else:
        print("cloudflared systemd service already installed; restarting", file=sys.stderr)
        sudo_check_call_stderr_exception(["systemctl", "restart", "cloudflared"], use_sudo=True)

    print("Waiting for tunnel to stabilize...", file=sys.stderr)
    time.sleep(7.0)

    print("Testing tunnel...", file=sys.stderr)
    test_url = f"https://tunnel-test.{zone_name}"
    response = urllib3.PoolManager().request('GET', test_url)
    if response.status != 200:
        print(f"ERROR: Got HTTP status {response.status} when testing tunnel at {test_url}", file=sys.stderr)
        return 1
    response_content = response.data.decode('utf-8')
    if not "Congrats! You created a tunnel!" in response_content:
        print(f"ERROR: Got unexpected response content when testing tunnel at {test_url}", file=sys.stderr)
        return 1
    print(f"Successfully tested tunnel at {test_url}", file=sys.stderr)


    print("\n============================================================", file=sys.stderr)
    print(f"Cloudflare username: {email}", file=sys.stderr)
    print("Cloudflare API key: <verified>", file=sys.stderr)
    print(f"Cloudflare zone: '{zone_name}', ID='{zone_id}'", file=sys.stderr)
    print(f"Cloudflare tunnel: '{tunnel_name}', ID='{tunnel_id}'", file=sys.stderr)
    print(f"Cloudflare tunnel test URL: https://tunnel-test.{zone_name}", file=sys.stderr)
    if expose_traefik:
        print(f"Traefik dashboard URL: https://traefik.{zone_name}", file=sys.stderr)
    if expose_portainer:
        print(f"Portainer web UI: https://portainer.{zone_name}", file=sys.stderr)
    if expose_ssh:
        print("SSH tunnel client config (install `cloudflared` and add these lines to ~/.ssh/config on client machine):", file=sys.stderr)
        print(f"    Host ssh.{zone_name}", file=sys.stderr)
        print("            ProxyCommand /usr/local/bin/cloudflared access ssh --hostname %h", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print("Cloudflare configuration complete", file=sys.stderr)

    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)