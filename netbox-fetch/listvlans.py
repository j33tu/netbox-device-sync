import os
import pynetbox
import urllib3

# Suppress SSL warnings for internal servers
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# NetBox Connection Setup
URL = os.getenv("NETBOX_URL", "https://netbox.yourcompany.com")
TOKEN = os.getenv("NETBOX_TOKEN", "your_token_here")

nb = pynetbox.api(URL, token=TOKEN)
nb.http_session.verify = False

def list_all_vlans():
    print("==========================================================================")
    print(" 🌐 NETBOX VLAN & MAPPED SUBNET INVENTORY")
    print("==========================================================================")

    vlans = list(nb.ipam.vlans.all())

    if not vlans:
        print("No VLANs found in NetBox.")
        return

    # Table Header
    print(f"{'VID':<6} | {'VLAN Name':<25} | {'Site':<10} | {'Status':<8} | {'Mapped Prefix'}")
    print("-" * 74)

    for vlan in sorted(vlans, key=lambda x: x.vid):
        # Fetch associated prefix directly bound to this VLAN
        prefix_obj = nb.ipam.prefixes.get(vlan_id=vlan.id)
        mapped_prefix = prefix_obj.prefix if prefix_obj else "Unassigned"
        
        site_name = vlan.site.name if vlan.site else "Global"
        status = getattr(vlan.status, "value", str(vlan.status)).capitalize()

        print(f"{vlan.vid:<6} | {vlan.name:<25} | {site_name:<10} | {status:<8} | {mapped_prefix}")

    print("-" * 74)
    print(f"Total VLANs: {len(vlans)}\n")

if __name__ == "__main__":
    list_all_vlans()