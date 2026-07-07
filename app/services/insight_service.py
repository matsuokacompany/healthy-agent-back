from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


class InsightService:
    MAX_REPORT_CHARS = 6000

    def __init__(self, api_key: str, modo: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada")

        if modo not in ("preventivo", "avaliacao_clinica"):
            raise ValueError("Modo inválido")

        self.modo = modo

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            max_tokens=500,
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
                    "PT-BR. Sem diagnóstico. Responda só JSON válido, curto e objetivo."
                ),
                (
                    "human",
                    (
                        "Analise o relatório preventivo e retorne JSON compacto:\n"
                        "{{\"cenarios\":{{\"otimista\":{{\"descricao\":\"\",\"condicoes_para_ocorrer\":\"\",\"probabilidade\":\"baixa|media|alta\"}},"
                        "\"intermediario\":{{\"descricao\":\"\",\"condicoes_para_ocorrer\":\"\",\"probabilidade\":\"baixa|media|alta\"}},"
                        "\"grave\":{{\"descricao\":\"\",\"condicoes_para_ocorrer\":\"\",\"probabilidade\":\"baixa|media|alta\"}}}},"
                        "\"cenario_mais_provavel\":\"\",\"especialista_recomendado\":\"\",\"exames_sugeridos\":[],\"alerta_importante\":\"\"}}\n"
                        "Relatório:\n{relatorio}"
                    )
                ),
            ]
        )

    # 🔴 AVALIAÇÃO CLÍNICA
    def _prompt_avaliacao_clinica(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "PT-BR. Não confirme diagnóstico. Liste possíveis doenças só como hipóteses, se necessário. Responda só JSON válido e compacto."
                ),
                (
                    "human",
                    (
                        "Analise o relatório clínico e retorne JSON compacto:\n"
                        "{{\"avaliacao_clinica\":{{\"hipotese_principal\":\"\",\"possiveis_doencas\":[],\"nivel_de_suspeicao\":\"baixo|moderado|alto\",\"justificativa\":[]}},"
                        "\"especialista_recomendado\":\"\",\"exames_prioritarios\":[],\"urgencia\":\"baixa|media|alta\",\"alerta_legal\":\"\"}}\n"
                        "Relatório:\n{relatorio}"
                    )
                ),
            ]
        )

    def gerar_interpretacao(self, relatorio_texto: str) -> dict:
        relatorio_texto = (relatorio_texto or "").strip()[: self.MAX_REPORT_CHARS]
        resultado = self.chain.invoke({"relatorio": relatorio_texto})

        if self.modo == "avaliacao_clinica" and "avaliacao_clinica" not in resultado:
            raise RuntimeError("Resposta inválida para avaliação clínica")

        return resultado
