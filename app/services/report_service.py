from datetime import datetime, timezone, timedelta
from collections import defaultdict
from app.models.models import DailyReport, DailyReportSymptomTerm, SymptomTerm
from app.services.daily_report_service import DailyReportService

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

        atual = self._agrupar_sintomas(com_sintomas(relatorios_atuais))
        anterior = self._agrupar_sintomas(com_sintomas(relatorios_anteriores))

        total_atual = sum(grupo["ocorrencias"] for grupo in atual.values())
        total_anterior = sum(grupo["ocorrencias"] for grupo in anterior.values()) or 1
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
        for sintoma, grupo in atual.items():
            relatorio.append(f"- {sintoma}: {self._descricao_ocorrencias(grupo)}")

        relatorio.append("\nSINTOMAS — PERÍODO ANTERIOR:")
        for sintoma, grupo in anterior.items():
            relatorio.append(f"- {sintoma}: {self._descricao_ocorrencias(grupo)}")

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

    @staticmethod
    def _descricao_ocorrencias(grupo: dict) -> str:
        base = f"{grupo['ocorrencias']} ocorrência(s)"
        # streak_days > 1 means SymptomNormalizationService resolved a later
        # check-in (e.g. "mesma dor, mesmo lugar") as a continuation of this
        # same symptom -- surfacing it here, in the text that feeds the AI's
        # hypothesis/exam-direction prompt, is what makes "persistent for 5
        # days straight" read differently from "reported 5 unrelated times".
        if grupo["maior_sequencia"] > 1:
            base += f", persistente por até {grupo['maior_sequencia']} dias seguidos"
        return base

    def _agrupar_sintomas(self, relatorios: list[DailyReport]) -> dict:
        """Agrupa check-ins com sintoma pelo(s) SymptomTerm normalizado(s)
        (ver SymptomNormalizationService) em vez do texto livre bruto -- é
        isso que evita que uma resposta como "mesma dor, mesmo lugar" apareça
        como uma linha nova e sem relação em vez de somar à contagem do
        sintoma que ela está, na verdade, confirmando. Um check-in que o
        classificador ainda não alcançou cai de volta para o texto bruto,
        então nada desaparece silenciosamente da lista.
        """
        if not relatorios:
            return {}

        report_ids = [r.id for r in relatorios]
        term_rows = (
            self.db.query(DailyReportSymptomTerm.daily_report_id, SymptomTerm.label, DailyReportSymptomTerm.streak_days)
            .join(SymptomTerm, SymptomTerm.id == DailyReportSymptomTerm.symptom_term_id)
            .filter(DailyReportSymptomTerm.daily_report_id.in_(report_ids))
            .all()
        )
        terms_by_report: dict[int, list[str]] = defaultdict(list)
        streak_by_report: dict[int, int] = {}
        for daily_report_id, label, streak_days in term_rows:
            terms_by_report[daily_report_id].append(label)
            streak_by_report[daily_report_id] = max(streak_by_report.get(daily_report_id, 0), streak_days)

        grupos: dict[str, dict] = defaultdict(lambda: {"ocorrencias": 0, "maior_sequencia": 0})
        for r in relatorios:
            DailyReportService.hydrate_clinical(r)
            labels = terms_by_report.get(r.id)
            if not labels and r.symptom_description:
                # Matches the pre-normalization fallback exactly (lowercased,
                # whitespace-collapsed raw text) so a report the classifier
                # hasn't reached yet still groups with itself across calls.
                labels = [" ".join(r.symptom_description.split()).lower()]
            if not labels:
                continue
            chave = ", ".join(dict.fromkeys(sorted(labels, key=str.casefold)))
            grupos[chave]["ocorrencias"] += 1
            if r.id in streak_by_report:
                grupos[chave]["maior_sequencia"] = max(grupos[chave]["maior_sequencia"], streak_by_report[r.id])

        return dict(grupos)
