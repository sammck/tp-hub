sudo ip -4 rule delete table 51820
sudo ip -4 rule delete table main suppress_prefixlength 0
sudo ip link delete dev ovpn-dmz
cat <<EOF | sudo nft -f -
#!/usr/sbin/nft -f

table ip wg-quick-ovpn-dmz
delete table ip wg-quick-ovpn-dmz
EOF
