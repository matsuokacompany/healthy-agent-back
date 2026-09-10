# Padrões cumulativos e o modelo de 4 níveis (vermelho/laranja/amarelo/verde)

> **v2 deste documento.** A v1 propunha um único grupo de sinais disparado por contagem genérica ("N de M
> sinais distintos numa janela"). O critério clínico trazido pelo usuário (CDC, AHA/ACC, OMS, NICE — ver
> seção 6) **rejeita explicitamente esse formato de regra** ("não deve ser utilizada uma regra genérica
> baseada apenas na quantidade de sintomas"). Esta versão reestrutura o sistema inteiro em torno do modelo
> de 4 níveis descrito nesse critério e substitui a regra genérica por combinações específicas com fonte.
> **Já implementado** em `app/services/red_flag_symptoms.py`/`app/bot/scheduler.py`, mas desligado por
> padrão (`ORANGE_COMBINATION_ALERTS_ENABLED=False`) até a validação do médico responsável.

## 1. O modelo de 4 níveis

| Nível | Significado | No sistema hoje |
|---|---|---|
| 🔴 **Vermelho** | Possível emergência — nunca condicionado a duração | `RED_FLAG_ABSOLUTE_CATEGORIES` + `RED_FLAG_CONTEXTUAL_CATEGORIES` (já existiam, revisados anteriormente) |
| 🟠 **Laranja** | Avaliação médica em curto prazo — combinação/persistência específica, não é emergência | **Novo**: `ORANGE_COMBINATION_RULES` (seção 3) |
| 🟡 **Amarelo** | Avaliação médica programada — sintoma único recorrente, sem combinação preocupante | `_fire_symptom_pattern_alert`/`SYMPTOM_PATTERN_ALERT` (já existia, sem mudança de lógica) |
| 🟢 **Verde** | Baixo risco imediato | Nenhum match — reclassificável automaticamente a cada novo check-in |

**Por que ABSOLUTO e CONTEXTUAL viram os dois "vermelho"**: ABSOLUTO porque é agudo e nunca espera
duração (regra de ouro da seção 9 do critério clínico); CONTEXTUAL porque, uma vez que o fator de risco da
anamnese realmente bate, o sistema já trata com a mesma urgência (`RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR`
já cita o SAMU/192, igual ao absoluto) — ex.: falta de ar leve numa paciente com insuficiência cardíaca é,
na prática, um possível sinal de descompensação, não uma queixa rotineira. Essas duas listas **não foram
alteradas** nesta reestruturação — já passaram por revisão anterior e continuam avaliadas a partir do
texto de um único check-in (`RedFlagDetectionService`).

**Amarelo também não mudou de lógica** — `SYMPTOM_PATTERN_ALERT` (mesmo sintoma 3x em 7 dias) já
corresponde ao "sintoma persiste, sem combinação preocupante" da seção 4 do critério clínico. Só passou a
ser rotulado explicitamente como o nível amarelo do modelo.

**O que é novo é o laranja** — antes não existia nada entre "sintoma único recorrente" (amarelo) e
"emergência" (vermelho). A v1 tentou preencher isso com uma regra genérica de contagem; esta versão troca
por combinações nomeadas e específicas, com fonte.

## 2. O problema que isso resolve

`RedFlagDetectionService` só analisa o texto livre de **um único check-in** e devolve **no máximo uma
categoria** — cobre bem "o paciente descreveu algo agudo hoje", mas não cobre um conjunto de sinais leves
isolados que só fazem sentido juntos ao longo de semanas (o exemplo que motivou isto: dor abdominal alta +
perda de apetite + emagrecimento + coceira + urina escura + dor nas costas, relatados em dias diferentes —
compatível com obstrução biliar/pancreática, mas nenhum desses sinais sozinho está na lista de red flags).

## 3. As regras laranja (`ORANGE_COMBINATION_RULES`)

Cada regra é uma associação **nomeada e específica**, retirada diretamente dos exemplos do critério
clínico (seção 3, "Nível laranja") — nunca "N sintomas quaisquer". `min_occurrences=2`
(`PERSISTENCE_MIN_OCCURRENCES`) é a aproximação usada para "persistente": como o check-in por WhatsApp não
pergunta duração/intensidade explicitamente (ver limitação na seção 5), "persistente" hoje significa
"relatado em pelo menos 2 check-ins distintos dentro da janela da regra" — uma aproximação, não uma medida
literal de duração.

| Regra | Exige | Janela |
|---|---|---|
| Perda de peso + outro sintoma persistente | emagrecimento (1x) + **qualquer** outro sinal persistente (2x) | 21 dias |
| Alteração do hábito intestinal + sangue nas fezes | hábito intestinal alterado (2x) + sangue nas fezes (1x) | 21 dias |
| Dor abdominal persistente + perda de peso | dor abdominal (2x) + emagrecimento (1x) | 21 dias |
| Dor abdominal + icterícia | dor abdominal (1x) + (coceira OU urina escura) (1x) | 21 dias |
| Tosse persistente + sinais respiratórios/peso | tosse (2x) + (emagrecimento OU desconforto torácico OU falta de ar) | 21 dias |
| Vômitos persistentes + sinais | vômitos (2x) + (emagrecimento OU dor abdominal OU alteração do estado geral) | 21 dias |
| Sangramento inexplicado + outro sintoma persistente | sangramento (1x) + qualquer outro sinal persistente (2x) | 21 dias |
| Massa/caroço persistente | caroço/nódulo (2x) | 21 dias |

A janela de 21 dias é o único valor com apoio textual direto no critério clínico ("tosse persistente por
mais de 3 semanas" — regra de tosse); as demais janelas usam o mesmo valor por padrão razoável, **não**
individualmente sourced — a confirmar com o médico (seção 7).

**Mensagem ao paciente** (calma, nunca nomeia doença, sem SAMU/192 — não é emergência):
> "Ao longo dos últimos check-ins você relatou uma combinação de sinais que pode merecer uma avaliação
> médica em curto prazo — mesmo que nenhum deles pareça grave isoladamente. Considere agendar uma consulta
> nos próximos dias para investigar."

## 4. Desenho técnico

Reaproveita a mesma infraestrutura da v1 (nada de nova pergunta no WhatsApp, ver README "Otimização de
custo do WhatsApp"):

- `SymptomNormalizationService`/`SymptomTerm`/`DailyReportSymptomTerm` já tagueiam toda descrição de
  check-in num vocabulário controlado, independente de ser red flag.
- `app/bot/scheduler.py::_fire_symptom_combination_alert` (dentro do já existente `send_monitoring_alerts`)
  avalia cada `OrangeCombinationRule` contra a contagem de ocorrências de cada sinal do paciente na janela
  da regra (`_term_occurrences_in_window`), casando por lista de aliases por sinal (`ClinicalSign`), nunca
  por rótulo exato — o vocabulário do normalizador cresce livre, então "coceira"/"prurido"/"comichão"
  precisam contar como o mesmo sinal.
- `notify_symptom_combination_alert` (notification_service.py) — mesmo formato duplo de
  `notify_red_flag_symptom`: paciente sempre, profissional vinculado quando houver, com o hook de push
  notification (`PR #127`) já plugado.
- Gated por `settings.ORANGE_COMBINATION_ALERTS_ENABLED` (default `False`).
- **Frontend**: nenhuma mudança feita ainda — o alerta chega hoje só pelo sino de notificações (já
  construído), não pelo card de status/relatório de automonitoramento (que só reflete `red_flag_category`
  de um único check-in). Estender essas telas para o nível laranja é trabalho futuro, não incluído aqui.

## 5. Limitações a não esconder do médico

- **"Persistente" é uma aproximação** (≥2 check-ins na janela), não a duração real do sintoma — o sistema
  não pergunta "há quantos dias" nem "está piorando/melhorando/estável" (seção 8 do critério clínico). Se
  isso for essencial, precisaria de uma pergunta nova no fluxo do WhatsApp, o que tem custo (ver README).
- **Evolução do quadro não é avaliada** — o critério clínico trata a trajetória (melhorando/estável/
  piorando) como um dos componentes principais da classificação; hoje o sistema não tem esse dado
  estruturado, só sabe se o sinal apareceu ou não em cada check-in.
- **As regras são independentes**, não uma única classificação de prioridade por paciente — um paciente
  pode receber, no mesmo dia, um alerta de inatividade (engajamento) e um alerta laranja (clínico); o
  sistema não escolhe "o alerta mais alto" entre eles, cada um dispara pela sua própria lógica.

## 6. Fontes usadas (fornecidas pelo usuário)

1. CDC — Signs and Symptoms of Stroke.
2. Gulati M, Levy PD, Mukherjee D, et al. — 2021 AHA/ACC/ASE/CHEST/SAEM/SCCT/SCMR Guideline for the
   Evaluation and Diagnosis of Chest Pain. *Circulation*.
3. WHO — Colorectal cancer (Fact sheet).
4. WHO — Case management desk guide for doctors — Consider Cancer.
5. WHO — Early detection of cancer.
6. WHO — Cancer (Fact sheet).
7. NICE — Suspected cancer: recognition and referral (NG12).
8. NICE — Sepsis: recognition, diagnosis and early management (NG51).

## 7. Perguntas para o médico responsável

1. As 8 regras laranja da seção 3 estão clinicamente corretas? Falta alguma combinação relevante das
   fontes acima (ex.: critérios de sepse do NICE NG51 ainda não têm regra própria aqui)?
2. A janela de 21 dias serve para todas as 8 regras, ou algumas precisam de janela diferente (mais curta
   para sangramento inexplicado, por exemplo)?
3. `PERSISTENCE_MIN_OCCURRENCES = 2` (2 check-ins na janela) é um proxy aceitável para "persistente" sem
   perguntar duração explicitamente, ou isso é importante o suficiente para justificar uma pergunta nova
   no WhatsApp (com o custo que isso implica)?
4. O tom da mensagem ao paciente (seção 3) está certo?
5. Faz sentido priorizar entre as 8 regras (ex.: sangramento inexplicado antes de perda de peso) quando
   mais de uma bate no mesmo dia, ou a ordem atual (primeira regra que casar, ver `ORANGE_COMBINATION_RULES`)
   é aceitável?

## 8. Ponto que também precisa do advogado

Cruzar sinais de dias diferentes para apontar um padrão de risco é qualitativamente diferente de "esta
frase de hoje é alarmante" — passa a ser uma análise de tendência temporal, o que pode mudar o
enquadramento de risco na avaliação do art. 12 da Resolução CFM nº 2.454/2026 (ver
`docs/cfm-2454-avaliacao-risco-ia.md`) e merece uma palavra do advogado sobre se isso aproxima a
funcionalidade de "apoio diagnóstico preditivo" perante a ANVISA (RDC 657/2022), mesmo sem nomear doença
nenhuma ao paciente. Independente da resposta do médico às perguntas da seção 7.

## 9. Status

Implementado (`app/services/red_flag_symptoms.py`, `app/bot/scheduler.py`, `app/services/notification_service.py`),
com testes, mas **desligado por padrão** (`ORANGE_COMBINATION_ALERTS_ENABLED=False`). Ligar só depois da
validação das seções 7 e 8.
