SSH Reverse tunnel port-forwarding stack
===================================================

If your gateway router does not support support port forwarding, or you do not have administrative control of
your gateway route–e.g., if you are in a corporate LAN, using a 5G Internet gateway, or are behind a 3rd-party
WiFi hotspot–then you will need an alternate solution to maintain a discoverable public IP address and forward public ports 80
and 443 to ports 7080 and 7443, respectively, on this hub host.

There are multiple possible solutions, but they all involve having a cloud service with a dedicated IP address for you, listening on ports
80 and 443, then, in a secure way,  forwarding TCP connections from 80 to port 7080 on this host, and forwarding TCP connections on
port 443 to port 7443 on this host.

One very easy and secure way to to this is to create a small dedicated host VM using a cloud service provider (e.g., AWS EC2), give it
a stable public IP address (or use Dynamic DNS as described elseware), have it listen on ports 80 and 443, and use the reverse port
tunnel features of an ssh connection to forward connections on those ports back to this host machine.

> **Note**
> Using this method to forward ports will make it impossible for Traefik or your Web services to discern the original IP
> address of the requesting client. All HTTP/HTTPS requests that enter through the public address will appear to originate
> from the Docker container on tp-hub that provides port forwarding.

The instructions provided here are for AWS, but any cloud provider (Azure, Google Cloud, etc.) would be able to do similar.


  1. Create an AWS Elastic IP. This will be the stable public IP address that all of your hub DNS names will resolve to and
     through which Internet clients will reach your hub.  Note that this address will be used for incoming Internet requests
     only; outgoing requests from the tp-hub to the Internet will go directly through your gateway router
  2. Create a DNS A record `port-tunnel.${PARENT_DNS_DOMAIN}` that resolved to the elastic IP.
  3. Create a new EC2 SSH keypair 'port-tunnel' and copy the private key for use below.  It is best to create a new
     keypair instead of using your usual one, because the unencrypted private key must be saved on this hub for use by this stack.
  4. In subdirectory `ssh-keys` of this docker-compose directory, create a file named `keyfile` and paste the private key
     created in step 3 into it. Protect the file with `chmod 600 keyfile`
  5. Launch an Ubuntu 22.04 EC2 instance. A t2.micro instance (free tier) will work if you're not concerned about network throughput
     (typical for t2.micro is 60Mb/s sustained with 720Mb/s bursts). Set the instance keypair to the one you just created. For
     the security group, make sure TCP ingress ports 22, 80, and 443 are open from anywhere.
  6. Associate the Elastic IP you created with the new EC2 instance.
  7. ssh into the instance with `ssh ubuntu@port-tunnel.${PARENT_DNS_DOMAIN}`.
  8. Install `curl`` and `socat``:
     ```bash
     sudo apt-get update
     sudo apt-get upgrade -y
     sudo apt-get install -y curl socat
     ```
  9. Create a systemctl service that will forward local port 80 to local port 8080. This is necessary because nonroot users cannot
     directly listen on port 80...
     ```bash
     sudo bash -c "cat >/etc/systemd/system/port-forward-80-to-8080.service" << EOF
     [Unit]
     Description=Forward port 80 to port 8080
     After=network.target
     
     
     [Service]
     Type=simple
     Restart=always
     RestartSec=5
     #StandardOutput=syslog
     #StandardError=syslog
     SyslogIdentifier=port-forward-80
     
     ExecStart=socat tcp-listen:80,reuseaddr,fork tcp:localhost:8080
     
     [Install]
     WantedBy=multi-user.target
     EOF 
     ```
  10. Create a systemctl service that will forward local port 443 to local port 8443. This is necessary because nonroot users cannot
      directly listen on port 443...
      ```bash
      sudo bash -c "cat >/etc/systemd/system/port-forward-443-to-8443.service" << EOF
      [Unit]
      Description=Forward port 443 to port 8443
      After=network.target
      
      
      [Service]
      Type=simple
      Restart=always
      RestartSec=5
      #StandardOutput=syslog
      #StandardError=syslog
      SyslogIdentifier=port-forward-443
      
      ExecStart=socat tcp-listen:443,reuseaddr,fork tcp:localhost:8443
      
      [Install]
      WantedBy=multi-user.target
      EOF 
      ```
  11. Start the two little local port forwarders:
      ```bash
      sudo systemctl start port-forward-80-to-8080 && sudo systemctl start port-forward-443-to-8443 
      ```
  12. Disconnect from the ssh session.
  13. In this docker-compose directory, create a `.env` file (subsitution your parent DNS domain name):
      ```bash
      cd ~/tp-hub/stacks/ssh-tunnel
      echo "PARENT_DNS_DOMAIN=${PARENT_DNS_DOMAIN}" > .env
      ```
  14. Build the Docker image used by the stack.
      ```bash
      cd ~/tp-hub/stacks/ssh-tunnel
      docker-compose build
      ```

  14. Bring up a Docker container that will maintain an SSH connection to the cloud VM and reverse-forward
      ports 8080 and 8443 on the cloud VM to ports 7080 and 7443 on this host, respectively:
      ```bash
      cd ~/tp-hub/stacks/ssh-tunnel
      docker-compose up -d
      ```

  15. Port forwarding should be up and running.  Proceed with tp-hub installation, using `port-tunnel.${PARENT_DNS_DOMAIN}`
      as `${DNS_OBSCURE_NAME}.

