tp-hub: Bootstrap files and tools for a flexible single-box container-based web-services hub, built on docker-compose, Traefik and Portainer
===================================================

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Latest release](https://img.shields.io/github/v/release/sammck/tp-hub.svg?style=flat-square&color=b44e88)](https://github.com/sammck/tp-hub/releases)

`tp-hub` is a project directory and collection of tools intended to make it easy to bootstrap a small container-based web-services hub
on an Ubuntu/Debian host machine. It is suitable for installation on Raspberry Pi or any dedicated 64-bit host that has ports 80, 443, 7080, and 7443 available for use.
The hub can manage multiple services sharing a single port and can expose individual services to the local intranet or to the public Internet. HTTPS termination is provided, including automatic provisioning of SSL certificates using [lets-encrypt](https://letsencrypt.org/)

[Traefik](https://doc.traefik.io/traefik/) is used as a reverse-proxy, and [Portainer](https://docs.portainer.io/) is used to manage service [docker-compose](https://docs.docker.com/compose/) stacks.

Table of contents
-----------------

* [Introduction](#introduction)
* [Installation](#installation)
* [Known issues and limitations](#known-issues-and-limitations)
* [Getting help](#getting-help)
* [Contributing](#contributing)
* [License](#license)
* [Authors and history](#authors-and-history)

Introduction
------------

`tp-hub` is a project directory and collection of tools intended to make it easy to bootstrap a small container-based web-services hub
on an Ubuntu/Debian host machine. It is suitable for installation on Raspberry Pi or any dedicated 64-bit host that has ports 80, 443, 7080, and 7443 available for use.

[Traefik](https://doc.traefik.io/traefik/) is used as a reverse-proxy, and [Portainer](https://docs.portainer.io/) is used to manage service [docker-compose](https://docs.docker.com/compose/) service stacks.

All services, including Traefik and Portainer themselves, run in docker containers and are managed with [docker-compose](https://docs.docker.com/compose/).
 Individual service stacks can be easily configured to be visible to the LAN only, or to the public Internet.

A new web service can be added simply by authoring a docker-compose.yml file and using Portainer's web UI to add a managed stack. All reverse-proxy configuration settings for each service (including hostname/path routing, public/private entrypoints, etc.) are expressed with labels attached
to the service container and defined in its docker-compose.yml file, so there is never any need to edit reverse-proxy configuration as services are added, removed, and edited.

There are two primary docker-compose stacks that are directly configured and launched in the bootstrap process.:

  - [Traefik](https://doc.traefik.io/traefik/) is used as a reverse-proxy and firewall for all services.
  It has the wonderful quality of automatically provisioning/deprovisioning reverse-proxy policy for
  services in docker containers when they are launched, modified, or stopped--based solely on configuration
  info attached to the container's docker labels. Once traefik is launched it generally never needs to be explicitly
  managed again. Traefik also automatically provisions private keys and SSL certificates (using lets-encrypt) for services as they
  are needed, and terminates HTTPS entrypoints so your service containers only need to implement HTTP.
  Traefik provides a web-based dashboard to view status and information related to the reverse-proxy.
  Traefik reverse-proxy has wide adoption, is open-source and free to use. 

  - [Portainer](https://docs.portainer.io/) is a nifty and very full-featured docker-compose service stack manager with a
  rich web UI to manage docker-compose stacks. With Portainer, you can add/remove/restart/reconfigure stacks, view logs, browse volumes,
  inspect resource usage, etc. Portainer includes a multiuser username/password database and full-featured access control
  if you need to allow multiple people to manage containers. Portainer Community Edition is open-source and free to use.
  The Portainer stack creates two containers--one for the main Portainer Web UI (Portainer itself), and another for the
  Portainer Agent--a backend service that allows Portainer to control Docker on the host machine. The two components
  are separated so that in complex environments, a single Portainer instance can manage Docker stacks on multiple host
  machines; for our purposes only one Portainer Agent is used and it is on the same host as Portainer itself

All of the containers in the two primary stacks are launched wi `restart: always` so they will automatically be
restarted after host reboot or restart of the Docker daemon.

### Prerequisites

  - **Ubuntu/Debian**: The bootstrapping code provided here must be running an Ubuntu/Debian variant. The hub has only been tested on Ubuntu 22.04. However, if you skip auto-provisioning and manually install docker and docker-compose, the hub may well work on any Linux variant.
  - **Python 3.8+** is required by the bootstrapping scripts.

Installation
=====

## Ensure your hub host has a static or reserved DHCP LAN IP address.
Because you will be enabling port forwarding for ports 80 and 443 on your Internet gateway router,
it is essential that the LAN IP address (hereon referred to as `${HUB_LAN_IP}`) of your hub host will never change. You can make that assurance
by either:

  1. using a static LAN IP address for your hub host; or
  2. configuring your DHCP server (generally built into your gateway router) to always provide the same IP address to your hub host (based on its MAC address). Note that with this method, you will have to reconfigure your DHCP server if you ever replace or upgrade your hub host.

## Configure port forwarding on your gateway router
Your network's gateway router must be configured to forward public TCP ports 80 and 443 to the hub host's stable
`${HUB_LAN_IP}` (see above) on alternate destination ports 7080 and 7443, respectively. Alternate internal ports are required because ports 80 and 443 on the hub host will be used to serve LAN-local (non-Internet) requests.

After this step is complete, there will be public, untrusted Internet traffic coming into your hub host on ports
7080 and 7443. It is important that those ports are not served by code that does not defend itself against malicious
visitors. The Traefik reverse proxy will handle requests coming into these ports and only route them to web services that
are explicitly configured to receive public Internet traffic.

## Register a public DNS Domain that you can administer
To serve requests to the Internet on well-known, easy-to-remember names, and to enable certificate generation for SSL/HTTPS, you must be able to create your own public DNS records that resolve to your network's public IP address. You
need to register or already have administrative access to a public domain we will call `${PARENT_DNS_DOMAIN}` (e.g., `smith-vacation-home.com`). You can use AWS Route53, Squarespace, GoDaddy or whatever registrar you like. If you use AWS Route53, this project provides
handy commands to easily create new DNS names within ${PARENT_DNS_DOMAIN}

## Provision a Dynamic DNS (DDNS) name for your network's gateway router public IP Address

Since typical residential ISPs may change your public IP address periodically, if you are running in a residential LAN, it is
usually necessary to involve Dynamic DNS (DDNS) to provide a stable name through which your
network's public IP address can be resolved. This requires running a DDNS agent inside the network
that periodically updates a public DNS server if the public IP address changes. Many gateway routers (e.g., eero) have a DDNS agent built-in. Or you can run a DDNS agent on this or another host inside your LAN. Your DDNS provider will provide you with an obscure but unique and stable (as long as you stay with the DDNS provider) DNS name for your gateway's public IP address; e.g., "g1234567.eero.online".

## Create a master CNAME record ddns.${PARENT_DNS_DOMAIN} that will always resolve to your public IP address
The first record you should create in your public domain is a CNAME record `ddns.${PARENT_DNS_DOMAIN}` that points to the
obscure DNS name given to you by your DDNS provider (see above). That makes an easy-to-remember DNS name for your
network's public IP address, and ensures that if your DDNS obscure name ever changes, you will only have to update this one CNAME record to be back in business.

## Copy this project directory tree onto the hub host machine
A copy of this directory tree must be placed on the host machine. You can do this in several ways; for example:

 - If git is installed, you can directly clone it from GitHub:
   ```bash
   sudo apt-get install git   # if necessary to install git first
   cd ~
   git clone https://github.com/sammck/tp-hub.git
   cd tp-hub
   ```

- If you have SSH access to the host, you can copy the directory tree from another machine using rsync:
  ```bash
  # On other machine
  rsync -a tp-hub/ <my-username>@<my-hub-host>:~/tp-hub/
  ssh <my-username>@<my-hub-host>
  # On the hub
  cd tp-hub
  ```

## Run bin/hub-env to install the project's Python virtualenv and launch a bash shell in the project enviromnent:

There is a script `<project-dir>/bin/hub-env` which will activate the project environment including the Python
virtualenv that it uses. It can be invoked in one of 3 ways:

  - If sourced from another script or on the command line (bash '.' or 'source' command), it will directly modify
  environment variables, etc in the running process to activate the environment. This is similar to the way
  `. ./.venv/bin/activate` is typically used with Python virtualenv's.
  - If invoked as a command with arguments, the arguments are treated as a command to run within the environment.
  The command will be executed, and when it exits, control will be returned to the original caller, without
  modifying the original caller's environment.
  - If invoked as a command with no arguments, launches an interactive bash shell within the environment. When the
  shell exits, control is returned to the original caller, without modifying the original caller's environment.

Regardless of which way hub-env is invoked, if the virtualenv does not exist, hub-env will create it and initialize it with required
packages.  If necessary, hub-env will install system prerequisites needed to create the virtualenv, which might require
sudo. This is only done the first time hub-env is invoked.

In addition, hub-env tweaks the Python virtualenv's .venv/bin/activate to activate the entire project rather than just the virtualenv.
This is a convenience primarily so that tools like vscode that understand how to activate a Python virtualenv will work properly
with this project.

To set initialize and activate the environment the first time:

```bash
$ cd ~/tp-hub
$ bin/hub-env
...
# The first time you run bin/hub-env, there will be a lot of output as prerequisites are
# installed, the virtualenv is created, and required Python packages are installed. If
# necessary for prerequisite installation, you may be asked to enter your sudo password.
# If you don't wish to do this, you can CTRL-C out, install the prerequisite manually,
# and then restart this step.
# After the first time you run bin/hub-env, there will be no such spew or prompts.
...
Launching hub-env bash shell...
(hub-env) $
# You are now running a bash shell in the project environment, with all commands in the search PATH, etc.
```
> **Note**
> All of the instructions that follow assume you are running in a hub-env activated bash shell.


## Install prerequisite system packages

Docker and docker-compose must be installed, and the bootstrapping user must be in the `docker`
security group. A script is provided to automatically do this:

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
install-prereqs
```

This command is safe to run multiple times; it will only install what is missing.
If required, you will be prompted for your `sudo` password. If you don't wish to do this;
you can CRTL-C out, install the prerequisite manually, then restart this step.

> **Note**
> If you were not already in the `docker` security group when you started the current login session, you will
> be added, but the change will not take effect until you log out and log back in again. Until you do that,
> sudo will be required to run docker (you may be prompted for sudo password for each subsequent step that
> invokes docker).

## Create an initial config.yml file with minimal required configuration settings

A script `init-config` is provided that will create a boilerplate config.yml if needed,
and prompt you to provide values for required config settings. These include:

  - An email address to use for Lets-encrypt SSL certificate generation
  - An admin password to use for access to the Traefik dashboard web UI
  - An initial admin password to use for access to the Portainer web UI. Only used until the first timeyou set a new password.
  - The value of `${PARENT_DNS_DOMAIN}` that you set up as described above.

It is safe to run `init-config` multiple times; it will only prompt you for values that have not yet been
initialized.

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
init-config
# Answer the questions as prompted
```

## Verify that the initial configuration is valid

Just to make sure the initial configuration is readable and all values are sane, run this command to display
the resolved configuration:

```bash
# if not running in hub-env shell, launch with './bin/hub-env'
hub config
# ...json configuration is displayed
```
## Create CNAME records for the initial set of services
Create the following CNAME records that are used by the initial configuration of the hub:

```
CNAME      traefik.${PARENT_DNS_DOMAIN}.com           ==> ddns.${PARENT_DNS_DOMAIN}.com    (Traefik dashboard UI; only exposed on LAN)
CNAME      portainer.${PARENT_DNS_DOMAIN}.com         ==> ddns.${PARENT_DNS_DOMAIN}.com    (Portainer web UI; only exposed on LAN)
CNAME      hub.${PARENT_DNS_DOMAIN}.com               ==> ddns.${PARENT_DNS_DOMAIN}.com    (Shared general purpose app DNS name)
CNAME      whoami.${PARENT_DNS_DOMAIN}.com            ==> ddns.${PARENT_DNS_DOMAIN}.com    (Used for initial example web service)
```
If you are using AWS route53, and have credentials configured in  `~/.aws/credentials`, you can use the following commands to create these records:

```bash
# if not running in hub-env shell, launch with './bin/hub-env'
hub cloud dns create-name traefik
hub cloud dns create-name portainer
hub cloud dns create-name hub
hub cloud dns create-name whoami
```

> **Note**
> While an SSL cert is generated for the Traefik dashboard, and HTTPS can be used to access
> it through the local LAN entry point, tp_hub does not expose the Traefik dashboard to the
> public Internet. It is not a good idea to expose the Traefik dashboard directly to the Internet;
> even though we authenticate it with HTTP basic authentication, it is read-only and it
> does not directly expose secrets, it reveals a lot
> of information about configuration that could make an attacker's job easier.

> **Note**
> While an SSL cert is generated for the Portainer UI, and HTTPS can be used to access
> it through the local LAN entry point, tp_hub does not expose the Portainer UI to the
> public Internet.
> Though thousands of users have done so, Portainer does not recommend exposing the Portainer
> UI directly to the Internet. It does have username/password authentication, multi-user support, and ACLs,
> so in theory it is OK. But placing it on the Internet exposes a bigger attack surface, and if Portainer is
> compromised then the attacker can launch any docker container (even privileged containers) and easily root
> the hub-host, and from there attempt to attack other hosts inside your LAN.

## Test the physical network configuration

Before launching the hub stacks for the first time, it is important to ensure tha the network has been properly
set up in the previous steps. This includes:

  - All above mentioned DNS CNAME entries are created and point to this network's public IP address
  - Port forwarding from public port 80 to this host port 7080 is working
  - Port forwarding from public port 443 to this host port 7443 is working
  - Ports 80, 443, 7080, 7443, 8080, and 9000 are available for use on this host

You can test all of these assumptions with `test-network-prereqs`

> **Note**
> The `test-network-prereqs` script requires that the traefik and portainer stacks are not running, or tests will fail.

The environment variables and other customizable configuration elements used by docker-compose
to launch the Traefic and Portainer docker-compose stacks are derived from the hub configuration
you set up in previous steps. To prepare these derived files for use by docker-compose, run the following command:

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
test-network-prereqs
```
## Build the traefik and portainer docker-compose configuration files

The environment variables and other customizable configuration elements used by docker-compose
to launch the Traefik and Portainer docker-compose stacks are derived from the hub configuration
you set up in previous steps. To prepare these derived files for use by docker-compose, run the following command:

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
hub build
```

## Launch Traefik reverse-proxy

Next, start the Traefik reverse-proxy. To perform this step, the user must be in the `docker` security group.

> **Note**
> If you were not already in the `docker` security group when you started the current login session, you were
> added by `install-prereqs.sh`, but the change will not take effect until you log out and log back in again.
> Until you do that, you will be prompted for your sudo password when invoking commands that require docker.

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
traefik-up
```

Traefik will immediately begin serving requests on ports 80 and 443 on both the local hub-host and on the public
Internet. It will also obtain a lets-encrypt SSL certificate for traefik.${PARENT_DNS_DOMAIN}.
However, no proxied services are yet exposed to the Internet, so requests to the public addresses will
always receive `404 page not found` regardless of host name.

## Verify basic Traefik functionality

Make a cursory check to see that everything thinks it is running by examining the logs

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
traefik-logs | grep error
```

Verify that the Traefik Dashboard is functioning by opening a web browser on the hub-host or any other
host in the LAN and navigating to `http://${HUB_LAN_IP}:8080`, where `${HUB_LAN_IP}` is the stable LAN
IP address of your hub-host, as described above.

You will be prompted for login credentials.  The username is "admin" and the password is the one you entered
for the Traefik dashboard in the above steps.

Verify that Traefik is serving LAN-local HTTP requests (from any host in the LAN):
```bash
curl http://${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that Traefik is serving LAN-local HTTPS requests (from any host in the LAN):
```bash
curl -k https://${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 80 to 7080 is working and Traefik is serving public Internet HTTP requests (from any host with Internet access):
```bash
curl http://ddns.${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 443 to 7443 is working and Traefik is serving public Internet HTTPS requests (from any host with Internet access):
```bash
curl -k https://ddns.${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

## Launch Portainer

Next, start the Portainer stack. To perform this step, the user must be in the `docker` security group.

> **Note**
> If you were not already in the `docker` security group when you started the current login session, you were
> added by `install-prereqs.sh`, but the change will not take effect until you log out and log back in again.
> Until you do that, you will be prompted for your sudo password when invoking commands that require docker.

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
portainer-up
```

Portainer will immediately be recognized by Traefik and Traefik will begin reverse-proxying requests to it.

## Verify basic Portainer functionality

Make a cursory check to see that everything thinks it is running by examining the logs

```bash
# if not running in hub-env shell, launch with '~/tp-hub/bin/hub-env'
portainer-logs | grep ERR
```

Verify that the Portainer Dashboard is functioning by opening a web browser on the hub-host or any other
host in the LAN and navigating to `http://${HUB_LAN_IP}:9080`, where `${HUB_LAN_IP}` is the stable LAN
IP address of your hub-host, as described above.

You will be prompted for login credentials.  The username is "admin" and the password is the one you entered
for the Portainer Web UI in the above steps.

Verify that Traefik is serving LAN-local HTTP requests (from any host in the LAN):
```bash
curl http://${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that Traefik is serving LAN-local HTTPS requests (from any host in the LAN):
```bash
curl -k https://${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 80 to 7080 is working and Traefik is serving public Internet HTTP requests (from any host with Internet access):
```bash
curl http://ddns.${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 443 to 7443 is working and Traefik is serving public Internet HTTPS requests (from any host with Internet access):
```bash
curl -k https://ddns.${HUB_LAN_IP}
# you will receive 404 page not found, which is expected
```


```
Known issues and limitations
----------------------------

* TBD

Getting help
------------

Please report any problems/issues [here](https://github.com/sammck/tp-hub/issues).

Contributing
------------

Pull requests welcome.

License
-------

`tp-hub` is distributed under the terms of the [MIT License](https://opensource.org/licenses/MIT).  The license applies to this file and other files in the [GitHub repository](http://github.com/sammck/tp-hub) hosting this file.

Authors and history
-------------------

The author of `tp-hub` is [Sam McKelvie](https://github.com/sammck).
