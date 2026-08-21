import os
import pynetbox
import urllib3

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# NetBox Connection Setup
URL = os.getenv("NETBOX_URL", "https://netbox.yourcompany.com")
TOKEN = os.getenv("NETBOX_TOKEN", "your_token_here")

nb = pynetbox.api(URL, token=TOKEN)
nb.http_session.verify = False

def purge_endpoint(title, endpoint):
    """Fetches all items from a NetBox endpoint and deletes them safely."""
    print(f"\n--> Purging {title}...")
    try:
        items = list(endpoint.all())
        if not items:
            print(f"    (No {title} found)")
            return
            
        count = 0
        for item in items:
            name = getattr(item, 'name', getattr(item, 'prefix', getattr(item, 'address', str(item))))
            try:
                item.delete()
                count += 1
            except Exception as e:
                print(f"    ❌ Failed to delete {name}: {e}")
        print(f"    ✓ Successfully deleted {count} {title}")
    except Exception as e:
        print(f"    ⚠️ Could not process endpoint {title}: {e}")

def wipe_entire_netbox():
    print("==================================================")
    print(" 🚨 WARNING: STARTING FULL NETBOX WIPE 🚨")
    print("==================================================")

    # 1. IPAM Clean (IP Addresses -> Prefixes -> VLANs -> VRFs)
    purge_endpoint("IP Addresses", nb.ipam.ip_addresses)
    purge_endpoint("Prefixes", nb.ipam.prefixes)
    purge_endpoint("VLANs", nb.ipam.vlans)
    purge_endpoint("VLAN Groups", nb.ipam.vlan_groups)
    purge_endpoint("VRFs", nb.ipam.vrfs)
    purge_endpoint("RIRs", nb.ipam.rirs)

    # 2. DCIM Hardware & Cabling Clean
    purge_endpoint("Cables", nb.dcim.cables)
    purge_endpoint("Interface Connections / Interfaces", nb.dcim.interfaces)
    purge_endpoint("Devices", nb.dcim.devices)
    purge_endpoint("Virtual Chassis", nb.dcim.virtual_chassis)
    purge_endpoint("Device Types", nb.dcim.device_types)
    purge_endpoint("Device Roles", nb.dcim.device_roles)
    purge_endpoint("Platform Definitions", nb.dcim.platforms)
    purge_endpoint("Manufacturers", nb.dcim.manufacturers)

    # 3. DCIM Structure Clean (Racks -> Locations -> Sites -> Regions)
    purge_endpoint("Rack Reservations", nb.dcim.rack_reservations)
    purge_endpoint("Racks", nb.dcim.racks)
    purge_endpoint("Rack Roles", nb.dcim.rack_roles)
    
    # Sub-locations and Parent locations
    purge_endpoint("Locations", nb.dcim.locations)
    
    purge_endpoint("Sites", nb.dcim.sites)
    purge_endpoint("Site Groups", nb.dcim.site_groups)
    purge_endpoint("Regions", nb.dcim.regions)

    print("\n==================================================")
    print(" 💥 FULL WIPE COMPLETE - NETBOX IS NOW EMPTY")
    print("==================================================")

if __name__ == "__main__":
    confirm = input("Are you absolutely sure you want to DELETE ALL OBJECTS IN NETBOX? (type 'YES' to confirm): ")
    if confirm.strip() == "YES":
        wipe_entire_netbox()
    else:
        print("Aborted. No objects were deleted.")