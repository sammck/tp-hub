#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
tools to test port availability and port forwarding
"""

from __future__ import annotations

import os
import re
import time
import socket
import threading
from secrets import token_bytes
from threading import Thread
import urllib3

from .internal_types import *
from .pkg_logging import logger
from .pkg_data import get_pkg_data_dir

hub_test_compose_file = os.path.join(get_pkg_data_dir(), "hub_port_test", "docker-compose.yml")

from .util import (
    docker_compose_call,
    download_url_text,
    get_public_ip_address,
    get_lan_ip_address,
  )

from .docker_compose_stack import DockerComposeStack

_whoami_get_re = re.compile(r"^(?P<verb>GET|POST)\s+(?P<path>.*[^\s])\s+HTTP/(?P<http_version>\d+\.\d+)\s*$")
def parse_whoami_response(response: str) -> Dict[str, Union[str, List[str]]]:
    """Parse the response from a whoami server"""
    result: Dict[str, Union[str, List[str]]] = {}

    for line in response.splitlines():
        if line.strip() == "":
            continue
        m = _whoami_get_re.match(line)
        if m is not None:
            result["http-verb"] = m.group("verb")
            result["http-path"] = m.group("path")
            result["http-version"] = m.group("http_version")
        else:
            if ":" not in line:
                raise HubUtilError(f"Invalid whoami response line (no colon): {line!r}")
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key in result:
                if isinstance(result[key], list):
                    result[key].append(value)
                else:
                    result[key] = [result[key], value]
            else:
                result[key] = value
    return result

def test_whoami_port_connection(
        remote_host: str,
        remote_port: int,
        *,
        expected_hostname: Optional[str]=None,
        stripped_path_prefix: Optional[str]=None,
        connect_timeout: float=5.0,
        read_timeout: float=5.0,
      ):
    """Test whether a whoami server can be reachedat a given host and port"""
    logger.debug(f"test_whoami_port_connection: Testing connection to {remote_host}:{remote_port}")

    if stripped_path_prefix is not None:
        if stripped_path_prefix == "":
            stripped_path_prefix = None
        elif not stripped_path_prefix.startswith("/"):
            stripped_path_prefix = "/" + stripped_path_prefix


    req_timeout = urllib3.Timeout(connect=connect_timeout, read=read_timeout)
    pool_manager = urllib3.PoolManager(timeout=req_timeout)
    random_path = token_bytes(16).hex()

    response = download_url_text(f"http://{remote_host}:{remote_port}/{random_path}", pool_manager=pool_manager)
    headers = parse_whoami_response(response)
    http_path = headers.get("http-path")
    if http_path is None:
        raise HubUtilError(f"test_whoami_port_connection: whoami server did not return an HTTP path")
    if stripped_path_prefix is not None:
        http_path = stripped_path_prefix + http_path
    expected_http_path = f"/{random_path}"
    if http_path != expected_http_path:
        raise HubUtilError(f"test_whoami_port_connection: whoami server returned nonmatching HTTP path (correct is {expected_http_path!r}): {http_path!r}")
    hostname = headers.get("Hostname")
    if hostname is None:
        raise HubUtilError(f"test_whoami_port_connection: whoami server did not return a hostname")
    if expected_hostname is not None and hostname != expected_hostname:
        raise HubUtilError(f"test_whoami_port_connection: whoami server returned nonmatching hostname (correct is {expected_hostname!r}): {hostname!r}")
    logger.debug(f"test_whoami_port_connection: whoami server at {remote_host}: {remote_port} responded correctly")

def test_server_traefik_ports():
    """Test whether all traefik ports are available to listen on and
       in the case of 7080 and 7443, are properly port-forwarded from the gateway router

    Useful for checking port forwarding rules.

    Actually listens on the traefik listener ports, which must not be in use. Traefik must be shut down
    before performing this test.
    """

    logger.debug(f"test_server_traefik_ports: Testing availability and connectivity of all hub ports using temporary whoami stub servers")
    random_hostname_suffix = "-" + token_bytes(16).hex()
    expected_hostname = f"port-test{random_hostname_suffix}"

    lan_ip_address = get_lan_ip_address()
    public_ip_address = get_public_ip_address()

    try:
        with DockerComposeStack(
                compose_file=hub_test_compose_file,
                additional_env=dict(HOSTNAME_SUFFIX=random_hostname_suffix),
                auto_down=True,
            ) as stack:
            time.sleep(4.0)   # let services start up
            for port in [ 80, 443, 7080, 7443, 8080 ]:
                test_whoami_port_connection(lan_ip_address, port, expected_hostname=expected_hostname)
            for port in [ 80, 443 ]:
                test_whoami_port_connection(public_ip_address, port, expected_hostname=expected_hostname)
    except Exception as e:
        logger.debug(f"test_server_traefik_ports: Test failed: {e}")
        raise
    else:
        logger.debug(f"test_server_traefik_ports: Test passed!")
