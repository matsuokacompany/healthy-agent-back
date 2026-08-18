from app.models.models import AiReportCache, Anamnese, DailyReport


def test_clinical_encryption_envelope_columns_are_nullable_and_additive():
    expected = {
        Anamnese: ("info", "info_encryption_envelope"),
        DailyReport: (
            "symptom_description",
            "symptom_description_encryption_envelope",
            "suspected_cause",
            "suspected_cause_encryption_envelope",
        ),
        AiReportCache: (
            "clinical_summary",
            "clinical_summary_encryption_envelope",
            "ai_response",
            "ai_response_encryption_envelope",
        ),
    }

    for model, column_names in expected.items():
        columns = model.__table__.columns
        for column_name in column_names:
            assert column_name in columns
        for column_name in column_names:
            if column_name.endswith("_envelope"):
                assert columns[column_name].nullable is True

    assert Anamnese.__table__.columns.info.nullable is True
    assert AiReportCache.__table__.columns.ai_response.type.none_as_null is True
