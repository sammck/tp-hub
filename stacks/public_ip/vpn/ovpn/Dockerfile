FROM python:3.10-alpine3.18
WORKDIR /usr/src/app
RUN apk add --update \
      curl \
      jq \
      openvpn \
      wireguard-tools-wg-quick \
      iptables \
      sysctl \
    && rm -rf /var/cache/apk/*
COPY entry.py ./entry.py
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "/bin/sh" ]
# ENTRYPOINT ["python", "/usr/src/app/entry.py"]
