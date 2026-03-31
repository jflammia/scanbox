"""mDNS scanner discovery via zeroconf (eSCL/AirScan service types)."""

import asyncio
import socket
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

ESCL_SERVICE_TYPES = ["_uscan._tcp.local.", "_uscans._tcp.local."]

DISCOVERY_HINT = (
    "No scanners found. Make sure your scanner is turned on and connected to the same network. "
    "If running in Docker, use network_mode: host in your compose file so ScanBox can "
    "discover scanners via mDNS. You can also enter the scanner's IP address manually."
)

BRIDGE_NETWORK_HINT = (
    "Scanner discovery is unavailable. ScanBox appears to be running on a Docker bridge "
    "network, which blocks mDNS multicast. Add network_mode: host to your Docker Compose "
    "file to enable automatic scanner discovery."
)

# Docker/Podman bridge subnets (default ranges)
_BRIDGE_PREFIXES = (
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
)


def mdns_available() -> bool:
    """Check if mDNS discovery is likely to work.

    Returns False if the only non-loopback IPs are on Docker bridge subnets
    (172.17-31.x.x), which means we're in a container without host networking
    and mDNS multicast won't reach the LAN.

    Returns True on host networking, macvlan, or bare metal (any non-bridge
    LAN IP found).
    """
    try:
        addrs = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        ips = {info[4][0] for info in addrs}
    except socket.gaierror:
        ips = set()

    # Filter out loopback
    non_loopback = {ip for ip in ips if not ip.startswith("127.")}

    if not non_loopback:
        # No network interfaces at all — can't do mDNS
        return False

    # If every non-loopback IP is on a Docker bridge subnet, mDNS won't work
    all_bridge = all(
        any(ip.startswith(prefix) for prefix in _BRIDGE_PREFIXES) for ip in non_loopback
    )
    return not all_bridge


@dataclass
class DiscoveredScanner:
    ip: str
    port: int
    name: str
    model: str
    base_path: str
    uuid: str
    icon_url: str
    secure: bool


def _dedup_scanners(scanners: list[DiscoveredScanner]) -> list[DiscoveredScanner]:
    """Deduplicate scanners by UUID, preferring secure entries."""
    by_uuid: dict[str, DiscoveredScanner] = {}
    for scanner in scanners:
        key = scanner.uuid
        if key not in by_uuid or (scanner.secure and not by_uuid[key].secure):
            by_uuid[key] = scanner
    return list(by_uuid.values())


async def discover_scanners(timeout: float = 5.0) -> list[DiscoveredScanner]:
    """Discover eSCL scanners on the local network via mDNS.

    Browses both _uscan._tcp.local. and _uscans._tcp.local. service types,
    resolves each discovered service to extract IP, port, and TXT record fields,
    then returns deduplicated results (preferring secure entries).
    """
    found: list[DiscoveredScanner] = []
    zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

    def on_service_state_change(
        zeroconf_instance: AsyncZeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Added:
            asyncio.ensure_future(_resolve_and_add(zeroconf_instance, service_type, name, found))

    browser = AsyncServiceBrowser(
        zeroconf.zeroconf,
        ESCL_SERVICE_TYPES,
        handlers=[on_service_state_change],
    )

    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()
        await zeroconf.async_close()

    return _dedup_scanners(found)


async def _resolve_and_add(
    zeroconf: AsyncZeroconf,
    service_type: str,
    name: str,
    found: list[DiscoveredScanner],
) -> None:
    """Resolve a discovered service and append a DiscoveredScanner to found."""
    info = AsyncServiceInfo(service_type, name)
    resolved = await info.async_request(zeroconf.zeroconf, timeout=3000)
    if not resolved:
        return

    addresses = info.parsed_addresses(IPVersion.V4Only)
    if not addresses:
        return

    ip = addresses[0]
    port = info.port or 80
    props = info.decoded_properties

    model = props.get("ty", "") or ""
    base_path = props.get("rs", "") or ""
    uuid = props.get("UUID", "") or ""
    icon_url = props.get("representation", "") or ""
    secure = service_type.startswith("_uscans")

    found.append(
        DiscoveredScanner(
            ip=ip,
            port=port,
            name=name,
            model=model,
            base_path=base_path,
            uuid=uuid,
            icon_url=icon_url,
            secure=secure,
        )
    )
