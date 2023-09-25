#!/bin/bash

ip link add ovpn-dmz type wireguard
wg setconf ovpn-dmz /dev/fd/63
ip -4 address add 156.146.51.235/32 dev ovpn-dmz
ip link set mtu 1420 up dev ovpn-dmz
wg set ovpn-dmz fwmark 51820
ip -4 route add 0.0.0.0/0 dev ovpn-dmz table 51820
ip -4 rule add not fwmark 51820 table 51820
ip -4 rule add table main suppress_prefixlength 0
sysctl -q net.ipv4.conf.all.src_valid_mark=1
cat <<EOF | sudo nft -f -
#!/usr/sbin/nft -f

table ip wg-quick-ovpn-dmz
flush table ip wg-quick-ovpn-dmz

table ip wg-quick-ovpn-dmz {
        chain preraw {
                type filter hook prerouting priority raw; policy accept;
                iifname != "ovpn-dmz" ip daddr 156.146.51.235 fib saddr type != local drop
        }

        chain premangle {
                type filter hook prerouting priority mangle; policy accept;
                meta l4proto udp meta mark set ct mark
        }

        chain postmangle {
                type filter hook postrouting priority mangle; policy accept;
                meta l4proto udp meta mark 0x0000ca6c ct mark set meta mark
        }
}
EOF
