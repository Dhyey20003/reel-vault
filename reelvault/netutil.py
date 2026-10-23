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


_VIRTUAL_HINTS = ("docker", "veth", "br-", "vmnet", "vbox", "virbr", "tun", "tap", "utun", "wg", "zt", "tailscale", "hyper-v", "vethernet", "lo")


def lan_candidates() -> list[dict]:
    """All private IPv4 addresses on this machine, best first. Virtual/VPN adapters and CGNAT are listed but ranked last.
    Uses psutil-free stdlib probing: socket.getaddrinfo plus a UDP connect trick per default route."""
    found: dict[str, dict] = {}
    primary = lan_ip()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or not is_private_client(ip):
                continue
            found.setdefault(ip, {"ip": ip, "adapter": "", "virtual": False})
    except OSError:
        pass
    if primary and is_private_client(primary):
        found.setdefault(primary, {"ip": primary, "adapter": "", "virtual": False})
    # Try to label adapters with `ip`/`ifconfig`/`ipconfig` when available (best effort, no extra deps).
    try:
        import subprocess, re, sys
        if sys.platform.startswith("linux"):
            out = subprocess.run(["ip", "-o", "-4", "addr"], capture_output=True, text=True, timeout=5).stdout
            for m in re.finditer(r"^\d+:\s+(\S+)\s+inet\s+([\d.]+)", out, re.M):
                name, ip = m.group(1), m.group(2)
                if ip in found:
                    found[ip]["adapter"] = name
                elif is_private_client(ip) and not ip.startswith("127."):
                    found[ip] = {"ip": ip, "adapter": name, "virtual": False}
        elif sys.platform == "darwin":
            out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5).stdout
            cur = ""
            for line in out.splitlines():
                if line and not line[0].isspace():
                    cur = line.split(":")[0]
                m = re.search(r"\binet\s+([\d.]+)", line)
                if m:
                    ip = m.group(1)
                    if ip.startswith("127.") or not is_private_client(ip):
                        continue
                    found.setdefault(ip, {"ip": ip, "adapter": cur, "virtual": False})["adapter"] = cur
        else:
            out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5).stdout
            cur = ""
            for line in out.splitlines():
                if line and not line[0].isspace() and line.strip().endswith(":"):
                    cur = line.strip().rstrip(":")
                m = re.search(r"IPv4.*?:\s*([\d.]+)", line)
                if m:
                    ip = m.group(1)
                    if ip.startswith("127.") or not is_private_client(ip):
                        continue
                    found.setdefault(ip, {"ip": ip, "adapter": cur, "virtual": False})["adapter"] = cur
    except (OSError, subprocess.SubprocessError):
        pass
    for c in found.values():
        name = (c["adapter"] or "").lower()
        cg = ipaddress.ip_address(c["ip"]) in ipaddress.ip_network("100.64.0.0/10")
        c["virtual"] = cg or any(h in name for h in _VIRTUAL_HINTS) or c["ip"].startswith("169.254.")
        c["reason"] = "CGNAT/VPN range" if cg else ("virtual or VPN adapter" if c["virtual"] else "")
    ordered = sorted(found.values(), key=lambda c: (c["virtual"], c["ip"] != primary, c["ip"]))
    return ordered
