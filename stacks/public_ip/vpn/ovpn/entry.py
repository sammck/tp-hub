#!/bin/sh
set -e

if [ -z "$ENV_DOMAIN" ] ; then
    echo "Missing environment variable: ENV_DOMAIN"
	exit 1;
fi
if [ -z "$ENV_TOKEN" ] ; then
    echo "Missing environment variable: ENV_TOKEN"
	exit 1;
fi

current=""
while true; do
	echo ""
	latest=$(curl -s --max-time 60 https://httpbin.org/ip |jq -r .origin?)
	echo "$(date) public ipv4=$latest"
	if [ "$current" == "$latest" ]
	then
		echo "ip not changed"
	else
		echo "ip has changed - updating"
		current=$latest
		echo url="https://www.duckdns.org/update?domains=$ENV_DOMAIN&token=$ENV_TOKEN&ip=" | curl -sk -K -
	fi
	sleep 5m
done
