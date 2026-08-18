import argparse

from app.db.session import SessionLocal
from app.services.clinical_encryption_backfill_service import ClinicalEncryptionBackfillService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill clinical encryption envelopes")
    parser.add_argument("--execute", action="store_true", help="persist envelopes (the default only reports counts)")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-records", type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    with SessionLocal() as db:
        service = ClinicalEncryptionBackfillService(db)
        before = service.pending_counts()
        print("Pending records: " + ", ".join(f"{table}={count}" for table, count in before.items()))
        if not args.execute:
            print("Dry run only; pass --execute to persist the backfill.")
            return
        stats = service.run(batch_size=args.batch_size, max_records=args.max_records)
        after = service.pending_counts()
        print(f"Encrypted records={stats.records}, fields={stats.fields}")
        print("Remaining records: " + ", ".join(f"{table}={count}" for table, count in after.items()))


if __name__ == "__main__":
    main()
