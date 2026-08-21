import os
import sys
import ipaddress
from pathlib import Path
import yaml
import urllib3
import pynetbox
from pynetbox.core.query import RequestError

# Disable HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# 1. NetBox API Configuration
# ---------------------------------------------------------------------------
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: Missing NETBOX_URL or NETBOX_TOKEN environment variable.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
nb.http_session.verify = False


# ---------------------------------------------------------------------------
# 2. Sync Logic Functions
# ---------------------------------------------------------------------------
def sync_vlan(vid: int, name: str, site_id: int, status: str = "active"):
    """Fetches or creates a VLAN scoped to a Site."""
    status_clean = status.lower()
    
    # Lookup existing VLAN by site and VID
    vlan = nb.ipam.vlans.get(site_id=site_id, vid=vid)

    payload = {
        "vid": vid,
        "name": name,
        "site": site_id,
        "status": status_clean
    }

    if not vlan:
        try:
            vlan = nb.ipam.vlans.create(payload)
            print(f"  + Created VLAN {vid} ('{name}') [Status: {status_clean}]")
        except RequestError as e:
            print(f"  ! Error creating VLAN {vid}: {e}")
            return None
    else:
        vlan.update(payload)
        print(f"  ✓ Updated VLAN {vid} ('{name}') [Status: {status_clean}]")

    return vlan


def sync_prefix(network: ipaddress.IPv4Network, site_id: int, vlan_id: int, status: str = "active"):
    """Creates or updates a Prefix tied to a Site and VLAN."""
    prefix_str = str(network)
    status_clean = status.lower()

    prefix_obj = nb.ipam.prefixes.get(prefix=prefix_str, vrf_id="null")

    payload = {
        "prefix": prefix_str,
        "site": site_id,
        "vlan": vlan_id,
        "status": status_clean,
        "vrf": None
    }

    if not prefix_obj:
        try:
            prefix_obj = nb.ipam.prefixes.create(payload)
            print(f"    + Created Prefix: {prefix_str}")
        except RequestError as e:
            print(f"    ! Error creating Prefix {prefix_str}: {e}")
            return None
    else:
        prefix_obj.update(payload)
        print(f"    ✓ Updated Prefix: {prefix_str}")

    return prefix_obj


def sync_gateway(network: ipaddress.IPv4Network, site_id: int, position: str = "first", status: str = "active"):
    """Creates default gateway IP address within the prefix."""
    if not position or position.lower() == "none":
        return None

    if position.lower() == "first":
        gw_ip = network.network_address + 1
    elif position.lower() == "last":
        gw_ip = network.broadcast_address - 1
    else:
        gw_ip = ipaddress.IPv4Address(position)

    gw_str = f"{gw_ip}/{network.prefixlen}"
    
    ip_obj = nb.ipam.ip_addresses.get(address=gw_str, vrf_id="null")

    payload = {
        "address": gw_str,
        "status": status.lower(),
        "description": "Default Gateway",
        "site": site_id,
        "vrf": None
    }

    if not ip_obj:
        try:
            ip_obj = nb.ipam.ip_addresses.create(payload)
            print(f"      + Created Gateway IP: {gw_str}")
        except RequestError as e:
            print(f"      ! Error creating Gateway {gw_str}: {e}")
    else:
        ip_obj.update(payload)
        print(f"      ✓ Updated Gateway IP: {gw_str}")

    return ip_obj


# ---------------------------------------------------------------------------
# 3. Execution Pipeline
# ---------------------------------------------------------------------------
def main():
    BASE_DIR = Path(__file__).resolve().parent.parent
    file_path = BASE_DIR / "inputs" / "vlans_and_prefixes.yml"

    if not file_path.exists():
        print(f"File {file_path} not found.")
        sys.exit(0)

    with open(file_path, "r") as f:
        data = yaml.safe_load(f) or {}

    allocations = data.get("vlan_allocations", [])

    print(f"\nProcessing {len(allocations)} VLAN & Prefix entries...")

    for entry in allocations:
        site_code = entry.get("site_code")
        vlan_id = entry.get("vlan_id")
        vlan_name = entry.get("vlan_name")
        cidr = entry.get("cidr")
        status = entry.get("status", "active")
        gateway_pos = entry.get("gateway", "first")

        if not all([site_code, vlan_id, vlan_name, cidr]):
            print(f" ! Missing required parameters in entry: {entry}")
            continue

        # 1. Resolve Site
        site_obj = nb.dcim.sites.get(name=site_code) or nb.dcim.sites.get(slug=site_code.lower())
        if not site_obj:
            print(f" ! Site '{site_code}' not found in NetBox. Skipping...")
            continue

        network = ipaddress.ip_network(cidr, strict=False)

        print(f"\nSite: {site_code} | VLAN {vlan_id} ({vlan_name})")

        # 2. Sync VLAN
        vlan_obj = sync_vlan(vid=vlan_id, name=vlan_name, site_id=site_obj.id, status=status)

        if vlan_obj:
            # 3. Sync Prefix attached to VLAN
            sync_prefix(network=network, site_id=site_obj.id, vlan_id=vlan_obj.id, status=status)

            # 4. Sync Gateway IP
            sync_gateway(network=network, site_id=site_obj.id, position=gateway_pos, status=status)


if __name__ == "__main__":
    main()