"""Create the project-root .env file for local development.

* Copies .env.example and fills CG_ENCRYPTION_KEY with 32 fresh random bytes.
* NEVER overwrites an existing .env or an existing key: if .env exists and
  already has a valid key, nothing changes. If .env exists with only the
  placeholder, the placeholder is replaced and every other line is kept.

Usage (from the project root):  python scripts/setup_env.py
"""

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"
PLACEHOLDER = "REPLACE_WITH_GENERATED_BASE64_KEY"


def new_key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def main():
    if not EXAMPLE.exists():
        sys.exit("ERROR: .env.example not found; run this from the ConsentGuard project.")

    if TARGET.exists():
        text = TARGET.read_text(encoding="utf-8")
        if f"CG_ENCRYPTION_KEY={PLACEHOLDER}" not in text:
            print(".env already exists and contains an encryption key - leaving it unchanged.")
            print("(Replacing a key would make existing encrypted records unreadable.)")
            return
        TARGET.write_text(text.replace(PLACEHOLDER, new_key()), encoding="utf-8")
        print("Filled the placeholder encryption key in the existing .env.")
        return

    text = EXAMPLE.read_text(encoding="utf-8").replace(PLACEHOLDER, new_key())
    TARGET.write_text(text, encoding="utf-8")
    print(f"Created {TARGET} with a new random development key.")
    print("Back up this key: encrypted demo records cannot be recovered without it.")


if __name__ == "__main__":
    main()
