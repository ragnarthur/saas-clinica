# SaaS Médico – Sistema de Agendamentos Multi‑Clínicas

> **Estado atual do desenvolvimento:**  
> Backend e frontend já implementam o fluxo completo de autenticação JWT, cadastro público de paciente com LGPD, verificação de e‑mail com código de 6 dígitos, multi‑tenant de clínicas e dashboard inicial para secretárias. O projeto está pronto para uso em ambiente de desenvolvimento e para demonstração de arquitetura.

---

## 1. Visão Geral

Este repositório contém um SaaS médico pensado para **várias clínicas** utilizando a mesma infraestrutura (multi‑tenant lógico) e respeitando **LGPD by design**:

- Cada clínica é um *tenant* (`Clinic`), isolando pacientes, agenda e staff.
- Pacientes são cadastrados em uma clínica específica e não “vazam” para outras.
- Dados sensíveis (CPF de paciente, notas clínicas) são **criptografados em banco**.
- Consentimento LGPD é obrigatório, registrado em auditoria e checado em cada acesso.
- Cadastro público de paciente com:
  - Termos de Uso, Política de Privacidade e Termo de Consentimento;
  - verificação de e‑mail via token + **código numérico de 6 dígitos**.

---

## 2. Stack Tecnológica

### Backend

- **Django 5.x**
- **Django REST Framework**
- **PostgreSQL**
- Autenticação via **JWT** (`rest_framework_simplejwt`)
- Modelo de usuário customizado: `core.CustomUser`
- Manager multi‑tenant: `TenantManager`
- Criptografia de campos sensíveis com **`fernet_fields`**
- Seed de dados para desenvolvimento: `python manage.py seed_demo_clinics`

### Frontend

- **React + Vite**
- **TypeScript**
- Cliente HTTP centralizado em `src/api/client.ts` (`apiRequest<T>`)
- Páginas principais:
  - `LoginPage.tsx`
  - `PatientSignupPage.tsx` (cadastro público + LGPD)
  - `VerifyEmailPage.tsx` (código de 6 dígitos)
  - `DashboardPage.tsx` (agenda da secretária)

---

## 3. Arquitetura Multi‑Tenant de Clínicas

### 3.1. Modelo `Clinic` (Tenant)

Cada clínica é representada pelo modelo:

- `id` (UUID)
- `name`
- `schema_name` (slug único, ex.: `vida_plena`, `bem_estar`)
- `is_active`

```python
class Clinic(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    schema_name = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
```

Este modelo é usado em todo o resto como “chave” de isolamento de dados.

### 3.2. Usuários por Clínica (`CustomUser`)

O modelo de usuário customizado (`CustomUser`) traz:

- `clinic` → FK para `Clinic` (opcional apenas para `SAAS_ADMIN`);
- `role` → `SAAS_ADMIN`, `CLINIC_OWNER`, `SECRETARY`, `DOCTOR`, `PATIENT`;
- `doctor_for_secretary` → médico principal de cada secretária.

```python
class CustomUser(AbstractUser):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    doctor_for_secretary = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="secretaries",
        limit_choices_to={"role": Role.DOCTOR},
    )
```

### 3.3. Manager Multi‑Tenant (`TenantManager`)

Os modelos principais (paciente, agendamento, auditoria) usam `TenantManager`, permitindo consultas padronizadas por clínica:

```python
# exemplo de uso dentro de viewsets
clinic = getattr(request, "clinic", None) or getattr(user, "clinic", None)
queryset = PatientProfile.objects.for_tenant(clinic)
```

Isso garante que:

- secretárias, médicos e donos veem somente dados da própria clínica;
- o `SAAS_ADMIN` pode optar por consultar dados de qualquer clínica, quando necessário;
- endpoints críticos sempre incluem `clinic` no filtro.

---

## 4. Proteção de Dados e Criptografia (LGPD)

### 4.1. CPF de Paciente Criptografado + Hash

O modelo `PatientProfile` separa os dados do paciente do usuário e protege o CPF:

```python
class PatientProfile(TimeStampedModel):
    cpf = EncryptedCharField(max_length=14)
    cpf_hash = models.CharField(max_length=64, editable=False, null=True, blank=True)
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="patients")
```

- `cpf` é armazenado criptografado em banco usando `fernet_fields`.
- `cpf_hash` é um **SHA‑256 do CPF normalizado (somente dígitos)**:

```python
def _build_cpf_hash(self) -> str | None:
    if not self.cpf:
        return None
    normalized = "".join(filter(str.isdigit, str(self.cpf)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

Constraint de unicidade:

```python
models.UniqueConstraint(
    fields=["clinic", "cpf_hash"],
    name="uniq_patient_cpf_hash_per_clinic",
)
```

> Resultado: a mesma pessoa pode ser paciente em clínicas diferentes, mas **não pode ser cadastrada duas vezes na mesma clínica** com o mesmo CPF, sem expor o CPF em texto no banco.

### 4.2. Notas Clínicas Criptografadas

O modelo `Appointment` guarda as notas médicas em `EncryptedTextField`:

```python
class Appointment(TimeStampedModel):
    clinical_notes = EncryptedTextField(
        blank=True,
        help_text="Notas clínicas criptografadas; acesso só do médico.",
    )
```

- O texto é criptografado em repouso.
- Apenas o app (com a chave) consegue ler/editar o conteúdo.

### 4.3. Documentos Legais, Consentimento e Auditoria

**LegalDocument**

```python
class LegalDocument(TimeStampedModel):
    class DocType(models.TextChoices):
        TERMS = "TERMS"
        PRIVACY = "PRIVACY"
        CONSENT = "CONSENT"

    version = models.CharField(max_length=10)
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    content = models.TextField()
    is_active = models.BooleanField(default=False)
```

Constraint garantindo **apenas uma versão ativa por tipo**:

```python
models.UniqueConstraint(
    fields=["doc_type"],
    condition=models.Q(is_active=True),
    name="uniq_active_legal_document_per_type",
)
```

**UserConsent**

Registra o aceite de cada usuário para cada documento ativo:

```python
class UserConsent(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    agreed_at = models.DateTimeField(auto_now_add=True)
```

**AuditLog**

Toda ação sensível (CREATE, UPDATE, DELETE, LOGIN, EXPORT) grava um log com:

- ator (`actor`)
- clínica
- modelo alvo
- ID do objeto
- `changes` (JSON com os campos relevantes)

---

## 5. Fluxo de Cadastro Público de Paciente (com LGPD e E‑mail)

### 5.1. Frontend – `PatientSignupPage`

A tela `/cadastro-paciente`:

- carrega **clínicas ativas** em `GET /api/clinics/active/`;
- carrega documentos legais ativos em `GET /api/legal-documents/active/`;
- exibe:
  - seleção da clínica;
  - dados pessoais (nome, CPF, celular, data de nascimento, sexo, e‑mail);
  - senha + confirmação com **medidor de força de senha**;
  - seção “LGPD e consentimento“ com:
    - cards para Termos, Política e Consentimento;
    - cada card abre um **modal fullscreen**, exibindo o conteúdo HTML do documento;
    - dentro do modal existe um toggle “Li e concordo...“ que registra o aceite.
- só permite enviar o formulário se os 3 documentos estiverem aceitos.

O payload enviado para `POST /api/patients/register/`:

```json
{
  "clinic_schema_name": "vida_plena",
  "full_name": "Paciente Exemplo",
  "cpf": "000.000.000-00",
  "phone": "(34) 9 9999-9999",
  "email": "paciente@example.com",
  "password": "SenhaF0rte!",
  "password_confirm": "SenhaF0rte!",
  "sex": "F",
  "birth_date": "1990-01-01",
  "agree_terms": true,
  "agree_privacy": true,
  "agree_consent": true
}
```

### 5.2. Backend – `PatientRegistrationSerializer` + `PatientRegisterView`

Valida:

- clínica ativa (`clinic_schema_name`);
- unicidade de e‑mail;
- unicidade de CPF (via `cpf_hash`);
- senha = confirmação;
- os 3 flags de LGPD marcados.

Cria:

- `CustomUser` (role `PATIENT`, `is_active=False`, `is_verified=False`);
- `PatientProfile` com CPF criptografado e hash calculado;
- `UserConsent` para todos os `LegalDocument` marcados como `is_active=True`.

Em seguida, cria um `EmailVerificationToken` e dispara o e‑mail de verificação.

---

## 6. Verificação de E‑mail com Código de 6 Dígitos

### 6.1. Modelo `EmailVerificationToken`

```python
class EmailVerificationToken(TimeStampedModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
```

Método auxiliar para gerar código:

```python
@classmethod
def generate_code_for_user(cls, user: "CustomUser") -> "EmailVerificationToken":
    for _ in range(5):
        code = f"{secrets.randbelow(1_000_000):06d}"  # "031942"
        ...
        # cria registro com token = code (ou estrutura escolhida)
```

### 6.2. E‑mail de Verificação

A função `send_email_verification(user, token)` monta:

- link para o frontend: `FRONTEND_BASE_URL/verify-email?token=<token>`;
- mensagem com instruções e o código de 6 dígitos.

### 6.3. Endpoint `/api/auth/verify-email/`

Espera:

```json
{
  "token": "<token-da-url>",
  "code": "123456"
}
```

Valida:

- token existente e `is_used=False`;
- código informado pelo usuário;
- expiração (30 minutos, configurado na criação).

Se estiver tudo certo:

- marca `EmailVerificationToken.is_used=True` + `used_at`;
- ativa o usuário (`is_active=True`);
- marca `is_verified=True`;
- grava `AuditLog` indicando que o e‑mail foi confirmado.

---

## 7. Painel da Secretária e Multi‑Tenant na Prática

### 7.1. Endpoint `/api/auth/me/`

Retorna:

- dados básicos do usuário autenticado;
- clínica associada;
- se for secretária, o médico principal (`doctor_for_secretary`), já com nome “Dr./Dra.“.

### 7.2. Endpoint `/api/appointments/`

Aplicando `AppointmentViewSet` + `IsClinicStaffOrReadOnly`:

- SAAS_ADMIN / superuser → todos os agendamentos;
- CLINIC_OWNER → todos da própria clínica;
- DOCTOR → somente seus agendamentos;
- SECRETARY → somente a agenda do médico vinculado em `doctor_for_secretary`.

Esse comportamento está totalmente alinhado com o desenho multi‑tenant: cada usuário enxerga apenas os dados da sua clínica (e, no caso da secretária, do médico principal).

---

## 8. Instalação e Execução (Desenvolvimento)

### 8.1. Pré‑requisitos

- Python 3.11+
- PostgreSQL
- Node.js 18+ e npm
- Git

### 8.2. Clonar o repositório

```bash
git clone https://github.com/SEU_USUARIO/saas-medico.git
cd saas-medico
```

### 8.3. Backend – Ambiente virtual e dependências

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 8.4. Backend – `.env` e banco

Crie um arquivo `.env` na raiz:

```env
SECRET_KEY=django-insecure-dev-key
DEBUG=True

DB_NAME=saas_medico_db
DB_USER=postgres
DB_PASSWORD=senha_do_postgres
DB_HOST=localhost
DB_PORT=5432

FRONTEND_BASE_URL=http://localhost:5173

WHATSAPP_SERVICE_URL=http://localhost:4000
WHATSAPP_ENABLED=False
```

Crie o banco:

```sql
CREATE DATABASE saas_medico_db;
```

Rode migrações e seed:

```bash
python manage.py migrate
python manage.py seed_demo_clinics
```

### 8.5. Backend – Servidor de desenvolvimento

```bash
python manage.py runserver
```

Backend: `http://127.0.0.1:8000/`.

### 8.6. Frontend – Setup

```bash
cd frontend
npm install
```

`.env` do frontend:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

Rodar:

```bash
npm run dev
```

Frontend: `http://localhost:5173/`.

---

## 9. Próximos Passos de Desenvolvimento

- Painel completo para médicos (visualização da própria agenda + prontuários por paciente).
- UI para o paciente solicitar agendamento diretamente (`AppointmentRequestView`).
- Tela dedicada para o usuário revisar e aceitar novas versões de documentos LGPD.
- Exportação de agenda e logs em CSV/Excel.
- Estrutura de deploy em produção (Gunicorn + Nginx, banco gerenciado, fila de tarefas).

---

## 10. Status do Projeto

Neste ponto, o projeto já demonstra:

- arquitetura multi‑tenant de clínicas funcional;
- proteção de dados sensíveis com criptografia em repouso;
- fluxo de cadastro público de paciente totalmente alinhado com LGPD;
- verificação de e‑mail com token + código de 6 dígitos;
- dashboard inicial de secretária respeitando limites de acesso por clínica e por médico.

Pronto para ser usado como **prova de conceito** e como **projeto de portfólio** para arquitetura backend + frontend voltada à área da saúde.
