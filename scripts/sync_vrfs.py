import os
import sys
import re
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
# 2. Helpers & VRF Sync
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Generates a clean, NetBox-compliant slug."""
    text = str(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def sync_vrf(vrf_data: dict):
    """Fetches, creates, or updates a VRF in NetBox."""
    name = vrf_data.get("name")
    if not name:
        print("  ! Skipping VRF entry with missing name.")
        return None

    rd = vrf_data.get("rd", None)
    description = vrf_data.get("description", "")
    enforce_unique = vrf_data.get("enforce_unique", True)

    # 1. Specific exact-name lookup
    vrfs_matching = list(nb.ipam.vrfs.filter(name=name))
    vrf = vrfs_matching[0] if vrfs_matching else None

    payload = {
        "name": name,
        "description": description,
        "enforce_unique": enforce_unique,
    }
    
    # Only supply RD if defined (NetBox throws errors on null RDs if unique constraints trigger)
    if rd:
        payload["rd"] = rd

    if not vrf:
        try:
            vrf = nb.ipam.vrfs.create(payload)
            rd_str = f" (RD: {rd})" if rd else ""
            print(f"  + Created VRF: '{name}'{rd_str}")
        except RequestError as e:
            print(f"  ! Error creating VRF '{name}': {e}")
            return None
    else:
        try:
            vrf.update(payload)
            rd_str = f" (RD: {rd})" if rd else ""
            print(f"  ✓ Updated VRF: '{name}'{rd_str}")
        except RequestError as e:
            print(f"  ! Error updating VRF '{name}': {e}")

    return vrf


# ---------------------------------------------------------------------------
# 3. Execution Pipeline
# ---------------------------------------------------------------------------
def main():
    BASE_DIR = Path(__file__).resolve().parent.parent
    file_path = BASE_DIR / "inputs" / "vrfs.yml"

    if not file_path.exists():
        print(f"File {file_path} not found.")
        sys.exit(1)

    with open(file_path, "r") as f:
        data = yaml.safe_load(f) or {}

    vrf_entries = data.get("vrfs", [])

    if not vrf_entries:
        print("No VRFs defined in YAML file.")
        return

    print(f"\nProcessing {len(vrf_entries)} VRF entries...")
    for entry in vrf_entries:
        sync_vrf(entry)


if __name__ == "__main__":
    main()