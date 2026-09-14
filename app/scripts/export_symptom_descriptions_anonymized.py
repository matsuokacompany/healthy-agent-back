"""Export an ANONYMIZED sample of real patients' check-in symptom
descriptions for building a real golden case set for the red-flag
classifier -- see app/scripts/fixtures/red_flag_golden_cases.json and
app/scripts/red_flag_eval.py, which today only have Claude-drafted synthetic
cases. This script classifies nothing and assigns no category: a physician
still has to fill in categoria_esperada for every exported case.

Output NEVER includes name, e-mail, phone, or user id -- only an opaque
sequential id, the free-text description (decrypted through
ClinicalDataService, the same path production reads use), and the boolean
anamnese risk-factor flags the contextual categories need.

IMPORTANT: this changes the PURPOSE the data is used for (aggregate
model/prompt improvement, not generating one patient's own report), which is
a separate legal basis under the LGPD from what
docs/legal/politica-de-privacidade.md discloses today. Do not run this
against production before that document says so -- the --confirm flag below
is a reminder, not a substitute for actually checking.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.security_context import set_database_service_context
from app.models.models import Anamnese, DailyReport
from app.services.clinical_data_service import ClinicalDataService
from app.services.red_flag_symptoms import ANAMNESE_RISK_FACTOR_FIELDS

README = (
    "DRAFT export of real (anonymized) check-in descriptions -- no categoria_esperada "
    "assigned yet, this is not a classified golden set. A physician must review every "
    "case and fill categoria_esperada (see red_flag_golden_cases.json for the shape) "
    "before this is used for evaluation or few-shot examples."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=200, help="maximum number of check-ins to export")
    parser.add_argument("--out", type=Path, default=Path("symptom_descriptions_export.json"))
    parser.add_argument(
        "--confirm-privacy-policy-covers-this",
        action="store_true",
        dest="confirmed",
        help=(
            "required -- confirms docs/legal/politica-de-privacidade.md already discloses "
            "aggregate/anonymized use of check-in data to improve triage accuracy"
        ),
    )
    return parser


def export_symptom_descriptions(
    db: Session, *, limit: int, clinical_data: ClinicalDataService | None = None
) -> list[dict]:
    """The testable core: reads and anonymizes, writes nothing. `run()`
    below is the thin CLI wrapper that owns the real SessionLocal and the
    output file. `clinical_data` defaults to the real KMS-backed service
    (production behavior); tests inject a local one instead of needing
    AWS credentials configured."""
    clinical_data = clinical_data or ClinicalDataService()
    set_database_service_context(db, "symptom_description_export")
    reports = (
        db.query(DailyReport)
        .filter(DailyReport.had_symptoms.is_(True))
        .order_by(DailyReport.id.desc())
        .limit(limit)
        .all()
    )
    cases = []
    for index, report in enumerate(reports, start=1):
        texto = clinical_data.read_text(report, "symptom_description")
        if not texto:
            continue
        anamnese = db.query(Anamnese).filter(Anamnese.user_id == report.user_id).first()
        risk_factors = {
            field: bool(getattr(anamnese, field, False)) for field in ANAMNESE_RISK_FACTOR_FIELDS
        } if anamnese else {}
        cases.append(
            {
                "id": f"real-{index:04d}",
                "categoria_esperada": None,
                "fator_risco_presente": risk_factors,
                "texto": texto,
                "nota": "Texto real de produção, anonimizado -- precisa de rótulo médico.",
                "revisado_pelo_medico": False,
            }
        )
    return cases


def run(*, limit: int, out_path: Path) -> int:
    with SessionLocal() as db:
        cases = export_symptom_descriptions(db, limit=limit)

    out_path.write_text(
        json.dumps({"_readme": README, "cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(cases)} caso(s) exportado(s) para {out_path}")
    return 0


def main() -> None:
    args = _parser().parse_args()
    if not args.confirmed:
        print(
            "Recusando exportar: confirme que docs/legal/politica-de-privacidade.md já "
            "cobre esse uso agregado/anonimizado e rode de novo com "
            "--confirm-privacy-policy-covers-this."
        )
        sys.exit(1)
    sys.exit(run(limit=args.limit, out_path=args.out))


if __name__ == "__main__":
    main()
