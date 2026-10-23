"""LAN helpers: detect the PC's LAN IP and decide whether a client is on a private network."""
from __future__ import annotations

import ipaddress
import socket


def lan_ip() -> str | None:
    """Best-effort local IP used to reach the LAN (no packets are sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return None


def is_private_client(host: str | None) -> bool:
    """True for loopback, RFC1918, link-local, CGNAT and IPv6 ULA/link-local addresses."""
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return host in ("localhost",)
    if addr.is_loopback or addr.is_private or addr.is_link_local:
        return True
    if isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"):
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return is_private_client(str(addr.ipv4_mapped))
    return False
