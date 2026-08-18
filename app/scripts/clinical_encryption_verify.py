import argparse

from app.db.session import SessionLocal
from app.services.clinical_encryption_verification_service import ClinicalEncryptionVerificationService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify persisted clinical encryption envelopes")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-records", type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    with SessionLocal() as db:
        result = ClinicalEncryptionVerificationService(db).run(
            batch_size=args.batch_size,
            max_records=args.max_records,
        )

    for issue in result.issues:
        print(
            f"Verification issue: table={issue.table} record_id={issue.record_id} "
            f"field={issue.field} kind={issue.kind}"
        )
    print(
        f"Verified records={result.records}, fields={result.fields}, "
        f"mismatches={result.mismatches}, failures={result.failures}"
    )
    if not result.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
