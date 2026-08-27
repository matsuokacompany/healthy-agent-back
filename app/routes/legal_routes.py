from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Legal"])

_LEGAL_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "legal"

# Whitelisted by slug rather than accepting a raw filename, so a client can
# never traverse outside docs/legal/ regardless of what's requested.
_DOCUMENTS = {
    "termos-de-uso": "termos-de-uso.md",
    "politica-de-privacidade": "politica-de-privacidade.md",
    "politica-de-reembolso": "politica-de-reembolso.md",
}


@router.get("/{slug}", response_class=PlainTextResponse)
def get_legal_document(slug: str):
    filename = _DOCUMENTS.get(slug)
    if not filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown legal document")
    path = _LEGAL_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal document not available")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")
