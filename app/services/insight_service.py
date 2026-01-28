from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


class InsightService:
    def __init__(self, api_key: str, modo: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada")

        if modo not in ("preventivo", "avaliacao_clinica"):
            raise ValueError("Modo inválido")

        self.modo = modo

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=api_key,
        )

        self.parser = JsonOutputParser()
        self.prompt = self._build_prompt()
        self.chain = self.prompt | self.llm | self.parser

    def _build_prompt(self) -> ChatPromptTemplate:
        return (
            self._prompt_avaliacao_clinica()
            if self.modo == "avaliacao_clinica"
            else self._prompt_preventivo()
        )

    # 🟢 PREVENTIVO
    def _prompt_preventivo(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are a preventive health AI assistant.
You do NOT provide medical diagnoses.
All responses MUST be written in Brazilian Portuguese.
Output ONLY valid JSON.
"""
                ),
                (
                    "human",
                    """
Analyze the preventive health report below.

Report:
{relatorio}

Return ONLY the following JSON structure:

{{
  "cenarios": {{
    "otimista": {{
      "descricao": "",
      "condicoes_para_ocorrer": "",
      "probabilidade": "baixa | media | alta"
    }},
    "intermediario": {{
      "descricao": "",
      "condicoes_para_ocorrer": "",
      "probabilidade": "baixa | media | alta"
    }},
    "grave": {{
      "descricao": "",
      "condicoes_para_ocorrer": "",
      "probabilidade": "baixa | media | alta"
    }}
  }},
  "cenario_mais_provavel": "",
  "especialista_recomendado": "",
  "exames_sugeridos": [],
  "alerta_importante": ""
}}
"""
                ),
            ]
        )

    # 🔴 AVALIAÇÃO CLÍNICA
    def _prompt_avaliacao_clinica(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are a clinical risk assessment AI.

You do NOT confirm medical diagnoses.
You MAY provide diagnostic hypotheses and risk stratification.
All responses MUST be written in Brazilian Portuguese.
Output ONLY valid JSON.
"""
                ),
                (
                    "human",
                    """
Analyze the clinical report below.

Report:
{relatorio}

Return ONLY the following JSON:

{{
  "avaliacao_clinica": {{
    "hipotese_principal": "",
    "nivel_de_suspeicao": "baixo | moderado | alto",
    "justificativa": []
  }},
  "especialista_recomendado": "",
  "exames_prioritarios": [],
  "urgencia": "baixa | media | alta",
  "alerta_legal": ""
}}
"""
                ),
            ]
        )

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        resultado = self.chain.invoke({"relatorio": relatorio_texto})

        if self.modo == "avaliacao_clinica" and "avaliacao_clinica" not in resultado:
            raise RuntimeError("Resposta inválida para avaliação clínica")

        return resultado
