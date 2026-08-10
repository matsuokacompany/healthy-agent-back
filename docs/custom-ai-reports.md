# Relatórios personalizados com IA

Este documento define as regras da fundação dos relatórios personalizados. A
integração com a IA e a substituição dos endpoints legados serão feitas em
etapas posteriores.

## Período analisado

- O profissional informa `start_date` e `end_date` no formato ISO `YYYY-MM-DD`.
- A interface pode exibir as datas no formato brasileiro `DD/MM/AAAA`.
- O intervalo inclui a data inicial e a data final.
- O intervalo mínimo é de 30 dias.
- O intervalo máximo inicial é de cinco anos-calendário.
- `start_date` não pode ser posterior a `end_date`.
- `end_date` não pode estar no futuro.

Atalhos como "últimos 30 dias" e "últimos 365 dias" apenas preenchem as duas
datas; eles não representam tipos diferentes de relatório no backend.

## Elegibilidade e cota

- A cota pertence ao paciente e ao modo do relatório, independentemente do
  profissional solicitante.
- Cada paciente pode gerar um relatório preventivo e um relatório de apoio à
  avaliação clínica na mesma janela; uma nova geração do mesmo modo é permitida
  30 dias após a última geração concluída desse modo.
- Pré-visualizações não consomem a cota.
- Relatórios pendentes, em processamento ou com falha não iniciam uma nova
  janela de 30 dias.
- A cota só é consumida quando o relatório chega ao estado `COMPLETED`.
- O relatório concluído mais recente continua disponível durante a espera.
- São necessários inicialmente pelo menos 10 check-ins concluídos. Esse limite
  deverá ser configurável quando o serviço de elegibilidade for implementado.

## Estados de processamento

- `PENDING`: solicitação aceita e aguardando processamento.
- `PROCESSING`: consolidação ou interpretação em andamento.
- `COMPLETED`: relatório persistido com sucesso; consome a cota.
- `FAILED`: geração encerrada com falha; não consome a cota.

## Segurança de custo

- O backend deve agregar os check-ins antes de enviar conteúdo à IA.
- A pré-visualização deverá informar cobertura, quantidade de check-ins e uma
  estimativa de tokens e custo.
- A geração deverá respeitar limites de entrada, saída, custo por relatório e
  orçamento global, definidos em uma etapa posterior.
- Repetições e solicitações simultâneas deverão reutilizar uma chave de
  idempotência, evitando chamadas duplicadas.

## Consolidação clínica determinística

Antes da interpretação por IA, o backend consolida os dados do intervalo sem
inferir diagnósticos:

- adesão é a proporção de check-ins concluídos entre os check-ins registrados;
- cobertura de calendário é a proporção de dias do intervalo que possuem ao
  menos um check-in;
- taxa de sintomas é a proporção de check-ins com sintomas entre os concluídos;
- descrições iguais, ignorando caixa e espaços repetidos, são agrupadas;
- a maior lacuna considera dias consecutivos sem qualquer check-in, inclusive
  no início e no final do intervalo;
- a tendência compara a taxa de sintomas na primeira e na segunda metade e só
  muda de classificação quando a diferença alcança cinco pontos percentuais;
  ela é considerada insuficiente antes de 10 respostas ou quando uma das
  metades não possui resposta.

A linha do tempo usa grupos semanais para até 90 dias, mensais para até 365
dias e anuais para períodos maiores. Grupos mensais e anuais seguem o
calendário e têm suas extremidades limitadas ao intervalo solicitado.

## Compatibilidade

Os endpoints atuais de relatórios permanecem ativos durante a implantação do
novo fluxo. Eles só serão descontinuados depois da migração do frontend.

## Pré-visualização

`POST /api/professional/patients/{patient_id}/ai-reports/preview` valida o
acesso profissional, consolida o período e verifica a cota do paciente sem
chamar a IA ou consumir uma geração.

Quando o paciente está elegível, a resposta contém um token assinado com
validade de 15 minutos. O token vincula paciente, solicitante, datas, modo e o
hash do resumo consolidado. Dados clínicos textuais não são armazenados no
token. A configuração exige um segredo exclusivo em
`AI_REPORT_PREVIEW_SECRET`.
O segredo deve conter pelo menos 32 caracteres.

A elegibilidade pode retornar `REPORT_IN_PROGRESS`,
`PATIENT_MONTHLY_LIMIT_REACHED` ou `INSUFFICIENT_DATA`. Somente uma resposta
sem motivo de bloqueio contém `preview_token`; o endpoint não grava um novo
relatório e não altera a cota.

## Confirmação e geração

`POST /api/professional/patients/{patient_id}/ai-reports` recebe as mesmas
datas e modo do preview, além de `preview_token`. Antes da chamada à IA, o
backend valida assinatura, expiração, paciente, solicitante, período, modo,
hash atual do consolidado, cota e idempotência.

A geração registra primeiro `PENDING` e depois `PROCESSING`. Apenas uma
conclusão muda o estado para `COMPLETED`, grava `generated_at` e libera nova
geração após 30 dias. Falhas ficam em `FAILED`, sem consumir a cota.

O custo é protegido por limites configuráveis de tokens de entrada, tokens de
saída e valor máximo por chamada. Os preços por milhão de tokens não ficam
fixos no código: devem ser configurados para o modelo contratado. A aplicação
registra estimativa, uso retornado pelo provedor e custo real calculado.

Uma restrição única parcial impede mais de um relatório `PENDING` ou
`PROCESSING` por paciente. Repetir o mesmo token retorna o registro existente,
sem uma segunda chamada à IA.

## Histórico profissional

- `GET /api/professional/patients/{patient_id}/ai-reports` lista somente
  relatórios personalizados, com paginação e filtro opcional `status`.
- `GET /api/professional/patients/{patient_id}/ai-reports/{report_id}` retorna
  o consolidado, a interpretação, custos, estado e informações de falha.

As duas consultas exigem acesso profissional ao paciente, não chamam a IA e
não alteram a cota. A listagem omite os textos extensos do consolidado e da
interpretação; esses dados aparecem apenas no detalhe.
