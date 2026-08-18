from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import AiReportCache, AiReportStatusEnum, Anamnese
from app.models.schemas import CustomAiReportCreateRequest, CustomAiReportResponse
from app.services.custom_report_preview_service import CustomReportPreviewService
from app.services.custom_report_service import CustomReportService
from app.services.insight_service import InsightService
from app.services.anamnese_clinical_service import AnamneseClinicalService


@dataclass(frozen=True)
class CustomReportCostPolicy:
    model_name: str
    max_input_tokens: int
    max_output_tokens: int
    max_cost_usd: Decimal
    input_cost_per_million_usd: Decimal
    output_cost_per_million_usd: Decimal


class CustomReportGenerationService:
    PROMPT_VERSION = "custom-clinical-v1"
    APPROXIMATE_PROMPT_OVERHEAD_TOKENS = 400

    def __init__(
        self,
        db: Session,
        *,
        token_secret: str,
        api_key: str,
        cost_policy: CustomReportCostPolicy,
    ):
        self.db = db
        self.preview_service = CustomReportPreviewService(db, token_secret)
        self.api_key = api_key
        self.cost_policy = cost_policy

    def generate(
        self,
        *,
        patient_id: int,
        requested_by_user_id: int,
        payload: CustomAiReportCreateRequest,
        now: datetime | None = None,
    ) -> CustomAiReportResponse:
        now = now or datetime.now(timezone.utc)
        token_payload = self._validate_token(payload, patient_id, requested_by_user_id, now)
        idempotency_key = self._idempotency_key(payload.preview_token)
        existing = self.db.query(AiReportCache).filter(AiReportCache.idempotency_key == idempotency_key).first()
        if existing:
            return self._response(existing)

        preview = self.preview_service.preview(
            patient_id=patient_id,
            requested_by_user_id=requested_by_user_id,
            payload=payload,
            now=now,
        )
        if not preview.eligibility.can_generate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=preview.eligibility.reason)
        if token_payload["summary_hash"] != self.preview_service.summary_hash(preview.summary):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PREVIEW_DATA_CHANGED")

        clinical_summary = self._build_clinical_text(patient_id, preview.summary)
        estimated_input_tokens = self._estimate_input_tokens(clinical_summary)
        if estimated_input_tokens > self.cost_policy.max_input_tokens:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="REPORT_INPUT_TOO_LARGE")
        estimated_cost = self._calculate_cost(estimated_input_tokens, self.cost_policy.max_output_tokens)
        if estimated_cost > self.cost_policy.max_cost_usd:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="REPORT_COST_LIMIT_EXCEEDED")

        report = AiReportCache(
            patient_id=patient_id,
            professional_user_id=requested_by_user_id,
            periodo="personalizado",
            modo=payload.modo,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=AiReportStatusEnum.PENDING.value,
            clinical_summary_hash=token_payload["summary_hash"],
            clinical_summary=clinical_summary,
            requested_at=now,
            estimated_cost=estimated_cost,
            model_name=self.cost_policy.model_name,
            prompt_version=self.PROMPT_VERSION,
            idempotency_key=idempotency_key,
        )
        self.db.add(report)
        try:
            self.db.flush()
            AiReportClinicalService.write_summary(report, clinical_summary)
            self.db.commit()
            self.db.refresh(report)
        except IntegrityError:
            self.db.rollback()
            existing = self._active_or_idempotent_report(patient_id, idempotency_key)
            if existing:
                return self._response(existing)
            raise

        report.status = AiReportStatusEnum.PROCESSING.value
        report.processing_started_at = now
        self.db.commit()

        try:
            result = InsightService(
                api_key=self.api_key,
                modo=payload.modo,
                model=self.cost_policy.model_name,
                max_tokens=self.cost_policy.max_output_tokens,
            ).gerar_interpretacao_com_uso(clinical_summary)
            generated_at = datetime.now(timezone.utc)
            AiReportClinicalService.write_response(report, result.data)
            report.input_tokens = result.input_tokens
            report.output_tokens = result.output_tokens
            report.actual_cost = self._calculate_cost(result.input_tokens, result.output_tokens)
            report.generated_at = generated_at
            report.next_generation_at = generated_at + timedelta(days=30)
            report.status = AiReportStatusEnum.COMPLETED.value
            self.db.commit()
            self.db.refresh(report)
            return self._response(report)
        except Exception as exc:
            self.db.rollback()
            report = self.db.query(AiReportCache).filter(AiReportCache.id == report.id).first()
            report.status = AiReportStatusEnum.FAILED.value
            report.failure_code = "AI_GENERATION_FAILED"
            report.failure_message = str(exc)[:1000]
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "AI_GENERATION_FAILED", "report_id": report.id},
            ) from exc

    def _validate_token(self, payload, patient_id: int, requested_by_user_id: int, now: datetime) -> dict:
        try:
            token_payload = self.preview_service.decode_token(payload.preview_token, now=now)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        expected = {
            "patient_id": patient_id,
            "requested_by_user_id": requested_by_user_id,
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
            "modo": payload.modo,
        }
        if any(token_payload.get(key) != value for key, value in expected.items()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PREVIEW_TOKEN_MISMATCH")
        return token_payload

    def _build_clinical_text(self, patient_id: int, summary) -> str:
        anamnese = self.db.query(Anamnese).filter(Anamnese.user_id == patient_id).first()
        return "\n\n".join(
            [
                "ANAMNESE DO PACIENTE:",
                AnamneseClinicalService.hydrate(anamnese).info if anamnese else "Anamnese não registrada.",
                "DADOS CONSOLIDADOS DO PERÍODO (JSON):",
                json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")),
            ]
        )

    def _estimate_input_tokens(self, text: str) -> int:
        return math.ceil(len(text) / 4) + self.APPROXIMATE_PROMPT_OVERHEAD_TOKENS

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal("1000000")
        return (
            Decimal(input_tokens) * self.cost_policy.input_cost_per_million_usd / million
            + Decimal(output_tokens) * self.cost_policy.output_cost_per_million_usd / million
        ).quantize(Decimal("0.00000001"))

    @staticmethod
    def _idempotency_key(preview_token: str) -> str:
        return hashlib.sha256(preview_token.encode("utf-8")).hexdigest()

    def _active_or_idempotent_report(self, patient_id: int, idempotency_key: str):
        return (
            self.db.query(AiReportCache)
            .filter(
                (AiReportCache.idempotency_key == idempotency_key)
                | (
                    (AiReportCache.patient_id == patient_id)
                    & AiReportCache.status.in_([AiReportStatusEnum.PENDING.value, AiReportStatusEnum.PROCESSING.value])
                )
            )
            .order_by(AiReportCache.id.desc())
            .first()
        )

    @staticmethod
    def _response(report: AiReportCache) -> CustomAiReportResponse:
        AiReportClinicalService.hydrate(report)
        return CustomAiReportResponse(
            report_id=report.id,
            patient_id=report.patient_id,
            start_date=report.start_date,
            end_date=report.end_date,
            modo=report.modo,
            status=report.status,
            requested_by_user_id=report.professional_user_id,
            requested_at=report.requested_at,
            processing_started_at=report.processing_started_at,
            generated_at=report.generated_at,
            next_generation_at=report.next_generation_at,
            clinical_summary=report.clinical_summary,
            ai=report.ai_response,
            input_tokens=report.input_tokens,
            output_tokens=report.output_tokens,
            estimated_cost=float(report.estimated_cost) if report.estimated_cost is not None else None,
            actual_cost=float(report.actual_cost) if report.actual_cost is not None else None,
            model_name=report.model_name,
            failure_code=report.failure_code,
        )
