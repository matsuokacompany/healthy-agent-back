import argparse
import logging
import sys

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.symptom_term_dedup_service import SymptomTermDedupService

# Run standalone via `python -m`, this never imports app.main, so nothing
# else configures logging -- without a handler, logger.info() calls are
# silently dropped by Python's logging module instead of reaching stdout.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find near-duplicate labels in the shared SymptomTerm vocabulary "
            '(e.g. "Enjoo" vs "Náusea") and merge them into one canonical term.'
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="merge the duplicate clusters found (the default only lists them)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=SymptomTermDedupService.DEFAULT_SIMILARITY_THRESHOLD,
        help=f"cosine similarity threshold to treat two labels as duplicates (default {SymptomTermDedupService.DEFAULT_SIMILARITY_THRESHOLD})",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY não configurada.")
        return

    with SessionLocal() as db:
        clusters = SymptomTermDedupService.find_duplicate_clusters(
            db, api_key=settings.OPENAI_API_KEY, threshold=args.threshold
        )
        if not clusters:
            print("Nenhum termo duplicado encontrado.")
            return

        print(f"{len(clusters)} grupo(s) de termos duplicados encontrados:")
        for cluster in clusters:
            duplicate_labels = ", ".join(f'"{d.label}"' for d in cluster.duplicates)
            print(f'  "{cluster.canonical.label}" <- {duplicate_labels} (similaridade mínima {cluster.similarity:.2f})')

        if not args.execute:
            print("Dry run only; pass --execute to merge these terms.")
            return

        for cluster in clusters:
            SymptomTermDedupService.merge(db, cluster)
        print("Termos mesclados.")


if __name__ == "__main__":
    main()
