rpi-home-hub: Bootstrap files for a home hub server on Raspberry Pi Ubuntu, built on traefik and Portainer
===================================================

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Latest release](https://img.shields.io/github/v/release/sammck/rpi-home-hub.svg?style=flat-square&color=b44e88)](https://github.com/sammck/rpi-home-hub/releases)

`rpi-home-hub` is a a simple directory tree of scripts and configuration files intended to make it easy to bootstrap a small container-based home web services hub on Ubuntu/Debian on Raspberry Pi or any dedicated 64-bit host that has ports 80, 443, 7080, and 7443 available for use. The hub can manage multiple services sharing a single port and can expose
individual services to the local intranet or to the public Internet. HTTPS termination is provided, including
automatic provisioning of SSL certificates using [lets-encrypt](https://letsencrypt.org/)

[Traefik](https://doc.traefik.io/traefik/) is used as a reverse-proxy, and [Portainer](https://docs.portainer.io/) is used to manage service docker-compose stacks.

Table of contents
-----------------

* [Introduction](#introduction)
* [Installation](#installation)
* [Usage](#usage)
  * [Command line](#command-line)
  * [API](api)
* [Known issues and limitations](#known-issues-and-limitations)
* [Getting help](#getting-help)
* [Contributing](#contributing)
* [License](#license)
* [Authors and history](#authors-and-history)


Introduction
------------

`rpi-home-hub` is a a simple directory tree of scripts and configuration files intended to make it easy
to bootstrap a small container-based home web services hub on Ubuntu/Debian on Raspberry Pi or any dedicated
64-bit host that has ports 80, 443, 7080, and 7443 available for use. All services run in docker containers and are managed with docker-compose. Individual service stacks can be easily configured to be visible to the LAN only, or to the public Internet.

The only prerequisite tools that need to be directly installed on the host machine are [docker](https://docs.docker.com/get-started/overview/) and [docker-compose](https://docs.docker.com/compose/).

There are two primary docker-compose stacks that are directly configured and launched in the bootstrap process.:

  - [Traefik](https://doc.traefik.io/traefik/) is used as a reverse-proxy and firewall for all services.
  It has the wonderful quality of automatically provisioning/deprovisioning reverse-proxy policy for
  services in docker containers when they are launched, modified, or stopped--based solely on configuration
  info attached to the container's docker labels. Once traefik is launched it never needs to be explicitly
  managed again. Traefik also automatically provisions SSL certificates (using lets-encrypt) for services as they
  are needed, and terminates HTTPS entrypoints so your service containers only need to implement HTTP. Traefik provides a web-based dashboard to view status and information related to the reverse-proxy. Traefik reverse-proxy has wide adoption, is open-source and free to use.

  - [Portainer](https://docs.portainer.io/) is a nifty and very full-featured docker service manager with a rich web UI to manage docker stacks. With Portainer, you can add/remove/restart/reconfigure stacks, view logs, browse volumes,
  inspect resource usage, etc. Portainer includes a multiuser username/password database and full-featured access control
  if you need to allow multiple people to manage containers. Portainer Community Edition is open-source and free to use.

All of the containers in the two primary stacks are launched wi `restart: always` so they will automatically be
restarted after host reboot or restart of the Docker daemon.

### Prerequisites

  - **Ubuntu/Debian**: The bootstrapping code provided here must be running an Ubuntu/Debian variant. The hub has only been tested on Ubuntu 22.04. However, if you manually install docker and docker-compose, the hub may well work on any Linux variant.
  - **Python 3.7** is required by the bootstrapping scripts.
  - **curl**: curl is required by the bootstrapping scripts.
  - **Docker**: Docker must be installed before the primary stacks can be launched. A script is
  provided here to install a current docker version from Docker's apt repos in an idempotent way.
  - **docker-compose**: docker-compose must be installed before the primary stacks can be launched. A script is
  provided here to install a current docker-compose version from Docker's apt repos in an idempotent way.

Installation
=====

## Ensure your hub host has a static or reserved DHCP LAN IP address.
Because you will be enabling port forwarding for porst 80 and 443 on your Internet gateway router,
it is essential that the LAN IP address (hereon referred to as `${LAN_IP_ADDRESS}` of your hub host will never change. You can make that assurance
by either:

  1. using a static LAN IP address for your hub host; or
  2. configuring your DHCP server (generally built into your gateway router) to always provide the same IP address to your hub host (based on its MAC address). Note that with this method, you will have to reconfigure your DHCP server if you ever replace or upgrade your hub host.
## Provision a Dynamic DNS (DDNS) name for your network's gateway router public IP Address

Since typical residential ISPs may change your public IP address periodically, it is
usually necessary to involve Dynamic DNS (DDNS) to provide a stable name through which your
network's public IP address can be resolved. This requires running a DDNS agent inside the network
that periodically updates a public DNS server if the public IP address changes. Many gateway routers (e.g., eero) have a DDNS agent built-in. Or you can run a DDNS agent on this or another host inside your LAN. Your DDNS provider will provide you with an obscure but unique and stable (as long as you stay with the DDNS provider) DNS name for your gateway's public IP address; e.g., "g1234567.eero.online".

## Register a public DNS Domain that you can administer
To serve requests to the Internet on well-known, easy-to-remember names, and to enable certificate generation for SSL/HTTPS, you must be able to create your own public DNS records that resolve to your network's public IP address. You
need to register or already have administrative access to a public domain we will call `${DNS_DOMAIN}` (e.g., `smith-vacation-home.com`). You can use AWS, Squarespace, GoDaddy or whatever registrar you like.

## Create a master CNAME record home.${DNS_DOMAIN} that will always resolve to your publid IP address
The first record you should create in your public domain is a CNAME record `home.${DNS_DOMAIN}` that points to the
obscure DNS name given to you by your DDNS provider (see above). That makes an easy-to-remember DNS name for your
network's public IP address, and ensures that if your DDNS obscure name ever changes, you will only have to update this one CNAME record to be back in business.

## Create a CNAME record for your Traefik dashboard
Create another CNAME record `traefik.${DNS_DOMAIN}` that points to `home.${DNS_DOMAIN}`. This will allow
lets-encrypt to issue an SSL certificate for Traefik's dashboard web server. Note that as Traefik
is configured here, the Traefik dashboard is actually not exposed to from the Internet (all requests will
receive `404 page not found`), but the service will receive a proper SSL certificate and HTTPS can
be used from inside the LAN if the client overrides public DNS with `/etc/hosts` or with a LAN-local
DNS server (see below).

{% note %}

**Note:** It is not a good idea to expose the Traefik dashboard directly to the Internet; though
it is read-only and does not directly expose secrets, it is not authenticated and it reveals a lot
of information about configuration that could make an attacker's job easier.

{% endnote %}

## Create a CNAME record for your Portainer web interface
Create another CNAME record `portainer.${DNS_DOMAIN}` that points to `home.${DNS_DOMAIN}`. This will allow
lets-encrypt to issue an SSL certificate for Portainer's rich UI web server. Note that as Traefik
is configured here, the Portainer UI is actually not exposed to from the Internet (all requests will
receive `404 page not found`), but the service will receive a proper SSL certificate and HTTPS can
be used from inside the LAN if the client overrides public DNS with `/etc/hosts` or with a LAN-local
DNS server (see below).

{% note %}

**Note:** Though thousands of users have done so, Portainer does not recommend exposing the Portainer
UI directly to the Internet. It does have username/password authentication, multi-user support, and ACLs,
so in theory it is OK. But placing it on the Internet exposes a bigger attack surface, and if Portainer is
compromised then the attacker can launch any docker container (even privileged containers) and easily root
the hub-host, and from there attempt to attack other hosts inside your LAN.

{% endnote %}

## Configure port forwarding on your gateway router
Your network's gateway router must be configured to forward public TCP ports 80 and 443 to the hub host's stable
`${LAN_IP_ADDRESS}` (see above) on alternate destination ports 7080 and 7443, respectively. Alternate internal ports are required because ports 80 and 443 on the hub host will be used to serve LAN-local (non-Internet) requests.

After this step is complete, there will be public, untrusted Internet traffic coming into your hub host on ports
7080 and 7443. It is important that those ports are not served by code that does not defend itself against malicious
visitors.

## Copy the bootstrap directory tree
A copy of this directory tree must be placed on the host machine. You can do this in several ways:

 - If git is installed, you can directly clone it from GitHub:
   ```bash
   sudo apt-get install git   # if necessary to install git first
   cd ~
   git clone https://github.com/sammck/rpi-home-hub.git
   cd rpi-home-hub
   ```

- If you have SSH access to the host, you can copy the directory tree from another machine using rsync:
  ```bash
  # On other machine
  rsync -a rpi-home-hub/ <my-username>@<my-hub-host>:~/rpi-home-hub/
  ssh <my-username>@<my-hub-host>
  # On the hub
  cd rpi-home-hub
  ```

## Install prerequisite system packages

Docker and docker-compose must be installed, and the bootstrapping user must be in the `docker`
security group. A script is provided to do all of these things:

```bash
cd ~/rpi-home-hub
./install-prereqs.sh
```
If required, you will be prompted for your `sudo` password.

{% note %}

**Note:** If you were not already in the `docker` security group when you started the current login session, you will
be added, but the change will not take effect until you log out and log back in again.

{% endnote %}

## Configuring the environment

Before you launch the two primary docker-compose stacks, you must create a `.env` file containing values that are
unique to your hub:

```bash
cd ~/rpi-home-hub
cat <<EOF >.env
TRAEFIK_DNS_DOMAIN=<registered-domain-name>
PORTAINER_AGENT_SECRET=<any-random-secret-string>
LETSENCRYPT_OWNER_EMAIL=<your-email-address>
EOF
```

Replace `<registered-domain-name>` with the public `${DNS_DOMAIN}` you have administrative control over; e.g., `smith-vacation-home.com`.

Replace `<any-random-secret-string>` with a longish secure password. It does not need to be memorable and you
do not need to write it down.  It is only used to secure communication between Portainer and the Portaner Agent.

Replace `<your-email-address>` with your email address. This is the email address that will be associated
with public SSL certificates issued by lets-encrypt.

## Launch Traefik reverse-proxy

Next, start the Traefik reverse-proxy. To perform this step, the user must be in the `docker` security group.

{% note %}

**Note:** If you were not already in the `docker` security group when you started the current login session, you were
added by `install-prereqs.sh, but the change will not take effect until you log out and log back in again.

{% endnote %}


```bash
cd ~/rpi-home-hub/traefik
docker-compose up -d
```

Traefik will immediately begin serving requests on ports 80 and 443 on both the local hub-host and on the public
Internet. It will also obtain a lets-encrypt SSL certificate for traefik.${DNS_DOMAIN}.
However, no proxied services are yet exposed to the Internet, so requests to the public addresses will
always receive `404 page not found` regardless of host name.

## Verify basic Traefik functionality

Make a cursory check to see that everything thinks it is running by examining the logs

```bash
cd ~/rpi-home-hub/traefik
docker-compose logs
```

Verify that the Traefik Dashboard is functioning by opening a web browser on the hub-host or any other
host in the LAN and navigating to `http://${LAN_IP_ADDRESS}:8080`, where `${LAN_IP_ADDRESS}` is the stable LAN
IP address of your hub-host, as described above.

Verify that Traefik is serving LAN-local HTTP requests:
```bash
curl http://${LAN_IP_ADDRESS}
# you will receive 404 page not found, which is expected
```

Verify that Traefik is serving LAN-local HTTPS requests:
```bash
curl -k https://${LAN_IP_ADDRESS}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 80 to 7080 is working and Traefik is serving public Internet HTTP requests:
```bash
curl http://home.${LAN_IP_ADDRESS}
# you will receive 404 page not found, which is expected
```

Verify that port forwarding from 443 to 7443 is working and Traefik is serving public Internet HTTPS requests:
```bash
curl -k https://home.${LAN_IP_ADDRESS}
# you will receive 404 page not found, which is expected
```



```
Known issues and limitations
----------------------------

* TBD

Getting help
------------

Please report any problems/issues [here](https://github.com/sammck/rpi-home-hub/issues).

Contributing
------------

Pull requests welcome.

License
-------

`rpi-home-hub` is distributed under the terms of the [MIT License](https://opensource.org/licenses/MIT).  The license applies to this file and other files in the [GitHub repository](http://github.com/sammck/rpi-home-hub) hosting this file.

Authors and history
-------------------

The author of `rpi-home-hub` is [Sam McKelvie](https://github.com/sammck).
