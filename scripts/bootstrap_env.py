"""Generate local-only authentication secrets without overwriting existing values."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
env = root / ".env"
values = {}
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
new = {}
for key, size in (("JWT_SECRET_KEY", 48),):
    if not values.get(key):
        new[key] = secrets.token_urlsafe(size)
if new:
    with env.open("a", encoding="utf-8", newline="\n") as output:
        output.write("\n# Locally generated credentials. Keep this file private.\n")
        for key, value in new.items():
            output.write(f"{key}={value}\n")
    print("Generated local credentials in .env (never commit this file):")
else:
    print("The private GateLog session secret is already configured in .env.")
