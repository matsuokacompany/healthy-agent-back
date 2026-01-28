from datetime import datetime, timedelta, timezone
from collections import Counter

from app.models.models import Symptom, DailyLog


class ReportService:
    def __init__(self, db):
        self.db = db

    def gerar_relatorio(self, user_id: int, periodo: str = "semanal"):
        agora = datetime.now(timezone.utc)

        if periodo == "semanal":
            dias = 7
        elif periodo == "mensal":
            dias = 30
        else:
            raise ValueError("Período inválido. Use 'semanal' ou 'mensal'.")

        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = inicio_atual - timedelta(days=dias)

        # --- Sintomas ---
        sintomas_atuais = (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .filter(Symptom.created_at >= inicio_atual)
            .all()
        )

        sintomas_anteriores = (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .filter(Symptom.created_at >= inicio_anterior)
            .filter(Symptom.created_at < inicio_atual)
            .all()
        )

        # --- Logs ---
        logs = (
            self.db.query(DailyLog)
            .filter(DailyLog.user_id == user_id)
            .filter(DailyLog.created_at >= inicio_atual)
            .all()
        )

        if not sintomas_atuais and not logs:
            return "Nenhum dado registrado no período analisado."

        relatorio = []
        relatorio.append("RELATÓRIO CLÍNICO OBJETIVO\n")
        relatorio.append(f"Período analisado: {inicio_atual.date()} até {agora.date()}\n")

        def contar(lista):
            return Counter(s.description.lower().strip() for s in lista)

        atual = contar(sintomas_atuais)
        anterior = contar(sintomas_anteriores)

        # --- Sintomas atuais ---
        relatorio.append("SINTOMAS — PERÍODO ATUAL:")
        for sintoma, qtd in atual.items():
            relatorio.append(f"- {sintoma}: {qtd} ocorrências")

        # --- Sintomas anteriores ---
        relatorio.append("\nSINTOMAS — PERÍODO ANTERIOR:")
        for sintoma, qtd in anterior.items():
            relatorio.append(f"- {sintoma}: {qtd} ocorrências")

        total_atual = sum(atual.values())
        total_anterior = sum(anterior.values()) or 1
        variacao = ((total_atual - total_anterior) / total_anterior) * 100

        relatorio.append("\nVARIAÇÃO DE SINTOMAS:")
        relatorio.append(f"- Total atual: {total_atual}")
        relatorio.append(f"- Total anterior: {total_anterior}")
        relatorio.append(f"- Variação percentual: {variacao:.1f}%")

        # --- Logs ---
        if logs:
            relatorio.append("\nATIVIDADES RELATADAS:")
            for l in logs:
                relatorio.append(f"- {l.action}")

        # --- Observações ---
        relatorio.append("\nOBSERVAÇÕES:")
        relatorio.append("- Dados auto-relatados pelo paciente")
        relatorio.append("- Sem diagnóstico médico")
        relatorio.append("- Análise automatizada para fins preventivos")

        return "\n".join(relatorio)
