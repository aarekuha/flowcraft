from __future__ import annotations

import argparse
from datetime import UTC, datetime

from app.core.database import SessionLocal
from app.core.phone import normalize_phone
from app.core.security import hash_password
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update an admin user for Flowcraft.",
    )
    parser.add_argument("--name", required=True, help="Admin user name.")
    parser.add_argument("--phone", required=True, help="Admin phone number.")
    parser.add_argument(
        "--password",
        default=None,
        help="Optional admin password. If omitted, password remains empty.",
    )
    return parser.parse_args()


def now_ts() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def main() -> None:
    args = parse_args()
    normalized_phone = normalize_phone(args.phone)
    normalized_name = args.name.strip()

    if not normalized_name:
        raise SystemExit("Admin name must not be empty.")

    session = SessionLocal()
    try:
        timestamp = now_ts()
        user = session.query(User).filter(User.phone == normalized_phone).one_or_none()

        if user is None:
            user = User(
                name=normalized_name,
                phone=normalized_phone,
                password_hash=hash_password(args.password) if args.password else None,
                roles=["admin"],
                is_active=True,
                created_at=timestamp,
                updated_at=timestamp,
                deleted_at=None,
                author_user_id=None,
            )
            session.add(user)
            session.flush()
            user.author_user_id = user.id
            action = "created"
        else:
            user.name = normalized_name
            if "admin" not in user.roles:
                user.roles = [*user.roles, "admin"]
            user.is_active = True
            user.deleted_at = None
            user.updated_at = timestamp
            if args.password:
                user.password_hash = hash_password(args.password)
            if user.author_user_id is None:
                user.author_user_id = user.id
            action = "updated"

        session.commit()
        print(
            {
                "status": action,
                "id": user.id,
                "name": user.name,
                "phone": user.phone,
                "roles": user.roles,
                "password_set": bool(user.password_hash),
            }
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
