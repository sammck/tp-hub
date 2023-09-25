OVPN  VPN port-forwarding stack
===================================================

If you use [OVPN](https://www.ovpn.com) as a VPN service provider, and you have subscribed to their _Public IPv4_ add-on service,
then you can use this container to instantiate a network adapter that has a public IP address with all ports open.

Since creating a VPN client using the _Public IPv4_ mechanism opens *ALL* ports, it is important to firewall
the adapter so that unintended ports (e.g., the Traefik intranet entrypoints) on the host are not accessible from the Internet.

This stack creates the adapter inside a container so it is easier to isolate.

