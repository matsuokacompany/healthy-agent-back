import argparse

from app.db.session import SessionLocal
from app.db.security_context import set_database_service_context
from app.services.symptom_terms_backfill_service import SymptomTermsBackfillService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify existing check-ins' symptom_description text into the controlled SymptomTerm vocabulary"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="call the AI classifier and persist symptom terms (the default only reports the pending count)",
    )
    parser.add_argument(
        "--reclassify-all",
        action="store_true",
        help=(
            "also re-run check-ins that already have a linked term, not just unclassified ones — "
            "use after a prompt change to re-derive terms for everything with the improved prompt"
        ),
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-records", type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    with SessionLocal() as db:
        set_database_service_context(db, "symptom_terms_backfill")
        service = SymptomTermsBackfillService(db)
        pending = service.pending_count(reclassify_all=args.reclassify_all)
        label = "check-ins to reclassify" if args.reclassify_all else "pending check-ins"
        print(f"{label.capitalize()}: {pending}")
        if not args.execute:
            print("Dry run only; pass --execute to classify and persist symptom terms.")
            return
        # Each processed check-in is one OpenAI call (same "normalizacao_sintomas"
        # mode used on new check-ins) — a large --max-records on a big backlog has
        # a real, if small, cost. Run a small batch first if unsure of the size.
        stats = service.run(batch_size=args.batch_size, max_records=args.max_records, reclassify_all=args.reclassify_all)
        remaining = service.pending_count(reclassify_all=args.reclassify_all)
        print(f"Processed={stats.processed}, linked={stats.linked}")
        print(f"Remaining {label}: {remaining}")


if __name__ == "__main__":
    main()
