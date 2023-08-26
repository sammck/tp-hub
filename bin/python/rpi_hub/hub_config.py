#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Access project and package directories
"""

from __future__ import annotations

import os
import socket
from io import StringIO
from copy import deepcopy
from ruamel.yaml import YAML, MappingNode, ScalarNode, SequenceNode
from functools import cache
from .internal_types import *
from threading import Lock

from .internal_types import *

from .proj_dirs import get_project_dir

YAMLNode = Union[MappingNode, ScalarNode, SequenceNode]

class HubConfig:
  """
  Container for the hub configuration as loaded from base-config.yml and config.yml.
  """

  _project_dir: str
  _base_config_file: str
  _base_config_yaml: MappingNode
  _conf_file: str
  _config_yaml: MappingNode

  _parent_dns_domain: Optional[str] = None
  
  @property
  def parent_dns_domain(self) -> str:
    """
    The registered public DNS domain under which subdomains are created
    as needed for added web services. You must be able to create DNS
    record sets in this domain. If hosted on AWS Route53, tools are
    provided to automate this. Also becomes the default value for
    Traefik and Portainer PARENT_DNS_DOMAIN stack variable.
    REQUIRED.
    """
    if self._parent_dns_domain is None:
      raise HubError("parent_dns_domain is not set in project configuration")
    return self._parent_dns_domain
  
  @parent_dns_domain.setter
  def parent_dns_domain(self, value: str) -> None:
    self._parent_dns_domain = value

  _admin_parent_dns_domain: Optional[str] = None
  
  @property
  def admin_parent_dns_domain(self) -> str:
    """
    The registered public DNS domain under which the "traefik."
    and "portainer." subdomains are created to access the Traefik
    and Portainer web interfaces. You must be able to create DNS
    record sets in this domain. If hosted on AWS Route53, tools are
    provided to automate this. By default, the value of
    parent_dns_domain is used.
    """
    result = self._admin_parent_dns_domain
    if result is None:
      result = self.parent_dns_domain
    return result
  
  @admin_parent_dns_domain.setter
  def admin_parent_dns_domain(self, value: Optional[str]) -> None:
    self._admin_parent_dns_domain = value
  
  _letsencrypt_owner_email: Optional[str] = None

  @property
  def letsencrypt_owner_email(self) -> str:
    """
    The default email address to use for Let's Encrypt registration  to produce
    SSL certificates. If not provided, and this project is a git clone of the
    rpi-hub project, the value from git config user.email is used. Otherwise, REQUIRED.
    """
    if self._letsencrypt_owner_email is None:
      raise HubError("letsencrypt_owner_email is not set in project configuration")
    return self._letsencrypt_owner_email
  
  @letsencrypt_owner_email.setter
  def letsencrypt_owner_email(self, value: str) -> None:
    self._letsencrypt_owner_email = value

  _letsencrypt_owner_email_prod: Optional[str] = None

  @property
  def letsencrypt_owner_email_prod(self) -> str:
    """
    The email address to use for Let's Encrypt registration in the "prod"
    name resolver, which produces trusted certificates for production use.
    If not provided, the value from letsencrypt_owner_email is used.
    """
    result = self._letsencrypt_owner_email_prod
    if result is None:
      result = self.letsencrypt_owner_email
    return result
  
  @letsencrypt_owner_email_prod.setter
  def letsencrypt_owner_email_prod(self, value: Optional[str]) -> None:
    self._letsencrypt_owner_email_prod = value

  _letsencrypt_owner_email_staging: Optional[str] = None

  @property
  def letsencrypt_owner_email_staging(self) -> str:
    """
    The email address to use for Let's Encrypt registration in the "staging"
    name resolver, which produces untrusted certificates for testing purposes.
    If not provided, the value from letsencrypt_owner_email is used.
    """
    result = self._letsencrypt_owner_email_staging
    if result is None:
      result = self.letsencrypt_owner_email
    return result
  
  @letsencrypt_owner_email_staging.setter
  def letsencrypt_owner_email_staging(self, value: Optional[str]) -> None:
    self._letsencrypt_owner_email_staging = value

  _default_cert_resolver: Optional[str] = None

  @property
  def default_cert_resolver(self) -> str:
    """
    The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes. Generally, this should be "prod" for production use (real certs),
    and "staging" for testing purposes (untrusted certs).
    If not provided, "staging" is used.
    """
    result = self._default_cert_resolver
    if result is None:
      result = "staging"
    return result
  
  @default_cert_resolver.setter
  def default_cert_resolver(self, value: Optional[str]) -> None:
    self._default_cert_resolver = value

  _admin_cert_resolver: Optional[str] = None

  @property
  def admin_cert_resolver(self) -> str:
    """
    The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes for the Traefik dashboard and Portainer web interface. By default,
    "prod" is used.
    """
    result = self._admin_cert_resolver
    if result is None:
      result = self.default_cert_resolver
    return result
  
  @admin_cert_resolver.setter
  def admin_cert_resolver(self, value: Optional[str]) -> None:
    self._admin_cert_resolver = value

  _traefik_dashboard_cert_resolver: Optional[str] = None

  @property
  def traefik_dashboard_cert_resolver(self) -> str:
    """
    The name of the Traefik certificate resolver to use for the Traefik dashboard.
    By default, the value of admin_cert_resolver is used.
    """
    result = self._traefik_dashboard_cert_resolver
    if result is None:
      result = self.admin_cert_resolver
    return result
  
  @traefik_dashboard_cert_resolver.setter
  def traefik_dashboard_cert_resolver(self, value: Optional[str]) -> None:
    self._traefik_dashboard_cert_resolver = value

  _portainer_cert_resolver: Optional[str] = None

  @property
  def portainer_cert_resolver(self) -> str:
    """
    The name of the Traefik certificate resolver to use for the Portainer web interface.
    By default, the value of admin_cert_resolver is used.
    """
    result = self._portainer_cert_resolver
    if result is None:
      result = self.admin_cert_resolver
    return result
  
  @portainer_cert_resolver.setter
  def portainer_cert_resolver(self, value: Optional[str]) -> None:
    self._portainer_cert_resolver = value

  _traefik_dashboard_htpasswd: Optional[str] = None

  @property
  def traefik_dashboard_htpasswd(self) -> str:
    """
    The admin username and bcrypt-hashed password to use for HTTP Basic authhentication on
    the Traefik dashboard. The value of this string is of the form "username:hashed_password",
    and can be generated using the `htpasswd -nB admin` or tools included in this project.
    This value is sensitive, and should not be stored in a git repository. Also, a hard-to-guess
    password should be used to defend against a dictionary attack if the hash is ever compromised.
    If not provided, the value of traefik_dashboard_htpasswd is used.
    """
    result = self._traefik_dashboard_htpasswd
    if result is None:
      raise HubError("traefik_dashboard_htpasswd is not set in project configuration")
    return result
  
  @traefik_dashboard_htpasswd.setter
  def traefik_dashboard_htpasswd(self, value: str) -> None:
    self._traefik_dashboard_htpasswd = value

  _portainer_agent_secret: Optional[str] = None

  @property
  def portainer_agent_secret(self) -> str:
    """
    A random string used to secure communication between Portainer and the Portainer
    agent. Typically 32 hex digits.
    REQUIRED (generated and installed in user config by provisioning tools).
    """
    if self._portainer_agent_secret is None:
      raise HubError("portainer_agent_secret is not set in project configuration")
    return self._portainer_agent_secret
  
  @portainer_agent_secret.setter
  def portainer_agent_secret(self, value: str) -> None:
    self._portainer_agent_secret = value

  _stable_public_dns_name: Optional[str] = None

  @property
  def stable_public_dns_name(self) -> str:
    """
    A permanent DNS name (e.g., ddns.mydnsname.com) that has been configured to always
    resolve to the current public IP address of your network's gateway router. Since typical
    residential ISPs may change your public IP address periodically, it is usually necessary to
    involve Dynamic DNS (DDNS) to make this work. Some gateway routers (e.g., eero) have DDNS
    support built-in. Otherwise, you can run a DDNS client agent on any host inside your network,
    and use a DDNS provider such as noip.com.
    Your DDNS provider will provide you with an obscure but unique and stable (as long as you stay
    with the DDNS provider) DNS name for your gateway's public IP address; e.g.,
    "g1234567.eero.online". You should then create a permanent CNAME entry (e.g., ddns.mydnsname.com)
    that points at the obscure DDNS name. That additional level of indirection makes an
    easy-to-remember DNS name for your network's public IP address, and ensures that if your
    provided obscure name ever changes, you will only have to update this one CNAME record to
    be back in business.
    All DNS names created by this project will be CNAME records that point to this DNS name.
    As a convenience, if this value is a sinple subdomain name with no dots, it will be
    automatically prepended to the value of admin_parent_dns_domain to form the full DNS name.
    The default value is "ddns".
    """
    result = self._stable_public_dns_name
    if result is None:
      result = "ddns"
    if not '.' in result:
      result = f"{result}.{self.admin_parent_dns_domain}"
    return result
  
  @stable_public_dns_name.setter
  def stable_public_dns_name(self, value: Optional[str]) -> None:
    self._stable_public_dns_name = value

  _traefik_dashboard_subdomain: Optional[str] = None

  @property
  def traefik_dashboard_subdomain(self) -> str:
    """
    The subdomain under admin_parent_dns_domain to use for the Traefik dashboard.
    The default value is "traefik".
    """
    result = self._traefik_dashboard_subdomain
    if result is None:
      result = "traefik"
    return result
  
  @traefik_dashboard_subdomain.setter
  def traefik_dashboard_subdomain(self, value: Optional[str]) -> None:
    self._traefik_dashboard_subdomain = value

  _portainer_subdomain: Optional[str] = None

  @property
  def portainer_subdomain(self) -> str:
    """
    The subdomain under admin_parent_dns_domain to use for the Portainer web interface.
    The default value is "portainer".
    """
    result = self._portainer_subdomain
    if result is None:
      result = "portainer"
    return result
  
  @portainer_subdomain.setter
  def portainer_subdomain(self, value: Optional[str]) -> None:
    self._portainer_subdomain = value

  _default_app_subdomain: Optional[str] = None

  @property
  def default_app_subdomain(self) -> str:
    """
    A subdomain under parent_dns_domain to use for general-purpose path-routed web services
    created by Portainer. This allows multiple simple services to share a single provisioned
    DNS name and certificate if they can be routed with a traefik Path or PathPrefix rule.
    The default value is "rpi-hub".
    """
    result = self._default_app_subdomain
    if result is None:
      result = "rpi-hub"
    return result
  
  @default_app_subdomain.setter
  def default_app_subdomain(self, value: Optional[str]) -> None:
    self._default_app_subdomain = value

  _app_subdomain_cert_resolver: Optional[str] = None

  @property
  def app_subdomain_cert_resolver(self) -> str:
    """
    The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes using the default app subdomain. Generally, this should be "prod"
    once the default app subdomain route has been validated.
    and "staging" for testing purposes (untrusted certs).
    If not provided, the value of default_cert_resolver is used.
    """
    result = self._app_subdomain_cert_resolver
    if result is None:
      result = self.default_cert_resolver
    return result
  
  @app_subdomain_cert_resolver.setter
  def app_subdomain_cert_resolver(self, value: Optional[str]) -> None:
    self._app_subdomain_cert_resolver = value

  _base_stack_env: Optional[Dict[str, str]] = None

  @property
  def base_stack_env(self) -> Dict[str, str]:
    """
    Environment variables that will be passed to all docker-compose stacks, including
    the Traefik and Portainer stacks, and stacks created by Portainer. Note that
    properties defined here will be installed directly into Portainer's runtime
    environment, and thus will be available for expansion in all docker-compose
    stacks started by Portainer.
    """
    if self._base_stack_env is None:
      self._base_stack_env = {}
    return self._base_stack_env
  
  @base_stack_env.setter
  def base_stack_env(self, value: Optional[Mapping[str, str]]) -> None:
    v = None if value is None else dict(value)
    self._base_stack_env = value
    self._dirty = True

  def update_base_stack_env(self, *args, **kwargs) -> Dict[str, str]:
    new_value = dict(self.base_stack_env)
    new_value.update(*args, **kwargs)
    self.base_stack_env = new_value
    self._dirty = True
    return self.base_stack_env
  
  def set_base_stack_env_var(self, name: str, value: str) -> Dict[str, str]:
    self.update_base_stack_env([(name, value)])

  _traefik_stack_env: Optional[Dict[str, str]] = None

  @property
  def traefik_stack_env(self) -> Dict[str, str]:
    """
    Environment variables that will be passed to the Traefik docker-compose stack.
    Inherits from base_stack_env.
    """
    if self._traefik_stack_env is None:
      self._traefik_stack_env = {}
    return self._traefik_stack_env
  
  @traefik_stack_env.setter
  def traefik_stack_env(self, value: Optional[Mapping[str, str]]) -> None:
    v = None if value is None else dict(value)
    self._traefik_stack_env = value
    self._dirty = True

  def update_traefik_stack_env(self, *args, **kwargs) -> Dict[str, str]:
    new_value = dict(self.traefik_stack_env)
    new_value.update(*args, **kwargs)
    self.traefik_stack_env = new_value
    self._dirty = True
    return self.traefik_stack_env
  
  def set_traefik_stack_env_var(self, name: str, value: str) -> Dict[str, str]:
    self.update_traefik_stack_env([(name, value)])

  _portainer_stack_env: Optional[Dict[str, str]] = None

  @property
  def portainer_stack_env(self) -> Dict[str, str]:
    """
    Environment variables that will be passed to the Portainer docker-compose stack.
    Inherits from base_stack_env.
    """
    if self._portainer_stack_env is None:
      self._portainer_stack_env = {}
    return self._portainer_stack_env
  
  @portainer_stack_env.setter
  def portainer_stack_env(self, value: Optional[Mapping[str, str]]) -> None:
    v = None if value is None else dict(value)
    self._portainer_stack_env = value
    self._dirty = True

  def update_portainer_stack_env(self, *args, **kwargs) -> Dict[str, str]:
    new_value = dict(self.portainer_stack_env)
    new_value.update(*args, **kwargs)
    self.portainer_stack_env = new_value
    self._dirty = True
    return self.portainer_stack_env
  
  def set_portainer_stack_env_var(self, name: str, value: str) -> Dict[str, str]:
    self.update_portainer_stack_env([(name, value)])
  
  _base_app_stack_env: Optional[Dict[str, str]] = None  

  @property
  def base_app_stack_env(self) -> Dict[str, str]:
    """
    Environment variables that should be passed to all app stacks, including
    stacks created by Portainer. Note that properties defined here will be
    installed directly into Portainer's runtime environment, and thus will
    be available for expansion in all docker-compose stacks started by Portainer.
    Inherits from base_stack_env.
    """
    if self._base_app_stack_env is None:
      self._base_app_stack_env = {}
    return self._base_app_stack_env
  
  @base_app_stack_env.setter
  def base_app_stack_env(self, value: Optional[Mapping[str, str]]) -> None:
    v = None if value is None else dict(value)
    self._base_app_stack_env = value
    self._dirty = True

  def update_base_app_stack_env(self, *args, **kwargs) -> Dict[str, str]:
    new_value = dict(self.base_app_stack_env)
    new_value.update(*args, **kwargs)
    self.base_app_stack_env = new_value
    self._dirty = True
    return self.base_app_stack_env
  
  def set_base_app_stack_env_var(self, name: str, value: str) -> Dict[str, str]:
    self.update_base_app_stack_env([(name, value)])

  _portainer_runtime_env: Optional[Dict[str, str]] = None

  @property
  def portainer_runtime_env(self) -> Dict[str, str]:
    """
    # Environment variables that will be installed into Portainer's actual runtime
    # environment, and thus will be available for expansion in all docker-compose stacks
    # started by Portainer.
    # Inherits from base_app_stack_env.
    """
    if self._portainer_runtime_env is None:
      self._portainer_riuntime_env = {}
    return self._portainer_runtime_env
  
  @portainer_stack_env.setter
  def portainer_runtime_env(self, value: Optional[Mapping[str, str]]) -> None:
    v = None if value is None else dict(value)
    self._portainer_runtime_env = value
    self._dirty = True

  def update_portainer_runtime_env(self, *args, **kwargs) -> Dict[str, str]:
    new_value = dict(self.portainer_runtime_env)
    new_value.update(*args, **kwargs)
    self.portainer_runtime_env = new_value
    self._dirty = True
    return self.portainer_runtime_env
  
  def set_portainer_runtime_env_var(self, name: str, value: str) -> Dict[str, str]:
    self.update_portainer_runtime_env([(name, value)])
  
  _dirty: bool = True
  """True if a property has changed and merged views must be recomputed"""

  _realized_base_stack_env: Optional[Dict[str, str]] = None
  _realized_traefik_stack_env: Optional[Dict[str, str]] = None
  _realized_portainer_stack_env: Optional[Dict[str, str]] = None
  _realized_base_app_stack_env: Optional[Dict[str, str]] = None
  _realized_portainer_runtime_env: Optional[Dict[str, str]] = None

  @property
  def realized_base_stack_env(self) -> Dict[str, str]:
    self._rebuild()
    result = self._realized_base_stack_env
    assert result is not None
    return result

  @property
  def realized_traefik_stack_env(self) -> Dict[str, str]:
    self._rebuild()
    result = self._realized_traefik_stack_env
    assert result is not None
    return result

  @property
  def realized_portainer_stack_env(self) -> Dict[str, str]:
    self._rebuild()
    result = self._realized_portainer_stack_env
    assert result is not None
    return result

  @property
  def realized_base_app_stack_env(self) -> Dict[str, str]:
    self._rebuild()
    result = self._realized_base_app_stack_env
    assert result is not None
    return result

  @property
  def realized_portainer_runtime_env(self) -> Dict[str, str]:
    self._rebuild()
    result = self._realized_portainer_runtime_env
    assert result is not None
    return result

  def _merge_env(self, env1: Optional[Mapping[str, str]], env2: Optional[Mapping[str, str]]) -> Dict[str, str]:
    result = {} if env1 is None else dict(env1)
    if env2 is not None:
      result.update(env2)
    return result
  
  def _rebuild(self, force: bool=False) -> None:
    if force or self._dirty:
      default_realized_base_stack_env = dict(
        PARENT_DNS_DOMAIN=self.parent_dns_domain,
      )
      self._realized_base_stack_env = self._merge_env(default_realized_base_stack_env, self.base_stack_env)
      self._realized_traefik_stack_env = self._merge_env(self._realized_base_stack_env, self.traefik_stack_env)
      self._realized_portainer_stack_env = self._merge_env(self._realized_base_stack_env, self.portainer_stack_env)
      self._realized_base_app_stack_env = self._merge_env(self._realized_base_stack_env, self.base_app_stack_env)
      self._realized_portainer_runtime_env = self._merge_env(self._realized_base_app_stack_env, self.portainer_runtime_env)
      self._dirty = False

  scalar_hub_property_names = [
    "parent_dns_domain",
    "admin_parent_dns_domain",
    "letsencrypt_owner_email",
    "letsencrypt_owner_email_prod",
    "letsencrypt_owner_email_staging",
    "default_cert_resolver",
    "admin_cert_resolver",
    "traefik_dashboard_cert_resolver",
    "portainer_cert_resolver",
    "traefik_dashboard_htpasswd",
    "portainer_agent_secret",
    "stable_public_dns_name",
    "traefik_dashboard_subdomain",
    "portainer_subdomain",
    "default_app_subdomain",
    "app_subdomain_cert_resolver",
  ]

  dict_hub_property_names = [
    "base_stack_env",
    "traefik_stack_env",
    "portainer_stack_env",
    "base_app_stack_env",
    "portainer_runtime_env",
  ]

  realized_hub_property_names = dict_hub_property_names

  def get_unrealized_property(self, name: str) -> Any:
    """
    Get a hub property before inheritance has been applied
    """
    if name in self.scalar_hub_property_names or name in self.dict_hub_property_names:
      return getattr(self, name)
    else:
      raise KeyError(f"Unknown hub property: {name}")
    
  def get_property(self, name: str) -> Any:
    """
    Get a hub property after inheritance has been applied
    """
    if name in self.realized_hub_property_names:
      return getattr(self, f"realized_{name}")
    else:
      return self.get_unrealized_property(name)

  def update_property(self, name: str, value: Any) -> None:
    """
    Update from a single name/value
    """
    if name in self.scalar_hub_property_names:
      setattr(self, name, value)
    elif name in self.dict_hub_property_names:
      update_func = getattr(self, f"update_{name}")
      update_func(value)
    else:
      raise KeyError(f"Unknown hub property: {name}")

  def update_from_map(self, map: Mapping[str, Any]) -> None:
    """
    Update the hub configuration from a mapping
    """
    for k, v in map.items():
      self.update_property(k, v)

  def __getitem__(self, name: str) -> Jsonable:
    """
    Get a hub property
    """
    return self.get_property(name)
    
  def __setitem__(self, name: str, value: Any) -> None:
    """
    Set a hub property
    """
    self.update_property(name, value)

  def update_from_yaml(self, data: Any) -> None:
    """
    Update the hub configuration from a YAML config
    """
    if isinstance(data, Mapping) and "hub" in data:
      hub_data: MappingNode = data["hub"]
      self.update_from_map(hub_data)

  def iter_keys(self) -> Iterator[str]:
    """
    Iterate over the keys
    """
    for name in sorted(self.scalar_hub_property_names + self.dict_hub_property_names):
      yield name

  def iter_items(self) -> Iterator[Tuple[str, Jsonable]]:
    """
    Iterate over the items
    """
    for name in self.iter_keys():
      yield (name, self[name])


  def to_dict(self) -> Dict[str, Jsonable]:
    """
    Convert to a dict
    """
    result = {}
    for k, v in self.iter_items():
      if isinstance(v, Mapping):
        v = dict(v)
      result[k] = v
    return result
  
  def yaml_dumps(self, obj: YAMLNode, y: Optional[YAML]=None, **kwargs) -> str:
    """
    Dump to a YAML string
    """
    if y is None:
      y = YAML(typ="rt")
    ss = StringIO()
    try:
      y.dump(obj, ss, **kwargs)
      result = ss.getvalue()
    finally:
      ss.close()
    return result
  
  def yaml_deep_copy(self, v: Any) -> Any:
    return deepcopy(v)

  def yaml_deep_update(self, v1: Any, v2: Any) -> Any:
    if isinstance(v1, Mapping) and isinstance(v2, Mapping):
      result = v1
      for k, v in v2.items():
        if k in result:
          result[k] = self.yaml_deep_update(result[k], v)
        else:
          result[k] = self.yaml_deep_copy(v)
    else:
      result = self.yaml_deep_copy(v2)
    return result

  def yaml_deep_merge(self, v1: Any, v2: Any) -> Any:
    if isinstance(v1, Mapping) and isinstance(v2, Mapping):
      result = self.yaml_deep_update(deepcopy(v1), v2)
    else:
      result = self.yaml_deep_copy(v2)
    return result
  
  def update_yaml_obj_from_this_config(self, obj: MappingNode) -> MappingNode:
    """
    Update a YAML object from this config
    """
    self.yaml_deep_merge(obj, self.to_dict())

  def to_yaml_obj(self, y: Optional[YAML]=None, include_comments: bool=False):
    result = self.yaml_deep_copy(self._base_config_yaml)
    result = self.yaml_deep_update(result, self._config_yaml)
    result = self.yaml_deep_update(result, self.to_dict())
    return result
  
  def to_yaml(self, y: Optional[YAML]=None, include_comments: bool=False) -> str:
    """
    Dump to a YAML string
    """
    obj = self.to_yaml_obj(y=y, include_comments=include_comments)
    return self.yaml_dumps(obj, y=y)

  def __init__(self, project_dir: Optional[str]=None):
    if project_dir is None:
      project_dir = get_project_dir()
    self._project_dir = project_dir

    base_config_file = os.path.join(project_dir, "base-config.yml")
    self._base_config_file = base_config_file
    config_file = os.path.join(project_dir, "config.yml")
    self._config_file = config_file

    y = YAML(typ="rt")
    with open(base_config_file, "r") as f:
      base_config_yaml = y.load(f)
    self._base_config_yaml = base_config_yaml

    with open(config_file, "r") as f:
      config_yaml: MappingNode = y.load(f)
    self._config_yaml = config_yaml

    self.update_from_yaml(base_config_yaml)
    self.update_from_yaml(config_yaml)

    self._rebuild(force=True)


