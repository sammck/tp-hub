#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Builder tools for traefik
"""

import os
#from envyaml import EnvYAML
import yaml

from ..internal_types import *
from ..pkg_logging import logger
from ..util import rel_symlink, atomic_mv
from ..config import HubSettings, current_hub_settings
from ..proj_dirs import get_project_dir, get_project_build_dir
from ..x_dotenv import x_dotenv_save_file
from ..yaml_template import load_yaml_template_file

def build_traefik(settings: Optional[HubSettings]=None):
    if settings is None:
        settings = current_hub_settings()

    logger.info("Building Traefik")

    project_dir = get_project_dir()
    src_dir = os.path.join(project_dir, "stacks", "traefik")
    build_dir = get_project_build_dir()
    os.makedirs(build_dir, exist_ok=True)
    dst_dir = os.path.join(build_dir, "stacks", "traefik")
    os.makedirs(dst_dir, mode=0o700, exist_ok=True)
    src_compose_pathname = os.path.join(src_dir, "docker-compose.yml")
    dst_compose_pathname = os.path.join(dst_dir, "docker-compose.yml")
    src_env_pathname = os.path.join(src_dir, ".env")
    dst_env_pathname = os.path.join(dst_dir, ".env")
    if not os.path.islink(src_env_pathname):
        rel_symlink(dst_env_pathname, src_env_pathname)
    if os.path.exists(dst_compose_pathname) or os.path.islink(dst_compose_pathname):
        os.unlink(dst_compose_pathname)
    rel_symlink(src_compose_pathname, dst_compose_pathname)
    env = dict(settings.traefik_stack_env)
    x_dotenv_save_file(dst_env_pathname, env, mode=0o400)

    dst_traefik_config_file = os.path.join(dst_dir, "traefik-config.yml")
    dst_traefik_config_tmp_file = dst_traefik_config_file + ".tmp"
    src_traefik_config_file = os.path.join(src_dir, "traefik-config.yml")
    traefik_config_template_file = os.path.join(src_dir, "traefik-config-template.yml")
    traefik_config = load_yaml_template_file(traefik_config_template_file, env=env)
    if os.path.exists(dst_traefik_config_tmp_file):
        os.unlink(dst_traefik_config_tmp_file)
    try:
        with open(os.open(dst_traefik_config_tmp_file, os.O_CREAT | os.O_WRONLY, 0o400), 'w', encoding='utf-8') as f:
            print("# Traefik configuration file", file=f)
            print("#", file=f)
            print("# Auto-generated from traefik-config-template.yml by `hub build`. DO NOT EDIT!", file=f)
            print("#", file=f)
            f.write(yaml.dump(traefik_config, indent=2, sort_keys=True))
        atomic_mv(dst_traefik_config_tmp_file, dst_traefik_config_file, force=True)
    finally:
        if os.path.exists(dst_traefik_config_tmp_file):
            os.unlink(dst_traefik_config_tmp_file)
    if not os.path.islink(src_traefik_config_file):
        rel_symlink(dst_traefik_config_file, src_traefik_config_file)

    dst_traefik_dynamic_config_file = os.path.join(dst_dir, "traefik-dynamic-config.yml")
    dst_traefik_dynamic_config_tmp_file = dst_traefik_dynamic_config_file + ".tmp"
    src_traefik_dynamic_config_file = os.path.join(src_dir, "traefik-dynamic-config.yml")
    traefik_dynamic_config_template_file = os.path.join(src_dir, "traefik-dynamic-config-template.yml")
    traefik_dynamic_config = load_yaml_template_file(traefik_dynamic_config_template_file, env=env)
    if os.path.exists(dst_traefik_dynamic_config_tmp_file):
        os.unlink(dst_traefik_dynamic_config_tmp_file)
    try:
        with open(os.open(dst_traefik_dynamic_config_tmp_file, os.O_CREAT | os.O_WRONLY, 0o400), 'w', encoding='utf-8') as f:
            print("# Traefik dynamic configuration file", file=f)
            print("#", file=f)
            print("# Auto-generated from traefik-dynamic-config-template.yml by `hub build`. DO NOT EDIT!", file=f)
            print("#", file=f)
            f.write(yaml.dump(traefik_dynamic_config, indent=2, sort_keys=True))
        atomic_mv(dst_traefik_dynamic_config_tmp_file, dst_traefik_dynamic_config_file, force=True)
    finally:
        if os.path.exists(dst_traefik_dynamic_config_tmp_file):
            os.unlink(dst_traefik_dynamic_config_tmp_file)
    if not os.path.islink(src_traefik_dynamic_config_file):
        rel_symlink(dst_traefik_dynamic_config_file, src_traefik_dynamic_config_file)

    logger.info("Traefik build complete")
