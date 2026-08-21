import os
import yaml
import pynetbox
import urllib3

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# NetBox Connection Setup
URL = os.getenv("NETBOX_URL", "https://netbox.yourcompany.com")
TOKEN = os.getenv("NETBOX_TOKEN", "your_token_here")

nb = pynetbox.api(URL, token=TOKEN)
nb.http_session.verify = False

def provision_device_from_yaml(filepath):
    print("==================================================")
    print(f" TESTING DEVICE PROVISIONING FROM: {filepath}")
    print("==================================================")

    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    device_name = str(data["device_name"]).strip()
    site_code = str(data["site_code"]).upper()
    floor = str(data["floor"]).zfill(2)
    room_type = str(data["room_type"]).upper()
    rack_name = str(data["rack_name"]).upper()
    rack_pos = data.get("rack_position")
    mfr_name = str(data["manufacturer"]).strip()
    model_name = str(data["model"]).strip()
    role_name = str(data["role"]).strip()
    primary_ip = data.get("primary_ip")

    # 1. Fetch Site
    site = nb.dcim.sites.get(slug=site_code.lower())
    if not site:
        print(f"❌ Site '{site_code}' not found in NetBox! Run deploy.py first.")
        return False
    print(f"✓ Found Site: {site.name}")

    # 2. Fetch Sub-Location (e.g., FIZ01-06-MDF)
    sub_loc_name = f"{site_code}-{floor}-{room_type}"
    location = nb.dcim.locations.get(site_id=site.id, slug=sub_loc_name.lower())
    if not location:
        print(f"❌ Location '{sub_loc_name}' not found! Run deploy.py first.")
        return False
    print(f"✓ Found Sub-Location: {location.name}")

    # 3. Fetch Rack
    rack = nb.dcim.racks.get(site_id=site.id, location_id=location.id, name=rack_name)
    if not rack:
        print(f"❌ Rack '{rack_name}' not found in location '{sub_loc_name}'!")
        return False
    print(f"✓ Found Rack: {rack.name}")

    # 4. Get/Create Manufacturer
    mfr_slug = mfr_name.lower().replace(" ", "-")
    manufacturer = nb.dcim.manufacturers.get(slug=mfr_slug)
    if not manufacturer:
        manufacturer = nb.dcim.manufacturers.create(name=mfr_name, slug=mfr_slug)
        print(f"   + Created Manufacturer: {mfr_name}")
    else:
        print(f"✓ Manufacturer Exists: {manufacturer.name}")

    # 5. Get/Create Device Type
    dt_slug = model_name.lower().replace(" ", "-")
    device_type = nb.dcim.device_types.get(model=model_name, manufacturer_id=manufacturer.id)
    if not device_type:
        device_type = nb.dcim.device_types.create({
            "manufacturer": manufacturer.id,
            "model": model_name,
            "slug": dt_slug,
            "u_height": 1,
            "is_full_depth": True
        })
        print(f"   + Created Device Type: {model_name}")
    else:
        print(f"✓ Device Type Exists: {device_type.model}")

    # 6. Get/Create Device Role
    role_slug = role_name.lower().replace(" ", "-")
    device_role = nb.dcim.device_roles.get(slug=role_slug)
    if not device_role:
        device_role = nb.dcim.device_roles.create({
            "name": role_name,
            "slug": role_slug,
            "color": "009688" # Teal
        })
        print(f"   + Created Device Role: {role_name}")
    else:
        print(f"✓ Device Role Exists: {device_role.name}")

    # 7. Create/Update Device
    device_payload = {
        "name": device_name,
        "site": site.id,
        "location": location.id,
        "rack": rack.id,
        "position": rack_pos,
        "face": "front",
        "device_type": device_type.id,
        "role": device_role.id,
        "status": "active"
    }

    device = nb.dcim.devices.get(name=device_name, site_id=site.id)
    if not device:
        device = nb.dcim.devices.create(device_payload)
        print(f"✓ Device Created: {device_name} (Rack: {rack_name}, Unit: {rack_pos})")
    else:
        device.update(device_payload)
        print(f"✓ Device Updated: {device_name}")

    # 8. Manage Primary IP Address & Interface
    if primary_ip:
        print("\n--> Configuring Management Interface & Primary IP...")
        # Step A: Get or create interface
        interfaces = list(nb.dcim.interfaces.filter(device_id=device.id))
        if interfaces:
            mgmt_iface = interfaces[0]
        else:
            mgmt_iface = nb.dcim.interfaces.create({
                "device": device.id,
                "name": "Management0",
                "type": "virtual"
            })
            print(f"   + Created Virtual Interface: {mgmt_iface.name}")

        # Step B: Get or create IP Address
        ip_obj = nb.ipam.ip_addresses.get(address=primary_ip)
        if not ip_obj:
            ip_obj = nb.ipam.ip_addresses.create({
                "address": primary_ip,
                "status": "active",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": mgmt_iface.id
            })
            print(f"   + Created IP Address: {primary_ip}")
        else:
            if ip_obj.assigned_object_id != mgmt_iface.id:
                ip_obj.update({
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": mgmt_iface.id
                })

        # Step C: Bind as Primary IPv4 on Device
        if getattr(device, "primary_ip4", None) is None or device.primary_ip4.id != ip_obj.id:
            device.update({"primary_ip4": ip_obj.id})
            print(f"   + Bound {primary_ip} as Primary IPv4 on {device.name}")

    print("\n==================================================")
    print(f" ✓ TEST DEVICE PROVISIONING COMPLETE")
    print("==================================================")
    return True

if __name__ == "__main__":
    provision_device_from_yaml("test_device.yml")