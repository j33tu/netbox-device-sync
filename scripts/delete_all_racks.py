import os
import sys
import urllib3
import pynetbox

# Disable HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. NetBox Connection
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: Missing NETBOX_URL or NETBOX_TOKEN environment variables.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
nb.http_session.verify = False


def delete_all_racks():
    """Deletes all racks across the target sites/locations."""
    # Fetch all existing racks from NetBox
    racks = list(nb.dcim.racks.all())

    if not racks:
        print("No racks found in NetBox.")
        return

    print(f"Found {len(racks)} total rack(s) to delete...\n")

    deleted_count = 0
    for rack in racks:
        rack_name = rack.name
        try:
            rack.delete()
            print(f"  - Deleted Rack: {rack_name}")
            deleted_count += 1
        except Exception as e:
            print(f"  ! Failed to delete Rack {rack_name}: {e}")

    print(f"\nCleanup finished: Successfully removed {deleted_count} rack(s).")


if __name__ == "__main__":
    # Prompt for confirmation to avoid accidental deletion
    confirm = input("Are you sure you want to delete ALL racks in NetBox? (yes/no): ")
    if confirm.strip().lower() == "yes":
        delete_all_racks()
    else:
        print("Operation cancelled.")