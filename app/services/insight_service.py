from openai import OpenAI

class InsightService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def gerar_interpretacao(self, relatorio_texto: str):
        prompt = f"""
Você é um assistente médico digital. Analise o relatório abaixo e gere um resumo interpretativo:
- Destaque os sintomas mais importantes.
- Diga se há tendência de melhora ou piora.
- Dê uma recomendação personalizada, incluindo possíveis causas e hábitos saudáveis.
- Se houver piora significativa, recomende procurar um médico.

Relatório:
{relatorio_texto}
"""

        resposta = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente especializado em saúde preventiva."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
        )

        return resposta.choices[0].message.content
