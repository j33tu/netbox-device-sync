import os
import sys
import ipaddress
from pathlib import Path
import yaml
import urllib3
import pynetbox
from pynetbox.core.query import RequestError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: Missing NETBOX_URL or NETBOX_TOKEN environment variable.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
nb.http_session.verify = False


def sync_prefix(network: ipaddress.IPv4Network, site_id: int, role_name: str, vrf_id: int = None):
    """Creates or updates the parent IP Prefix."""
    prefix_str = str(network)
    
    lookup = {"prefix": prefix_str, "vrf_id": vrf_id if vrf_id else "null"}
    prefix_obj = nb.ipam.prefixes.get(**lookup)

    payload = {
        "prefix": prefix_str,
        "site": site_id,
        "vrf": vrf_id,
        "status": "active"
    }

    if not prefix_obj:
        try:
            prefix_obj = nb.ipam.prefixes.create(payload)
            print(f"  + Created Prefix: {prefix_str}")
        except RequestError as e:
            print(f"  ! Error creating prefix {prefix_str}: {e}")
            return None
    else:
        print(f"  ✓ Found Prefix: {prefix_str}")

    return prefix_obj


def sync_gateway(network: ipaddress.IPv4Network, site_id: int, position: str = "first", vrf_id: int = None):
    """Creates the default gateway IP address within the subnet."""
    if position.lower() == "none":
        return None

    if position.lower() == "first":
        gw_ip = network.network_address + 1
    elif position.lower() == "last":
        gw_ip = network.broadcast_address - 1
    else:
        gw_ip = ipaddress.IPv4Address(position)

    gw_str = f"{gw_ip}/{network.prefixlen}"
    
    lookup = {"address": gw_str, "vrf_id": vrf_id if vrf_id else "null"}
    ip_obj = nb.ipam.ip_addresses.get(**lookup)

    if not ip_obj:
        payload = {
            "address": gw_str,
            "status": "active",
            "description": "Default Gateway",
            "vrf": vrf_id,
            "site": site_id
        }
        try:
            ip_obj = nb.ipam.ip_addresses.create(payload)
            print(f"    + Created Gateway IP: {gw_str}")
        except RequestError as e:
            print(f"    ! Error creating Gateway {gw_str}: {e}")
    else:
        print(f"    ✓ Found Gateway IP: {gw_str}")

    return ip_obj


def sync_ip_range(network: ipaddress.IPv4Network, pool: dict, site_id: int, vrf_id: int = None):
    """Calculates start and end addresses from offsets and creates an IP Range."""
    start_offset = pool.get("start_offset")
    end_offset = pool.get("end_offset")
    status = pool.get("status", "active")
    description = pool.get("description", "")

    start_ip = network.network_address + start_offset
    end_ip = network.network_address + end_offset

    start_str = f"{start_ip}/{network.prefixlen}"
    end_str = f"{end_ip}/{network.prefixlen}"

    lookup = {
        "start_address": start_str,
        "end_address": end_str,
        "vrf_id": vrf_id if vrf_id else "null"
    }

    range_obj = nb.ipam.ip_ranges.get(**lookup)

    payload = {
        "start_address": start_str,
        "end_address": end_str,
        "status": status,
        "description": description,
        "vrf": vrf_id,
        "site": site_id
    }

    if not range_obj:
        try:
            range_obj = nb.ipam.ip_ranges.create(payload)
            print(f"    + Created Range: {start_str} - {end_str} [Size: {range_obj.size}] ({description})")
        except RequestError as e:
            print(f"    ! Error creating Range {start_str} - {end_str}: {e}")
    else:
        range_obj.update(payload)
        print(f"    ✓ Updated Range: {start_str} - {end_str} [Size: {range_obj.size}]")

    return range_obj


def main():
    BASE_DIR = Path(__file__).resolve().parent.parent
    file_path = BASE_DIR / "inputs" / "ipam_structure.yml"

    if not file_path.exists():
        print(f"File {file_path} not found.")
        sys.exit(0)

    with open(file_path, "r") as f:
        data = yaml.safe_load(f) or {}

    allocations = data.get("ipam_allocations", [])

    for entry in allocations:
        site_code = entry.get("site_code")
        cidr = entry.get("cidr")
        gateway_pos = entry.get("gateway", "first")
        role = entry.get("role", "")
        pools = entry.get("pools", [])

        if not cidr:
            continue

        network = ipaddress.ip_network(cidr, strict=False)

        # 1. Site Lookup
        site_obj = nb.dcim.sites.get(name=site_code) or nb.dcim.sites.get(slug=site_code.lower()) if site_code else None
        site_id = site_obj.id if site_obj else None

        print(f"\nProcessing Subnet: {cidr} for Site: {site_code or 'Global'}")

        # 2. Sync Parent Prefix
        sync_prefix(network, site_id, role, vrf_id=None)

        # 3. Sync Gateway IP
        sync_gateway(network, site_id, position=gateway_pos, vrf_id=None)

        # 4. Sync IP Ranges inside the subnet
        for pool in pools:
            sync_ip_range(network, pool, site_id, vrf_id=None)


if __name__ == "__main__":
    main()