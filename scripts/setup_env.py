"""Create the .env file with new random keys.

Run from the project root:  python scripts/setup_env.py
It never replaces a key that already exists, because encrypted data
can't be read any more if the encryption key changes.
"""

import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")


def random_key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def main():
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()

    existing = {line.split("=", 1)[0] for line in lines if "=" in line and not line.endswith("=REPLACE_ME")}
    lines = [line for line in lines if not line.endswith("=REPLACE_ME")]
    added = []
    for name in ("CG_SECRET_KEY", "CG_ENCRYPTION_KEY"):
        if name not in existing:
            lines.append(f"{name}={random_key()}")
            added.append(name)

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Added:", ", ".join(added) if added else "nothing (keys already exist)")


if __name__ == "__main__":
    main()
