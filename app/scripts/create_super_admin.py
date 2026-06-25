"""Bootstrap or promote the first super admin without hard-coded IDs or emails.

Usage:
    python -m app.scripts.create_super_admin --supabase-user-id <uuid> --email admin@example.com --name "Admin"
"""

import argparse
import uuid

from app.core.auth import assign_role
from app.db.session import SessionLocal
from app.models.models import RoleNameEnum, User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or promote a local user to super_admin.")
    parser.add_argument("--supabase-user-id", required=True, help="Supabase Auth user UUID (auth.users.id).")
    parser.add_argument("--email", required=True, help="Email associated with the Supabase Auth user.")
    parser.add_argument("--name", default="Super Admin", help="Local display name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    supabase_user_id = uuid.UUID(args.supabase_user_id)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.supabase_user_id == supabase_user_id).first()
        if not user:
            user = db.query(User).filter(User.email == args.email).first()
            if user and user.supabase_user_id and user.supabase_user_id != supabase_user_id:
                raise SystemExit("Email is already linked to a different Supabase user.")

        if not user:
            user = User(
                supabase_user_id=supabase_user_id,
                email=args.email,
                name=args.name,
                is_admin=True,
            )
            db.add(user)
            db.flush()
            action = "created"
        else:
            user.supabase_user_id = supabase_user_id
            user.email = args.email
            user.name = user.name or args.name
            user.is_admin = True
            action = "promoted"

        assign_role(db, user, RoleNameEnum.PATIENT)
        assign_role(db, user, RoleNameEnum.PROFESSIONAL)
        assign_role(db, user, RoleNameEnum.ADMIN)
        assign_role(db, user, RoleNameEnum.SUPER_ADMIN)
        db.commit()
        db.refresh(user)
        print(f"User {action}: id={user.id} email={user.email} roles={','.join(user.roles)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
