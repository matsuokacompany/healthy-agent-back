from datetime import datetime, timezone, timedelta
from collections import Counter
from app.models.models import DailyReport

class ReportService:
    """Gera relatórios a partir da tabela DailyReport"""

    def __init__(self, db):
        self.db = db

    def gerar_relatorio(self, user_id: int, periodo: str = "semanal"):
        agora = datetime.now(timezone.utc)

        dias_por_periodo = {
            "diario": 1,
            "semanal": 7,
            "mensal": 30,
        }
        try:
            dias = dias_por_periodo[periodo]
        except KeyError:
            raise ValueError("Período inválido. Use 'diario', 'semanal' ou 'mensal'.")

        inicio_atual = agora - timedelta(days=dias)
        inicio_anterior = inicio_atual - timedelta(days=dias)

        # Busca registros do período atual
        relatorios_atuais = (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == user_id)
            .filter(DailyReport.completed == True)
            .filter(DailyReport.created_at >= inicio_atual)
            .all()
        )

        # Busca registros do período anterior
        relatorios_anteriores = (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == user_id)
            .filter(DailyReport.completed == True)
            .filter(DailyReport.created_at >= inicio_anterior)
            .filter(DailyReport.created_at < inicio_atual)
            .all()
        )

        if not relatorios_atuais and not relatorios_anteriores:
            return "Nenhum dado registrado no período analisado."

        def contar(relatorios):
            counter = Counter()
            for r in relatorios:
                if r.symptom_description:
                    counter[r.symptom_description.lower().strip()] += 1
            return counter

        atual = contar(relatorios_atuais)
        anterior = contar(relatorios_anteriores)

        total_atual = sum(atual.values())
        total_anterior = sum(anterior.values()) or 1
        variacao = ((total_atual - total_anterior) / total_anterior) * 100

        relatorio = [
            "RELATÓRIO CLÍNICO OBJETIVO\n",
            f"Período analisado: {inicio_atual.date()} até {agora.date()}\n",
            "SINTOMAS — PERÍODO ATUAL:"
        ]
        for sintoma, qtd in atual.items():
            relatorio.append(f"- {sintoma}: {qtd} ocorrência(s)")

        relatorio.append("\nSINTOMAS — PERÍODO ANTERIOR:")
        for sintoma, qtd in anterior.items():
            relatorio.append(f"- {sintoma}: {qtd} ocorrência(s)")

        relatorio.append("\nVARIAÇÃO DE SINTOMAS:")
        relatorio.append(f"- Total atual: {total_atual}")
        relatorio.append(f"- Total anterior: {total_anterior}")
        relatorio.append(f"- Variação percentual: {variacao:.1f}%")

        relatorio.append("\nOBSERVAÇÕES:")
        relatorio.append("- Dados auto-relatados pelo paciente")
        relatorio.append("- Sem diagnóstico médico")
        relatorio.append("- Análise automatizada para fins preventivos")

        return "\n".join(relatorio)