# Política de Privacidade — Julha

**Última atualização:** 27 de agosto de 2026

> **Este documento é uma minuta técnica preparada com base no funcionamento real da plataforma Julha
> e na Lei Geral de Proteção de Dados (Lei 13.709/2018 — LGPD). Não constitui aconselhamento
> jurídico. Antes de publicar, submeta este texto à revisão de um advogado especializado em LGPD e
> direito da saúde.**

## 1. Quem é o controlador dos seus dados

- **Razão social:** 66.039.068 IGOR EIIJI AVELAR MATSUOKA
- **CNPJ:** 66.039.068/0001-92
- **Endereço:** Rua Leonel de Oliveira Reis, 92, Londrina/PR
- **Contato geral:** contato@julha.com.br
- **Encarregado de Dados (DPO):** Igor Eiiji Avelar Matsuoka — contato@julha.com.br

Esta Política explica quais dados a Julha coleta, por quê, com quem compartilha e quais direitos você
tem sobre eles, em conformidade com a LGPD.

## 2. A quem esta Política se aplica

Esta Política se aplica a Pacientes, Profissionais, Administradores e a qualquer pessoa cujos dados
sejam processados através da Plataforma, incluindo Responsáveis Legais que cadastrem um Paciente menor
de idade.

## 3. Quais dados coletamos

### 3.1. Dados cadastrais

Nome, e-mail, telefone/WhatsApp, CPF, data de nascimento, cidade e estado, gênero — conforme
informados no cadastro, pelo próprio Usuário, por um Profissional que o cadastra como Paciente, ou por
um Responsável Legal.

### 3.2. Dados de saúde (dados sensíveis)

Nos termos do art. 5º, II, da LGPD, os seguintes dados são **dados pessoais sensíveis** e recebem
proteção reforçada:

- respostas aos check-ins diários de sintomas (se houve sintomas, descrição textual, data e horário);
- anamnese registrada pelo Profissional;
- Relatórios de IA gerados a partir desse histórico;
- imagens clínicas enviadas voluntariamente pelo Paciente ou Profissional, quando essa funcionalidade
  estiver habilitada.

### 3.3. Dados de autenticação e uso

Identificador de sessão (via Supabase Auth), endereço de e-mail vinculado à conta, registros técnicos
de acesso e uso da Plataforma para fins de segurança (ex.: detecção de tentativas de acesso indevido).

### 3.4. Dados de cobrança

Para Usuários que contratam a modalidade paga (autoacompanhamento B2C ou assinatura profissional),
coletamos CPF e utilizamos um identificador de cliente/assinatura junto ao processador de pagamentos.
**A Julha não coleta nem armazena número de cartão de crédito ou outros dados sensíveis de pagamento**:
esse processamento é feito diretamente pelo processador de pagamentos terceirizado (Cláusula 6),
seguindo os padrões de segurança do setor (PCI-DSS). A Julha armazena apenas o status da assinatura
(ativa, pendente, atrasada, cancelada), datas do ciclo de cobrança e um identificador de referência
junto ao processador — necessários para liberar o acesso e processar solicitações de cancelamento e
reembolso.

## 4. Como coletamos seus dados

- diretamente do Usuário, no cadastro e no uso da Plataforma;
- de um Profissional, quando cadastra um Paciente sob seu acompanhamento;
- por respostas enviadas via WhatsApp aos check-ins automáticos;
- por upload de imagens clínicas, quando essa funcionalidade estiver habilitada e o Usuário optar por
  utilizá-la.

## 5. Para que usamos seus dados e em qual base legal

| Finalidade | Base legal (LGPD) |
|---|---|
| Criar e gerenciar sua conta | Execução de contrato (art. 7º, V) |
| Enviar e processar check-ins de sintomas por WhatsApp | Execução de contrato / tutela da saúde em procedimento realizado por profissionais de saúde (art. 11, II, "f") |
| Disponibilizar o histórico ao Profissional responsável pelo acompanhamento | Tutela da saúde em procedimento realizado por profissionais de saúde (art. 11, II, "f") |
| Gerar Relatórios de IA como apoio à análise do Profissional | Tutela da saúde (art. 11, II, "f"), com consentimento adicional do titular quando exigido |
| Processar imagens clínicas enviadas voluntariamente | Consentimento específico e destacado do titular (art. 11, I) |
| Prevenir fraude e proteger a segurança da Plataforma | Legítimo interesse (art. 7º, IX) e cumprimento de obrigação legal |
| Cobrar pela assinatura (autoacompanhamento B2C ou assinatura profissional) | Execução de contrato (art. 7º, V) |

Quando o Paciente for menor de idade, o tratamento de seus dados depende do consentimento específico e
destacado de um dos pais ou de seu responsável legal, nos termos do art. 14 da LGPD, obtido no momento
do cadastro conforme descrito nos Termos de Uso.

## 6. Com quem compartilhamos seus dados

Não vendemos dados pessoais. Compartilhamos dados apenas com operadores (art. 5º, VII, da LGPD) que
processam informações em nosso nome, sob instrução e finalidade limitada, e com autoridades quando
exigido por lei:

- **Supabase** — hospedagem do banco de dados, autenticação de usuários e, quando habilitado,
  armazenamento de imagens clínicas.
- **OpenAI** — geração dos Relatórios de IA a partir do histórico clínico enviado. O conteúdo enviado
  é limitado e truncado para reduzir a exposição de dados desnecessários.
- **Meta Platforms, Inc. (WhatsApp Cloud API)** — envio e recebimento de mensagens do check-in de
  sintomas.
- **Amazon Web Services (AWS KMS)** — gestão das chaves criptográficas usadas para proteger campos
  clínicos sensíveis (ver Cláusula 8); a AWS não tem acesso ao conteúdo clínico em texto claro.
- **Asaas** — processamento de pagamentos e cobrança recorrente para as assinaturas pagas (Cláusula
  3.4). Recebe nome, e-mail, telefone e CPF do titular da cobrança para emissão da fatura; a Julha não
  tem acesso a dados de cartão de crédito, que são inseridos diretamente na página de pagamento do
  Asaas.

Nenhum desses operadores está autorizado a usar seus dados para finalidade própria ou de terceiros
alheia à prestação do serviço à Julha.

## 7. Transferência internacional de dados

Alguns dos operadores listados na Cláusula 6 (em especial OpenAI e Meta) processam dados em servidores
localizados fora do Brasil. Essa transferência internacional é realizada com base no art. 33 da LGPD,
por meio de cláusulas contratuais e políticas de proteção de dados desses fornecedores, adotando os
resguardos necessários à proteção dos seus dados durante esse tratamento.

## 8. Como protegemos seus dados

- **Criptografia de campos clínicos**: sintomas, anamnese e Relatórios de IA são protegidos com
  criptografia de envelope (AES-256-GCM), com chaves gerenciadas por um serviço dedicado de gestão de
  chaves (AWS KMS) e contexto de autenticação vinculado ao registro, paciente e campo específicos, o
  que impede que um dado criptografado seja reaproveitado fora do contexto original.
- **Isolamento por linha no banco de dados (Row Level Security)**: o banco de dados aplica regras que
  restringem cada consulta ao escopo do próprio Paciente ou aos Pacientes efetivamente vinculados ao
  Profissional que faz a consulta, como camada adicional à validação da aplicação.
- **Autenticação e sessão**: acesso via Supabase Auth, com tokens de sessão armazenados em cookies
  `HttpOnly` (inacessíveis a scripts do navegador) e proteção contra CSRF em operações sensíveis.
- **Verificação de origem das mensagens do WhatsApp**: mensagens recebidas via webhook são validadas
  por assinatura criptográfica (HMAC-SHA256) antes de qualquer processamento.
- **Limitação de tentativas (rate limiting)**: rotas sensíveis como login, recuperação de senha e
  geração de relatórios têm limite de tentativas por período, para reduzir o risco de ataques
  automatizados.

Nenhuma medida de segurança é absoluta; em caso de incidente de segurança que possa acarretar risco ou
dano relevante, notificaremos a Autoridade Nacional de Proteção de Dados (ANPD) e os titulares
afetados, nos termos do art. 48 da LGPD.

## 9. Por quanto tempo mantemos seus dados

Mantemos seus dados enquanto sua conta estiver ativa e pelo tempo necessário para cumprir as
finalidades desta Política, obrigações legais ou regulatórias aplicáveis.

Você pode solicitar a exclusão da sua conta e dos dados associados a qualquer momento, pelos canais de
suporte da Plataforma ou pelo contato do encarregado indicado na Cláusula 1. Essa exclusão é completa,
e não apenas um bloqueio de acesso: os registros vinculados à sua conta (dados cadastrais, check-ins,
anamnese, Relatórios de IA e imagens clínicas) são removidos de nossa base.

Se você é ou foi atendido por um Profissional sujeito a obrigação própria de guarda de prontuário
perante seu conselho de classe (por exemplo, obrigações aplicáveis a médicos), a exclusão de seus
dados na Plataforma não afeta eventual dever desse Profissional de manter registro próprio do
atendimento, fora da Julha, conforme suas próprias obrigações regulatórias.

## 10. Seus direitos como titular de dados

Nos termos do art. 18 da LGPD, você pode solicitar, mediante requisição ao encarregado indicado na
Cláusula 1:

- confirmação da existência de tratamento e acesso aos seus dados;
- correção de dados incompletos, inexatos ou desatualizados;
- anonimização, bloqueio ou eliminação de dados desnecessários ou tratados em desconformidade com a
  LGPD;
- portabilidade dos dados a outro fornecedor de serviço, mediante requisição expressa;
- eliminação dos dados tratados com base no seu consentimento;
- informação sobre as entidades com as quais compartilhamos seus dados;
- revogação do consentimento, quando o tratamento tiver essa base legal, sem afetar a licitude do
  tratamento realizado antes da revogação;
- oposição a tratamento realizado com base em hipótese de dispensa de consentimento, quando aplicável.

Você também tem o direito de apresentar reclamação à Autoridade Nacional de Proteção de Dados (ANPD).

Quando o titular for menor de idade, esses direitos podem ser exercidos por seu Responsável Legal.

## 11. Cookies

Utilizamos cookies estritamente técnicos, necessários para manter sua sessão autenticada de forma
segura (cookies `HttpOnly` de acesso e atualização de sessão, e um cookie de proteção contra CSRF).
Não utilizamos cookies de rastreamento publicitário ou de terceiros para perfilamento comportamental.

## 12. Alterações desta Política

Esta Política pode ser atualizada periodicamente para refletir mudanças na Plataforma ou na
legislação aplicável. Alterações relevantes — em especial o lançamento da modalidade de
autoacompanhamento pago descrita nos Termos de Uso — serão comunicadas com antecedência razoável antes
de entrarem em vigor.

## 13. Contato

Dúvidas, solicitações sobre seus dados pessoais ou reclamações podem ser enviadas para
**contato@julha.com.br**.
