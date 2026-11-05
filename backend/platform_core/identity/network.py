"""Network zone of a client address (DEC-052 APPROVED).

* INTERNAL: inside an explicit factory CIDR range of the server configuration (``ALEEKHAN_INTERNAL_CIDRS``).
* EXTERNAL: any other parseable address, and every address in a VPN range (``ALEEKHAN_VPN_CIDRS``): VPN =
  outside.
* UNKNOWN : no address or an unparseable one (treated as outside everywhere).

The client address must come from the trusted reverse proxy (DRF ``NUM_PROXIES``; wiring in 01.4), never from
a
client-controlled header. The CIDR lists live only in server configuration, never in Git or the database.
"""

from __future__ import annotations

import ipaddress
from typing import Final

from django.conf import settings

from platform_core.schema_common import NetworkZone

OUTSIDE: Final = frozenset({NetworkZone.EXTERNAL, NetworkZone.UNKNOWN})


def _networks(name: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(c, strict=False) for c in getattr(settings, name, ())]


def classify(client_ip: str | None) -> NetworkZone:
    if not client_ip:
        return NetworkZone.UNKNOWN
    try:
        addr = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return NetworkZone.UNKNOWN
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if any(addr in net for net in _networks("ALEEKHAN_VPN_CIDRS")):
        return NetworkZone.EXTERNAL  # DEC-052: VPN = outside
    if any(addr in net for net in _networks("ALEEKHAN_INTERNAL_CIDRS")):
        return NetworkZone.INTERNAL
    return NetworkZone.EXTERNAL


def is_inside(zone: str) -> bool:
    return zone == NetworkZone.INTERNAL


def normalised_ip(client_ip: str | None) -> str | None:
    """The address as stored in ``client_ip`` columns (None if missing/unparseable)."""
    if not client_ip:
        return None
    try:
        return str(ipaddress.ip_address(client_ip.strip()))
    except ValueError:
        return None
