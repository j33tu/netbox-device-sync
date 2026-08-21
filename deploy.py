import os
import glob
import yaml
import pynetbox
import urllib3

# Suppress SSL warnings for self-signed certificates on internal NetBox servers
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# NetBox Connection Setup
URL = os.getenv("NETBOX_URL", "https://netbox.yourcompany.com")
TOKEN = os.getenv("NETBOX_TOKEN", "your_token_here")

nb = pynetbox.api(URL, token=TOKEN)
nb.http_session.verify = False

# Fixed Enterprise VLAN Schema (/21 CIDR-Aligned Subnets)
STANDARD_VLANS = [
    {"vid": 64,  "name": "SECURITY", "base_octet": 64,  "mask": "21"},  # 10.X.64.0/21  (Range: 64.0 - 71.255)
    {"vid": 72,  "name": "IOT",      "base_octet": 72,  "mask": "21"},  # 10.X.72.0/21  (Range: 72.0 - 79.255)
    {"vid": 136, "name": "CORP",     "base_octet": 136, "mask": "21"},  # 10.X.136.0/21 (Range: 136.0 - 143.255)
    {"vid": 200, "name": "AV",       "base_octet": 200, "mask": "21"},  # 10.X.200.0/21 (Range: 200.0 - 207.255)
    {"vid": 240, "name": "GUEST",    "base_octet": 240, "mask": "21"},  # 10.X.240.0/21 (Range: 240.0 - 247.255)
    {"vid": 255, "name": "MGMT",     "base_octet": 254, "mask": "23"},  # 10.X.248.0/21 (Range: 248.0 - 255.255)
]

def format_floor(val):
    """Ensure double-digit string formatting for floors (e.g., 3 -> '03')."""
    return str(val).zfill(2)

def process_site(filepath):
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    # 1. Parse Site Data
    region_name = str(data["region"]).upper()
    subregion_name = str(data["subregion"]).upper()
    site_code = str(data["site_code"]).upper()
    facility = data.get("facility", "")
    time_zone = data.get("time_zone", "UTC")
    site_num = int(data["site_code_numeric"])

    print(f"\n==================================================")
    print(f" PROCESSING SITE: {site_code} (Site Code Numeric: {site_num})")
    print(f"==================================================")

    # 2. Safety Rule: Validate MDF and IDF Floor Separation
    mdf_floor = format_floor(data["mdf"]["floor"])
    idf_floors = [format_floor(i["floor"]) for i in data.get("idfs", [])]

    if mdf_floor in idf_floors:
        print(f"❌ ERROR: Site {site_code} has MDF and IDF co-located on Floor {mdf_floor}. Aborting build.")
        return False

    print("✓ Business Rules: Floor separation check passed.")

    # 3. Provision Region, Subregion, and Site
    region = nb.dcim.regions.get(slug=region_name.lower())
    if not region:
        region = nb.dcim.regions.create(name=region_name, slug=region_name.lower())

    subregion = nb.dcim.regions.get(slug=subregion_name.lower())
    if not subregion:
        subregion = nb.dcim.regions.create(name=subregion_name, slug=subregion_name.lower(), parent=region.id)

    site = nb.dcim.sites.get(slug=site_code.lower())
    site_payload = {
        "name": site_code,
        "slug": site_code.lower(),
        "region": subregion.id,
        "facility": facility,
        "time_zone": time_zone,
        "status": "active"
    }

    if not site:
        site = nb.dcim.sites.create(site_payload)
        print(f"✓ Created Site: {site_code}")
    else:
        site.update(site_payload)
        print(f"✓ Site Exists/Updated: {site_code}")

    # 4. Provision Standard VLANs and Map Direct IPAM Prefixes
    print("\n--> Provisioning IPAM Subnets & Standard VLANs...")
    for vlan_cfg in STANDARD_VLANS:
        vid = int(vlan_cfg["vid"])
        vlan_name = f"{site_code}-{vlan_cfg['name']}"
        prefix_cidr = f"10.{site_num}.{vlan_cfg['base_octet']}.0/{vlan_cfg['mask']}"

        # Step 4a: Create/Retrieve NetBox VLAN
        vlan_obj = nb.ipam.vlans.get(site_id=site.id, vid=vid)
        if not vlan_obj:
            vlan_obj = nb.ipam.vlans.create(
                name=vlan_name,
                vid=vid,
                site=site.id,
                status="active"
            )
            print(f"   + Created VLAN {vid:<3} ({vlan_name})")
        else:
            if vlan_obj.name != vlan_name:
                vlan_obj.update({"name": vlan_name})
            print(f"   + Existing VLAN {vid:<3} ({vlan_obj.name})")

        # Step 4b: Create/Retrieve Prefix & Directly Map to VLAN Object ID
        prefix_obj = nb.ipam.prefixes.get(prefix=prefix_cidr)
        
        prefix_payload = {
            "prefix": prefix_cidr,
            "site": site.id,
            "vlan": vlan_obj.id,  # Direct foreign-key binding to VLAN in NetBox
            "status": "active",
            "description": f"{site_code} {vlan_cfg['name']} Subnet"
        }

        if not prefix_obj:
            prefix_obj = nb.ipam.prefixes.create(prefix_payload)
            print(f"      └── Bound Subnet: {prefix_cidr:<15} ---> VLAN {vid:<3} ({vlan_name})")
        else:
            # Update VLAN association if missing or pointing to wrong VLAN
            if not getattr(prefix_obj, "vlan", None) or prefix_obj.vlan.id != vlan_obj.id:
                prefix_obj.update({"vlan": vlan_obj.id, "site": site.id})
            print(f"      └── Verified Mapping: {prefix_cidr:<15} ---> VLAN {vid:<3} ({vlan_name})")

    # 5. Build Locations, Sub-Locations, and Racks
    print("\n--> Provisioning Locations, Sub-Locations & Racks...")
    rooms = [{"floor": mdf_floor, "type": "MDF", "racks": int(data["mdf"]["racks"])}]
    for idf in data.get("idfs", []):
        rooms.append({"floor": format_floor(idf["floor"]), "type": "IDF", "racks": int(idf["racks"])})

    for room in rooms:
        floor_str = room["floor"]
        room_type = room["type"]

        # Floor Location (e.g. FIZ01-06)
        floor_loc_name = f"{site_code}-{floor_str}"
        floor_loc = nb.dcim.locations.get(site_id=site.id, slug=floor_loc_name.lower())
        if not floor_loc:
            floor_loc = nb.dcim.locations.create(name=floor_loc_name, slug=floor_loc_name.lower(), site=site.id, status="active")
            print(f"   [Floor Location Created]: {floor_loc_name}")

        # Sub-Location (e.g. FIZ01-06-MDF)
        sub_loc_name = f"{site_code}-{floor_str}-{room_type}"
        sub_loc = nb.dcim.locations.get(site_id=site.id, slug=sub_loc_name.lower())
        if not sub_loc:
            sub_loc = nb.dcim.locations.create(name=sub_loc_name, slug=sub_loc_name.lower(), site=site.id, parent=floor_loc.id, status="active")
            print(f"     └── [Sub-Location Created]: {sub_loc_name}")

        # Rack Allocation (e.g. FIZ01-06-R01)
        for r in range(1, room["racks"] + 1):
            rack_name = f"{site_code}-{floor_str}-R{r:02d}"
            rack_obj = nb.dcim.racks.get(site_id=site.id, location_id=sub_loc.id, name=rack_name)
            if not rack_obj:
                nb.dcim.racks.create(name=rack_name, site=site.id, location=sub_loc.id, u_height=42, status="active")
                print(f"          ├── [Rack Created]: {rack_name}")
            else:
                print(f"          ├── [Rack Exists]: {rack_name}")

    print(f"\n==================================================")
    print(f" ✓ SITE {site_code} SYNC COMPLETE")
    print(f"==================================================")
    return True

if __name__ == "__main__":
    files = sorted(glob.glob("sites/*.yml"))
    if not files:
        print("No YAML site files found in 'sites/' folder. Create a site YAML to begin.")
    for site_file in files:
        process_site(site_file)