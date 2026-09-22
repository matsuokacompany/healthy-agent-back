# Plano alimentar em PDF — MVP

Cada paciente pode anexar no máximo um plano alimentar em PDF (o upload
substitui o anterior, não é uma galeria). Assim como as imagens clínicas, só
metadados e a chave do objeto ficam no PostgreSQL — o arquivo em si vai para
um bucket privado do Supabase Storage.

## Por que um bucket separado

O bucket `clinical-images` (`SUPABASE_STORAGE_BUCKET`) só aceita
`image/jpeg`, `image/png` e `image/webp`, e `ClinicalAttachmentService`
sempre reconverte o upload para JPEG via Pillow. Um PDF não passa por essa
conversão, então precisa do próprio bucket, com a própria política de MIME
type.

## Configuração necessária antes de habilitar

1. Criar o bucket privado `clinical-documents` no Supabase Storage (mesmo
   projeto do `clinical-images`), aceitando apenas `application/pdf`.
2. Definir as variáveis de ambiente:

```dotenv
DIET_DOCUMENTS_ENABLED=false
DIET_DOCUMENTS_BUCKET=clinical-documents
DIET_DOCUMENT_MAX_UPLOAD_BYTES=10485760
DIET_DOCUMENT_SIGNED_URL_TTL_SECONDS=300
```

`DIET_DOCUMENTS_ENABLED` continua `false` até o bucket existir — os
endpoints retornam 503 enquanto estiver desligado, sem quebrar o resto da
aplicação.

## Endpoints

```http
PUT    /api/diet-documents/patients/{patient_id}
GET    /api/diet-documents/patients/{patient_id}
GET    /api/diet-documents/patients/{patient_id}/view
DELETE /api/diet-documents/patients/{patient_id}
```

O `PUT` recebe multipart com um único campo `file`; um novo upload substitui
o documento anterior (mesma linha na tabela `diet_documents`, novo objeto no
Storage — o objeto antigo é removido do Storage depois que a troca é
confirmada no banco). Pacientes só operam sobre si mesmos; profissionais
precisam de vínculo ativo com o paciente, igual às imagens clínicas.
`GET .../view` retorna uma URL assinada de leitura temporária (mesmo TTL
configurável das imagens clínicas); não a persista, pois ela expira.

## Resumo para o médico

`GET /api/patient-handoff/me` (ou `/api/patient-handoff/patients/{id}` para
um profissional vinculado) reúne anamnese, alergias/restrições, fatores de
risco, suplementos, o resumo objetivo do automonitoramento no período e uma
referência ao plano alimentar (nome do arquivo e data de envio) — sem
chamar IA, pensado para ser baixado/impresso e levado a uma consulta.
