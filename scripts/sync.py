import os
import sys
import shutil
import tempfile
import yaml
import subprocess
import pynetbox
from dotenv import load_dotenv

load_dotenv()

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
DATA_EXCHANGE_REPO = "https://github.com/netbox-community/devicetype-library.git"

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: NETBOX_URL and NETBOX_TOKEN must be set in environment.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

def load_vendor_config(config_path="config/vendors.yml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def fetch_latest_library(target_dir):
    """Clones the official NetBox Device Type Library."""
    print("Fetching latest Device Type Library from GitHub...")
    subprocess.run(
        ["git", "clone", "--depth", "1", DATA_EXCHANGE_REPO, target_dir],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def parse_yaml_file(filepath):
    """Parses a device-type YAML definition file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def sync_vendor_device_types(vendor, library_path):
    v_name = vendor["name"]
    v_dir = vendor["directory"]
    v_slug = v_name.lower().replace(" ", "-")
    vendor_path = os.path.join(library_path, "device-types", v_dir)

    if not os.path.exists(vendor_path):
        print(f"Warning: Directory '{v_dir}' not found in library. Skipping {v_name}.")
        return

    # Check for existing Manufacturer by name OR slug to prevent duplicate slug 400 errors
    manufacturer = nb.dcim.manufacturers.get(name=v_name) or nb.dcim.manufacturers.get(slug=v_slug)

    if not manufacturer:
        print(f"Manufacturer '{v_name}' not found in NetBox. Creating...")
        manufacturer = nb.dcim.manufacturers.create(
            name=v_name, 
            slug=v_slug
        )
    else:
        print(f"Using existing Manufacturer in NetBox: '{manufacturer.name}' (ID: {manufacturer.id})")

    # Cache existing NetBox device types for this manufacturer
    existing_types = {
        dt.model: dt for dt in nb.dcim.device_types.filter(manufacturer_id=manufacturer.id)
    }

    checked, skipped, created, errors = 0, 0, 0, 0

    # Walk vendor directory for YAML definitions
    for root, _, files in os.walk(vendor_path):
        for file in files:
            if not file.endswith((".yaml", ".yml")):
                continue

            checked += 1
            file_path = os.path.join(root, file)

            try:
                dt_data = parse_yaml_file(file_path)
                model = dt_data.get("model")

                if not model:
                    continue

                if model in existing_types:
                    skipped += 1
                    continue

                # Core NetBox Device Type payload
                payload = {
                    "manufacturer": manufacturer.id,
                    "model": dt_data.get("model"),
                    "slug": dt_data.get("slug"),
                    "part_number": dt_data.get("part_number", ""),
                    "u_height": dt_data.get("u_height", 1),
                    "is_full_depth": dt_data.get("is_full_depth", True),
                    "comments": dt_data.get("comments", "Synced from Data Exchange"),
                }

                # Optional metadata parameters from Data Exchange YAMLs
                if "airflow" in dt_data:
                    payload["airflow"] = dt_data["airflow"]

                if "weight" in dt_data:
                    payload["weight"] = dt_data["weight"]
                    payload["weight_unit"] = dt_data.get("weight_unit", "kg")

                if "description" in dt_data:
                    payload["description"] = dt_data["description"]

                nb.dcim.device_types.create(payload)
                created += 1
                print(f"  [CREATED] {model}")

            except Exception as e:
                errors += 1
                print(f"  [ERROR] Failed to process {file}: {e}")

    print(f"\n--- {v_name} Summary ---")
    print(f"Checked:         {checked}")
    print(f"Already Present: {skipped}")
    print(f"Created:         {created}")
    print(f"Errors:          {errors}\n")

def main():
    config = load_vendor_config()
    enabled_vendors = [v for v in config.get("vendors", []) if v.get("enabled", False)]

    if not enabled_vendors:
        print("No vendors enabled for synchronization.")
        return

    # Use a clean temp folder for cloning every run
    with tempfile.TemporaryDirectory() as temp_dir:
        fetch_latest_library(temp_dir)

        for vendor in enabled_vendors:
            print(f"\n==========================================")
            print(f" Syncing Vendor: {vendor['name']}")
            print(f"==========================================")
            sync_vendor_device_types(vendor, temp_dir)

if __name__ == "__main__":
    main()