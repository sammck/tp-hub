#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Handy Python utilities for docker
"""

from __future__ import annotations

import os
import subprocess

from project_init_tools.util import (
    sudo_Popen,
    sudo_check_output_stderr_exception,
    sudo_check_call_stderr_exception,
    CalledProcessErrorWithStderrMessage,
)

from .pkg_logging import logger

from .internal_types import *
from .internal_types import _CMD, _FILE, _ENV

def docker_volume_exists(volume_name: str) -> bool:
    """
    Check if a docker volume exists.

    Args:
        volume_name: The name of the docker volume.
    """
    args = [
        "docker",
        "volume",
        "inspect",
        volume_name,
      ]
    try:
        sudo_check_output_stderr_exception(
            args,
            use_sudo=False,
            run_with_group='docker',
          )
        return True
    except subprocess.CalledProcessError:
        return False

def verify_docker_volume_exists(volume_name: str) -> None:
    """
    Verify that a docker volume exists.

    Args:
        volume_name: The name of the docker volume.
    """
    if not docker_volume_exists(volume_name):
        raise RuntimeError(f"Docker volume '{volume_name}' does not exist")
        
def list_files_in_docker_volume(volume_name: str, dir_name: str='/', include_dirs:bool=False) -> List[str]:
    """
    List the files in a directory of a docker volume.

    Args:
        volume_name: The name of the docker volume.
        dir_name: The name of the directory relative to the root of the docker volume.
                  any leading slash will be removed. By default, the root of the volume
                  is used.

    """
    verify_docker_volume_exists(volume_name)
    dir_name = os.path.join('/', dir_name)
    assert dir_name.startswith('/')
    if dir_name == '/':
        dir_name = '.'
        abs_dir_name = '/volume'
    else:
        dir_name = dir_name[1:]
        abs_dir_name = f'/volume/{dir_name}'

    args = [
        "docker",
        "run",
        "--rm",
        "--volume",
        f"{volume_name}:/volume",
        "alpine:3.12",
        "find",
        abs_dir_name,
        "-maxdepth",
        "1",
      ]
    if not include_dirs:
        args += [
            "-not",
            "-type",
            "d",
          ]
    result_txt = sudo_check_output_stderr_exception(
        args,
        use_sudo=False,
        run_with_group='docker',
      ).decode('utf-8').rstrip()
    prefixed_result = result_txt.split('\n')
    result: List[str] = []
    for v in prefixed_result:
        if v != abs_dir_name and v != '' and not v.endswith('/'):
            tail = os.path.basename(v)
            result.append(tail)

    return sorted(result)

def remove_docker_volume_file(
        volume_name: str,
        filename: str,
      ) -> None:
    """
    Remove a single file in a docker volume.
    If the file does not exist, no error is raised.

    Args:
        volume_name: The name of the docker volume.

        filename: The name of the file relative to the root of the docker volume.
                  any leading slash will be removed.
    """
    verify_docker_volume_exists(volume_name)
    filename = os.path.join('/', filename)
    assert filename.startswith('/')
    filename = filename[1:]
    sudo_check_call_stderr_exception(
        [
            "docker",
            "run",
            "--rm",
            "--volume",
            f"{volume_name}:/volume",
            "alpine:3.12",
            "rm",
            "-f",
            f"/volume/{filename}",
          ],
        use_sudo=False,
        run_with_group='docker',
      )

def read_docker_volume_text_file(
        volume_name: str,
        filename: str,
        encoding: str = 'utf-8'
      ) -> str:
    """
    Get the contents of a text file in a docker volume.

    Args:
        volume_name: The name of the docker volume.

        filename: The name of the file relative to the root of the docker volume.
                  any leading slash will be removed.
    """
    verify_docker_volume_exists(volume_name)
    filename = os.path.join('/', filename)
    assert filename.startswith('/')
    filename = filename[1:]
    result = sudo_check_output_stderr_exception(
        [
            "docker",
            "run",
            "--rm",
            "--volume",
            f"{volume_name}:/volume",
            "alpine:3.12",
            "cat",
            f"/volume/{filename}",
          ],
        use_sudo=False,
        run_with_group='docker',
      ).decode(encoding)
    return result

def write_docker_volume_text_file(
        volume_name: str,
        filename: str,
        content: str,
        mode: int = 0o640,
        encoding: str = 'utf-8',
      ) -> None:
    """
    Write the contents of a text file in a docker volume.

    Args:
        volume_name: The name of the docker volume.

        filename: The name of the file relative to the root of the docker volume.
                  any leading slash will be removed.

        content: The content to write to the file.

        mode: The mode to use when creating the file.
    """
    verify_docker_volume_exists(volume_name)
    filename = os.path.join('/', filename)
    assert filename.startswith('/')

    args = [
        "docker",
        "run",
        "-i",
        "--rm",
        "--volume",
        f"{volume_name}:/volume",
        "alpine:3.12",
        "sh",
        "-c",
        f"rm -f /volume/{filename}.tmp && touch /volume/{filename}.tmp && chmod {mode:o} /volume/{filename}.tmp && cat >> /volume/{filename}.tmp && mv /volume/{filename}.tmp /volume/{filename} && rm -f /volume/{filename}.tmp",
      ]

    with sudo_Popen(
        args,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        use_sudo=False,
        run_with_group='docker',
      ) as proc:
        _, stderr_data = proc.communicate(content.encode(encoding))
        exit_code = proc.returncode
    if exit_code != 0:
        if encoding is None:
            encoding = 'utf-8'
        stderr_s = stderr_data if isinstance(stderr_data, str) else stderr_data.decode(encoding)
        stderr_s = stderr_s.rstrip()
        raise CalledProcessErrorWithStderrMessage(exit_code, args, stderr=stderr_s)

