# Proposta — detecção de combinações de sinais ao longo do tempo ("padrões cumulativos")

> Este documento é uma **proposta de desenho**, ainda não implementada. Define o problema, o desenho
> clínico (grupos de sinais, regra de disparo) e o desenho técnico (como encaixa na infraestrutura que já
> existe), e lista o que precisa da validação do médico responsável e, num ponto específico, do advogado.
> Nada aqui deve ser lido como "já está no ar".

## 1. O problema que isso resolve

Hoje (`app/services/red_flag_detection_service.py`) o sistema só analisa o texto livre de **um único
check-in** e devolve **no máximo uma categoria** da lista revisada em `red_flag_symptoms.py`. Isso cobre
bem o caso "o paciente descreveu algo agudo e alarmante hoje" (ex.: dor no peito, sinais neurológicos).

Não cobre o caso em que um conjunto de sinais, cada um leve/inespecífico isoladamente, vai aparecendo em
**dias diferentes** e só faz sentido junto — o exemplo concreto que motivou esta proposta: dor abdominal
alta, perda de apetite, emagrecimento, coceira, urina escura e dor nas costas, relatados ao longo de
algumas semanas, é um padrão compatível com obstrução biliar/pancreática e hoje não gera nenhum alerta,
porque nenhum desses sinais sozinho está na lista de red flags e o sistema nunca olha mais de um dia por
vez.

## 2. Desenho clínico — grupos de sinais cumulativos

**Princípio igual ao resto do produto**: o sistema nunca diz ao paciente "isso pode ser câncer de
pâncreas" nem qualquer outro nome de doença. Ele sinaliza que **uma combinação de sinais ao longo do
tempo** merece avaliação médica — a mesma postura de `RED_FLAG_SAFETY_MESSAGE_PT_BR` hoje, só que
motivada por acúmulo, não por um evento agudo.

### 2.1 Proposta de um primeiro grupo (exemplo a validar com o médico)

| Grupo | Sinais que contam | Tier sugerido |
|---|---|---|
| `sinais_hepatobiliares_digestivos` | dor abdominal (região superior), perda de apetite, emagrecimento não intencional, coceira sem causa aparente, urina escura, pele/olhos amarelados, dor nas costas associada a dor abdominal | proposto: **cumulativo** (novo tier — ver 2.2) |

Esta tabela é só um ponto de partida — o médico pode adicionar, remover ou dividir em mais de um grupo
(ex.: separar "sinais digestivos altos inespecíficos" de "sinais de colestase" como dois grupos com
regras de disparo diferentes).

### 2.2 Por que um tier novo, e não reaproveitar ABSOLUTO/CONTEXTUAL

- **ABSOLUTO**: um sinal isolado já é grave por si só (dor no peito, AVC). Não é o caso aqui.
- **CONTEXTUAL**: um sinal leve só escala com um fator de risco **fixo** da anamnese (ex.: histórico de
  trombose). Aqui a escalada vem do **tempo/repetição**, não de um fator de risco cadastrado — o padrão é
  perigoso mesmo num paciente sem nenhum fator de risco na anamnese.
- Proposta: **CUMULATIVO** — um grupo de sinais que, sozinhos, não disparam nada, mas que juntos (N sinais
  distintos do mesmo grupo, dentro de uma janela de dias) disparam o mesmo tipo de alerta que um
  CONTEXTUAL hoje dispara.

### 2.3 Regra de disparo — parâmetros a decidir com o médico

- **Janela de tempo**: sugestão inicial 14–21 dias (pode ser por grupo). Curta demais perde o padrão que
  se constrói devagar; longa demais aumenta falso positivo por sintomas não relacionados.
- **Quantos sinais distintos do grupo precisam aparecer dentro da janela**: sugestão inicial 3 de 6
  possíveis no exemplo da tabela acima.
- **Podem ser o mesmo sinal repetido, ou precisam ser sinais diferentes do grupo?** Proposta: diferentes —
  "dor abdominal" relatada 5 vezes não é o mesmo alerta que "dor abdominal + urina escura + coceira".
- **Mensagem ao paciente** (rascunho, sem nomear doença):
  > "Ao longo das últimas semanas você relatou alguns sinais que, juntos, podem merecer uma avaliação
  > médica — mesmo que nenhum deles pareça grave isoladamente. Considere agendar uma consulta para
  > investigar."
  (Tom deliberadamente mais calmo que o aviso ABSOLUTO/CONTEXTUAL — não é uma emergência, é "vale
  investigar".)
- **Notifica o profissional também?** Proposta: sim, sempre que houver profissional vinculado — mesma
  lógica de `notify_red_flag_symptom`, nomeando os sinais que compuseram o padrão (não o nome de doença).

## 3. Desenho técnico — encaixa quase todo em infraestrutura que já existe

A boa notícia: **já existe uma camada estruturada por dia** que não depende de nova pergunta no WhatsApp
nem de mudança no fluxo de check-in (o que é sensível, ver README "Otimização de custo do WhatsApp").

- `SymptomNormalizationService` já normaliza **todo** `symptom_description` de cada check-in num
  vocabulário controlado (`SymptomTerm`), independente de ser ou não um red flag hoje — isso já roda para
  todo check-in completado (ver `app/models/models.py:467-493`, tabelas `symptom_terms` e
  `daily_report_symptom_terms`).
- `app/bot/scheduler.py::_fire_symptom_pattern_alert` **já faz algo estruturalmente parecido**: consulta
  `DailyReportSymptomTerm` numa janela de 7 dias, agrupa por termo, dispara se o **mesmo** termo aparecer
  >= 3 vezes, com cooldown de 7 dias via `Notification` já enviada. É o mesmo esqueleto que a regra
  cumulativa precisa — só muda a condição de "mesmo termo N vezes" para "N termos **distintos** de um
  grupo definido, dentro da janela".

### 3.1 O que seria novo

1. **`app/services/red_flag_symptoms.py`**: uma nova estrutura `CUMULATIVE_SYMPTOM_CLUSTERS` — cada
   entrada com `key`, `label`, janela em dias, mínimo de termos distintos, e a lista de `SymptomTerm.label`
   aceitos no grupo (mesmo formato de dados que `RED_FLAG_ALL_CATEGORIES`, só que com uma lista de termos
   em vez de frases de exemplo para um classificador).
2. **`app/bot/scheduler.py`**: uma função nova `_fire_symptom_cluster_alert`, irmã de
   `_fire_symptom_pattern_alert` — mesma janela de consulta a `DailyReportSymptomTerm`/`SymptomTerm`, mas
   contando termos distintos dentro da lista do cluster em vez de contar ocorrências do mesmo termo.
   Reaproveita o mesmo advisory lock (`MONITORING_ALERTS_ADVISORY_LOCK_ID`) e é chamada dentro do mesmo
   `send_monitoring_alerts` — não precisa de um job novo.
3. **`app/services/notification_service.py`**: uma `notify_symptom_cluster` nova (mesma forma dupla de
   `notify_red_flag_symptom`: sempre notifica o paciente, mais o(s) profissional(is) vinculado(s) quando
   houver) — e já chama `send_push_notification` (o hook que acabamos de preparar em `PR #127`), então a
   notificação por push, quando o app mobile existir, já sai "de fábrica" também para este caso novo.
4. **Frontend**: o card de status de monitoramento no dashboard e o `RedFlagEventsCard` do relatório de
   automonitoramento (ambos já construídos) só precisam aceitar esse novo tier/categoria — não é uma tela
   nova, é estender o que já existe para reconhecer "cumulativo" como um terceiro tipo junto de
   absoluto/contextual.

### 3.2 O risco técnico a não ignorar

`SymptomNormalizationService` **cresce o vocabulário livremente** — quando a descrição do paciente não
bate com nenhum termo existente, o classificador cria um termo novo (é assim que hoje cobre a
variabilidade de como as pessoas escrevem). Isso significa que o rótulo exato de "coceira" pode variar
("Coceira", "Prurido", "Pele com comichão") entre pacientes diferentes, e um cluster definido por rótulos
exatos vai vazar casos reais.

Mitigação proposta: o cluster não deveria casar pelo rótulo exato, e sim por uma lista curta de **aliases
aceitos por entrada do cluster**, revisada periodicamente contra os termos novos que o normalizador
realmente cria (dá pra auditar isso com uma query simples em `symptom_terms`). Alternativa mais robusta
(mais cara): usar um classificador (como o `RedFlagDetectionService` já faz) para mapear cada termo novo a
um cluster no momento em que ele é criado, em vez de casar por string.

## 4. Perguntas para o médico responsável

1. O grupo da seção 2.1 está clinicamente correto e completo? Que outros grupos cumulativos valeria
   desenhar (ex.: sinais de anemia progressiva, sinais de descompensação renal)?
2. Janela de tempo e número mínimo de sinais distintos — os valores sugeridos (14–21 dias, 3 de 6) fazem
   sentido, ou deveriam ser mais/menos sensíveis?
3. A mensagem ao paciente (seção 2.3) está no tom certo — "vale investigar" em vez de "urgência"? Faz
   sentido o sistema sempre recomendar agendar consulta, mesmo sem saber a gravidade real do caso?
4. Esse padrão cumulativo deveria sempre notificar o profissional vinculado, mesmo quando o paciente não
   está em acompanhamento ativo com foco nesse sistema (ex.: plano focado em outra condição)?

## 5. Ponto que precisa também do advogado

Olhar histórico e cruzar sinais de dias diferentes para apontar um padrão de risco é qualitativamente
diferente de "esta frase de hoje é alarmante" — passa a ser uma análise de tendência temporal, o que pode
mudar o enquadramento de risco na avaliação do art. 12 da Resolução CFM nº 2.454/2026 (ver
`docs/cfm-2454-avaliacao-risco-ia.md`) e merece uma palavra do advogado sobre se isso aproxima a
funcionalidade de "apoio diagnóstico preditivo" perante a ANVISA (RDC 657/2022), mesmo sem nomear doença
nenhuma ao paciente.

## 6. Status

Proposta apenas — nenhum código foi alterado. Próximo passo: validar seções 2 e 4 com o médico responsável
e a seção 5 com o advogado antes de abrir a implementação (seção 3).
