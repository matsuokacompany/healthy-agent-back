# Imagens clínicas — MVP

O MVP aceita imagens JPEG, PNG e WebP, normaliza todo arquivo para JPEG, remove
metadados EXIF e limita o maior lado a 1.600 pixels. Os objetos ficam no bucket
privado `clinical-images`; somente metadados e a chave do objeto são gravados no
PostgreSQL. Imagens não são enviadas à IA.

## Limites e desligamento

- WhatsApp: uma imagem por check-in, somente durante a etapa de descrição dos sintomas;
- portal: até três imagens por requisição;
- arquivo recebido: até 5 MiB;
- cota: até 30 imagens ativas por paciente;
- URL de leitura: assinada por cinco minutos.

As flags permitem desligar todos os uploads ou somente um canal sem retirar a
visualização das imagens existentes:

```dotenv
CLINICAL_IMAGES_ENABLED=false
WHATSAPP_CLINICAL_IMAGES_ENABLED=false
PORTAL_CLINICAL_IMAGES_ENABLED=false
SUPABASE_STORAGE_BUCKET=clinical-images
SUPABASE_SERVICE_ROLE_KEY=<BACKEND_ONLY>
```

Nunca exponha `SUPABASE_SERVICE_ROLE_KEY` ao navegador. O bucket deve permanecer
privado e aceitar apenas `image/jpeg`, `image/png` e `image/webp`, com limite
absoluto de 10 MiB. A aplicação aplica o limite menor de 5 MiB.

## Portal

Endpoints autenticados:

```http
POST   /api/clinical-attachments/patients/{patient_id}
GET    /api/clinical-attachments/patients/{patient_id}
GET    /api/clinical-attachments/{attachment_id}/view
DELETE /api/clinical-attachments/{attachment_id}
```

O `POST` recebe multipart com `files`, `description` e `daily_report_id`
opcional. Pacientes só operam sobre si mesmos; profissionais precisam de perfil,
plano e vínculo ativos. Mutações autenticadas por cookie também enviam o token
CSRF já exigido pela API.

## WhatsApp

Depois da resposta positiva, a mensagem pede uma única foto opcional com os
sintomas na legenda. Imagem com legenda conclui o check-in; imagem sem legenda é
anexada e mantém o check-in aguardando uma descrição textual. Uma restrição
única no banco impede uma segunda imagem WhatsApp no mesmo relatório.

O webhook recebe apenas o identificador da mídia. O backend consulta a Graph
API, baixa o arquivo temporário sob HTTPS, valida e normaliza antes de enviá-lo
ao bucket privado. URLs da Meta, URLs assinadas, legendas e bytes nunca devem ser
registrados em logs.
