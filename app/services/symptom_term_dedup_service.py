import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.security_context import set_database_service_context
from app.models.models import DailyReportSymptomTerm, SymptomTerm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DuplicateCluster:
    canonical: SymptomTerm
    duplicates: tuple[SymptomTerm, ...]
    # Lowest pairwise cosine similarity between the canonical term and any
    # duplicate in the cluster -- a rough confidence signal for the operator
    # reviewing the dry-run output, not used by merge() itself.
    similarity: float


class SymptomTermDedupService:
    """Finds near-duplicate labels in the shared SymptomTerm vocabulary --
    e.g. "Enjoo" vs "Náusea", "Dor de cabeça" vs "Cefaleia" -- that
    SymptomNormalizationService left as separate rows because it only ever
    sees the vocabulary at the moment of a single classification call;
    consistency across many calls, months apart, isn't something a prompt
    alone can guarantee, and the vocabulary only ever grows.

    Deliberately embedding similarity, not another LLM call: this is a
    clustering problem over a fixed, already-normalized list of short
    labels, not a judgment call that needs reasoning. Comparing vectors is
    cheap (no per-call token cost beyond the one-off embedding) and doesn't
    depend on prompt wording drifting between runs.

    Always read-only: find_duplicate_clusters() only proposes merges.
    Nothing is written until merge() is called explicitly -- see
    app/scripts/symptom_term_dedup.py, which is dry-run unless --execute is
    passed, matching the other operational scripts in app/scripts/.
    """

    DEFAULT_SIMILARITY_THRESHOLD = 0.90
    EMBEDDING_MODEL = "text-embedding-3-small"

    @classmethod
    def find_duplicate_clusters(
        cls, db: Session, *, api_key: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> list[DuplicateCluster]:
        terms = db.query(SymptomTerm).order_by(SymptomTerm.id.asc()).all()
        if len(terms) < 2:
            return []

        embeddings = cls._embed([term.label for term in terms], api_key=api_key)
        usage_counts = cls._usage_counts(db)
        return cls._cluster(terms, embeddings, usage_counts, threshold)

    @classmethod
    def _embed(cls, labels: list[str], *, api_key: str) -> list[list[float]]:
        from langchain_openai import OpenAIEmbeddings

        embedder = OpenAIEmbeddings(model=cls.EMBEDDING_MODEL, api_key=api_key)
        return embedder.embed_documents(labels)

    @staticmethod
    def _usage_counts(db: Session) -> dict[int, int]:
        rows = (
            db.query(DailyReportSymptomTerm.symptom_term_id, func.count(DailyReportSymptomTerm.daily_report_id))
            .group_by(DailyReportSymptomTerm.symptom_term_id)
            .all()
        )
        return dict(rows)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @classmethod
    def _cluster(
        cls,
        terms: list[SymptomTerm],
        embeddings: list[list[float]],
        usage_counts: dict[int, int],
        threshold: float,
    ) -> list[DuplicateCluster]:
        n = len(terms)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(n):
            for j in range(i + 1, n):
                if cls._cosine_similarity(embeddings[i], embeddings[j]) >= threshold:
                    union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        clusters = []
        for indices in groups.values():
            if len(indices) < 2:
                continue
            # Canonical = the term with the most existing check-in links
            # (the label patients' reports actually accumulated under),
            # tie-broken by whichever was created first -- never an
            # arbitrary pick, since renaming an already-reported-on term
            # would be the more disruptive direction for existing reports.
            ordered = sorted(indices, key=lambda i: (-usage_counts.get(terms[i].id, 0), terms[i].created_at))
            canonical_idx, duplicate_idxs = ordered[0], ordered[1:]
            min_similarity = min(
                cls._cosine_similarity(embeddings[canonical_idx], embeddings[d]) for d in duplicate_idxs
            )
            clusters.append(
                DuplicateCluster(
                    canonical=terms[canonical_idx],
                    duplicates=tuple(terms[d] for d in duplicate_idxs),
                    similarity=min_similarity,
                )
            )
        return clusters

    @classmethod
    def merge(cls, db: Session, cluster: DuplicateCluster) -> None:
        """Repoints every DailyReportSymptomTerm link from a duplicate term
        to the cluster's canonical term, then deletes the now-unreferenced
        duplicate SymptomTerm rows.

        A report that already links to BOTH the canonical term and a
        duplicate (the same symptom normalized differently on two separate
        check-ins) would collide on the composite primary key
        (daily_report_id, symptom_term_id) if the duplicate's link were
        simply re-pointed -- that link is dropped instead, since the
        existing canonical link already represents it.
        """
        set_database_service_context(db, "symptom_term_dedup")
        canonical_id = cluster.canonical.id
        for duplicate in cluster.duplicates:
            links = db.query(DailyReportSymptomTerm).filter(DailyReportSymptomTerm.symptom_term_id == duplicate.id).all()
            for link in links:
                existing = (
                    db.query(DailyReportSymptomTerm)
                    .filter(
                        DailyReportSymptomTerm.daily_report_id == link.daily_report_id,
                        DailyReportSymptomTerm.symptom_term_id == canonical_id,
                    )
                    .first()
                )
                if existing is not None:
                    db.delete(link)
                else:
                    link.symptom_term_id = canonical_id
            db.flush()
            db.delete(duplicate)
        db.commit()
        logger.info(
            "Merged symptom term duplicates %r into canonical %r (id=%s)",
            [d.label for d in cluster.duplicates],
            cluster.canonical.label,
            canonical_id,
        )
