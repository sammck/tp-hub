#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Handy Python utilities for this project
"""

from __future__ import annotations

import os
import sys
import dotenv
import json
import re
import urllib3
from functools import cache
import copy

from ruamel.yaml.comments import CommentedMap as YAMLContainer
from tomlkit.container import Container as TOMLContainer

from .internal_types import *
from .internal_types import _CMD, _FILE, _ENV
from .pkg_logging import logger

from project_init_tools.installer.docker import install_docker, docker_is_installed
from project_init_tools.installer.docker_compose import install_docker_compose, docker_compose_is_installed
from project_init_tools.installer.aws_cli import install_aws_cli, aws_cli_is_installed
from project_init_tools.util import (
    sudo_check_call,
    sudo_check_output,
    sudo_check_call_stderr_exception,
    sudo_check_output_stderr_exception,
    should_run_with_group,
    download_url_text,
)

@cache
def get_public_ip_address() -> str:
    """
    Get the public IP address of this host by asking https://api.ipify.org/
    """
    try:
        result = download_url_text("https://api.ipify.org/").strip()
        if result == "":
            raise HubError("https://api.ipify.org returned an empty string")
        return result
    except Exception as e:
        raise HubError("Failed to get public IP address") from e

class IpRouteInfo():
    remote_ip_addr: str
    """The IP address of the remote host"""

    gateway_lan_addr: str
    """The LAN-local IP address of the gateway router on the route to the remote host"""

    network_interface: str
    """The name of the local network interface that is on the route to remote host"""

    local_lan_addr: str
    """The LAN-local IP address of this host on the route to the remote host"""

    _ip_route_re = re.compile(r"^(?P<remote_addr>\d+\.\d+\.\d+\.\d+)\s+via\s+(?P<gateway_lan_addr>\d+\.\d+\.\d+\.\d+)\s+dev\s+(?P<network_interface>.*[^\s])\s+src\s+(?P<local_lan_addr>\d+\.\d+\.\d+\.\d+)\s+uid\s")

    def __init__(self, remote_ip_addr: str):
        """
        Get info about the route to a remote IP address
        
        This is done by parsing the output of the "ip route" command when it describes
        the route to the remote address; e.g.:

                $ ip -o route get 8.8.8.8
                8.8.8.8 via 192.168.0.1 dev eth0 src 192.168.0.245 uid 1000 \    cache 
        """
        
        self.remote_ip_addr = remote_ip_addr
        response = sudo_check_output_stderr_exception(
            ["ip", "-o", "route", "get", remote_ip_addr],
            use_sudo=False,
        ).decode("utf-8").split('\n')[0].rstrip()
        match = self._ip_route_re.match(response)
        if match is None:
            raise HubError(f"Failed to parse output of 'ip -o route get {remote_ip_addr}: '{response}'")
        self.gateway_lan_addr = match.group("gateway_lan_addr")
        self.network_interface = match.group("network_interface")
        self.local_lan_addr = match.group("local_lan_addr")

@cache
def get_route_info(remote_ip_addr: str) -> IpRouteInfo:
    """
    Get info about the route to a remote IP address
    """
    return IpRouteInfo(remote_ip_addr)

@cache
def get_internet_route_info() -> IpRouteInfo:
    """
    Get info about the route to the public internet.

    An arbitrary internet host address (Google's name servers) is used to determine the route.

    """
    return IpRouteInfo("8.8.8.8")

@cache
def get_lan_ip_address() -> str:
    """
    Get the LAN-local IP address of this host that is on the same subnet with the default gateway
    router. This will be the address that should be used for port-forwarding.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_route_info()
    return info.local_lan_addr

@cache
def get_gateway_lan_ip_address() -> str:
    """
    Get the LAN-local IP address of the default gateway
    router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_route_info()
    return info.gateway_lan_addr

@cache
def get_default_interface() -> str:
    """
    Get the name of the network interface that is on the route to the default gateway router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_route_info()
    return info.network_interface

def loads_ndjson(text: str) -> List[JsonableDict]:
    """
    Parse a string containing newline-delimited JSON into a list of objects
    """
    result: List[JsonableDict] = list(json.loads(line) for line in text.split("\n") if line != "")
    assert isinstance(result, list)
    return result

def ndjson_to_dict(text:str, key_name: str="Name") -> Dict[str, JsonableDict]:
    """
    Parse a string containing newline-delimited JSON objects, each with a key property,
    into a dictionary of objects.
    """
    data = loads_ndjson(text)
    result: Dict[str, JsonableDict] = {}
    for item in data:
        if not isinstance(item, dict):
            raise HubError("ndjson Object is not a dictionary")
        key = item.get(key_name)
        if key is None:
            raise HubError(f"ndjson Object is missing key {key_name}")
        if not isinstance(key, str):
            raise HubError(f"ndjson Object key {key_name} is not a string")
        result[key] = item
    return result

def docker_call(
        args: List[str],
        env: Optional[_ENV]=None,
        cwd: Optional[StrOrBytesPath]=None,
        stderr_exception: bool=True,
      ) -> None:
    """
    Call docker with the given arguments.
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    logger.debug(f"docker_call: Running {['docker']+args}, cwd={cwd!r}")
    if stderr_exception:
        sudo_check_call_stderr_exception(
            ["docker"] + args,
            use_sudo=False,
            run_with_group="docker",
            env=env,
            cwd=cwd,
        )
    else:
        sudo_check_call(
            ["docker"] + args,
            use_sudo=False,
            run_with_group="docker",
            env=env,
            cwd=cwd,
        )

def docker_call_output(
        args: List[str],
        env: Optional[_ENV]=None,
        cwd: Optional[StrOrBytesPath]=None,
        stderr_exception: bool=True,
      ) -> str:
    """
    Call docker with the given arguments and return the stdout text
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    logger.debug(f"docker_call_output: Running {['docker']+args}, cwd={cwd!r}")
    result_bytes: bytes
    if stderr_exception:
        result_bytes = cast(bytes, sudo_check_output_stderr_exception(
            ["docker"] + args,
            use_sudo=False,
            run_with_group="docker",
            env=env,
            cwd=cwd,
        ))
    else:
        result_bytes = cast(bytes, sudo_check_output(
            ["docker"] + args,
            use_sudo=False,
            run_with_group="docker",
            env=env,
            cwd=cwd,
        ))
    return result_bytes.decode("utf-8")

@cache
def get_docker_networks() -> Dict[str, JsonableDict]:
    """
    Get all docker networks
    """
    data_json = docker_call_output(
        ["network", "ls", "--format", "json"],
      )
    result = ndjson_to_dict(data_json)
    return result

def refresh_docker_networks() -> None:
    """
    Refresh the cache of docker networks
    """
    get_docker_networks.cache_clear()

def create_docker_network(name: str, driver: str="bridge", allow_existing: bool=True) -> None:
    """
    Create a docker network
    """
    if not (allow_existing and name in get_docker_networks()):
        try:
            docker_call(["network", "create", "--driver", driver, name])
        finally:
            refresh_docker_networks()

@cache
def get_docker_volumes() -> Dict[str, JsonableDict]:
    """
    Get all docker volumes
    """
    data_json = docker_call_output(
        ["volume", "ls", "--format", "json"],
      )
    result = ndjson_to_dict(data_json)
    return result

def refresh_docker_volumes() -> None:
    """
    Refresh the cache of docker volumes
    """
    get_docker_volumes.cache_clear()

def create_docker_volume(name: str, allow_existing: bool=True) -> None:
    """
    Create a docker volume
    """
    if not (allow_existing and name in get_docker_volumes()):
        try:
            docker_call(["volume", "create", name])
        finally:
            refresh_docker_volumes()

def docker_compose_call(
        args: List[str],
        env: Optional[_ENV]=None,
        cwd: Optional[StrOrBytesPath]=None,
        stderr_exception: bool=True,
      ) -> None:
    """
    Call docker-compose with the given arguments.
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    # use the "docker compose" plugin form
    docker_call(
        ["compose"] + args,
        env=env,
        cwd=cwd,
        stderr_exception=stderr_exception,
      )

def docker_compose_call_output(
        args: List[str],
        env: Optional[_ENV]=None,
        cwd: Optional[StrOrBytesPath]=None,
        stderr_exception: bool=True,
      ) -> str:
    """
    Call docker-compose with the given arguments and return the stdout text
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    # use the "docker compose" plugin form
    return docker_call_output(
        ["compose"] + args,
        env=env,
        cwd=cwd,
        stderr_exception=stderr_exception,
      )

def raw_resolve_public_dns(public_dns: str) -> JsonableDict:
    """
    Resolve a public DNS name to an IP address. Bypasses all host files, mDNS, intranet DNS servers etc.
    """
    http = urllib3.PoolManager()
    response = http.request("GET", "https://dns.google/resolve", fields=dict(name=public_dns))
    if response.status != 200:
        raise HubError(f"Failed to resolve public DNS name {public_dns}: {response.status} {response.reason}")
    data: JsonableDict = json.loads(response.data.decode("utf-8"))
    return data

def resolve_public_dns(public_dns: str, error_on_empty: bool = True) -> List[str]:
    """
    Resolve a public DNS name to one or more A record IP addresses. Bypasses all host files, mDNS, intranet DNS servers etc.
    """
    data = raw_resolve_public_dns(public_dns)
    results: List[str] = []
    if not "Status" in data:
        raise HubError(f"Failed to resolve public DNS name {public_dns}: No Status in response")
    if data["Status"] != 3:
        if data["Status"] != 0:
            raise HubError(f"Failed to resolve public DNS name {public_dns}: Status {data['Status']}")
        if not "Answer" in data:
            raise HubError(f"Failed to resolve public DNS name {public_dns}: No Answer in response")
        answers = data["Answer"]
        if not isinstance(answers, list):
            raise HubError(f"Failed to resolve public DNS name {public_dns}: Answer is not a list")
        for answer in answers:
            if not isinstance(answer, dict):
                raise HubError(f"Failed to resolve public DNS name {public_dns}: Answer entry is not a dictionary")
            if not "type" in answer:
                raise HubError(f"Failed to resolve public DNS name {public_dns}: Answer entry is missing type field")
            if answer["type"] == 1:
                if not "data" in answer:
                    raise HubError(f"Failed to resolve public DNS name {public_dns}: Answer entry is missing data field")
                result = answer["data"]
                if not isinstance(result, str):
                    raise HubError(f"Failed to resolve public DNS name {public_dns}: Answer entry data field is not a string")
                results.append(result)
    if len(results) == 0 and error_on_empty:
        raise HubError(f"Failed to resolve public DNS name {public_dns}: No A records found")
    return results

def unindent_text(
        text: str,
        reindent: int=0,
        strip_trailing_whitespace: bool=True,
        disregard_first_line: bool=False,
    ) -> str:
    """
    Remove common indentation from a multi-line string.

    Args:
        text:
            The text to unindent
        reindent:
            The number of spaces to indent each line after unindenting
        strip_trailing_whitespace:
            If True, strip trailing whitespace from each line after unindenting
        disregard_first_line:
            If True, do not unindent or reindent the first line of text, and do not include it
            when calculating the minimum indent of the remaining lines. Useful when normalizing
            multiline Python string literals.
    """
    lines = text.split("\n")
    if len(lines) == 0:
        ## this should never happen; even an empty string should have one line after splitting
        return ""
    min_indent = sys.maxsize
    for i, line in enumerate(lines):
        if i > 0 or not disregard_first_line:
            line_tail = line.lstrip()
            if len(line_tail) == 0:
                # ignore blank lines
                continue
            indent = len(line) - len(line_tail)
            if indent < min_indent:
                min_indent = indent
    if strip_trailing_whitespace or reindent > 0 or min_indent > 0:
        for i, line in enumerate(lines):
            if i > 0 or not disregard_first_line:
                if len(line) > min_indent:
                    lines[i] = line[min_indent:]
                else:
                    lines[i] = ""
            if strip_trailing_whitespace:
                lines[i] = lines[i].rstrip()
            if (i > 0 or not disregard_first_line) and (reindent > 0 and len(lines[i]) > 0):
                lines[i] = " " * reindent + lines[i]
    return "\n".join(lines)

def unindent_string_literal(
        text: str,
        reindent: int=0,
        strip_trailing_whitespace: bool=True,
        disregard_first_line: bool=True,
    ) -> str:
    """
    Remove common indentation from a multi-line string.

    Args:
        text:
            The text to unindent
        reindent:
            The number of spaces to indent each line after unindenting
        strip_trailing_whitespace:
            If True, strip trailing whitespace from each line after unindenting
        disregard_first_line:
            If True, do not unindent or reindent the first line of text, and do not include it
            when calculating the minimum indent of the remaining lines. Useful when normalizing
            multiline Python string literals.
    """
    return unindent_text(
        text,
        reindent=reindent,
        strip_trailing_whitespace=strip_trailing_whitespace,
        disregard_first_line=disregard_first_line,
      )

# A DNS name part can be 1 to 63 characters long, and can contain only letters, digits, and hyphens.
# It must not start or end with a hyphen.
_valid_dns_name_part_re = re.compile("^(?!-)[a-zA-Z\d-]{1,63}(?<!-)$")
def is_valid_dns_name(dns_name: str) -> bool:
    """
    Check if a string is a valid DNS name. The name does not need to exist.
    """
    dns_name = dns_name.lower()
    if not (3 <= len(dns_name) <= 255):
        # Maximum total length of a dns name is 255.
        return False
    if dns_name[-1] == ".":
        # Fully qualified DNS names may end in '.' to indicate they are fully
        # qualified. Strip the trailing '.' before validating.
        dns_name = dns_name[:-1]
    parts = dns_name.split(".")
    if len(parts) < 2:
        # A DNS name must have at least two parts, since the TLD is never used
        # alone.
        return False
    if not all(_valid_dns_name_part_re.match(x) for x in parts):
        # Each part must be 1-63 characters long, contain only letters, digits, and hyphens,
        # and must not start or end with a hyphen.
        return False
    # The last part must be a TLD, which is never numeric. This test excludes IPV4
    # addresses from being considered valid DNS names.
    if all(x.isdigit() for x in parts[-1]):
        return False
    return True

_valid_ipv4_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
def is_valid_ipv4_address(name: str) -> bool:
    """
    Check if a string is a valid IPV4 address. The address does not need to exist.
    """
    if not _valid_ipv4_re.match(name):
        return False
    if not all(0 <= int(x) <= 255 for x in name.split(".")):
        return False
    return True

def is_valid_dns_name_or_ipv4_address(name: str) -> bool:
    """
    Check if a string is a valid DNS name or IPV4 address. The name/address does not need to exist.
    """
    return is_valid_ipv4_address(name) or is_valid_dns_name(name)


_valid_email_username_re = re.compile(r"([-!#-'*+/-9=?A-Z^-~]+(\.[-!#-'*+/-9=?A-Z^-~]+)*|\"([]!#-[^-~ \t]|(\\[\t -~]))+\")")
def is_valid_email_address(name: str) -> bool:
    """
    Check if a string is a valid email address. The address does not need to exist.
    """
    parts = name.rsplit("@", 1)
    if len(parts) != 2:
        return False
    if not is_valid_dns_name(parts[1]):
        return False
    if not _valid_email_username_re.match(parts[0]):
        return False
    return True