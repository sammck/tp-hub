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
import ipaddress
import subprocess
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

from .internal_types import *

def normalize_ip_address(addr: IPAddressOrStr) -> IPAddress:
    """
    Normalize an IP address to an IPAddress object

    Raises ValueError if the address cannot be normalized to
    an IPAddress.
    """
    if isinstance(addr, (IPv4Address, IPv6Address)):
        result = addr
    elif isinstance(addr, str):
        if ':' in addr and addr.startswith('[') and addr.endswith(']'):
            # IPv6 address in brackets
            addr = addr[1:-1]
        result = ipaddress.ip_address(addr)
    elif isinstance(addr, int):
        result = ipaddress.ip_address(addr)
    else:
        raise ValueError(f"cannot convert type {type(addr)} to an IPAddress: {addr!r}")
    return result

def normalize_ipv4_address(addr: IPAddressOrStr) -> IPv4Address:
    """
    Normalize an IP address to an IPv4Address object
    """
    result = normalize_ip_address(addr)
    if not isinstance(result, IPv4Address):
        raise ValueError(f"Invalid IP address type {type(result)}; IPv4 required: {result}")
    return result

def normalize_ipv6_address(addr: IPAddressOrStr) -> IPv6Address:
    """
    Normalize an IP address to an IPv6Address object
    """
    result = normalize_ip_address(addr)
    if not isinstance(result, IPv6Address):
        raise ValueError(f"Invalid IP address type {type(result)}; IPv6 required: {result}")
    return result

def is_ip_address(addr: IPAddressOrStr) -> bool:
    """
    Check if a value is a valid IP address
    """
    try:
        normalize_ip_address(addr)
        return True
    except ValueError:
        return False

def is_ipv4_address(addr: IPAddressOrStr) -> bool:
    """
    Check if a value is a valid IPv4 address
    """
    try:
        normalize_ipv4_address(addr)
        return True
    except ValueError:
        return False

def is_ipv6_address(addr: IPAddressOrStr) -> bool:
    """
    Check if a value is a valid IPv6 address
    """
    try:
        normalize_ipv6_address(addr)
        return True
    except ValueError:
        return False
        
@cache
def get_public_ipv4_egress_address() -> IPv4Address:
    """
    Get the outgoing public IP4 address of this host by asking https://api.ipify.org/
    The result is the public IP address that is used for egress to the Internet over the default
    route, after all NATs have been traversed. Typically it is the WAN IPV4 address of your gateway router.
    If you are behind carrier-grade NAT, it will be the selected WAN IPV4 address of the carrier's NAT gateway.
    If you can use direct port-forwarding on your gateway router, this is the address you should use as
    your hub public IP address.
    """
    try:
        result = download_url_text("https://api.ipify.org/").strip()
        if result == "":
            raise HubError("https://api.ipify.org returned an empty string")
        return result
    except Exception as e:
        raise HubError("Failed to get public IPv4 egress address") from e

@cache
def get_public_ipv6_egress_address() -> Optional[str]:
    """
    Get the outgoing public IPv6 address of this host by asking https://api64.ipify.org/
    The result is the public IPv6 address that is used for egress to the Internet over the default
    route, after all NATs have been traversed. Typically (by default in Ubuntu),it is a "temporary"
    randomly generated IPv6 address which changes periodically in accordance with
    RFC 4941 (https://datatracker.ietf.org/doc/html/rfc4941).

    Temporary addresses are unsuitable for use as a hub public IP address, because they change
    too frequently. However, quite often your network adapter will also have a "stable" IPv6 address
    that does not change unless your gateway's IPv6 prefix changes. You should use
    get_stable_public_ipv6_address() to get the stable address.

    Returns None if the host does not have a route to the Internet via IPv6.
    """
    try:
        result = download_url_text("https://api64.ipify.org/").strip()
        if result == "":
            raise HubError("https://api64.ipify.org returned an empty string")
        if not ':' in result:
            # This is an IPv4 address, not IPv6, which means that no IPv6 route to the Internet
            # was found, and it fell back to IPv4
            return None
        return result
    except Exception as e:
        raise HubError("Failed to get public IPv6 egress address") from e

@cache
def get_stable_public_ipv6_address() -> Optional[str]:
    """
    Get the Global IPV6 address of this host that is stable until the Gateway router's IPv6
    prefix changes. If you are using direct IPv6 with firewall ports opened at your gateway,
    This is the address you should use as your hub public IPv6 address.

    By default on Ubuntu, there is no stable global IPv6 address, even if the
    gateway IPv6 prefix never changes. The closest thing is an address marked
    "scope global dynamic mngtmpaddr noprefixroute", which is derived from the mac address
    of the network adapter and a random GUID that is regenerated on every reboot. So
    it changes every time the host reboots. This is not ideal for use as a hub public
    IPv6 address, because it will change every time the host reboots. The DDNS client
    will update the DNS record, but it will take some time for the DNS recoords to time
    out of various DNS caches, so there will be a period of time after every reboot
    when the hub is unreachable.

    The solution is to configure a static global IPv6 address suffix on the host.
    This can be done by setting "IPv6Token=static:<suffix-address>" in the network adapter's
    configuration file. The suffix-address will be appended to the gateway's IPv6 prefix
    to form the host's global IPv6 address. The suffix-address must be unique on the
    network, so it should be a random byte sequence. The DDNS client will update the DNS record
    whenever the Gateway's IPv6 prefix changes, which may happen if the ISP changes the
    prefix, but it will be relatively rare.

    Returns None if no stable global IPv6 address on an interface that has a gateway
    route was found.
    """
    raise NotImplementedError("get_stable_public_ipv6_address() is not yet implemented")

class Ipv4RouteInfo:
    remote_ipv4_addr: IPv4Address
    """The IPv4 address of the remote host"""

    gateway_lan_ipv4_addr: IPv4Address
    """The LAN-local IPv4 address of the gateway router on the route to the remote host"""

    network_interface: str
    """The name of the local network interface that is on the route to remote host"""

    local_lan_ipv4_addr: IPv4Address
    """The LAN-local IPv4 address of this host on the route to the remote host"""

    _ip_route_re = re.compile(r"^(?P<remote_addr>\d+\.\d+\.\d+\.\d+)\s+via\s+(?P<gateway_lan_ipv4_addr>\d+\.\d+\.\d+\.\d+)\s+dev\s+(?P<network_interface>.*[^\s])\s+src\s+(?P<local_lan_ipv4_addr>\d+\.\d+\.\d+\.\d+)\s+uid\s")

    def __init__(self, remote_ipv4_addr: IPv4AddressOrStr):
        """
        Get info about the route to a remote IPv4 address
        
        This is done by parsing the output of the "ip route" command when it describes
        the route to the remote address; e.g.:

                $ ip -o route get 8.8.8.8
                8.8.8.8 via 192.168.0.1 dev eth0 src 192.168.0.245 uid 1000 \    cache 
        """
        
        self.remote_ipv4_addr = normalize_ipv4_address(remote_ipv4_addr)
        response = sudo_check_output_stderr_exception(
            ["ip", "-o", "route", "get", str(self.remote_ipv4_addr)],
            use_sudo=False,
        ).decode("utf-8").split('\n')[0].rstrip()
        match = self._ip_route_re.match(response)
        if match is None:
            raise HubError(f"Failed to parse output of 'ip -o route get {self.remote_ipv4_addr}: '{response}'")
        self.gateway_lan_ipv4_addr = normalize_ipv4_address(match.group("gateway_lan_ipv4_addr"))
        self.network_interface = match.group("network_interface")
        self.local_lan_ipv4_addr = normalize_ipv4_address(match.group("local_lan_ipv4_addr"))


class Ipv6RouteInfo:
    remote_ipv6_addr: IPv6Address
    """The IPv6 address of the remote host"""

    gateway_lan_ipv6_addr: IPv6Address
    """The LAN-local IPv6 address of the gateway router on the route to the remote host"""

    network_interface: str
    """The name of the local network interface that is on the route to remote host"""

    egress_ipv6_addr: IPv6Address
    """IPv6 address of this host on the route to the remote host"""

    ip_route_re = re.compile(r"^(?P<remote_ipv6_addr>[0-9a-f:]+)\s+from\s+(?P<from_ipv6_addr>[0-9a-f:]+)\s+via\s+(?P<gateway_lan_ipv6_addr>[0-9a-f:]+)\s+dev\s+(?P<network_interface>\S+)\s+((proto\s+\S+)\s+)*src\s+(?P<egress_ipv6_addr>[0-9a-f:]+)\s")

    def __init__(self, remote_ipv6_addr: IPv6AddressOrStr):
        """
        Get info about the route to a remote IPv6 address
        
        This is done by parsing the output of the "ip route" command when it describes
        the route to the remote address; e.g.:

                $ ip -o route get 2001:4860:4860::8888
                2001:4860:4860::8888 from :: via fe80::66c2:69ff:fe01:40cb dev eth0 proto ra src 2601:602:9700:2ac5:2546:163c:819f:b48a metric 100 pref medium        """
        
        self.remote_ipv6_addr = normalize_ipv6_address(remote_ipv6_addr)
        response = sudo_check_output_stderr_exception(
            ["ip", "-o", "route", "get", str(self.remote_ipv6_addr)],
            use_sudo=False,
        ).decode("utf-8").split('\n')[0].rstrip()
        match = self._ip_route_re.match(response)
        if match is None:
            raise HubError(f"Failed to parse output of 'ip -o route get {self.remote_ipv4_addr}: '{response}'")
        self.gateway_lan_ipv6_addr = normalize_ipv6_address(match.group("gateway_lan_ipv6_addr"))
        self.network_interface = match.group("network_interface")
        self.egress_ipv6_addr = normalize_ipv4_address(match.group("egress_ipv6_addr"))


@cache
def get_ipv4_route_info(remote_ipv4_addr: IPv4AddressOrStr) -> Ipv4RouteInfo:
    """
    Get info about the route to a remote IP address
    """
    return Ipv4RouteInfo(remote_ipv4_addr)

@cache
def get_internet_ipv4_route_info() -> Ipv4RouteInfo:
    """
    Get info about the IPv4 route to the public internet.

    An arbitrary internet host address (Google's name servers) is used to determine the route.

    """
    return Ipv4RouteInfo("8.8.8.8")

@cache
def get_lan_ipv4_address() -> IPv4Address:
    """
    Get the LAN-local IPv4 address of this host that is on the same subnet with the default gateway
    router. This will be the address that should be used for port-forwarding.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv4_route_info()
    return info.local_lan_ipv4_addr

@cache
def get_gateway_lan_ip4_address() -> IPv4Address:
    """
    Get the LAN-local IPv4 address of the default gateway
    router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv4_route_info()
    return info.gateway_lan_ipv4_addr

@cache
def get_default_ipv4_interface() -> str:
    """
    Get the name of the network interface that is on IPv4 the route to the default gateway router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv4_route_info()
    return info.network_interface

@cache
def get_ipv6_route_info(remote_ipv6_addr: IPv6AddressOrStr) -> Ipv6RouteInfo:
    """
    Get info about the IPv6 route to a remote IP address
    """
    return Ipv6RouteInfo(remote_ipv6_addr)

@cache
def get_internet_ipv6_route_info() -> Ipv6RouteInfo:
    """
    Get info about the IPv6 route to the public internet.

    An arbitrary internet host address (Google's name servers) is used to determine the route.

    """
    return Ipv6RouteInfo("2001:4860:4860::8888")

@cache
def get_routed_egress_ipv6_address() -> str:
    """
    Get the IPv6 address of this host that is on the same subnet with the default gateway
    router. In ubuntu this is normally a temporary address.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv6_route_info()
    return info.egress_ipv6_addr

@cache
def get_gateway_lan_ip6_address() -> str:
    """
    Get the LAN-local IPv^ address of the default gateway
    router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv6_route_info()
    return info.gateway_lan_ipv6_addr

@cache
def get_default_ipv6_interface() -> str:
    """
    Get the name of the network interface that is on the default IPv6 route to the default gateway router.
    """
    # Get info about the route to an arbitrary internet host (Google's DNS servers)
    info = get_internet_ipv4_route_info()
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

def raw_resolve_public_dns(public_dns: str, record_type: Optional[Union[int, str]]=None) -> JsonableDict:
    """
    Resolve a public DNS name to DNS record info. Bypasses all host files, mDNS, intranet DNS servers etc.
    By default fetches A records.
    """
    http = urllib3.PoolManager()
    fields: Dict[str, str] = dict(name=public_dns)
    if record_type is not None:
        fields["type"] = str(record_type)
    response = http.request("GET", "https://dns.google/resolve", fields=fields)
    if response.status != 200:
        raise HubError(f"Failed to resolve public DNS name {public_dns}: {response.status} {response.reason}")
    data: JsonableDict = json.loads(response.data.decode("utf-8"))
    return data

def resolve_public_dns(
        public_dns: str,
        error_on_empty: bool = True,
        allow_ipv6: bool=True,
        allow_ipv4: bool=True
      ) -> List[IPAddress]:
    """
    Resolve a public DNS name to one or more A or AAAA record IP addresses. Bypasses all host files, mDNS, intranet DNS servers etc.
    """
    if not (allow_ipv6 or allow_ipv4):
        raise HubError("resolve_public_dns: allow_ipv6 and allow_ipv4 cannot both be False")
    record_types: List[str] = []
    if allow_ipv6:
        record_types.append("AAAA")
    if allow_ipv4:
        record_types.append("A")
    results: List[str] = []
    for record_type in record_types:
        data = raw_resolve_public_dns(public_dns, record_type=record_type)
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
                    results.append(normalize_ip_address(result))
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

def rel_symlink(src: str, dst: str) -> None:
    """
    Create a relative symbolic link.

    Args:
        src:
            The path to target file that the link will point to

        dst:
            The path to the symlink file that will be created
    """
    abs_symlink_file = os.path.abspath(dst)
    abs_origin_dir = os.path.dirname(abs_symlink_file)
    abs_target = os.path.abspath(src)
    rel_pathname = os.path.relpath(abs_target, abs_origin_dir)
    logger.debug(f"os.symlink src (target)={rel_pathname}, dst (symlink file)={dst}, abs src (target)={abs_target}, abs dst (symlink file)={abs_symlink_file}")

    os.symlink(rel_pathname, dst)

def atomic_mv(source: str, dest: str, force: bool=True) -> None:
    """
    Equivalent to the linux "mv" commandline.  Atomic within same volume, and overwrites the destination.
    Works for directories.
  
    Args:
        source (str): Source file or directory.x
        dest (str): Destination file or directory. Will be overwritten if it exists.
        force (bool): Don't prompt for overwriting. Default is True
  
    Raises:
        RuntimeError: Any error from the mv command
    """
    source = os.path.expanduser(source)
    dest = os.path.expanduser(dest)
    cmd: List[str] = ['mv']
    if force:
        cmd.append('-f')
    cmd.extend([ source, dest ])
    subprocess.check_call(cmd)
