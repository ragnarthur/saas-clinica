# core/models.py
import uuid
import hashlib
import secrets
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.apps import apps
from django.utils import timezone
from fernet_fields import EncryptedCharField, EncryptedTextField

from .tenancy import TenantManager


# --- UTILS / BASES ---


class TimeStampedModel(models.Model):
    """
    Classe abstrata que adiciona created_at e updated_at
    automaticamente em todas as tabelas que a herdarem.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --- SAAS CORE ---


class Clinic(TimeStampedModel):
    """
    O 'Tenant' (Inquilino). Representa a clínica médica.
    Dados daqui não podem vazar para outra clínica.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    schema_name = models.SlugField(
        unique=True,
        help_text="Identificador único na URL ou DB",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class CustomUser(AbstractUser):
    """
    Substitui o User padrão do Django.
    Adiciona UUID, vínculo com a Clínica e papel (role).
    """

    # Enums para tipos de usuário
    class Role(models.TextChoices):
        SAAS_ADMIN = "SAAS_ADMIN", _("Admin do Sistema")
        CLINIC_OWNER = "CLINIC_OWNER", _("Dono da Clínica")
        SECRETARY = "SECRETARY", _("Secretária")
        DOCTOR = "DOCTOR", _("Médico")
        PATIENT = "PATIENT", _("Paciente")

    class Gender(models.TextChoices):
        MALE = "M", _("Masculino")
        FEMALE = "F", _("Feminino")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Vínculo com a clínica (Tenant). Opcional apenas para SAAS_ADMIN.
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PATIENT,
    )

    # Secretária -> médico principal com quem atua (agenda principal)
    doctor_for_secretary = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="secretaries",
        limit_choices_to={"role": Role.DOCTOR},
        help_text="Médico principal com quem a secretária atua.",
    )

    # Gênero (pra Dr. / Dra.)
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        null=True,
        blank=True,
        help_text="Usado para definir automaticamente Dr. ou Dra. para médicos.",
    )

    # Campos de auditoria básica
    is_verified = models.BooleanField(default=False)

    # Ajustes necessários para o Django não reclamar de conflito com auth.User padrão
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name=_("groups"),
        blank=True,
        related_name="customuser_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=_("user permissions"),
        blank=True,
        related_name="customuser_set",
        related_query_name="user",
    )

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    @property
    def has_active_consent(self) -> bool:
        """
        Verifica se o usuário aceitou TODOS os documentos legais ativos.
        Usa apps.get_model para evitar import recursivo de core.models.
        """
        LegalDocument = apps.get_model("core", "LegalDocument")
        UserConsent = apps.get_model("core", "UserConsent")

        active_docs = LegalDocument.objects.filter(is_active=True)
        if not active_docs.exists():
            # Se não há documentos ativos, não bloqueia o uso do sistema.
            return True

        consensos = UserConsent.objects.filter(user=self, document__in=active_docs)
        return consensos.count() == active_docs.count()

    # -------- display helpers --------

    def get_display_name_with_title(self) -> str:
        """
        Retorna o nome já com Dr. / Dra. quando for médico.
        Para outros papéis, só devolve o nome normal.
        """
        base = self.get_full_name() or self.username or getattr(self, "email", "") or ""
        if self.role == CustomUser.Role.DOCTOR:
            if self.gender == CustomUser.Gender.FEMALE:
                prefix = "Dra."
            else:
                prefix = "Dr."
            return f"{prefix} {base}".strip()
        return base


# --- LGPD & LEGAL ---


class LegalDocument(TimeStampedModel):
    """
    Armazena versões dos Termos de Uso, Política de Privacidade, etc.
    """

    class DocType(models.TextChoices):
        TERMS = "TERMS", _("Termos de Uso")
        PRIVACY = "PRIVACY", _("Política de Privacidade")
        CONSENT = "CONSENT", _("Termo de Consentimento Médico")

    version = models.CharField(max_length=10, help_text="Ex: 1.0, 2.1")
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    content = models.TextField(help_text="Conteúdo em HTML ou Markdown")
    is_active = models.BooleanField(default=False)

    class Meta:
        unique_together = ["version", "doc_type"]
        constraints = [
            # Garante que só exista UMA versão ativa por tipo
            models.UniqueConstraint(
                fields=["doc_type"],
                condition=models.Q(is_active=True),
                name="uniq_active_legal_document_per_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()} - v{self.version}"


class UserConsent(models.Model):
    """
    Registra o 'Aceito' do usuário. CRUCIAL PARA LGPD.
    """

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name="consents",
    )

    # Auditoria técnica
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text="Dados do navegador/dispositivo",
    )
    agreed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Consentimento de Usuário"
        verbose_name_plural = "Consentimentos de Usuários"
        unique_together = ["user", "document"]

    def __str__(self) -> str:
        return f"{self.user.email} aceitou {self.document}"


class EmailVerificationToken(TimeStampedModel):
    """
    Token simples para verificação de e-mail.

    - Vinculado a um usuário
    - Pode ser usado uma única vez
    - Usa código numérico de 6 dígitos em `token`
    """

    user = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    # Armazena o código de 6 dígitos (como string)
    token = models.CharField(max_length=64, unique=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Token de Verificação de E-mail"
        verbose_name_plural = "Tokens de Verificação de E-mail"

    def __str__(self) -> str:
        return f"{self.user.email} - {self.token}"

    @classmethod
    def generate_code_for_user(cls, user: "CustomUser") -> "EmailVerificationToken":
        """
        Gera e persiste um código numérico de 6 dígitos, único na tabela.

        - Usa secrets.randbelow para segurança
        - Define expiração em 30 minutos
        - Tenta algumas vezes em caso de colisão de unicidade
        """
        from django.db import IntegrityError

        for _ in range(5):
            code = f"{secrets.randbelow(1_000_000):06d}"  # ex: "031942"
            expires_at = timezone.now() + timedelta(minutes=30)
            try:
                return cls.objects.create(
                    user=user,
                    token=code,
                    expires_at=expires_at,
                )
            except IntegrityError:
                # se bater na unique constraint, tenta de novo
                continue

        # Se chegou aqui, algo está muito errado (provavelmente ambiente de teste)
        raise RuntimeError("Não foi possível gerar um código de verificação único.")


class AuditLog(TimeStampedModel):
    """
    Log de ações sensíveis, pensando LGPD:
    - quem fez
    - em qual registro
    - qual ação
    - o que mudou
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Criação"
        READ = "READ", "Leitura"
        UPDATE = "UPDATE", "Atualização"
        DELETE = "DELETE", "Exclusão"
        LOGIN = "LOGIN", "Login"
        EXPORT = "EXPORT", "Exportação"

    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    target_model = models.CharField(max_length=100)
    target_object_id = models.CharField(
        max_length=50,
        help_text="ID do objeto alvo (UUID ou outro identificador)",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    changes = models.JSONField(
        null=True,
        blank=True,
        help_text="Diferenças de estado (antes/depois) em updates.",
    )

    # Manager com helper de tenant
    objects = TenantManager()

    class Meta:
        verbose_name = "Log de Auditoria"
        verbose_name_plural = "Logs de Auditoria"

    def __str__(self) -> str:
        return f"{self.action} - {self.target_model} ({self.target_object_id})"


# --- PERFIS ESPECÍFICOS ---


class DoctorProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    crm = models.CharField(max_length=20)
    specialty = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.get_display_name_with_title()} - {self.crm}"


class PatientProfile(TimeStampedModel):
    """
    Dados médicos sensíveis do paciente.
    Separado do User para facilitar segurança.
    """

    class Sex(models.TextChoices):
        MALE = "M", _("Masculino")
        FEMALE = "F", _("Feminino")
        NOT_INFORMED = "N", _("Prefiro não informar")

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="patient_profile",
        null=True,
        blank=True,
    )

    # Paciente pertence a uma clínica (tenant)
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name="patients",
    )

    # CPF criptografado no banco
    cpf = EncryptedCharField(
        max_length=14,
        help_text="CPF criptografado (apenas app exibe em texto).",
    )

    # Hash do CPF normalizado (somente dígitos) para busca e unicidade por clínica
    cpf_hash = models.CharField(
        max_length=64,
        editable=False,
        null=True,
        blank=True,
        help_text="Hash SHA-256 do CPF normalizado (somente dígitos).",
    )

    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)

    # Novos campos de perfil do paciente
    sex = models.CharField(
        max_length=1,
        choices=Sex.choices,
        null=True,
        blank=True,
        help_text="Sexo do paciente.",
    )
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data de nascimento do paciente.",
    )

    # Manager com helper de tenant
    objects = TenantManager()

    class Meta:
        verbose_name = "Paciente"
        verbose_name_plural = "Pacientes"
        constraints = [
            # Garante que o mesmo CPF (hash) não se repita na mesma clínica.
            models.UniqueConstraint(
                fields=["clinic", "cpf_hash"],
                name="uniq_patient_cpf_hash_per_clinic",
            )
        ]

    def __str__(self) -> str:
        return self.full_name

    def _build_cpf_hash(self) -> str | None:
        """
        Normaliza o CPF (só dígitos) e gera hash SHA-256.
        Retorna None se não houver CPF.
        """
        if not self.cpf:
            return None
        normalized = "".join(filter(str.isdigit, str(self.cpf)))
        if not normalized:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        # Sempre recalcula o hash antes de salvar
        cpf_hash = self._build_cpf_hash()
        if cpf_hash:
            self.cpf_hash = cpf_hash
        super().save(*args, **kwargs)


# --- AGENDAMENTO / APPOINTMENT ---


class Appointment(TimeStampedModel):
    """
    Agendamento de consultas.
    Sempre vinculado a uma clínica e aos perfis corretos.
    """

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Solicitado"
        CONFIRMED = "CONFIRMED", "Confirmado"
        COMPLETED = "COMPLETED", "Concluído"
        CANCELED_BY_PATIENT = "CANCELED_BY_PATIENT", "Cancelado pelo paciente"
        CANCELED_BY_CLINIC = "CANCELED_BY_CLINIC", "Cancelado pela clínica"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name="appointments",
        verbose_name="Clínica",
    )

    doctor = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="appointments_as_doctor",
        limit_choices_to={"role": CustomUser.Role.DOCTOR},
        verbose_name="Médico",
    )

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="appointments",
        verbose_name="Paciente",
    )

    start_time = models.DateTimeField("Início")
    end_time = models.DateTimeField("Fim")

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.REQUESTED,
    )

    # Notas clínicas criptografadas (LGPD)
    clinical_notes = EncryptedTextField(
        blank=True,
        help_text="Notas clínicas criptografadas; acesso só do médico.",
    )

    # Manager com helper de tenant
    objects = TenantManager()

    class Meta:
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        ordering = ["-start_time"]

    def __str__(self) -> str:
        return f"{self.clinic} - {self.patient.full_name} ({self.start_time:%d/%m/%Y %H:%M})"
