"""Print the current TOTP code for a base32 secret (demo convenience).

Use this instead of a phone authenticator during a local demonstration:
    backend\\.venv\\Scripts\\python.exe scripts\\totp.py JBSWY3DPEHPK3PXP

The secret is the one shown during MFA setup or printed by `seed-demo`.
Never use this approach for real accounts: it removes the "something you
have" property that makes TOTP a second factor.
"""

import sys
import time

import pyotp


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/totp.py <BASE32_SECRET>")
    totp = pyotp.TOTP(sys.argv[1].strip().replace(" ", ""))
    remaining = totp.interval - int(time.time()) % totp.interval
    print(f"{totp.now()}  (valid for about {remaining}s more)")


if __name__ == "__main__":
    main()
