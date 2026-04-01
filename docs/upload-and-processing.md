# Upload e Processamento de Arquivos / Upload and File Processing

> Documentacao detalhada do pipeline de upload, reconhecimento de tipo e processamento de documentos financeiros.
>
> Detailed documentation of the upload pipeline, file type recognition, and financial document processing.

---

## PT-BR: Upload e Processamento

### Tipos de Arquivo Suportados

| Tipo | Extensoes | Processamento | Observacoes |
|---|---|---|---|
| **PDF** | `.pdf` | AI Vision (imagem) ou nativo | Poppler necessario para conversao de imagem |
| **Imagens** | `.jpg`, `.jpeg`, `.png`, `.webp` | AI Vision | Enviado como base64 |
| **Excel** | `.xlsx`, `.xls` | Pandas + AI | Detecta automaticamente se e livro-razao |
| **XML (NFe)** | `.xml` | Parser nativo | Notas Fiscais eletronicas brasileiras |
| **OFX** | `.ofx` | ofxparse | Extratos bancarios (formato Open Financial Exchange) |
| **OFC** | `.ofc` | Parser customizado | Formato legado de extratos |
| **Word** | `.doc`, `.docx` | python-docx + AI | Documentos de texto |
| **Texto** | `.txt` | Leitura direta + AI | Arquivos de texto simples |

### Pipeline de Upload (Passo a Passo)

#### 1. Validacao no Frontend
O usuario seleciona arquivo(s) na interface. O frontend faz validacoes basicas de tipo e tamanho antes de enviar.

#### 2. Envio para API
```
POST /documents/upload
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>
```

#### 3. Validacoes no Backend (`routers/documents.py`)

1. **Rate limiting**: Maximo 10 uploads por minuto por IP (slowapi)
2. **Autenticacao**: JWT valido obrigatorio
3. **Assinatura ativa**: `require_active_subscription` middleware verifica se trial nao expirou ou se plano esta ativo
4. **Extensao do arquivo**: Verifica contra lista permitida em `config.py`
   ```python
   ALLOWED_FILE_EXTENSIONS = [
       ".pdf", ".xlsx", ".xls", ".xml",
       ".jpg", ".jpeg", ".png", ".webp",
       ".txt", ".doc", ".docx", ".ofc", ".ofx"
   ]
   ```
5. **MIME type**: Se `python-magic` estiver disponivel, valida o MIME type real do arquivo (nao confia apenas na extensao)
6. **Tamanho**: Maximo 30MB (`MAX_UPLOAD_SIZE`)

#### 4. Armazenamento do Arquivo

- **Producao (S3)**: Arquivo salvo em `users/{user_id}/{uuid}.ext` no bucket S3
  - UUID garante unicidade
  - Organizacao por user_id garante isolamento multi-tenant
  - Content-type preservado como metadado S3
- **Desenvolvimento (local)**: Arquivo salvo em `uploads/{uuid}.ext`

#### 5. Hash de Arquivo (Deteccao de Duplicatas)

O sistema calcula SHA-256 do conteudo para detectar uploads duplicados:
```python
file_hash = hashlib.sha256(file_content).hexdigest()
```

#### 6. Registro no Banco de Dados

Criacao do registro `Document` com status `PENDING`:
```python
Document(
    file_name=original_name,
    file_type=extension,
    file_path=s3_key_or_local_path,
    file_size=len(content),
    file_hash=sha256_hash,
    status=DocumentStatus.PENDING,
    user_id=current_user.id,
)
```

#### 7. Processamento em Background

Uma `BackgroundTask` do FastAPI e disparada para processar o documento sem bloquear a resposta da API. O processamento acontece no `StructuredDocumentProcessor`.

### Processamento por Tipo de Arquivo

#### PDF (`_process_pdf`)

Duas estrategias, com fallback automatico:

**Estrategia 1 - PDF Nativo** (modelos grandes como GPT-4o):
- PDF enviado como base64 diretamente para a API
- Sem dependencia de Poppler
- Mais rapido, menor tamanho

**Estrategia 2 - Conversao para Imagem** (fallback, modelos mini):
- PDF convertido para PNG usando Poppler (`pdf2image`)
- Cada pagina e uma imagem separada
- Imagens redimensionadas para max 2000px
- Cada pagina processada individualmente pela AI
- Resultados combinados

```python
# Fallback automatico
if modelo_suporta_pdf_nativo:
    try:
        return _process_pdf_native(pdf_path)
    except:
        pass  # fallback para imagem
return _process_pdf_via_poppler(pdf_path)
```

#### Imagens (`_process_image`)

1. Arquivo lido e encodado em base64
2. Extensao mapeada para MIME type (`jpg` -> `jpeg`)
3. Enviado para AI Vision com prompt de extracao

#### Excel (`_process_excel`)

1. Lido com `pandas.read_excel`
2. **Deteccao automatica de formato**:
   - Se >= 10 linhas + keywords de livro-razao (`data`, `valor`, `descricao`, `debito`, `credito`): processado como **Transaction Ledger**
   - Caso contrario: processado como **documento unico**
3. **Ledger**: Cada linha vira uma `Transaction` com data, descricao, valor, categoria
4. **Documento unico**: Dados convertidos para texto e enviados para AI

#### XML - NFe (`_process_xml`)

1. Parsed com `lxml` e `xmltodict`
2. Extrai campos padrao da NFe brasileira:
   - Emitente (CNPJ, razao social)
   - Destinatario
   - Itens (descricao, quantidade, valor)
   - Totais (ICMS, IPI, PIS, COFINS)
   - Informacoes de pagamento
3. **Sem chamada de AI** - parsing deterministico
4. Suporta deteccao de NFe de cancelamento

#### OFX (`_process_ofx`)

1. Parsed com biblioteca `ofxparse`
2. Extrai transacoes bancarias com data, descricao, valor
3. Classifica automaticamente como income/expense baseado no sinal do valor
4. Retorna como `TransactionLedger`

#### OFC (`_process_ofc`)

1. Formato legado de extratos bancarios
2. Parser customizado para formato OFC
3. Similar ao OFX mas com estrutura diferente

#### Word - DOCX (`_process_docx`)

1. Lido com `python-docx`
2. Texto extraido de todos os paragrafos
3. Enviado para AI para extracao estruturada

#### TXT (`_process_txt`)

1. Arquivo lido como texto puro
2. Texto enviado para AI para extracao estruturada

### Validacao CNPJ (`ENABLE_CNPJ_VALIDATION`)

Quando habilitado (default: `true`), o sistema verifica se o CNPJ do usuario aparece no documento como emitente ou destinatario. Se nao aparecer, o documento e processado mas com um **warning** (nao bloqueia):

```python
doc.cnpj_mismatch = True
doc.cnpj_warning_message = "CNPJ do usuario nao encontrado no documento"
```

### Fila de Upload (`tasks/queue_manager.py`)

Para evitar sobrecarga, uploads sao enfileirados:
1. Novo documento entra na fila com `queue_position`
2. Apenas N documentos processados simultaneamente
3. Quando um termina, o proximo da fila e disparado
4. Posicao na fila mostrada ao usuario

### Cancelamento de NFe

O sistema detecta automaticamente NFe de cancelamento:
1. Documento marcado como `is_cancellation = True`
2. Numero da NF original identificado (`original_document_number`)
3. Documento original encontrado e marcado como `CANCELLED`
4. Links bidirecionais: `cancelled_by_document_id` / `cancels_document_id`

---

## EN-US: Upload and Processing

### Supported File Types

| Type | Extensions | Processing | Notes |
|---|---|---|---|
| **PDF** | `.pdf` | AI Vision (image) or native | Poppler required for image conversion |
| **Images** | `.jpg`, `.jpeg`, `.png`, `.webp` | AI Vision | Sent as base64 |
| **Excel** | `.xlsx`, `.xls` | Pandas + AI | Auto-detects if it's a ledger |
| **XML (NFe)** | `.xml` | Native parser | Brazilian electronic invoices |
| **OFX** | `.ofx` | ofxparse | Bank statements (Open Financial Exchange) |
| **OFC** | `.ofc` | Custom parser | Legacy bank statement format |
| **Word** | `.doc`, `.docx` | python-docx + AI | Text documents |
| **Text** | `.txt` | Direct read + AI | Plain text files |

### Upload Pipeline (Step by Step)

#### 1. Frontend Validation
User selects file(s) in the UI. The frontend performs basic type and size validations before sending.

#### 2. API Request
```
POST /documents/upload
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>
```

#### 3. Backend Validations (`routers/documents.py`)

1. **Rate limiting**: Max 10 uploads per minute per IP (slowapi)
2. **Authentication**: Valid JWT required
3. **Active subscription**: `require_active_subscription` middleware checks trial/plan status
4. **File extension**: Checked against allowlist in `config.py`
5. **MIME type**: If `python-magic` is available, validates the real MIME type (doesn't trust extension alone)
6. **Size**: Maximum 30MB (`MAX_UPLOAD_SIZE`)

#### 4. File Storage

- **Production (S3)**: File saved to `users/{user_id}/{uuid}.ext` in S3 bucket
  - UUID ensures uniqueness
  - user_id organization ensures multi-tenant isolation
  - Content-type preserved as S3 metadata
- **Development (local)**: File saved to `uploads/{uuid}.ext`

#### 5. File Hash (Duplicate Detection)

The system calculates SHA-256 of the content to detect duplicate uploads.

#### 6. Database Record

A `Document` record is created with status `PENDING`.

#### 7. Background Processing

A FastAPI `BackgroundTask` is triggered to process the document without blocking the API response. Processing happens in `StructuredDocumentProcessor`.

### Processing by File Type

#### PDF

Two strategies with automatic fallback:

**Strategy 1 - Native PDF** (large models like GPT-4o):
- PDF sent as base64 directly to the API
- No Poppler dependency
- Faster, smaller payload

**Strategy 2 - Image Conversion** (fallback, mini models):
- PDF converted to PNG using Poppler
- Each page is a separate image
- Images resized to max 2000px
- Each page processed individually by AI
- Results combined

#### Excel

1. Read with `pandas.read_excel`
2. **Auto-format detection**:
   - If >= 10 rows + ledger keywords: processed as **Transaction Ledger**
   - Otherwise: processed as **single document**
3. **Ledger**: Each row becomes a `Transaction`
4. **Single document**: Data converted to text and sent to AI

#### XML - NFe

1. Parsed with `lxml` and `xmltodict`
2. Extracts standard Brazilian NFe fields
3. **No AI call** - deterministic parsing
4. Supports cancellation NFe detection

#### OFX / OFC

1. Parsed with dedicated libraries
2. Extracts bank transactions
3. Auto-classifies income/expense by value sign
4. Returns as `TransactionLedger`

### AI Extraction

The AI receives the document content (image, text, or structured data) with a detailed prompt requesting extraction into the `FinancialDocument` schema. The prompt instructs the AI to:

1. Identify document type (invoice, receipt, expense, statement, etc.)
2. Extract issuer and recipient information (name, CNPJ, address)
3. Extract line items with description, quantity, unit price, total
4. Determine transaction type (income vs expense) using user company info
5. Classify into one of 52 accounting categories
6. Extract payment information
7. Provide a confidence score

The AI response is parsed into a Pydantic model and validated by the `FinancialValidator`.

### Data Validation Engine (`validation.py`)

After AI extraction, the data goes through validation:

1. **Required fields**: `total_amount` must be present
2. **Recommended fields**: `issue_date`, `transaction_type`, `category` (warns if missing)
3. **Date validation**: Checks format, warns if future date, errors if > 1 year old
4. **Amount validation**: Checks for negative totals, mismatched line items vs total
5. **Tax ID validation**: Validates CNPJ/CPF format (Brazilian tax IDs)
6. **Transaction type**: Ensures valid income/expense classification

### Upload Response

The API responds immediately with the document ID and status `pending`:
```json
{
  "id": 123,
  "file_name": "nota_fiscal.pdf",
  "status": "pending",
  "message": "Documento enviado, processamento em andamento"
}
```

The frontend then polls `GET /documents/{id}` until status changes to `completed` or `failed`.

### Error Handling

All errors during processing are:
1. Logged with full traceback
2. Document status set to `FAILED`
3. Error message stored in `doc.error_message`
4. Error messages translated to Portuguese via `i18n_errors.py`
5. AI-specific errors get user-friendly translations

### File Cleanup (Scheduled Job)

A daily scheduled job (`APScheduler`) runs at configurable hour (default: 3 AM):
1. Deletes files older than retention period (default: 365 days)
2. Deletes orphaned files (in storage but not in database)
3. Configurable via `FILE_CLEANUP_ENABLED`, `FILE_RETENTION_DAYS`
