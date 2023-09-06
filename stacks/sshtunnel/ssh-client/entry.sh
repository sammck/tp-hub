#!/bin/sh

set -e

set -x

IDENTITY_ARGS=""
if [ "$1" != "-i" ]; then
    IDENTITY_ARGS="-i /ssh-keys/keyfile"
fi

ssh -o "TCPKeepAlive=yes" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=4" -o "UserKnownHostsFile=/ssh-state/known_hosts" -o "StrictHostKeyChecking=accept-new" -o "IdentitiesOnly=yes" $IDENTITY_ARGS "$@" || exit $?
