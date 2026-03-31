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

    Uses a UDP connect to the mDNS multicast address (224.0.0.251:5353) to ask
    the OS which interface it would use for mDNS traffic.  This is reliable
    regardless of hostname resolution — the previous getaddrinfo approach failed
    on Linux servers where the hostname only resolves to 127.0.1.1 in /etc/hosts.

    Returns False if the outgoing IP is loopback or on a Docker bridge subnet
    (172.17-31.x.x), meaning we're in a container without host networking.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("224.0.0.251", 5353))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return False

    if ip.startswith("127."):
        return False

    return not any(ip.startswith(prefix) for prefix in _BRIDGE_PREFIXES)


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
    loop = asyncio.get_running_loop()
    zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

    def on_service_state_change(
        _zc,  # Zeroconf (sync) from callback — use outer AsyncZeroconf instead
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Added:
            asyncio.run_coroutine_threadsafe(
                _resolve_and_add(zeroconf, service_type, name, found), loop
            )

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
