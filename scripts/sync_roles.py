import os
import sys
import yaml
import pynetbox

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

if not NETBOX_URL or not NETBOX_TOKEN:
    print("Error: Missing NETBOX_URL or NETBOX_TOKEN environment variable.")
    sys.exit(1)

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

# Load YAML input
file_path = "inputs/device_roles.yml"
if not os.path.exists(file_path):
    print(f"File {file_path} not found. Skipping execution.")
    sys.exit(0)

with open(file_path, "r") as f:
    data = yaml.safe_load(f) or {}

roles = data.get("device_roles", [])

for role in roles:
    name = role.get("name")
    if not name:
        continue

    # Query NetBox by slug or name
    slug = role.get("slug")
    existing = nb.dcim.device_roles.get(slug=slug) if slug else nb.dcim.device_roles.get(name=name)

    if existing:
        existing.update(role)
        print(f"✓ Updated device role: {name}")
    else:
        nb.dcim.device_roles.create(role)
        print(f"+ Created device role: {name}")