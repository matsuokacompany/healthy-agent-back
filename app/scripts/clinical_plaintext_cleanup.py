import argparse

from app.db.security_context import set_database_service_context
from app.db.session import SessionLocal
from app.services.clinical_plaintext_cleanup_service import ClinicalPlaintextCleanupService


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely clear verified legacy clinical plaintext")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        set_database_service_context(db, "clinical_plaintext_cleanup")
        service = ClinicalPlaintextCleanupService(db)
        before = service.pending_counts()
        print("Plaintext records: " + ", ".join(f"{table}={count}" for table, count in before.items()))
        if not args.execute:
            print("Dry run only; pass --execute to authenticate envelopes and clear plaintext.")
            return
        stats = service.run(batch_size=args.batch_size, max_records=args.max_records)
        after = service.pending_counts()
        print(f"Cleared records={stats.records}, fields={stats.fields}")
        print("Remaining plaintext records: " + ", ".join(f"{table}={count}" for table, count in after.items()))


if __name__ == "__main__":
    main()
