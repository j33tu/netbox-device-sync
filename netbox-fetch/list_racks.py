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

def list_all_prefixes():
    print("==========================================================================================")
    print(" 📡 NETBOX IPAM PREFIX INVENTORY")
    print("==========================================================================================")

    prefixes = list(nb.ipam.prefixes.all())

    if not prefixes:
        print("No Prefixes found in NetBox.")
        return

    # Table Header
    print(f"{'Prefix / CIDR':<18} | {'Site':<10} | {'VLAN':<25} | {'Status':<8} | {'Description'}")
    print("-" * 90)

    for prefix in sorted(prefixes, key=lambda x: str(x.prefix)):
        # Safe attribute extraction using getattr
        site_obj = getattr(prefix, "site", None)
        site_name = site_obj.name if site_obj else "Global"

        vlan_obj = getattr(prefix, "vlan", None)
        if vlan_obj:
            vlan_vid = getattr(vlan_obj, "vid", "?")
            vlan_name = getattr(vlan_obj, "name", "")
            vlan_display = f"VLAN {vlan_vid} ({vlan_name})"
        else:
            vlan_display = "Unassigned"

        status_obj = getattr(prefix, "status", "active")
        status = getattr(status_obj, "label", str(status_obj)).capitalize()
        description = getattr(prefix, "description", "") or "-"

        print(f"{str(prefix.prefix):<18} | {site_name:<10} | {vlan_display:<25} | {status:<8} | {description}")

    print("-" * 90)
    print(f"Total Prefixes: {len(prefixes)}\n")

if __name__ == "__main__":
    list_all_prefixes()