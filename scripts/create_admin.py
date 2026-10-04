"""Create the first LOCAL GateLog admin interactively; never a Google password."""
import getpass
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import Settings
from app.database.connection import connect
from app.database.seed import seed
from app.schemas.campus import UserInput
from app.services.auth import password_hash


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
        password = getpass.getpass("New GateLog password (12+ characters; not your Google password): ")
        if password != getpass.getpass("Confirm GateLog password: "):
            raise SystemExit("Passwords do not match. No account created.")
        user = UserInput(username=username, email=email, full_name="GateLog Administrator", role="admin", password=password)
        row = user.model_dump(exclude={"password"})
        row.update(_id=str(uuid4()), password_hash=password_hash(password), auth_provider="local", created_at=datetime.now(timezone.utc))
        db.users.insert_one(row)
        seed(db, settings)  # Camera configuration and official references only; never invented operations.
        print("Administrator and reference configuration saved to MongoDB. Sign in with your GateLog credentials.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
