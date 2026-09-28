"""Read a setting from the environment first, then from <studio root>/.env (gitignored)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get(key):
    if os.environ.get(key):
        return os.environ[key]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key and not line.lstrip().startswith("#") and v.strip():
                return v.strip().strip('"').strip("'")
    return None
