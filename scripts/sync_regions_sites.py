import os
import sys
from pathlib import Path
import yaml
import pynetbox

# ---------------------------------------------------------------------------
# 1. NetBox API Configuration
# ---------------------------------------------------------------------------
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: Missing NETBOX_URL or NETBOX_TOKEN environment variable.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

# ---------------------------------------------------------------------------
# 2. Locate Input File Relative to Repository Root
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
file_path = BASE_DIR / "inputs" / "regions_and_sites.yml"

if not file_path.exists():
    print(f"File {file_path} not found. Skipping execution.")
    sys.exit(0)

with open(file_path, "r") as f:
    data = yaml.safe_load(f) or {}

# ---------------------------------------------------------------------------
# 3. Helper Function to Sync Sites
# ---------------------------------------------------------------------------
def sync_site(site_data, region_id):
    """
    Creates or updates a site assigned to a specific NetBox Region ID.
    """
    s_name = site_data.get("name")
    s_slug = site_data.get("slug")

    if not s_name or not s_slug:
        print("  ! Skipping site: Missing 'name' or 'slug'")
        return

    payload = {
        "name": s_name,
        "slug": s_slug,
        "region": region_id,
        "status": site_data.get("status", "active"),
        "facility": site_data.get("facility", ""),
        "time_zone": site_data.get("time_zone", ""),
    }

    site = nb.dcim.sites.get(slug=s_slug)
    if not site:
        nb.dcim.sites.create(payload)
        print(f"    + Created Site: {s_name} ({s_slug})")
    else:
        # Re-assign region ID in payload for updates
        payload["region"] = region_id
        site.update(payload)
        print(f"    ✓ Updated Site: {s_name} ({s_slug})")

# ---------------------------------------------------------------------------
# 4. Main Sync Logic (Regions -> Child Regions -> Sites)
# ---------------------------------------------------------------------------
def main():
    regions_list = data.get("regions", [])
    if not regions_list:
        print("No regions defined in input file.")
        return

    for parent_data in regions_list:
        p_name = parent_data.get("name")
        p_slug = parent_data.get("slug")

        if not p_name or not p_slug:
            continue

        # A. Create / Get Parent Region
        parent_region = nb.dcim.regions.get(slug=p_slug)
        if not parent_region:
            parent_region = nb.dcim.regions.create(name=p_name, slug=p_slug)
            print(f"+ Created Parent Region: {p_name} ({p_slug})")
        else:
            print(f"✓ Parent Region exists: {p_name} ({p_slug})")

        # B. Process Sites assigned directly to Parent Region (if any)
        for site_data in parent_data.get("sites", []):
            sync_site(site_data, parent_region.id)

        # C. Process Child Regions & Child Region Sites
        for child_data in parent_data.get("child_regions", []):
            c_name = child_data.get("name")
            c_slug = child_data.get("slug")

            if not c_name or not c_slug:
                continue

            child_region = nb.dcim.regions.get(slug=c_slug)
            if not child_region:
                child_region = nb.dcim.regions.create(
                    name=c_name,
                    slug=c_slug,
                    parent=parent_region.id
                )
                print(f"  + Created Child Region: {c_name} ({c_slug}) under {p_name}")
            else:
                # Ensure parent hierarchy remains correct
                if child_region.parent and child_region.parent.id != parent_region.id:
                    child_region.update({"parent": parent_region.id})
                print(f"  ✓ Child Region exists: {c_name} ({c_slug})")

            # Sync all sites associated with this Child Region
            for site_data in child_data.get("sites", []):
                sync_site(site_data, child_region.id)

if __name__ == "__main__":
    main()