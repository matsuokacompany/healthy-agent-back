import argparse
import logging
import sys

import httpx

from app.core.auth import _admin_headers, _supabase_project_url
from app.db.security_context import set_database_service_context
from app.db.session import SessionLocal
from app.models.models import User

# Run standalone via `python -m`, this never imports app.main, so nothing
# else configures logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Push each local User.name into the matching Supabase Auth user's "
            "metadata (both 'name' and 'full_name' keys, since it's unconfirmed which "
            "one Supabase Studio's Display Name column reads, and _metadata_name in "
            "app/core/auth.py already treats both as valid). Covers users provisioned "
            "before this metadata was set on signup/invite, and any local name edits "
            "that happened after that. One-way (local -> Supabase); safe to re-run, "
            "since app/core/auth.py's _sync_supabase_profile only overwrites the local "
            "name back from Supabase when the two actually differ."
        )
    )
    parser.add_argument("--email", help="limit to a single user's email (default: every user linked to Supabase Auth)")
    parser.add_argument(
        "--execute", action="store_true", help="apply the change (the default only reports what would happen)"
    )
    return parser


def _fetch_metadata(project_url: str, supabase_user_id) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{project_url}/auth/v1/admin/users/{supabase_user_id}", headers=_admin_headers())
    response.raise_for_status()
    return response.json().get("user_metadata") or {}


def _update_metadata(project_url: str, supabase_user_id, metadata: dict) -> None:
    # Sent under both keys because the Admin API's actual field name for this
    # (`data` vs `user_metadata`) isn't confirmed against a live project from
    # here -- an unrecognized key is ignored, so this costs nothing and removes
    # the risk of silently no-op'ing on the wrong one.
    with httpx.Client(timeout=10.0) as client:
        response = client.put(
            f"{project_url}/auth/v1/admin/users/{supabase_user_id}",
            headers=_admin_headers(),
            json={"data": metadata, "user_metadata": metadata},
        )
    response.raise_for_status()


def main() -> None:
    args = _parser().parse_args()
    project_url = _supabase_project_url()
    if not project_url:
        print("SUPABASE_PROJECT_URL is not configured; nothing to do.")
        return

    with SessionLocal() as db:
        set_database_service_context(db, "sync_supabase_display_names")

        query = db.query(User).filter(User.supabase_user_id.isnot(None), User.name.isnot(None))
        if args.email:
            query = query.filter(User.email == args.email)
        users = query.order_by(User.id).all()

        print(f"Users linked to Supabase Auth: {len(users)}")

        to_update: list[tuple[User, dict]] = []
        errors: list[tuple[User, str]] = []
        for user in users:
            try:
                metadata = _fetch_metadata(project_url, user.supabase_user_id)
            except httpx.HTTPError as exc:
                errors.append((user, str(exc)))
                continue
            if metadata.get("name") == user.name and metadata.get("full_name") == user.name:
                continue
            to_update.append((user, metadata))

        already_correct = len(users) - len(to_update) - len(errors)
        print(f"Already correct: {already_correct}")
        print(f"To update: {len(to_update)}")
        for user, _ in to_update:
            print(f"  - {user.email} (id={user.id}) -> {user.name!r}")
        if errors:
            print(f"Failed to fetch current metadata for {len(errors)} user(s):")
            for user, error in errors:
                print(f"  - {user.email} (id={user.id}): {error}")

        if not args.execute:
            print("\nDry run only; pass --execute to apply the change.")
            return

        updated = 0
        unverified = 0
        for user, metadata in to_update:
            merged = {**metadata, "name": user.name, "full_name": user.name}
            try:
                _update_metadata(project_url, user.supabase_user_id, merged)
            except httpx.HTTPError as exc:
                logger.warning("Failed to update Supabase metadata for user_id=%s: %s", user.id, exc)
                continue
            updated += 1
            try:
                confirmed = _fetch_metadata(project_url, user.supabase_user_id)
            except httpx.HTTPError:
                confirmed = {}
            if confirmed.get("name") != user.name:
                unverified += 1
                logger.warning(
                    "Update for user_id=%s returned success but did not stick -- "
                    "the Admin API may expect a different field name than 'data'/'user_metadata'.",
                    user.id,
                )

        print(f"\nDone: updated {updated}/{len(to_update)} user(s).")
        if unverified:
            print(f"WARNING: {unverified} update(s) did not verify on re-fetch -- see warnings above.")


if __name__ == "__main__":
    main()
