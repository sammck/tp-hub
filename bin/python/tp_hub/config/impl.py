#
# Copyright (c) 2023 Samuel J. McKelvie
#
# MIT License - See LICENSE file accompanying this package.
#

"""
Config file support
"""

import sys
import yaml
import os
from copy import deepcopy

from pydantic import (
    # AliasChoices,
    # AmqpDsn,
    BaseModel,
    Field,
    # ImportString,
)

from pydantic.fields import FieldInfo

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
  )

from ..internal_types import *
from ..proj_dirs import get_project_dir
from ..util import unindent_string_literal as usl
from ..version import __version__ as pkg_version

class YAMLConfigSettingsSource(PydanticBaseSettingsSource):
    """
    A settings source class that loads variables from a config.yml file
    """

    config_file: str
    cached_jsonable: Optional[JsonableDict] = None

    def __init__(
            self,
            settings_cls: type[BaseSettings],
            config_file: str = 'config.yml'
          ):
        self.config_file = config_file
        super().__init__(settings_cls)

    def get_jsonable(self) -> JsonableDict:
        if self.cached_jsonable is None:
            project_dir = get_project_dir()
            file_path = os.path.join(project_dir, self.config_file)
            if os.path.exists(file_path):
                encoding = self.config.get('env_file_encoding')
                with open(file_path, 'r', encoding=encoding) as f:
                    parent_jsonable = yaml.safe_load(f)
                    if not isinstance(parent_jsonable, dict):
                        raise TypeError(
                            f"YAML config file {file_path} must contain a dictionary"
                        )
                    if 'hub' in parent_jsonable and isinstance(parent_jsonable['hub'], dict):
                        self.cached_jsonable = parent_jsonable['hub']
                    else:
                        print(f"WARNING: YAML config file {file_path} does not contain a 'hub' section", file=sys.stderr)
                        self.cached_jsonable = {}
            else:
                self.cached_jsonable = {}
        return self.cached_jsonable

    # @override
    def get_field_value(
            self,
            field: FieldInfo,
            field_name: str
          ) -> Tuple[Any, str, bool]:
        """
        Gets the value, the key for model creation, and a flag to determine whether value is complex.

        This is an abstract method that should be overridden in every settings source classes.

        Args:
            field: The field.
            field_name: The field name.

        Returns:
            A tuple contains the key, value and a flag to determine whether value is complex.
        """
        jsonable = self.get_jsonable()
        field_value = jsonable.get(field_name)
        return field_value, field_name, False

    # @override
    def prepare_field_value(
            self,
            field_name: str,
            field: FieldInfo,
            value: Any,
            value_is_complex: bool
          ) -> Any:
        """
        Prepares the value of a field.

        Args:
            field_name: The field name.
            field: The field.
            value: The value of the field that has to be prepared.
            value_is_complex: A flag to determine whether value is complex.

        Returns:
            The prepared value.
        """
        return value

    def __call__(self) -> Dict[str, Any]:
        """Return a deep dictionary of settings initializer values from this source"""

        d: Dict[str, Any] = deepcopy(self.get_jsonable())

        #d: Dict[str, Any] = {}
        # for field_name, field in self.settings_cls.model_fields.items():
        #     field_value, field_key, value_is_complex = self.get_field_value(
        #         field, field_name
        #     )
        #     field_value = self.prepare_field_value(
        #         field_name, field, field_value, value_is_complex
        #     )
        #     if field_value is not None:
        #         d[field_key] = field_value

        return d


class EnvVarsModel(BaseModel):
    """A model for a collection of environment variable key/value pairsthat can be passed to
       docker-compose stacks, etc.
    """
    model_config = SettingsConfigDict(
        extra='allow'
    )


class HubSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding='utf-8',
        env_prefix='tp_hub_',
        env_nested_delimiter='__',
      )

    # @override
    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
          ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Return the settings sources in order from highest precendence to lowest.

        Each returned source, when later called, will return a deep, possibly incomplete dictionary of key/value pairs that will be
        used to populate the settings model.

        Later, an empty aggregate dict will be created, and then the sources will be called in order from lowest to highest priority
        (the opposite of the order returned by this function), and the values from each source are deeply merged into (i.e., override) the
        running aggregate dict

        The arguments after settings_cls are the traditional, default sources that would be used if there were
        no override. Subclasses that override this method should not change the function signature, but can
        override the default sources by returning a different tuple of sources.

        Args:
            settings_cls: The Settings class.
            init_settings: The `InitSettingsSource` instance.
            env_settings: The `EnvSettingsSource` instance.
            dotenv_settings: The `DotEnvSettingsSource` instance.
            file_secret_settings: The `SecretsSettingsSource` instance.

        Returns:
            A tuple containing the sources in order from highest to lowest precedence.
            The default implementation returns the following tuple:
                    (init_settings, env_settings, dotenv_settings, file_secret_settings)
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YAMLConfigSettingsSource(settings_cls),
        )

    
    hub_package_version: str = Field(default=pkg_version, description=usl(
        """The Hub package version for which the configuration was authored.
          If not provided, the current package version is used."""
      ))
    """The Hub package version for which the configuration was authored.
       If not provided, the current package version is used."""

    parent_dns_domain: str = Field(description=usl(
        """The registered public DNS domain under which subdomains are created
        as needed for added web services. You must be able to create DNS
        record sets in this domain. If hosted on AWS Route53, tools are
        provided to automate this. Also becomes the default value for
        Traefik and Portainer PARENT_DNS_DOMAIN stack variable.
        REQUIRED."""
      ))
    """The registered public DNS domain under which subdomains are created
    as needed for added web services. You must be able to create DNS
    record sets in this domain. If hosted on AWS Route53, tools are
    provided to automate this. Also becomes the default value for
    Traefik and Portainer PARENT_DNS_DOMAIN stack variable.
    REQUIRED."""

    admin_parent_dns_domain: Optional[str] = Field(default=None, description=usl(
        """The registered public DNS domain under which the "traefik."
        and "portainer." subdomains are created to access the Traefik
        and Portainer web interfaces. You must be able to create DNS
        record sets in this domain. If hosted on AWS Route53, tools are
        provided to automate this. By default, the value of
        parent_dns_domain is used."""
      ))
    """The registered public DNS domain under which the "traefik."
    and "portainer." subdomains are created to access the Traefik
    and Portainer web interfaces. You must be able to create DNS
    record sets in this domain. If hosted on AWS Route53, tools are
    provided to automate this. By default, the value of
    parent_dns_domain is used."""

    letsencrypt_owner_email: Optional[str] = Field(default=None, description=usl(
        """The default email address to use for Let's Encrypt registration  to produce
        SSL certificates. If not provided, and this project is a git clone of the
        rpi-hub project, the value from git config user.email is used. Otherwise, REQUIRED."""
      ))
    """The default email address to use for Let's Encrypt registration  to produce
    SSL certificates. If not provided, and this project is a git clone of the
    rpi-hub project, the value from git config user.email is used. Otherwise, REQUIRED."""

    letsencrypt_owner_email_prod: Optional[str] = Field(default=None, description=usl(
        """The email address to use for Let's Encrypt registration in the "prod"
        name resolver, which produces genuine valid certificates. If not provided,
        the value from letsencrypt_owner_email is used."""
      ))
    """The email address to use for Let's Encrypt registration in the "prod"
    name resolver, which produces genuine valid certificates. If not provided,
    the value from letsencrypt_owner_email is used."""

    letsencrypt_owner_email_staging: Optional[str] = Field(default=None, description=usl(
        """The email address to use for Let's Encrypt registration in the "staging"
        name resolver, which produces untrusted certificates for testing purposes.
        Using the staging resolver avoids hitting rate limits on the prod resolver.
        If not provided, the value from letsencrypt_owner_email is used."""
      ))
    """The email address to use for Let's Encrypt registration in the "staging"
    name resolver, which produces untrusted certificates for testing purposes.
    Using the staging resolver avoids hitting rate limits on the prod resolver.
    If not provided, the value from letsencrypt_owner_email is used."""

    default_cert_resolver: str = Field(default="staging", description=usl(
        """The default name of the Traefik certificate resolver to use for HTTPS/TLS
        routes. Generally, this should be "prod" for production use (real certs),
        and "staging" for testing purposes (untrusted certs).
        If not provided, "staging" is used."""
      ))
    """The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes. Generally, this should be "prod" for production use (real certs),
    and "staging" for testing purposes (untrusted certs).
    If not provided, "staging" is used."""

    admin_cert_resolver: str = Field(default="prod", description=usl(
        """The default name of the Traefik certificate resolver to use for HTTPS/TLS
        routes for the Traefik dashboard and Portainer web interface. By default,
        "prod" is used."""
      ))
    """The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes for the Traefik dashboard and Portainer web interface. By default,
    "prod" is used."""

    traefik_dashboard_cert_resolver: Optional[str] = Field(default=None, description=usl(
        """The name of the Traefik certificate resolver to use for the Traefik dashboard.
        By default, the value of admin_cert_resolver is used."""
      ))
    """The name of the Traefik certificate resolver to use for the Traefik dashboard.
    By default, the value of admin_cert_resolver is used."""

    portainer_cert_resolver: Optional[str] = Field(default=None, description=usl(
        """The name of the Traefik certificate resolver to use for the Portainer web interface.
        By default, the value of admin_cert_resolver is used."""
      ))
    """The name of the Traefik certificate resolver to use for the Portainer web interface.
    By default, the value of admin_cert_resolver is used."""

    portainer_agent_secret: str = Field(description=usl(
        """A random string used to secure communication between Portainer and the Portainer
        agent. Typically 32 hex digits.
        REQUIRED (generated and installed in user config by provisioning tools)."""
      ))
    """A random string used to secure communication between Portainer and the Portainer
    agent. Typically 32 hex digits.
    REQUIRED (generated and installed in user config by provisioning tools)."""

    traefik_dashboard_htpasswd: str = Field(description=usl(
        """The admin username and bcrypt-hashed password to use for HTTP Basic authhentication on
        the Traefik dashboard. The value of this string is of the form "username:hashed_password",
        and can be generated using the `htpasswd -nB admin` or tools included in this project.
        This value is sensitive, and should not be stored in a git repository. Also, a hard-to-guess
        password should be used to defend against a dictionary attack if the hash is ever compromised.
        Note that this value may contain dollar-signs, so when it is passed to docker-compose
        via an environment variable, all dollar-signs must be doubled to escape them (they
        are not doubled here).
        Example: 'admin:$2y$05$LCmVF2WJY/Ue0avRDcsDmelPqzXQcMIXoRxHF3bR62HuIP.fqqqZm'
        REQUIRED (generated and installed in user config by provisioning tools)."""
      ))
    """The admin username and bcrypt-hashed password to use for HTTP Basic authhentication on
    the Traefik dashboard. The value of this string is of the form "username:hashed_password",
    and can be generated using the `htpasswd -nB admin` or tools included in this project.
    This value is sensitive, and should not be stored in a git repository. Also, a hard-to-guess
    password should be used to defend against a dictionary attack if the hash is ever compromised.
    Note that this value may contain dollar-signs, so when it is passed to docker-compose
    via an environment variable, all dollar-signs must be doubled to escape them (they
    are not doubled here).
    Example: 'admin:$2y$05$LCmVF2WJY/Ue0avRDcsDmelPqzXQcMIXoRxHF3bR62HuIP.fqqqZm'
    REQUIRED (generated and installed in user config by provisioning tools)."""

    stable_public_dns_name: str = Field(default="ddns", description=usl(
        """A permanent DNS name (e.g., ddns.mydnsname.com) that has been configured to always
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
        The default value is "ddns"."""
      ))
    """A permanent DNS name (e.g., ddns.mydnsname.com) that has been configured to always
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
    The default value is "ddns"."""

    traefik_dashboard_subdomain: str = Field(default="traefik", description=usl(
        """The subdomain under admin_parent_dns_domain to use for the Traefik dashboard. The default value is "traefik"."""
      ))
    """The subdomain under admin_parent_dns_domain to use for the Traefik dashboard. The default value is "traefik"."""

    portainer_subdomain: str = Field(default="portainer", description=usl(
        """The subdomain under admin_parent_dns_domain to use for the Portainer web interface. The default value is "portainer"."""
      ))
    """The subdomain under admin_parent_dns_domain to use for the Portainer web interface. The default value is "portainer"."""

    default_app_subdomain: str = Field(default="hub", description=usl(
        """A subdomain under parent_dns_domain to use for general-purpose path-routed web services created by Portainer.
        this allows multiple simple services to share a single provisioned DNS name and certificate
        if they can be routed with a traefik Path or PathPrefix rule. The default value is "rpi-hub"."""
      ))
    """A subdomain under parent_dns_domain to use for general-purpose path-routed web services created by Portainer.
    this allows multiple simple services to share a single provisioned DNS name and certificate
    if they can be routed with a traefik Path or PathPrefix rule. The default value is "rpi-hub"."""

    app_subdomain_cert_resolver: Optional[str] = Field(default=None, description=usl(
        """The default name of the Traefik certificate resolver to use for HTTPS/TLS
        routes using the default app subdomain. Generally, this should be "prod"
        once the default app subdomain route has been validated, or "staging"
        for testing purposes (untrusted certs). If not provided, the value of
        default_cert_resolver is used."""
      ))
    """The default name of the Traefik certificate resolver to use for HTTPS/TLS
    routes using the default app subdomain. Generally, this should be "prod"
    once the default app subdomain route has been validated, or "staging"
    for testing purposes (untrusted certs). If not provided, the value of
    default_cert_resolver is used."""

    base_stack_env: EnvVarsModel = Field(default=EnvVarsModel(), description=usl(
      """Dictionary of environment variables that will be passed to all docker-compose stacks, including
      the Traefik and Portainer stacks, and stacks created by Portainer. Note that
      properties defined here will be installed directly into Portainer's runtime
      environment, and thus will be implicitly available for expansion in all docker-compose
      stacks started by Portainer."""
      ))
    """Dictionary of environment variables that will be passed to all docker-compose stacks, including
    the Traefik and Portainer stacks, and stacks created by Portainer. Note that
    properties defined here will be installed directly into Portainer's runtime
    environment, and thus will be implicitly available for expansion in all docker-compose
    stacks started by Portainer."""

    traefik_stack_env: EnvVarsModel = Field(default=EnvVarsModel(), description=usl(
        """Dictionary of environment variables that will be passed to the Traefik docker-compose stack.
        Actual used dict is created from base_stack_env, with this dict overriding."""
      ))
    """Dictionary of environment variables that will be passed to the Traefik docker-compose stack.
    Actual used dict is created from base_stack_env, with this dict overriding."""
    
    portainer_stack_env: EnvVarsModel = Field(default=EnvVarsModel(), description=usl(
        """Dictionary of environment variables that will be passed to the Portainer docker-compose stack.
        Actual used dict is created from base_stack_env, with this dict overriding."""
      ))
    """Dictionary of environment variables that will be passed to the Portainer docker-compose stack.
    Actual used dict is created from base_stack_env, with this dict overriding."""

    base_app_stack_env: EnvVarsModel = Field(default=EnvVarsModel(), description=usl(
        """Dictionary of environment variables that should be passed to all app stacks, including
        stacks created by Portainer. Note that properties defined here will be
        installed directly into Portainer's runtime environment, and thus will
        be implicitly available for expansion in all docker-compose stacks started by Portainer.
        Actual used dict is created from base_stack_env, with this dict overriding."""
      ))
    """Dictionary of environment variables that should be passed to all app stacks, including
    stacks created by Portainer. Note that properties defined here will be
    installed directly into Portainer's runtime environment, and thus will
    be implicitly available for expansion in all docker-compose stacks started by Portainer.
    Actual used dict is created from base_stack_env, with this dict overriding."""

    portainer_runtime_env: EnvVarsModel = Field(default=EnvVarsModel(), description=usl(
        """Dictionary of environment variables that will be installed into Portainer's actual runtime
        environment, and thus will be implicitly available for variable expansion in all
        docker-compose stacks started by Portainer, as well as by any processes started
        in the Portainer container.
        Actual used dict is created from base_app_stack_env, with this dict overriding."""
      ))
    """Dictionary of environment variables that will be installed into Portainer's actual runtime
    environment, and thus will be implicitly available for variable expansion in all
    docker-compose stacks started by Portainer, as well as by any processes started
    in the Portainer container.
    Actual used dict is created from base_app_stack_env, with this dict overriding."""
