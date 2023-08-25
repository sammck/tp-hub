#!/usr/bin/env python3

import os
import sys
import re
import dotenv
import argparse
import json
import logging

import functools
import boto3
from boto3 import Session
from botocore.client import BaseClient
from mypy_boto3_route53 import Route53Client
from mypy_boto3_route53.type_defs import HostedZoneTypeDef, ResourceRecordSetTypeDef, ResourceRecordTypeDef
from threading import Lock
from .internal_types import *
from .pkg_logging import logger

from .util import (
    install_docker,
    docker_is_installed,
    install_docker_compose,
    docker_compose_is_installed,
    create_docker_network,
    create_docker_volume,
    should_run_with_group,
    get_public_ip_address,
    get_gateway_lan_ip_address,
    get_lan_ip_address,
    get_default_interface,
    resolve_public_dns,
  )

_ipv4_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

class AwsContext:
    """
    A context for AWS operations within a single AWS session.
    
    AWS service clients are cached for reuse.
    
    This class is thread-safe.
    """
    _lock: Lock
    aws_session: Session
    clients: Dict[str, BaseClient]

    def __init__(self, *, aws_session: Optional[Session]=None, from_aws_client: Optional[BaseClient]=None, **kwargs):
        self._lock = Lock()
        if aws_session is None:
            if from_aws_client is not None and hasattr(from_aws_client, '_internal_aws_context'):
                aws_session: Session = from_aws_client._internal_aws_context.aws_session
            else:
                aws_session = boto3.session.Session(**kwargs)
                aws_session._internal_aws_context = self
        self.aws_session = aws_session
        self.clients = {}

    def client(self, client_name: str) -> BaseClient:
        with self._lock:
            client = self.clients.get(client_name)
            if client is None:
                client = self.aws_session.client(client_name)
                client._internal_aws_context = self
                self.clients[client_name] = client
        return client
    
    @property
    def route53(self) -> Route53Client:
        return cast(Route53Client, self.client('route53'))
    
    def __str__(self) -> str:
        return f"AwsContext({self.aws_session})"

    def __repr__(self) -> str:
        return f"AwsContext({repr(self.aws_session)})"

def get_aws(aws: Optional[AwsContext]=None, aws_session: Optional[Session]=None, aws_client: Optional[BaseClient]=None) -> AwsContext:
    if aws is not None:
        return aws
    if aws_session is not None:
        if hasattr(aws, '_internal_aws_context'):
            aws: AwsContext = aws_session._internal_aws_context
        else:
            aws = AwsContext(aws_session=aws_session)
    elif aws_client is not None and hasattr(aws_client, '_internal_aws_context'):
        aws: AwsContext = aws_client._internal_aws_context
    else:
        aws = AwsContext()
    return aws

def get_all_hosted_zones(aws: AwsContext, starting_name: Optional[str]=None) -> Generator[HostedZoneTypeDef, None, None]:
    route53 = aws.route53

    kwargs: Dict[str, Any] = {}
    if starting_name is not None:
        kwargs.update(DNSName=starting_name)

    while True:
        response = route53.list_hosted_zones_by_name(**kwargs)
        zones = response['HostedZones']
        for zone in zones:
            yield zone
        if not response['IsTruncated']:
            break
        kwargs.update(DNSName=response['NextDNSName'], HostedZoneId=response['NextHostedZoneId'])

def get_hosted_zone_info(
        aws: AwsContext,
        zone_dns_name: str,
        public: bool=True,
      ) -> HostedZoneTypeDef:
    """
    Get information about a hosted zone

    Args:
        zone_dns_name: The DNS name of the hosted zone to get information about
        public: If True, only return public hosted zones. If False, only return
            private hosted zones.

    Returns:
        An AWS response dictionary containing information about the hosted zone
    """
    if not zone_dns_name.endswith("."):
        zone_dns_name += "."
    matched: Optional[HostedZoneTypeDef] = None
    for zone in get_all_hosted_zones(aws, starting_name=zone_dns_name):
        if zone['Name'] == zone_dns_name and zone['Config']['PrivateZone'] == (not public):
            if matched is not None:
                raise HubUtilError(f"Multiple hosted zones found for {zone_dns_name} in current AWS account")
            matched = zone

    if matched is None:
        raise HubUtilError(f"Hosted zone {zone_dns_name} not found in current AWS account")
    
    return matched

def get_hosted_zone_id(
        aws: AwsContext,
        zone_dns_name: str,
        public: bool=True,
      ) -> str:
    zone_info = get_hosted_zone_info(aws, zone_dns_name, public=public)
    return zone_info['Id']

def get_hosted_zone_name(
        aws: AwsContext,
        zone_id: str,
      ) -> str:
    """
    Get the DNS name of a hosted zone

    Args:
        zone_id: The ID of the hosted zone to get the name of

    Returns:
        The DNS name of the hosted zone. The trailing "." is removed.
    """
    route53 = aws.route53
    response = route53.get_hosted_zone(Id=zone_id)
    result = response['HostedZone']['Name']
    if result.endswith("."):
        result = result[:-1]
    return result

def get_all_resource_record_sets(
        aws: AwsContext,
        zone_id: str,
        *,
        start_record_name: Optional[str]=None,
      ) -> Generator[ResourceRecordSetTypeDef, None, None]:
    """
    Get all resource record sets for a hosted zone
    """
    route53 = aws.route53

    kwargs: Dict[str, Any] = dict(HostedZoneId=zone_id)
    if start_record_name is not None:
        kwargs.update(StartRecordName=start_record_name)

    paginator = route53.get_paginator('list_resource_record_sets')
    for page in paginator.paginate(**kwargs):
        # record_sets = cast(List[ResourceRecordSetTypeDef], page['ResourceRecordSets'])
        record_sets = page['ResourceRecordSets']
        for record_set in record_sets:
            yield record_set

def get_resource_record_sets(
        aws: AwsContext,
        zone_id: str,
        record_name: str,
      ) -> List[ResourceRecordSetTypeDef]:
    """
    Get all resource record sets for a specific name in a hosted zone
    The name can be a fully qualified name or a simple subdomain of the hosted zone.
    """
    route53 = aws.route53

    hosted_zone_name = get_hosted_zone_name(aws, zone_id)
    full_hosted_zone_name = f"{hosted_zone_name}."

    if not "." in record_name:
        record_short_name = record_name
        record_parent_name = full_hosted_zone_name
        record_full_name = f"{record_short_name}.{record_parent_name}"
    else:
        record_full_name = record_name
        if not record_full_name.endswith("."):
            record_full_name += "."
        record_short_name, record_parent_name = record_full_name.split(".", 1)
        if record_parent_name != full_hosted_zone_name:
            raise HubUtilError(f"record_name {record_name} is not a simple subdomain of hosted zone {hosted_zone_name}")
    result: List[ResourceRecordSetTypeDef] = []
    for record_set in get_all_resource_record_sets(aws, zone_id, start_record_name=record_full_name):
        if record_set['Name'] != record_full_name:
            break
        result.append(record_set)

    return result

def resource_record_sets_are_equal(rs1: ResourceRecordSetTypeDef, rs2: ResourceRecordSetTypeDef) -> bool:
    """
    Compare two resource record sets for equality
    """
    if rs1['Name'] != rs2['Name']:
        return False
    if rs1['Type'] != rs2['Type']:
        return False
    if rs1['TTL'] != rs2['TTL']:
        return False
    if rs1['ResourceRecords'] != rs2['ResourceRecords']:
        return False
    return True

def delete_route53_dns_name(
        aws: AwsContext,
        dns_name: str,
        *,
        ignore_missing: bool=True,
      ) -> None:
    """
    Create a DNS name on AWS Route53.

    Args:
        dns_name:
            The fully-qualified DNS name to delete (required). Must be a subdomain of
            a hosted zone that is owned by the current AWS account.
        ignore_missing:
            If True, do not raise an exception if the DNS name does not exist.
            Default is True.
    """
    route53 = aws.route53

    if dns_name.endswith("."):
        dns_name = dns_name[:-1]

    full_dns_name = f"{dns_name}."

    if '..' in dns_name:
        raise HubUtilError(f"dns_name {dns_name} must not contain '..'")
    
    if dns_name.startswith("."):
        raise HubUtilError(f"dns_name {dns_name} must not start with '.'")
    
    if len(dns_name.split('.')) < 3:
        raise HubUtilError(f"dns_name {dns_name} must be a subdomain of a registered hosted zone")

    dns_subdomain, dns_zone_name = dns_name.split('.', 1)

    hosted_zone_info = get_hosted_zone_info(aws, dns_zone_name)
    hosted_zone_id = hosted_zone_info['Id']

    record_sets = get_resource_record_sets(aws, hosted_zone_id, dns_name)
    if len(record_sets) == 0:
        if ignore_missing:
            logger.debug(f"DNS name {dns_name} does not exist in hosted zone {dns_zone_name}; ignoring delete request")
            return
        else:
            raise HubUtilError(f"DNS name {dns_name} does not exist in hosted zone {dns_zone_name}--cannot delete")
    
    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch=dict(
            Changes=[
                dict(
                    Action='DELETE',
                    ResourceRecordSet=record_set,
                ) for record_set in record_sets
            ],
        ),
      )
    
    logger.debug(f"DNS name {dns_name} successfully deleted from hosted zone {dns_zone_name}: {response}")


def create_route53_dns_name(
        aws: AwsContext,
        dns_name: str,
        target: str,
        *,
        verify_public_ip: Optional[bool]=None,
        public_ip: Optional[str]=None,
        allow_exists: bool=True,
        allow_overwrite: bool=False,
        ttl: int=300,
      ) -> None:
    """
    Create a DNS name on AWS Route53.

    Args:
        dns_name:
            The fully-qualified DNS name to create (required). Must be a subdomain of
            a hosted zone that is owned by the current AWS account.
        target:
            The target of the DNS name (required). Either an IP address, a fully
            qualified DNS name, or a simple DNS subdomain.
            If an IP address is given, it must be a valid IPv4 address. An A record
            will be created.

            If a simple DNS subdomain (i.e., containing no dots) is given, it will be
            prefixed to the parent domain of dns_name to become fully qualified.
            For example, if dns_name is "foo.bar.com" and target is "baz", the
            resulting DNS name will be "baz.bar.com".

            If a DNS name or simple subdomain is given, the fully qualified name
            must be a valid public DNS name that resolves to a public IP address.
            A CNAME record will be created.
        verify_public_ip:
            Verify that the target's public IP address matches the the ip address given
            in public_ip, or matches this network's public IP address if public_ip is
            None. If None, verifacation will only be done if public_ip is given. Default
            is None.
        public_ip: The public IP address to verify against. If None, and verify_public_ip
            is True, the network's public IP address will be used. Default is None.
        allow_exists:
            If True, do not raise an exception if the DNS name already exists and
            matches the given target. Default is True.
        allow_overwrite:
            If True, overwrite the existing DNS name if it exists and does not match
            the given target. Default is False.
        ttl:
            The time-to-live property of the DNS name (how long clients and DNS servers will
            cache the DNS name's results). Default is 300 seconds (5 minutes).
    """
    route53 = aws.route53

    if target == "" or target == ".":
        raise HubUtilError("target must not be empty")

    if verify_public_ip is None:
        verify_public_ip = public_ip is not None

    if verify_public_ip and public_ip is None:
        public_ip = get_public_ip_address()

    if dns_name.endswith("."):
        dns_name = dns_name[:-1]

    full_dns_name = f"{dns_name}."

    if '..' in dns_name:
        raise HubUtilError(f"dns_name {dns_name} must not contain '..'")
    
    if dns_name.startswith("."):
        raise HubUtilError(f"dns_name {dns_name} must not start with '.'")
    
    if len(dns_name.split('.')) < 3:
        raise HubUtilError(f"dns_name {dns_name} must be a subdomain of a registered hosted zone")

    dns_subdomain, dns_zone_name = dns_name.split('.', 1)

    target_is_ip = _ipv4_re.match(target) is not None

    resolved_ips: List[str]

    if target_is_ip:
        resolved_ips = [ target ]
    else:
        if not '.' in target:
            target = f"{target}.{dns_zone_name}."
        elif not target.endswith("."):
            target = f"{target}."

        if '..' in target:
            raise HubUtilError(f"target {target} must not contain '..'")
        
        if target.startswith("."):
            raise HubUtilError(f"target {target} must not start with '.'")
        
        resolved_ips = resolve_public_dns(target)


    if verify_public_ip:
        if len(resolved_ips) == 0:
            raise HubUtilError(f"Target name {target} could not be resolved to an IP addresses")
        if public_ip not in resolved_ips:
            raise HubUtilError(f"Target name {target} resolves to {resolved_ips}, but required public IP address is {public_ip}")
        if len(resolved_ips) > 1:
            raise HubUtilError(f"Target name {target} resolves to {resolved_ips}, which includes {public_ip}, but multiple IP addresses are not supported")

    new_resource_record: ResourceRecordTypeDef = dict(
        Value=target,
    )

    new_resource_record_set: ResourceRecordSetTypeDef = dict(
        Name=full_dns_name,
        Type='A' if target_is_ip else 'CNAME',
        TTL=ttl,
        ResourceRecords=[ new_resource_record ],
    )
        
    hosted_zone_info = get_hosted_zone_info(aws, dns_zone_name)
    hosted_zone_id = hosted_zone_info['Id']

    record_sets = get_resource_record_sets(aws, hosted_zone_id, dns_name)

    if len(record_sets) > 1:
        raise HubUtilError(f"Multiple resource record sets found for {dns_name} in hosted zone {dns_zone_name}: {record_sets}")
    elif len(record_sets) > 0:
        record_set = record_sets[0]
        if not allow_exists:
            raise HubUtilError(f"Record set for DNS name {dns_name} already exists in zone ID {hosted_zone_id}: {record_set}")
        if resource_record_sets_are_equal(record_set, new_resource_record_set):
            logger.debug(f"DNS name {dns_name} already exists and matches target {target}")
            return
        else:
            if allow_overwrite:
                logger.info(f"DNS name {dns_name} already exists and does not match target {target}; overwriting: {record_set}")
            else:
                raise HubUtilError(f"DNS name {dns_name} already exists, but does not match target {target}: {record_set}")
            
    logger.debug(f"Creating/updating DNS name {dns_name} with target {target} in hosted zone {dns_zone_name}")
    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch=dict(
            Changes=[
                dict(
                    Action='UPSERT',
                    ResourceRecordSet=new_resource_record_set,
                ),
            ],
        ),
      )
    logger.debug(f"DNS name {dns_name} successfully created/updated in hosted zone {dns_zone_name}: {response}")
