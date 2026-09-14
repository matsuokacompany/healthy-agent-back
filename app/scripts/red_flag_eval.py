import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.models.models import Anamnese, User
from app.services.red_flag_detection_service import RedFlagDetectionService

# Standalone (doesn't import app.main), so nothing else configures logging.
logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout)

DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "red_flag_golden_cases.json"


def _build_session():
    # An isolated in-memory DB, same pattern the test suite uses -- this
    # never touches production data, it only needs a User+Anamnese to run
    # RedFlagDetectionService.detect_for_patient's contextual cross-check.
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_factory()


def _make_user(db, case: dict) -> User:
    user = User(name="Caso de teste", email=f"eval-{case['id']}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    if case.get("fator_risco_field"):
        anamnese = Anamnese(user_id=user.id, **{case["fator_risco_field"]: bool(case["fator_risco_presente"])})
        db.add(anamnese)
        db.commit()
    return user


def run(fixture_path: Path, *, only_mismatches: bool, only_unreviewed: bool) -> int:
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))["cases"]
    db = _build_session()

    passed = 0
    failed = 0
    unreviewed_count = 0
    for case in cases:
        if only_unreviewed and case.get("revisado_pelo_medico", False):
            continue
        user = _make_user(db, case)
        match = RedFlagDetectionService.detect_for_patient(db, user, case["texto"])
        got = match.category.key if match else None
        expected = case.get("categoria_esperada")
        ok = got == expected
        passed += ok
        failed += not ok
        if not case.get("revisado_pelo_medico", False):
            unreviewed_count += 1

        if ok and only_mismatches:
            continue
        status = "OK  " if ok else "FAIL"
        flag = "" if case.get("revisado_pelo_medico", False) else "  [NÃO REVISADO PELO MÉDICO]"
        print(f"{status} {case['id']:8s} esperado={str(expected):32s} obtido={str(got):32s}{flag}")
        if not ok:
            print(f"       texto: {case['texto']!r}")

    total = passed + failed
    print(f"\n{passed}/{total} corretos ({unreviewed_count} caso(s) ainda sem revisão médica).")
    return 0 if failed == 0 else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the red-flag classifier against the golden case set and report accuracy (calls the real OpenAI API — small real cost, see fixture file)."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--only-mismatches", action="store_true", help="only print cases where the classifier disagreed with the expected label")
    parser.add_argument("--only-unreviewed", action="store_true", help="only run cases not yet confirmed by a physician (revisado_pelo_medico=false)")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY não configurada.")
        sys.exit(1)
    sys.exit(run(args.fixture, only_mismatches=args.only_mismatches, only_unreviewed=args.only_unreviewed))


if __name__ == "__main__":
    main()
