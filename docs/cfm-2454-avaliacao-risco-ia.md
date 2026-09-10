# Modelo de avaliação preliminar de risco — uso de IA na Julha (art. 12, Resolução CFM nº 2.454/2026)

> Este documento é um modelo/template técnico, não uma avaliação já concluída. A Resolução CFM nº
> 2.454/2026 (em vigor desde 26/08/2026) exige, no seu art. 12, que a instituição/profissional que usa
> IA como apoio à decisão médica realize uma avaliação preliminar classificando o risco da aplicação
> como baixo, médio, alto ou inaceitável. A Julha preenche aqui a parte técnica/funcional (o que a
> ferramenta faz, que já é do nosso conhecimento); a classificação de risco em si e a assinatura da
> avaliação devem ser feitas pelo médico responsável pelo protocolo clínico de cada profissional/clínica
> cliente, com apoio de assessoria jurídica quando necessário — não pela Julha unilateralmente.
>
> Cada profissional/clínica cliente pode copiar este modelo e preencher sua própria avaliação, já que a
> responsabilidade pela avaliação institucional é de quem usa a ferramenta na prática clínica, não da
> Julha como fornecedora de software.

## 1. Identificação da aplicação de IA avaliada

- **Nome da funcionalidade:** Relatório de IA — modalidade "apoio à avaliação clínica" (`avaliacao_clinica`)
- **Fornecedor da plataforma:** Julha (66.039.068 IGOR EIIJI AVELAR MATSUOKA)
- **Provedor do modelo de IA:** OpenAI (modelos da família GPT, ex.: GPT-4o-mini; o modelo exato em uso
  pode ser consultado com o suporte da Julha a qualquer momento)
- **Quem pode acionar a funcionalidade:** profissionais de saúde cadastrados e administradores; nunca o
  paciente diretamente
- **Dado de entrada:** resumo consolidado dos check-ins de sintomas do período selecionado, anamnese e,
  quando cadastrados, fatores de risco estruturados do paciente (ver anamnese) — texto truncado em 6.000
  caracteres para limitar custo e exposição de dados
- **Saída gerada:** hipótese diagnóstica principal, lista de possíveis condições associadas, nível de
  suspeição (baixo/moderado/alto), justificativa, especialidade recomendada, exames prioritários e nível
  de urgência sugerido (baixa/média/alta)

## 2. Finalidade clínica declarada

Apoiar o raciocínio clínico do profissional responsável, oferecendo hipóteses e sugestões de
investigação a partir do histórico relatado pelo paciente — nunca substituindo exame físico, anamnese
presencial ou julgamento clínico do profissional. O profissional mantém responsabilidade exclusiva pela
decisão diagnóstica e terapêutica.

## 3. Controles já existentes na plataforma (mitigação técnica)

- A saída da IA é sempre apresentada como hipótese, nunca como diagnóstico confirmado, tanto na
  interface quanto no aviso fixo exibido junto a cada relatório.
- O acesso à modalidade diagnóstica é restrito a profissionais/administradores autenticados; pacientes
  em autoacompanhamento só recebem um resumo sem hipótese diagnóstica, suspeição ou urgência.
  (`app/services/self_monitoring_service.py`, modo `resumo_paciente`)
- Cada geração é registrada de forma durável e atribuível: paciente, profissional solicitante, modelo de
  IA usado, versão do prompt, datas de solicitação/geração e o conteúdo gerado
  (`AiReportCache.model_name`, `.prompt_version`, `.professional_user_id`, `.generated_at`).
- Limites técnicos de custo/tamanho de entrada e cooldown entre gerações por paciente (ver
  `docs/custom-ai-reports.md`).
- Conteúdo clínico sensível (resumo, anamnese, resposta da IA) é protegido por criptografia de envelope
  em repouso (ver `docs/security.md`).

## 4. Classificação de risco — **a preencher pelo médico responsável / assessoria jurídica**

- [ ] Baixo
- [ ] Médio
- [ ] Alto
- [ ] Inaceitável

**Justificativa da classificação:** _____________________________________________

**Fatores considerados** (sugestão de pontos a discutir, não uma lista exaustiva):
- Gravidade das condições que a ferramenta pode sugerir (inclui hipóteses de alta urgência?)
- Probabilidade e impacto de um falso negativo (a IA não sinalizar algo que seria relevante investigar)
  versus um falso positivo (a IA sugerir algo que não procede)
- Nível de dependência esperado do profissional em relação à sugestão da IA no fluxo real de trabalho
- Perfil de pacientes atendidos (ex.: presença de comorbidades/fatores de risco que mudem a gravidade
  esperada dos quadros monitorados)

## 5. Medidas de mitigação adicionais adotadas pela instituição/profissional (se houver)

_____________________________________________________________________________

## 6. Responsável pela avaliação

- **Nome:** _____________________________
- **Conselho de classe / nº de registro:** _____________________________
- **Data da avaliação:** ___/___/______
- **Data prevista de revisão:** ___/___/______ (recomenda-se revisar a cada nova versão relevante da
  funcionalidade, ou no mínimo anualmente)

## 7. Registro

Mantenha este documento preenchido e assinado junto aos demais registros de conformidade da sua
clínica/consultório. Ele não precisa ser enviado à Julha, mas a Julha pode solicitar evidência de sua
existência caso seja necessário demonstrar conformidade perante o CFM ou outra autoridade.
