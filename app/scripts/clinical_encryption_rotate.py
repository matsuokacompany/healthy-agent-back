import argparse

from app.core.config import settings
from app.db.security_context import set_database_service_context
from app.db.session import SessionLocal
from app.services.clinical_encryption_rotation_service import ClinicalEncryptionRotationService


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotate persisted clinical encryption envelopes")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--target-key-version", default=settings.CLINICAL_ENCRYPTION_ACTIVE_KEY_VERSION)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        set_database_service_context(db, "clinical_encryption_rotation")
        service = ClinicalEncryptionRotationService(db)
        before = service.pending_counts(args.target_key_version)
        print("Pending rotation: " + ", ".join(f"{table}={count}" for table, count in before.items()))
        if not args.execute:
            print("Dry run only; pass --execute to rotate envelopes.")
            return
        stats = service.run(
            args.target_key_version,
            batch_size=args.batch_size,
            max_records=args.max_records,
        )
        after = service.pending_counts(args.target_key_version)
        print(f"Rotated records={stats.records}, fields={stats.fields}")
        print("Remaining rotation: " + ", ".join(f"{table}={count}" for table, count in after.items()))


if __name__ == "__main__":
    main()
