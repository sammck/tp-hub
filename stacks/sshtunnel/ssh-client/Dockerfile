FROM alpine:3.18

VOLUME /ssh-keys
VOLUME /ssh-state
WORKDIR /app

RUN apk add -U --no-cache openssh-client

COPY entry.sh /app/entry.sh

ENTRYPOINT [ "/bin/sh", "/app/entry.sh" ]