from app.core.clinical_encryption import build_clinical_encryption_service
from app.core.config import settings


def main() -> None:
    service = build_clinical_encryption_service(settings)
    context = {
        "table": "preflight",
        "record_id": "0",
        "patient_id": "0",
        "field": "connectivity_test",
    }
    original = "healthy-agent-kms-preflight-no-patient-data"
    encrypted = service.encrypt(original, context=context)
    if service.decrypt(encrypted, context=context) != original:
        raise RuntimeError("Clinical encryption round trip did not match")
    print("Clinical encryption KMS preflight: OK")


if __name__ == "__main__":
    main()
