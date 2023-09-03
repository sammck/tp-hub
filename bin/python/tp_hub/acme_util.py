#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Handy Python utilities to read and edit acme.json files used to maintain
Traefik lets-encrypt certificates.
"""

from __future__ import annotations

import os
import subprocess
import json

from .pkg_logging import logger
from .docker_util import read_docker_volume_text_file, write_docker_volume_text_file, list_files_in_docker_volume

from .internal_types import *
from .internal_types import _CMD, _FILE, _ENV

def list_traefik_acme_files() -> List[str]:
    """
    List the acme files in the traefik_acme docker volume.
    """
    acme_files = [
        x for x in list_files_in_docker_volume('traefik_acme')
           if x.endswith('.json') and (x.startswith('acme_') or x.startswith('acme.'))
      ]
    return acme_files


def load_traefik_acme_data(acme_file: str="acme_prod.json") -> JsonableDict:
    """
    Get the acme data from the traefik_acme docker volume.

    Args:
        acme_file: The acme file to read. The default is "acme_prod.json".
    """
    acme_file = os.path.join('/', acme_file)
    assert acme_file.startswith('/')
    acme_file = acme_file[1:]
    acme_content = read_docker_volume_text_file(
        'traefik_acme',
        acme_file,
      )
    acme_data = json.loads(acme_content)
    return acme_data

def save_traefik_acme_data(acme_data: JsonableDict, acme_file: str="acme_prod.json") -> None:
    """
    Save the acme data to the traefik_acme docker volume.

    Args:
        acme_data: The acme data to save.

        acme_file: The acme file to write. The default is "acme_prod.json".
    """
    acme_file = os.path.join('/', acme_file)
    assert acme_file.startswith('/')
    acme_file = acme_file[1:]
    acme_content = json.dumps(acme_data, indent=2, sort_keys=True) + '\n'
    write_docker_volume_text_file(
        'traefik_acme',
        acme_file,
        acme_content,
      )

def get_acme_domain_data(acme_data: JsonableDict, domain: Optional[str]) -> List[Tuple[str, JsonableDict]]:
    """
    Get the acme certificate data records that correspond to a given domain.

    Args:
        acme_data: The acme data to search.

        domain: The domain to search for.

    Returns:
        A list of (resolver_key, certificate_data) tuples.
    """
    if domain is not None and domain.endswith("."):
        domain = domain[:-1]
    result: List[Tuple[str, JsonableDict]] = []
    for resolver_key in sorted(acme_data.keys()):
        resolver_data = acme_data[resolver_key]
        certificates_data = resolver_data.get("Certificates", [])
        for certificate_data in certificates_data:
            # TODO: Handle multi-domain certificates,
            if "domain" in certificate_data and "main" in certificate_data["domain"]:
                cert_main_domain = certificate_data["domain"]["main"]
                if domain is None or cert_main_domain == domain:
                    result.append((resolver_key, certificate_data))
    return result
