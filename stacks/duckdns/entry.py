#!/usr/bin/env python3

from typing import Optional

import os
import sys
import argparse
import logging

logger = logging.getLogger("DuckDNS")

class DuckDNSError(Exception):
		pass

def get_public_ip_address() -> IPv4Address:
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


def get_arg_val(args: argparse.Namespace, arg_name: str) -> Optional[str]:
		arg_val = getattr(args, arg_name)
		if arg_val is None or arg_val == "":
				env_var_name = "DUCKDNS_" + arg_name.upper().replace("-", "_")
				arg_val = os.environ.get(env_var_name)
				if arg_val == "":
						arg_val = None
		return arg_val


def serve(
				domain: Optional[str],
				ipv4_domain: Optional[str],
				ipv6_domain: Optional[str],
				token: Optional[str],
				ipv4_token: Optional[str],
				ipv6_token: Optional[str],
			) -> None:
		if ipv6_token is None:
				ipv6_token = token
		if domain is None and ipv4_domain is None and ipv6_domain is None:
				raise DuckDNSError("At least one of --domain, --ipv4-domain, or --ipv6-domain must be given")
		if domain is not None and token is None:
				raise DuckDNSError("--domain requires --token")
		if ipv4_domain is not None and ipv4_token is None:
				raise DuckDNSError("--ipv4-domain requires --token or --ipv4-token")
		if ipv6_domain is not None and ipv6_token is None:
				raise DuckDNSError("--ipv6-domain requires --token or --ipv6-token")
		
		last_ipv4: Optional[str] = None
		last_ipv6: Optional[str] = None


def run() -> int:
		parser = argparse.ArgumentParser("DuckDNS updater"))
		parser.add_argument("--domain", default=None, help="DuckDNS domain name that resolves to either or both A and AAAA records as available. By default, not used. Env var DUCKDNS_DOMAIN is used if --domain is not given")
		parser.add_argument("--ipv4-domain", default=None, help="DuckDNS domain name that is only updated with A records, if available, and cleared if not. By default, not used. Env var DUCKDNS_IPV4_DOMAIN is used if --ipv4-domain is not given")
		parser.add_argument("--ipv6-domain", default=None, help="DuckDNS domain name that is only updated with AAAA records, if available, and cleared if not. By default, not used. Env var DUCKDNS_IPV6_DOMAIN is used if --ipv6-domain is not given")
		parser.add_argument("--token", default=None, help="DuckDNS token that is used to update the dual-stack domain name. required if --domain is given. Env var DUCKDNS_TOKEN is used if --token is not given")
		parser.add_argument("--ipv4-token", required=True, help="DuckDNS token that is used to update the ipv4-only domain name. If not given, --token is used. Env var DUCKDNS_IPV4_TOKEN is used if --ipv4-token is not given")
		parser.add_argument("--ipv6-token", required=True, help="DuckDNS token that is used to update the ipv6-only domain name. If not given, --token is used. Env var DUCKDNS_IPV6_TOKEN is used if --ipv6-token is not given")

		args = parser.parse_args()
		domain = get_arg_val(args, "domain")
		ipv4_domain = get_arg_val(args, "ipv4_domain")
		ipv6_domain = get_arg_val(args, "ipv6_domain")
		token = get_arg_val(args, "token")
		ipv4_token = get_arg_val(args, "ipv4_token")
		if ipv4_token is None:
				ipv4_token = token
		ipv6_token = get_arg_val(args, "ipv6_token")
		
		return 0

		


'''
set -e

if [ -z "$ENV_DOMAIN" ] ; then
    echo "Missing environment variable: ENV_DOMAIN"
	exit 1;
fi
if [ -z "$ENV_TOKEN" ] ; then
    echo "Missing environment variable: ENV_TOKEN"
	exit 1;
fi

current=""
while true; do
	echo ""
	latest=$(curl -s --max-time 60 https://httpbin.org/ip |jq -r .origin?)
	echo "$(date) public ipv4=$latest"
	if [ "$current" == "$latest" ]
	then
		echo "ip not changed"
	else
		echo "ip has changed - updating"
		current=$latest
		echo url="https://www.duckdns.org/update?domains=$ENV_DOMAIN&token=$ENV_TOKEN&ip=" | curl -sk -K -
	fi
	sleep 5m
done
'''

