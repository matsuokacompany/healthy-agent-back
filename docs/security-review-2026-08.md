# Revisão de segurança — agosto de 2026

## Escopo

Revisão estática dos controles de autenticação, autorização, CSRF, webhook do
WhatsApp, isolamento por RLS e tratamento dos dados clínicos. Esta revisão não
substitui pentest externo nem valida a configuração efetiva da AWS, Supabase,
Meta ou da instância de produção.

## Achados e tratamento

### Corrigido: corpo ilimitado no webhook (médio)

O endpoint lia o corpo inteiro antes de autenticar a assinatura. Um remetente
não autenticado podia forçar alocação excessiva de memória. O endpoint agora
rejeita `Content-Length` inválido ou superior a 1 MB e também limita o total
durante a leitura incremental, inclusive para transferência sem o cabeçalho.

### Corrigido: coleta desnecessária de causa suspeita (privacidade)

O bot já concluía o check-in após a descrição do sintoma, mas a API ainda
aceitava e devolvia `suspected_cause`. O campo foi removido dos contratos de
escrita e leitura. A migration apaga plaintext e envelope históricos; as
colunas ficam temporariamente no banco para permitir deploy gradual sem
incompatibilidade entre instâncias.

Remover a lógica é de baixa complexidade porque relatórios e métricas não usam
a causa. A remoção física das colunas deve ocorrer em uma migration posterior,
depois que todas as instâncias estiverem nesta versão. Os marcadores legados
`AWAITING_CAUSE` e `awaiting_cause` também devem permanecer durante essa janela
para que check-ins antigos abertos sejam concluídos sem prender o paciente.

## Controles confirmados por inspeção e testes existentes

- JWT valida algoritmo permitido, audiência, emissor e identificador UUID;
- mutações autenticadas por cookie sob `/api` exigem double-submit CSRF;
- webhook usa HMAC-SHA256 e comparação em tempo constante;
- consultas clínicas têm testes de escopo entre pacientes e profissionais;
- campos clínicos suportam envelope encryption e contexto autenticado.

## Riscos residuais e recomendações

1. Executar DAST e teste de autorização em staging com dois pacientes, um
   profissional vinculado e outro não vinculado.
2. Confirmar no PostgreSQL de produção que o papel de runtime não possui
   `BYPASSRLS` e que RLS está ativo em todas as tabelas sensíveis.
3. Adicionar secret scanning e auditoria de dependências ao CI; travar hashes
   das dependências para builds reproduzíveis.
4. Aplicar rate limiting no proxy para login, recuperação de senha, geração de
   IA e webhook. O limite de corpo reduz impacto por requisição, mas não volume.
5. Após o deploy completo, remover fisicamente as duas colunas de causa e seus
   registros nos serviços de rotação, verificação, backfill e cleanup.
