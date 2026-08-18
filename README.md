# NetBox Sync

This project is a starter structure for syncing vendor device metadata into a NetBox instance.

## Layout

- `config/` contains vendor configuration files
- `scripts/` contains command-line entry points
- `.env` stores environment configuration
- `requirements.txt` lists Python dependencies

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or .venv\Scripts\activate  # Windows
pip install -r requirements.txt
python scripts/sync.py --dry-run
```

## Notes

This scaffold is intentionally minimal and ready to extend with real NetBox API calls, catalog parsing, and sync logic.
