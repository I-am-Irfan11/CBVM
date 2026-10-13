"""Invite the first Firebase administrator to GateLog by verified email."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import Settings
from app.database.connection import connect
from app.database.seed import seed
from app.schemas.campus import UserInput


def main():
    settings = Settings()
    if settings.app_env == "test" or settings.database_mode != "mongodb":
        raise SystemExit("Use a dedicated persistent MongoDB database for account setup.")
    client, db = connect(settings)
    try:
        if db.users.find_one({"role": "admin", "active": True}):
            raise SystemExit("An active administrator already exists. Manage accounts after signing in; no records changed.")
        username = input("GateLog admin username: ").strip()
        email = input("Admin email: ").strip()
        user = UserInput(username=username, email=email, full_name="GateLog Administrator", role="admin")
        now = datetime.now(timezone.utc)
        row = user.model_dump()
        row.update(_id=str(uuid4()), auth_provider="firebase-invited", created_at=now, updated_at=now)
        db.users.insert_one(row)
        seed(db, settings)  # Camera configuration and official references only; never invented operations.
        print("Admin access and reference configuration saved. Sign in to Firebase with this same verified email.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
