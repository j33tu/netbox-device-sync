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

def select_site():
    """Prompt the user to select a site or view all sites."""
    sites = list(nb.dcim.sites.all())
    if not sites:
        print("No sites found in NetBox.")
        return None

    print("\nSelect Site to Filter Prefixes:")
    print("  [0] ALL SITES")
    for idx, site in enumerate(sites, 1):
        print(f"  [{idx}] {site.name}")

    while True:
        try:
            choice = int(input(f"Enter choice (0-{len(sites)}): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(sites):
                return sites[choice - 1]
            print("Invalid selection. Please choose from the list.")
        except ValueError:
            print("Please enter a valid number.")

def list_prefixes():
    selected_site = select_site()

    print("\n==========================================================================================")
    all_prefixes = list(nb.ipam.prefixes.all())

    if selected_site:
        print(f" 📡 NETBOX IPAM PREFIX INVENTORY FOR SITE: {selected_site.name}")
        # Filter prefixes matching site ID OR mapped to VLANs belonging to the site
        prefixes = []
        for p in all_prefixes:
            site_obj = getattr(p, "site", None)
            vlan_obj = getattr(p, "vlan", None)
            vlan_site_id = getattr(getattr(vlan_obj, "site", None), "id", None)

            if (site_obj and site_obj.id == selected_site.id) or (vlan_site_id == selected_site.id) or (vlan_obj and selected_site.name in getattr(vlan_obj, "name", "")):
                prefixes.append(p)
    else:
        print(" 📡 NETBOX IPAM PREFIX INVENTORY (ALL SITES)")
        prefixes = all_prefixes

    print("==========================================================================================")

    if not prefixes:
        print("No Prefixes found for the selected criteria.")
        return

    # Table Header
    print(f"{'Prefix / CIDR':<18} | {'Site Scope':<12} | {'VLAN':<28} | {'Status':<8} | {'Description'}")
    print("-" * 95)

    for prefix in sorted(prefixes, key=lambda x: str(x.prefix)):
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

        print(f"{str(prefix.prefix):<18} | {site_name:<12} | {vlan_display:<28} | {status:<8} | {description}")

    print("-" * 95)
    print(f"Total Prefixes: {len(prefixes)}\n")

if __name__ == "__main__":
    list_prefixes()