{project}/bin: Executable commands and tools
============================================

The `{project}/bin` directory contains static executable commands for use within the project. Most of these executables can be directly
invoked from outside the project environment and they will self-activate the environment automatically.

This directory is added to PATH when the environment is activated.

## hub-env
Activates the project environment. If necessary creates a Python virtualenv and installs required packages into it.
If this command is sourced (with `. {project}/bin/hub-env` or `source {project}/bin/hub-env`) then it will set environment
variables for the current process.

If run as a command with no arguments; it will invoke a bash shell with the environment activated inside the shell--this makes
settings that are not inherited by child processes (e.g., the prompt string `PS1``) work correctly in the shell.

If run as a command with arguments, activates the environment and then runs the command specified in the arguments within the environment.

## install-prereqs
If needed, installs system prerequesites necessary for launching the hub:

* Installs a Python virtualenv used by this project.
* installs required Python packages into the virtualenv.
* Installs Docker.
* Installs docker-compose.
* Installs a Docker network "traefik"--used for backend communication between Traefik and reverse-proxied service containers.
* Installs a Docker volume "traefik_acme"--used to hold SSL keys and issued lets-encrypt certificates. This volume should
  not be deleted even if Traefik is reinstalled. Deleting this data will result in unnecessary premature refresh of lets-encrypt
  certificates, which lets-encrypt considers a violation of protocol. If repeated, lets-encrypt will block usage for up to a
  week at a time.
* Installs a Docker volume "portainer_data"--used to hold all Portainer persistent state, including a database of usernames and password
  hashes for Portainer access. This volume should not be deleted, unless you want to start completely clean with Portainer.

## test-network-prereqs
Runs a test to verify that your network, including gateway router port forwarding configuration, is configured properly.
Also verifies that the following public DNS names exist and resolve to your network's public IP address:

* traefik.{PARENT_DNS_DOMAIN}--Used to create a cert for the Traefik dashboard (will only be accessible from LAN)
* portainer.{PARENT_DNS_DOMAIN}--Used to create a cert for the Portainer WEB UI (will only be accessible from LAN)
* rpi-hub.{PARENT_DNS_DOMAIN}--Will be used for a general aggregate webserver that can route to multiple services by path prefix.


> **Note**
> This test can only be run when Traefik is shut down. It opens listeners on the same ports that Traefik uses.

## hub-up
Brings up the hub, including Traefik and Portainer. This command should only be 