Duck DNS Dynamic DNS Agent stack
===================================================

If you do not already have a DDNS solution, this simple stack launches a DDNS agent for
[Duck DNS](https://www.duckdns.org/). Duck DNS is a completely free, reliable and reputable DDNS service hosted on AWS. To use it:

  - Create an account and log in at https://www.duckdns.org/
  - Click "add domain" to create a unique DNS name `${DUCKDNS_SUBDOMAIN}.duckdns.org`.
  - Duck DNS will provide you with a secret token `${DUCKDNS_TOKEN}` which you will provide to the `duckdns` docker_compose stack
    so it can authenticate.
  - Run the following commands to launch the Duck DNS agent (substituting values from above):
    ```bash
    cd ~/tp-hub/stacks/duckdns
    echo "DUCKDNS_SUBDOMAIN=${DUCKDNS_SUBDOMAIN}" > .env
    echo "DUCKDNS_TOKEN=${DUCKDNS_TOKEN}" >> .env
    chmod 600 .env
    docker-compose up -d
    ```
Once you have launched the `duckdns` stack, you can forget about it. It will automatically restart when docker is restarted or
the hub host is rebooted. Your `${DDNS_OBSCURE_NAME}` is `${DUCKDNS_SUBDOMAIN}.duckdns.org`.
