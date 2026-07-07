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

        inicio_atual = (agora - timedelta(days=dias)).date()
        inicio_anterior = inicio_atual - timedelta(days=dias)
        fim_atual = agora.date()

        # Busca registros do período atual
        relatorios_atuais = (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == user_id)
            .filter(DailyReport.report_date >= inicio_atual)
            .filter(DailyReport.report_date <= fim_atual)
            .all()
        )

        # Busca registros do período anterior
        relatorios_anteriores = (
            self.db.query(DailyReport)
            .filter(DailyReport.user_id == user_id)
            .filter(DailyReport.report_date >= inicio_anterior)
            .filter(DailyReport.report_date < inicio_atual)
            .all()
        )

        if not relatorios_atuais and not relatorios_anteriores:
            return "Nenhum dado registrado no período analisado."

        def concluidos(relatorios):
            return [r for r in relatorios if r.completed]

        def com_sintomas(relatorios):
            return [r for r in concluidos(relatorios) if r.had_symptoms is True]

        def sem_sintomas(relatorios):
            return [r for r in concluidos(relatorios) if r.had_symptoms is False]

        def contar(relatorios):
            counter = Counter()
            for r in com_sintomas(relatorios):
                if r.symptom_description:
                    counter[r.symptom_description.lower().strip()] += 1
            return counter

        atual = contar(relatorios_atuais)
        anterior = contar(relatorios_anteriores)

        total_atual = sum(atual.values())
        total_anterior = sum(anterior.values()) or 1
        variacao = ((total_atual - total_anterior) / total_anterior) * 100
        concluidos_atual = concluidos(relatorios_atuais)
        concluidos_anterior = concluidos(relatorios_anteriores)
        com_sintomas_atual = com_sintomas(relatorios_atuais)
        sem_sintomas_atual = sem_sintomas(relatorios_atuais)
        pendentes_atual = [r for r in relatorios_atuais if not r.completed]
        taxa_adesao = (len(concluidos_atual) / len(relatorios_atuais) * 100) if relatorios_atuais else 0
        taxa_sintomas = (len(com_sintomas_atual) / len(concluidos_atual) * 100) if concluidos_atual else 0

        if len(com_sintomas_atual) > len(com_sintomas(relatorios_anteriores)):
            tendencia = "piorando"
        elif len(com_sintomas_atual) < len(com_sintomas(relatorios_anteriores)):
            tendencia = "melhorando"
        else:
            tendencia = "estável"

        relatorio = [
            "RELATÓRIO CLÍNICO OBJETIVO\n",
            f"Período analisado: {inicio_atual} até {fim_atual}\n",
            "RESUMO DO PERÍODO:",
            f"- Check-ins registrados: {len(relatorios_atuais)}",
            f"- Check-ins respondidos: {len(concluidos_atual)}",
            f"- Check-ins pendentes/expirados: {len(pendentes_atual)}",
            f"- Dias/check-ins com sintomas: {len(com_sintomas_atual)}",
            f"- Dias/check-ins sem sintomas: {len(sem_sintomas_atual)}",
            f"- Taxa de adesão: {taxa_adesao:.1f}%",
            f"- Taxa de sintomas entre respondidos: {taxa_sintomas:.1f}%",
            f"- Tendência vs período anterior: {tendencia}\n",
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
        relatorio.append(f"- Check-ins respondidos no período anterior: {len(concluidos_anterior)}")

        relatorio.append("\nOBSERVAÇÕES:")
        relatorio.append("- Dados auto-relatados pelo paciente")
        relatorio.append("- Sem diagnóstico médico")
        relatorio.append("- Análise automatizada para fins preventivos")

        return "\n".join(relatorio)
