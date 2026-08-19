import os
import sys
import re
from pathlib import Path
import yaml
import pynetbox
from pynetbox.core.query import RequestError

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
# 2. Helpers
# ---------------------------------------------------------------------------
def format_site_code(raw_name: str) -> str:
    """Transforms site names like 'Tokyo 02' into 'TOK02'."""
    clean_text = raw_name.strip()
    letters = re.sub(r"[^a-zA-Z]", "", clean_text)
    digits = re.sub(r"[^0-9]", "", clean_text)
    prefix = letters[:3].upper().ljust(3, "X")
    suffix = digits.zfill(2) if digits else ""
    return f"{prefix}{suffix}"


def slugify(text: str) -> str:
    """Generates a clean, NetBox-compliant slug."""
    text = str(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


def get_or_create_region(name: str, parent_id: int = None):
    """Fetches or creates a region/sub-region."""
    slug = slugify(name)
    region = nb.dcim.regions.get(slug=slug) or nb.dcim.regions.get(name=name)

    if not region:
        data = {"name": name, "slug": slug}
        if parent_id:
            data["parent"] = parent_id
        try:
            region = nb.dcim.regions.create(data)
            print(f"  + Created Region: '{name}' ({slug})")
        except RequestError:
            region = nb.dcim.regions.get(name=name) or nb.dcim.regions.get(slug=slug)
            print(f"  ✓ Found Existing Region: '{name}' ({slug})")
    else:
        if parent_id and (not region.parent or region.parent.id != parent_id):
            region.update({"parent": parent_id})
            print(f"  ✓ Updated Region Parent for: '{name}'")
        else:
            print(f"  ✓ Found Region: '{name}' ({slug})")
            
    return region


def sync_site(formatted_code: str, sub_region_id: int, site_meta: dict):
    """Creates or updates a site."""
    slug = slugify(formatted_code)
    payload = {
        "name": formatted_code,
        "slug": slug,
        "region": sub_region_id,
        "status": site_meta.get("status", "active"),
        "facility": site_meta.get("facility", ""),
        "time_zone": site_meta.get("time_zone", ""),
    }

    site = nb.dcim.sites.get(slug=slug) or nb.dcim.sites.get(name=formatted_code)
    
    if not site:
        try:
            site = nb.dcim.sites.create(payload)
            print(f"    + Created Site: {formatted_code}")
        except RequestError:
            site = nb.dcim.sites.get(name=formatted_code)
            print(f"    ✓ Found Site: {formatted_code}")
    else:
        payload["region"] = sub_region_id
        site.update(payload)
        print(f"    ✓ Updated Site: {formatted_code}")
        
    return site


def get_or_create_location(name: str, site_id: int, parent_id: int = None):
    """Fetches or creates parent and child locations."""
    slug = slugify(name)
    location = nb.dcim.locations.get(site_id=site_id, slug=slug) or nb.dcim.locations.get(site_id=site_id, name=name)

    if not location:
        data = {"name": name, "slug": slug, "site": site_id}
        if parent_id:
            data["parent"] = parent_id
        try:
            location = nb.dcim.locations.create(data)
            print(f"      + Created Location: {name}")
        except RequestError:
            location = nb.dcim.locations.get(site_id=site_id, name=name)
            print(f"      ✓ Found Location: {name}")
    else:
        print(f"      ✓ Found Location: {name}")
        
    return location


def get_or_create_rack(rack_name: str, site_id: int, location_id: int, u_height: int = 42):
    """Fetches or creates a rack within a specific Location in NetBox."""
    slug = slugify(rack_name)
    rack = nb.dcim.racks.get(site_id=site_id, name=rack_name) or nb.dcim.racks.get(site_id=site_id, slug=slug)

    if not rack:
        data = {
            "name": rack_name,
            "slug": slug,
            "site": site_id,
            "location": location_id,
            "u_height": u_height,
            "status": "active"
        }
        try:
            rack = nb.dcim.racks.create(data)
            print(f"        + Created Rack: {rack_name}")
        except RequestError:
            rack = nb.dcim.racks.get(site_id=site_id, name=rack_name)
            print(f"        ✓ Found Rack: {rack_name}")
    else:
        # Ensure correct location assignment
        if not rack.location or rack.location.id != location_id:
            rack.update({"location": location_id})
            print(f"        ✓ Updated Location for Rack: {rack_name}")
        else:
            print(f"        ✓ Found Rack: {rack_name}")

    return rack

# ---------------------------------------------------------------------------
# 3. Main Logic
# ---------------------------------------------------------------------------
def main():
    BASE_DIR = Path(__file__).resolve().parent.parent
    file_path = BASE_DIR / "inputs" / "regions_and_sites.yml"

    if not file_path.exists():
        print(f"File {file_path} not found. Skipping execution.")
        sys.exit(0)

    with open(file_path, "r") as f:
        data = yaml.safe_load(f) or {}

    site_entries = data.get("sites", [])
    if not site_entries:
        print("No sites defined in YAML file.")
        return

    for entry in site_entries:
        region_name = entry.get("region")
        sub_region_name = entry.get("sub_region")
        raw_site_name = entry.get("site_name")

        if not all([region_name, sub_region_name, raw_site_name]):
            print(f" ! Skipping entry due to missing required fields -> {entry}")
            continue

        site_code = format_site_code(raw_site_name)
        print(f"\nProcessing: {region_name} > {sub_region_name} > {site_code} (from '{raw_site_name}')")

        # 1. Regions
        parent_region = get_or_create_region(region_name)
        sub_region = get_or_create_region(sub_region_name, parent_id=parent_region.id)

        # 2. Site
        site = sync_site(site_code, sub_region.id, entry)

        # 3. Extract Floor & Rack Specifications
        idf_floors = [str(f).strip() for f in entry.get("floors", [])]
        raw_mdf_floor = entry.get("mdf_floor")
        mdf_floor_str = str(raw_mdf_floor).strip() if raw_mdf_floor is not None else None

        num_idf_racks = int(entry.get("idf_racks_per_room", 1))
        num_mdf_racks = int(entry.get("mdf_racks_per_room", 1))

        # Build total list of unique floors to process
        all_floors = set(idf_floors)
        if mdf_floor_str:
            all_floors.add(mdf_floor_str)

        sorted_floors = sorted(list(all_floors), key=lambda x: int(x) if x.isdigit() else x)

        # 4. Generate Locations & Racks
        for raw_floor in sorted_floors:
            floor_str = str(raw_floor).zfill(2)

            # Parent Floor Location: AMS01-03
            floor_location_name = f"{site.name}-{floor_str}"
            floor_loc = get_or_create_location(floor_location_name, site_id=site.id)

            # Process IDF Room & Racks
            if raw_floor in idf_floors:
                idf_location_name = f"{floor_location_name}-IDF"
                idf_loc = get_or_create_location(idf_location_name, site_id=site.id, parent_id=floor_loc.id)

                # Create requested number of IDF Racks (e.g., AMS01-03-R01, AMS01-03-R02)
                for r_num in range(1, num_idf_racks + 1):
                    rack_name = f"{floor_location_name}-R{str(r_num).zfill(2)}"
                    get_or_create_rack(rack_name, site_id=site.id, location_id=idf_loc.id)

            # Process MDF Room & Racks
            if mdf_floor_str and raw_floor == mdf_floor_str:
                mdf_location_name = f"{floor_location_name}-MDF"
                mdf_loc = get_or_create_location(mdf_location_name, site_id=site.id, parent_id=floor_loc.id)

                # Create requested number of MDF Racks (e.g., AMS01-03-MR01, AMS01-03-MR02)
                for r_num in range(1, num_mdf_racks + 1):
                    rack_name = f"{floor_location_name}-MR{str(r_num).zfill(2)}"
                    get_or_create_rack(rack_name, site_id=site.id, location_id=mdf_loc.id)

if __name__ == "__main__":
    main()