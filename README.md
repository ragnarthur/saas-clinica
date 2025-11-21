
# SaaS Médico – Sistema de Agendamentos para Clínicas

Aplicação full‑stack para gestão de clínicas médicas, focada em:

- multi‑clínicas (cada *Clinic* é um tenant lógico);
- agendamento de consultas;
- fluxo de pacientes com consentimento LGPD;
- painéis específicos para secretárias, médicos e donos de clínica;
- integração opcional com microserviço de WhatsApp para confirmação de consultas.

---

## Stack Tecnológica

### Backend

- **Django 5.x**
- **Django REST Framework**
- **PostgreSQL**
- Autenticação via **JWT** (`rest_framework_simplejwt`)
- Modelo de usuário customizado (`core.CustomUser`)
- Separação de perfis e dados sensíveis (LGPD)
- Seeds de desenvolvimento com `manage.py seed_demo_clinics`

### Frontend

- **React + Vite**
- **TypeScript**
- Consumo da API via `fetch` encapsulado em `api/client.ts`
- Tela de login, cadastro de paciente e **dashboard da secretária**

### Integração de WhatsApp (opcional)

- Microserviço Node/Express separado
- Backend Django chama o serviço via HTTP para enviar confirmações de consulta
- Variáveis de ambiente:
  - `WHATSAPP_SERVICE_URL`
  - `WHATSAPP_ENABLED`

---

## Domínio Principal

### Clinic

Modelo `Clinic` representa cada clínica (tenant):

- `id` (UUID)
- `name`
- `schema_name` (slug único, ex: `bem_estar`)
- `is_active`

### CustomUser

Modelo de usuário customizado: `core.CustomUser`

- `id` (UUID)
- `clinic` (FK para `Clinic`, opcional só para SAAS_ADMIN)
- `role` (enum):
  - `SAAS_ADMIN` – administrador global do SaaS
  - `CLINIC_OWNER` – dono/admin da clínica
  - `SECRETARY` – secretária da clínica
  - `DOCTOR` – médico
  - `PATIENT` – paciente
- `gender` (enum):
  - `M` – masculino
  - `F` – feminino
- `doctor_for_secretary` – FK opcional apontando para o médico principal com quem a secretária atua
- `is_verified` – flag de verificação de e‑mail/conta
- Propriedade `has_active_consent` – checa se o usuário aceitou todos os documentos legais ativos
- Helper `get_display_name_with_title()` – retorna o nome com prefixo automático:
  - `"Dr. Nome Sobrenome"` para médicos homens
  - `"Dra. Nome Sobrenome"` para médicas mulheres
  - Demais papéis retornam apenas o nome completo

### Perfis

- **DoctorProfile**
  - `user` (OneToOne para `CustomUser` com role DOCTOR)
  - `crm`
  - `specialty`
  - `__str__` usa `get_display_name_with_title()` para exibir `Dr.` ou `Dra.`

- **PatientProfile**
  - `user` (OneToOne para `CustomUser` com role PATIENT)
  - `clinic`
  - `full_name`
  - `cpf` (único)
  - `phone`

### LGPD e Auditoria

- **LegalDocument**
  - `doc_type`: TERMS, PRIVACY, CONSENT
  - `version`
  - `content`
  - `is_active`

- **UserConsent**
  - usuário que aceitou
  - documento aceito
  - auditoria técnica (IP, user agent, data/hora)

- **AuditLog**
  - `actor` (usuário que executou a ação)
  - `clinic`
  - `target_model`, `target_object_id`
  - `action` (CREATE, READ, UPDATE, DELETE, LOGIN, EXPORT)
  - `changes` (JSON com difs relevantes)

### Appointments (Agendamentos)

Modelo `Appointment`:

- `clinic`
- `doctor` (FK para `CustomUser` com role DOCTOR)
- `patient` (FK para `PatientProfile`)
- `start_time`, `end_time`
- `status` (enum):
  - `REQUESTED` – solicitado pelo paciente/secretária
  - `CONFIRMED` – confirmado pela clínica
  - `COMPLETED` – consulta concluída
  - `CANCELED_BY_PATIENT`
  - `CANCELED_BY_CLINIC`
- `clinical_notes` – texto livre (idealmente criptografado em produção)

---

## Fluxos Principais

### 1. Autenticação JWT

- Login em `/auth/login/` (usuário + senha)
- Backend retorna `access` e `refresh` tokens
- Frontend armazena o token de acesso e usa em todas as chamadas via `Authorization: Bearer <token>`
- Endpoint `/auth/me/` retorna os dados do usuário logado, clínica e (se for secretária) o médico principal:

```jsonc
{
  "id": "...",
  "username": "bem_estar_secretaria1",
  "email": "bem_estar_secretaria1@example.com",
  "first_name": "Juliana",
  "last_name": "Ramos",
  "role": "SECRETARY",
  "clinic": {
    "id": "...",
    "name": "Clínica Bem Estar"
  },
  "doctor_for_secretary": {
    "id": "...",
    "name": "Dr. Carlos Almeida"
  }
}
```

### 2. Consentimento LGPD

- Endpoints públicos para carregar textos de Termos, Política e Consentimento.
- Usuário logado pode aceitar todos os documentos ativos via endpoint dedicado.
- Permissão `HasActiveConsent` bloqueia uso da API se o usuário ainda não aceitou todas as versões vigentes.

### 3. Cadastro Público de Paciente

- Endpoint público recebe:
  - clínica alvo (`clinic_schema_name`)
  - `full_name`, `cpf`, `phone`, `email`, `password`/`password_confirm`
  - flags de aceite dos documentos (agree_terms, agree_privacy, agree_consent)
- Cria:
  - `CustomUser` com role PATIENT
  - `PatientProfile`
  - `UserConsent` para todos os `LegalDocument` ativos

### 4. Painel da Secretária (Dashboard)

- Frontend usa dois endpoints principais:
  - `GET /auth/me/` – dados do usuário + clínica + médico principal
  - `GET /appointments/` – lista de agendamentos
- Permissão `IsClinicStaffOrReadOnly` garante que SECRETARY, DOCTOR e CLINIC_OWNER veem apenas dados da própria clínica.
- Secretária tem campo `doctor_for_secretary` definido, e o backend usa isso para filtrar os agendamentos do dashboard.
- A listagem apresenta:
  - paciente
  - médico (já com prefixo **Dr./Dra.** via `get_display_name_with_title()`)
  - horários
  - status + ações (Confirmar / Concluir / Cancelar)
- Sempre que um agendamento muda para `CONFIRMED`, o backend dispara o serviço de WhatsApp (se habilitado).

### 5. Gestão de Staff

- `StaffUserViewSet` permite que:
  - **SAAS_ADMIN** crie/gerencie staff de qualquer clínica
  - **CLINIC_OWNER** gerencie staff apenas da sua clínica
- Roles permitidos nesse endpoint: `DOCTOR`, `SECRETARY`, `CLINIC_OWNER`
- Para médicos, o serializer aceita `crm` e `specialty` e mantém o `DoctorProfile` sincronizado.

---

## Instalação e Execução (Desenvolvimento)

### Pré-requisitos

- Python 3.11+
- PostgreSQL
- Node.js 18+ e npm
- Git

### 1. Clonar o repositório

```bash
git clone https://github.com/SEU_USUARIO/saas-medico.git
cd saas-medico
```

### 2. Backend – Ambiente virtual e dependências

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Backend – Configuração do banco (.env)

Crie um arquivo `.env` na raiz do projeto (mesmo nível de `config/`) com algo como:

```env
# Django
SECRET_KEY=django-insecure-dev-key
DEBUG=True

# Banco de dados
DB_NAME=saas_medico_db
DB_USER=postgres
DB_PASSWORD=senha_do_postgres
DB_HOST=localhost
DB_PORT=5432

# WhatsApp (opcional)
WHATSAPP_SERVICE_URL=http://localhost:4000
WHATSAPP_ENABLED=False
```

Crie o banco de dados no PostgreSQL (exemplo):

```sql
CREATE DATABASE saas_medico_db;
```

### 4. Backend – Migrações e seed

```bash
python manage.py migrate
python manage.py seed_demo_clinics
```

Esse comando irá:

- criar usuários **SAAS_ADMIN**;
- criar 3 clínicas (`Vida Plena`, `Bem Estar`, `Horizonte Saúde`);
- criar donos de clínica, médicos, secretárias, pacientes e agendamentos demo;
- criar documentos legais fake e registrar consentimento para todos os usuários (apenas em DEV).

### 5. Backend – Rodar o servidor

```bash
python manage.py runserver
```

O backend sobe em `http://127.0.0.1:8000/`.

### 6. Frontend – Instalação

Entre na pasta `frontend/`:

```bash
cd frontend
npm install
```

Crie o arquivo `.env` do frontend (se ainda não existir), por exemplo:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Rodar o servidor de desenvolvimento:

```bash
npm run dev
```

O frontend sobe em `http://localhost:5173/`.

---

## Dados de Seed (Usuários Demo)

### SAAS Admins

- `saas_admin1` / **teste123**
- `saas_admin2` / **teste123**

### Clínicas e times

Para cada clínica, são criados:

- 2 donos (`CLINIC_OWNER`)
- 3 médicos (`DOCTOR`)
- 3 secretárias (`SECRETARY`)
- 20 pacientes por médico
- ~10 agendamentos por médico

Exemplo para a **Clínica Bem Estar** (`schema_name = bem_estar`):

#### Médicos

- `bem_estar_dr1` – **Dr. Carlos Almeida** (Clínico Geral)
- `bem_estar_dr2` – **Dra. Fernanda Souza** (Clínico Geral)
- `bem_estar_dr3` – **Dr. Rafael Pereira** (Clínico Geral)

Todos com senha: **`teste123`**.

#### Secretárias

- `bem_estar_secretaria1` – Juliana Ramos → atende **Dr. Carlos Almeida**
- `bem_estar_secretaria2` – Bruno Lima → atende **Dra. Fernanda Souza**
- `bem_estar_secretaria3` – Patrícia Oliveira → atende **Dr. Rafael Pereira**

Senha: **`teste123`**.

Ao logar como, por exemplo, `bem_estar_secretaria1`, o dashboard exibirá:

- texto “Atuando com **Dr. Carlos Almeida**” no cabeçalho;
- lista de agendamentos filtrada apenas para esse médico;
- botões para confirmar, concluir e cancelar consultas (respeitando o status).

---

## Estrutura de Pastas (resumida)

```text
saas-medico/
├── config/                 # Projeto Django
├── core/                   # App principal (models, views, serializers, commands)
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo_clinics.py
│   ├── models.py
│   ├── serializers.py
│   ├── permissions.py
│   ├── services/
│   │   └── whatsapp_client.py
│   ├── views.py
│   └── urls.py
├── frontend/               # Aplicação React + Vite
│   ├── src/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   └── PatientSignupPage.tsx
│   │   └── styles/
│   └── vite.config.ts
├── manage.py
├── requirements.txt
└── README.md               # (este arquivo)
```

---

## Próximos Passos

- Implementar painel específico para médicos (visualização da própria agenda, prontuários, etc.).
- Adicionar filtros avançados no dashboard (por status, período, médico, paciente).
- Implementar exportação de agenda e logs em CSV/Excel.
- Configurar deploy em ambiente de produção (Gunicorn + Nginx + banco gerenciado).

---

## Licença

