# Padrões cumulativos e o modelo de 4 níveis (vermelho/laranja/amarelo/verde)

> **v3 deste documento.** A v1 propunha um único grupo de sinais disparado por contagem genérica ("N de M
> sinais distintos numa janela"). O primeiro critério clínico trazido pelo usuário (CDC, AHA/ACC, OMS,
> NICE) **rejeitou explicitamente esse formato de regra**, e a v2 reestruturou tudo em torno do modelo de 4
> níveis. Esta v3 incorpora um segundo critério clínico, mais detalhado (NICE NG12 atualizado em abril de
> 2026, NICE NG253 de sepse, AHA/ACC), que trouxe 11 combinações laranja novas e uma nova categoria
> vermelha (sinais de possível sepse). **Já implementado** em
> `app/services/red_flag_symptoms.py`/`app/bot/scheduler.py`, mas as regras laranja seguem desligadas por
> padrão (`ORANGE_COMBINATION_ALERTS_ENABLED=False`) até a validação do médico responsável — a categoria
> vermelha de sepse já está ativa (mesmo mecanismo das outras categorias absolutas, sem flag).

## 1. O modelo de 4 níveis

| Nível | Significado | No sistema hoje |
|---|---|---|
| 🔴 **Vermelho** | Possível emergência — nunca condicionado a duração | `RED_FLAG_ABSOLUTE_CATEGORIES` (inclui a nova `sinais_de_sepse`) + `RED_FLAG_CONTEXTUAL_CATEGORIES` |
| 🟠 **Laranja** | Avaliação médica em curto prazo — combinação/persistência específica, não é emergência | `ORANGE_COMBINATION_RULES` (seção 3) — 19 regras |
| 🟡 **Amarelo** | Avaliação médica programada — sintoma único recorrente, sem combinação preocupante | `_fire_symptom_pattern_alert`/`SYMPTOM_PATTERN_ALERT` (sem mudança de lógica) |
| 🟢 **Verde** | Baixo risco imediato | Nenhum match — reclassificável automaticamente a cada novo check-in |

**Por que ABSOLUTO e CONTEXTUAL viram os dois "vermelho"**: ABSOLUTO porque é agudo e nunca espera
duração; CONTEXTUAL porque, uma vez que o fator de risco da anamnese realmente bate, o sistema já trata com
a mesma urgência. Essas duas listas — com a única exceção da nova categoria de sepse abaixo — **não foram
alteradas** nesta reestruturação; continuam avaliadas a partir do texto de um único check-in
(`RedFlagDetectionService`).

## 2. O problema que isso resolve

`RedFlagDetectionService` só analisa o texto livre de **um único check-in** e devolve **no máximo uma
categoria** — cobre bem "o paciente descreveu algo agudo hoje", mas não cobre um conjunto de sinais leves
isolados que só fazem sentido juntos ao longo de semanas ou combinados entre si num mesmo relato.

## 3. Nova categoria vermelha: possível sepse

O segundo critério clínico trouxe uma seção própria (seção 5, "Suspeita de infecção grave", baseada na NICE
NG253) para combinações de "possível infecção" + sinal de gravidade (confusão, dificuldade respiratória,
queda de pressão, redução importante da urina, pele/lábios arroxeados, palidez/moteamento, manchas que não
somem à pressão). Diferente das regras laranja, **esses sinais foram implementados como uma nova categoria
ABSOLUTA** (`sinais_de_sepse`, `app/services/red_flag_symptoms.py`), não como regra de combinação
histórica — dois motivos:

1. Um paciente plausivelmente descreve "febre alta e muito confuso" numa única mensagem — o classificador
   de texto livre já existente (`RedFlagDetectionService`) é o lugar certo, igual às outras categorias
   absolutas.
2. Sepse pode evoluir para choque séptico em horas — a própria seção 7 do critério clínico ("regra de
   segurança") diz que uma combinação compatível com emergência não deve esperar. Tratar como laranja
   (avaliação em curto prazo, poderia esperar dias) seria clinicamente perigoso demais.

Esta é a única mudança nas listas ABSOLUTO/CONTEXTUAL já revisadas anteriormente — sinalizando explicitamente
para o médico validar, já que o resto dessas duas listas ficou intocado.

## 4. As regras laranja (`ORANGE_COMBINATION_RULES`)

Cada regra é uma associação **nomeada e específica** — nunca "N sintomas quaisquer".
`PERSISTENCE_MIN_OCCURRENCES = 2` é a aproximação usada para "persistente" (ver limitação na seção 6). A
maioria das 11 regras novas (do segundo critério) exige só **1** ocorrência de cada sinal — esse critério
lista a maior parte das combinações como pares simples, sem qualificar "persistente" em ambos os lados,
diferente do primeiro critério.

### Regras do primeiro critério (v2, sem mudança)

| Regra | Exige | Janela |
|---|---|---|
| Perda de peso + outro sintoma persistente | emagrecimento (1x) + **qualquer** outro sinal persistente (2x) | 21 dias |
| Alteração do hábito intestinal + sangue nas fezes | hábito intestinal alterado (2x) + sangue nas fezes (1x) | 21 dias |
| Dor abdominal persistente + perda de peso | dor abdominal (2x) + emagrecimento (1x) | 21 dias |
| Dor abdominal + icterícia | dor abdominal (1x) + (pele/olhos amarelados OU coceira OU urina escura) | 21 dias |
| Tosse persistente + sinais respiratórios/peso | tosse (2x) + (emagrecimento OU desconforto torácico OU falta de ar) | 21 dias |
| Vômitos persistentes + sinais | vômitos (2x) + (emagrecimento OU dor abdominal OU alteração do estado geral) | 21 dias |
| Sangramento inexplicado + outro sintoma persistente | sangramento (1x) + qualquer outro sinal persistente (2x) | 21 dias |
| Massa/caroço persistente | caroço/nódulo (2x) | 21 dias |

(A regra de icterícia ganhou um terceiro sinal — pele/olhos amarelados — vindo do segundo critério, que
nomeia esse sinal diretamente em vez de só coceira/urina escura.)

### Regras novas do segundo critério (NICE NG12 abril/2026, NG253)

| Regra | Exige | Janela |
|---|---|---|
| Dor abdominal + febre | dor abdominal (1x) + febre (1x) | 14 dias |
| Dor abdominal + perda de peso (par simples, sem exigir persistência) | dor abdominal (1x) + emagrecimento (1x) | 21 dias |
| Alteração intestinal persistente + perda de peso | hábito intestinal alterado (2x) + emagrecimento (1x) | 21 dias |
| Tosse persistente + sangue (hemoptise) | tosse (2x) + sangramento/hemoptise (1x) | 21 dias |
| Sangue na urina + dor | sangue na urina (1x) + (dor abdominal OU dor lombar/lateral) | 14 dias |
| Sangue na urina + perda de peso | sangue na urina (1x) + emagrecimento (1x) | 21 dias |
| Sintomas urinários + febre | sintomas urinários (1x) + febre (1x) | 14 dias |
| Febre + dor lombar/lateral + sintomas urinários (padrão de ITU alta) | os três sinais (1x cada) | 14 dias |
| Sangramento inexplicado + tontura ou desmaio | sangramento (1x) + tontura/desmaio (1x) | 14 dias |
| Sangramento inexplicado + perda de peso | sangramento (1x) + emagrecimento (1x) | 21 dias |
| Disfagia persistente + perda de peso | dificuldade para engolir (2x) + emagrecimento (1x) | 21 dias |

Janelas de 14 dias foram usadas para as combinações de padrão mais agudo/infeccioso (febre, sintomas
urinários, dor lombar, tontura); 21 dias ficou reservado para as combinações de padrão mais lento
(consistente com as regras do primeiro critério). Só a regra de tosse tem apoio textual direto para "21
dias" ("mais de 3 semanas") — as demais são um padrão razoável, a confirmar com o médico.

**Mensagem ao paciente** (calma, nunca nomeia doença, sem SAMU/192 — não é emergência):
> "Ao longo dos últimos check-ins você relatou uma combinação de sinais que pode merecer uma avaliação
> médica em curto prazo — mesmo que nenhum deles pareça grave isoladamente. Considere agendar uma consulta
> nos próximos dias para investigar."

## 5. Desenho técnico

Reaproveita a mesma infraestrutura desde a v2 (nada de nova pergunta no WhatsApp, ver README "Otimização de
custo do WhatsApp"):

- `SymptomNormalizationService`/`SymptomTerm`/`DailyReportSymptomTerm` já tagueiam toda descrição de
  check-in num vocabulário controlado, independente de ser red flag.
- `app/bot/scheduler.py::_fire_symptom_combination_alert` (dentro do já existente `send_monitoring_alerts`)
  avalia cada `OrangeCombinationRule` contra a contagem de ocorrências de cada sinal do paciente na janela
  da regra (`_term_occurrences_in_window`), casando por lista de aliases por sinal (`ClinicalSign`), nunca
  por rótulo exato.
- As regras são avaliadas **em ordem de lista, a primeira que casar dispara** — não há priorização entre
  regras quando mais de uma bateria no mesmo dia (pergunta 5 da seção 7 do documento anterior, ainda em
  aberto).
- `notify_symptom_combination_alert` (notification_service.py) — mesmo formato duplo de
  `notify_red_flag_symptom`: paciente sempre, profissional vinculado quando houver, com o hook de push
  notification já plugado.
- Gated por `settings.ORANGE_COMBINATION_ALERTS_ENABLED` (default `False`) — a categoria vermelha de sepse
  **não** tem flag, roda como qualquer outra categoria absoluta assim que este código for para produção.
- **Frontend**: nenhuma mudança feita ainda — os alertas laranja chegam hoje só pelo sino de notificações
  (já construído). A categoria de sepse aparece onde qualquer categoria vermelha já aparece hoje
  (`red_flag_category` no `DailyReport`, cards já construídos no relatório de automonitoramento e no
  dashboard).

## 6. Limitações a não esconder do médico

- **"Persistente" é uma aproximação** (≥2 check-ins na janela), não a duração real do sintoma — o sistema
  não pergunta "há quantos dias" nem "está piorando/melhorando/estável".
- **Evolução do quadro não é avaliada** — nenhum dos dois critérios de duração/intensidade/trajetória é
  capturado estruturalmente hoje.
- **As regras são independentes**, não uma única classificação de prioridade por paciente.
- **A categoria de sepse depende inteiramente do classificador de texto livre** (mesmo mecanismo das outras
  categorias absolutas) — não há verificação de sinais vitais reais (pressão, frequência respiratória,
  saturação), só o que o paciente descreve por texto.

## 7. Fontes usadas

**Primeiro critério** (v2):
1. CDC — Signs and Symptoms of Stroke.
2. Gulati M, Levy PD, Mukherjee D, et al. — 2021 AHA/ACC/ASE/CHEST/SAEM/SCCT/SCMR Guideline for the
   Evaluation and Diagnosis of Chest Pain. *Circulation*.
3. WHO — Colorectal cancer (Fact sheet); Case management desk guide for doctors — Consider Cancer; Early
   detection of cancer; Cancer (Fact sheet).
4. NICE — Suspected cancer: recognition and referral (NG12, versão anterior).
5. NICE — Sepsis: recognition, diagnosis and early management (NG51).

**Segundo critério** (v3):
1. NICE — Suspected cancer: recognition and referral (NG12), atualizado em 15 de abril de 2026 — principal
   referência para as 11 regras laranja novas.
2. NICE — Suspected sepsis in people aged 16 or over: recognition, assessment and early management (NG253),
   novembro de 2025 — base da nova categoria vermelha `sinais_de_sepse`.
3. AHA/ACC — 2021 Guideline for the Evaluation and Diagnosis of Chest Pain.
4. NICE — Suspected cancer: recognition and referral — Recommended actions organised by symptom.
5. NICE — Suspected cancer: recognition and referral — Patient support, safety netting and diagnostic
   process (conceito de "safety netting" — acompanhar mesmo quando os critérios de encaminhamento não são
   atingidos de início — ainda não implementado, ver seção 8).

## 8. Perguntas para o médico responsável

1. As 19 regras laranja (seção 4) estão clinicamente corretas e completas?
2. As janelas (14 dias para padrão agudo/infeccioso, 21 dias para padrão mais lento) fazem sentido regra a
   regra, ou algumas precisam de ajuste individual?
3. A nova categoria vermelha `sinais_de_sepse` (seção 3) está com as frases de exemplo certas para o
   classificador? Falta algum sinal de gravidade da NG253?
4. `PERSISTENCE_MIN_OCCURRENCES = 2` continua um proxy aceitável, ou vale a pena uma pergunta nova no
   WhatsApp para capturar duração/evolução diretamente?
5. Faz sentido implementar o conceito de "safety netting" da NICE (fonte 5 da seção 7) — reavaliar/reabrir
   um paciente que não bateu os critérios inicialmente, mas os sintomas persistem ou pioram depois?
6. Ordem de avaliação das regras (primeira que casar dispara, sem priorização) é aceitável?

## 9. Ponto que também precisa do advogado

Cruzar sinais de dias diferentes para apontar um padrão de risco é qualitativamente diferente de "esta
frase de hoje é alarmante" — passa a ser uma análise de tendência temporal, o que pode mudar o
enquadramento de risco na avaliação do art. 12 da Resolução CFM nº 2.454/2026 (ver
`docs/cfm-2454-avaliacao-risco-ia.md`) e merece uma palavra do advogado sobre se isso aproxima a
funcionalidade de "apoio diagnóstico preditivo" perante a ANVISA (RDC 657/2022), mesmo sem nomear doença
nenhuma ao paciente. Independente da resposta do médico às perguntas da seção 8.

## 10. Status

Implementado (`app/services/red_flag_symptoms.py`, `app/bot/scheduler.py`,
`app/services/notification_service.py`), com testes. As 19 regras laranja seguem **desligadas por padrão**
(`ORANGE_COMBINATION_ALERTS_ENABLED=False`); a categoria vermelha de sepse já está ativa como qualquer outra
categoria absoluta. Ligar as regras laranja só depois da validação das seções 8 e 9.
