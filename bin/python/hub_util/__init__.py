#!/usr/bin/env python3

"""
Package hub_util

Handy Python utilities for this project
"""
import os
import sys
import dotenv
import argparse
import json

from typing import Dict, List

import project_init_tools
from project_init_tools.internal_types import Jsonable, JsonableDict, JsonableList
from project_init_tools.installer.docker import install_docker, docker_is_installed
from project_init_tools.installer.docker_compose import install_docker_compose, docker_compose_is_installed
from project_init_tools.util import (
    sudo_check_call_stderr_exception,
    sudo_check_output_stderr_exception,
    should_run_with_group,
    download_url_text,
)

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
            raise RuntimeError("ndjson Object is not a dictionary")
        key = item.get(key_name)
        if key is None:
            raise RuntimeError(f"ndjson Object is missing key {key_name}")
        if not isinstance(key, str):
            raise RuntimeError(f"ndjson Object key {key_name} is not a string")
        result[key] = item
    return result

def get_public_ip_address() -> str:
    """
    Get the public IP address of this host
    """
    try:
        result = download_url_text("https://api.ipify.org/").strip()
        if result == "":
            raise RuntimeError("https://api.ipify.org returned an empty string")
        return result
    except Exception as e:
        raise RuntimeError("Failed to get public IP address") from e

def docker_call(args: List[str]) -> None:
    """
    Call docker with the given arguments.
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    sudo_check_call_stderr_exception(["docker"] + args, use_sudo=False, run_with_group="docker")

def docker_call_output(args: List[str]) -> str:
    """
    Call docker with the given arguments and return the stdout text
    Automatically uses sudo if login session is not yet in the "docker" group.
    If an error occurs, stderr output is printed and an exception is raised.
    """
    result_bytes: bytes = sudo_check_output_stderr_exception(
        ["docker"] + args, use_sudo=False, run_with_group="docker"
    )
    return result_bytes.decode("utf-8")


def get_docker_networks() -> Dict[str, JsonableDict]:
    """
    Get all docker networks
    """
    data_json = docker_call_output(
        ["network", "ls", "--format", "json"],
      )
    result = ndjson_to_dict(data_json)
    return result

def get_docker_volumes() -> Dict[str, JsonableDict]:
    """
    Get all docker volumes
    """
    data_json = docker_call_output(
        ["volume", "ls", "--format", "json"],
      )
    result = ndjson_to_dict(data_json)
    return result
