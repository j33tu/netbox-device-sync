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
    """Fetches or creates parent (Floor) and child (IDF/MDF) locations."""
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


def get_or_create_rack(rack_name: str, site_id: int, location_id: int, u_height: int = 45):
    """Fetches, creates, or updates a rack to 45U, scoped strictly to its site and location_id."""
    slug = slugify(rack_name)
    
    # Scoped query by site_id AND location_id to prevent cross-location lookup conflicts
    rack = nb.dcim.racks.get(site_id=site_id, location_id=location_id, name=rack_name) or \
           nb.dcim.racks.get(site_id=site_id, location_id=location_id, slug=slug)

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
            print(f"        + Created Rack: {rack_name} ({u_height}U)")
        except RequestError as e:
            print(f"        ! Error creating Rack {rack_name}: {e}")
    else:
        # Check and update existing racks to 45U if needed
        if rack.u_height != u_height:
            rack.update({"u_height": u_height})
            print(f"        ✓ Updated Rack Height to {u_height}U: {rack_name}")
        else:
            print(f"        ✓ Found Rack in location: {rack_name} ({u_height}U)")

    return rack


# ---------------------------------------------------------------------------
# 3. Execution Pipeline
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

        # 1. Regions & Site
        parent_region = get_or_create_region(region_name)
        sub_region = get_or_create_region(sub_region_name, parent_id=parent_region.id)
        site = sync_site(site_code, sub_region.id, entry)

        # 2. Floor mappings
        idf_floors = [int(f) for f in entry.get("floors", [])]
        raw_mdf_floor = entry.get("mdf_floor")
        mdf_floor = int(raw_mdf_floor) if raw_mdf_floor is not None else None

        num_idf_racks = int(entry.get("idf_racks_per_room", 1))
        num_mdf_racks = int(entry.get("mdf_racks_per_room", 1))

        # Collect unique floor numbers
        all_floors = set(idf_floors)
        if mdf_floor is not None:
            all_floors.add(mdf_floor)

        sorted_floors = sorted(list(all_floors))

        # 3. Create Locations & Place Racks
        for floor_num in sorted_floors:
            floor_str = str(floor_num).zfill(2)

            # Parent Floor Location (e.g., AMS01-03)
            floor_location_name = f"{site.name}-{floor_str}"
            floor_loc = get_or_create_location(floor_location_name, site_id=site.id)

            # IDF Floor (e.g., Floor 03) -> Rack Name: AMS01-03-R01, AMS01-03-R02
            if floor_num in idf_floors:
                idf_location_name = f"{floor_location_name}-IDF"
                idf_loc = get_or_create_location(idf_location_name, site_id=site.id, parent_id=floor_loc.id)

                for r_num in range(1, num_idf_racks + 1):
                    rack_name = f"{floor_location_name}-R{str(r_num).zfill(2)}"
                    get_or_create_rack(rack_name, site_id=site.id, location_id=idf_loc.id, u_height=45)

            # MDF Floor (e.g., Floor 06) -> Rack Name: AMS01-06-R01, AMS01-06-R02
            if mdf_floor is not None and floor_num == mdf_floor:
                mdf_location_name = f"{floor_location_name}-MDF"
                mdf_loc = get_or_create_location(mdf_location_name, site_id=site.id, parent_id=floor_loc.id)

                for r_num in range(1, num_mdf_racks + 1):
                    rack_name = f"{floor_location_name}-R{str(r_num).zfill(2)}"
                    get_or_create_rack(rack_name, site_id=site.id, location_id=mdf_loc.id, u_height=45)


if __name__ == "__main__":
    main()