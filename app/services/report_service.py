from datetime import datetime, timedelta, timezone
from collections import Counter
from app.models.models import Symptom, DailyLog, User

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

        # --- Período atual ---
        sintomas_atuais = (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .filter(Symptom.created_at >= inicio_atual)
            .all()
        )

        # --- Período anterior (para comparação) ---
        sintomas_anteriores = (
            self.db.query(Symptom)
            .filter(Symptom.user_id == user_id)
            .filter(Symptom.created_at >= inicio_anterior)
            .filter(Symptom.created_at < inicio_atual)
            .all()
        )

        logs = (
            self.db.query(DailyLog)
            .filter(DailyLog.user_id == user_id)
            .filter(DailyLog.created_at >= inicio_atual)
            .all()
        )

        if not sintomas_atuais and not logs:
            return f"📊 Nenhum dado registrado nos últimos {dias} dias."

        relatorio = [f"📅 Relatório {periodo.capitalize()}"]
        relatorio.append(f"🕒 Período: {inicio_atual.date()} até {agora.date()}\n")

        # --- Estatísticas de sintomas ---
        if sintomas_atuais:
            descricoes_atuais = [s.description.lower().strip() for s in sintomas_atuais]
            descricoes_anteriores = [s.description.lower().strip() for s in sintomas_anteriores]

            contagem_atual = Counter(descricoes_atuais)
            contagem_anterior = Counter(descricoes_anteriores)

            total_atual = sum(contagem_atual.values())
            total_anterior = sum(contagem_anterior.values()) or 1

            variacao_total = ((total_atual - total_anterior) / total_anterior) * 100
            relatorio.append(f"🤒 Total de sintomas relatados: {total_atual} ({variacao_total:+.1f}% vs período anterior)\n")

            relatorio.append("📈 Sintomas mais frequentes:")
            for sintoma, qtd in contagem_atual.most_common(5):
                qtd_ant = contagem_anterior.get(sintoma, 0)
                variacao = ((qtd - qtd_ant) / qtd_ant * 100) if qtd_ant > 0 else 100
                relatorio.append(f"• {sintoma.capitalize()} — {qtd}x ({variacao:+.0f}%)")

        else:
            relatorio.append("✅ Nenhum sintoma registrado.\n")

        # --- Logs de atividades ---
        if logs:
            relatorio.append("\n📘 Atividades diárias registradas:")
            for l in logs:
                relatorio.append(f"• {l.created_at.strftime('%d/%m %H:%M')} — {l.action}")
        else:
            relatorio.append("\n(sem atividades registradas)")

        # --- Conclusão geral ---
        if sintomas_atuais:
            if variacao_total > 20:
                relatorio.append("\n⚠️ Tendência de piora detectada. Mantenha acompanhamento e registre detalhes.")
            elif variacao_total < -20:
                relatorio.append("\n✅ Boa melhora! Continue com hábitos saudáveis.")
            else:
                relatorio.append("\n📊 Sintomas estáveis em relação ao período anterior.")

        return "\n".join(relatorio)
