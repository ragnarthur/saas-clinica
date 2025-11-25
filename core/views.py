from django.utils import timezone
from rest_framework import viewsets, permissions, exceptions, status
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import (
    TokenObtainPairView as SimpleJWTTokenObtainPairView,
)

from .models import (
    PatientProfile,
    CustomUser,
    Appointment,
    AuditLog,
    LegalDocument,
    UserConsent,
    Clinic,
    EmailVerificationToken,
)
from .serializers import (
    PatientProfileSerializer,
    AppointmentSerializer,
    PatientRegistrationSerializer,
    AppointmentRequestSerializer,
    StaffUserSerializer,
    ClinicSerializer,
)
from .permissions import HasActiveConsent
from .services.whatsapp_client import send_appointment_confirmation
from .services.email_client import send_email_verification


class IsClinicStaffOrReadOnly(BasePermission):
    """
    Regra de acesso:
    - SECRETARY, DOCTOR e CLINIC_OWNER podem listar/criar/editar pacientes/agenda da própria clínica.
    - SAAS_ADMIN / superuser podem ver todo mundo.
    - PATIENT não pode usar essas rotas de gestão.
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return True

        if user.role == CustomUser.Role.PATIENT:
            return False

        return user.role in {
            CustomUser.Role.CLINIC_OWNER,
            CustomUser.Role.SECRETARY,
            CustomUser.Role.DOCTOR,
        }

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return True

        clinic_id = getattr(user.clinic, "id", None)
        obj_clinic_id = getattr(obj, "clinic_id", None)

        if obj_clinic_id is None and hasattr(obj, "clinic"):
            obj_clinic_id = obj.clinic_id

        return clinic_id == obj_clinic_id


class IsClinicOwnerOrSaaSAdmin(BasePermission):
    """
    Permissão para endpoints de gestão de staff:

    - SAAS_ADMIN / superuser: acesso total
    - CLINIC_OWNER: acesso limitado à própria clínica
    - Demais roles: negado
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return True

        return user.role == CustomUser.Role.CLINIC_OWNER

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return True

        # CLINIC_OWNER só pode ver/editar staff da própria clínica
        return getattr(obj, "clinic_id", None) == getattr(user.clinic, "id", None)


def create_audit_log(user, clinic, target_model, target_id, action, changes=None):
    """
    Helper simples para registrar ações sensíveis.
    """
    AuditLog.objects.create(
        actor=user,
        clinic=clinic,
        target_model=target_model,
        target_object_id=str(target_id),
        action=action,
        changes=changes or {},
    )


class PatientViewSet(viewsets.ModelViewSet):
    """
    CRUD de pacientes isolado por clínica.
    """

    serializer_class = PatientProfileSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        HasActiveConsent,
        IsClinicStaffOrReadOnly,
    ]

    def get_queryset(self):
        user = self.request.user

        # Admin global vê todos os pacientes, independente da clínica
        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return PatientProfile.objects.all()

        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)

        if not clinic:
            return PatientProfile.objects.none()

        # Usa helper for_tenant para padronizar o filtro por clínica
        return PatientProfile.objects.for_tenant(clinic)

    def perform_create(self, serializer):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)

        if not clinic:
            raise exceptions.ValidationError(
                "Usuários sem clínica não podem cadastrar pacientes."
            )

        patient = serializer.save(clinic=clinic)
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="PatientProfile",
            target_id=patient.id,
            action=AuditLog.Action.CREATE,
        )

    def perform_update(self, serializer):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)
        instance = self.get_object()
        patient = serializer.save()
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="PatientProfile",
            target_id=patient.id,
            action=AuditLog.Action.UPDATE,
            changes={"id": str(instance.id)},
        )

    def perform_destroy(self, instance):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)
        patient_id = instance.id
        instance.delete()
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="PatientProfile",
            target_id=patient_id,
            action=AuditLog.Action.DELETE,
        )


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    CRUD de agendamentos, isolado por clínica.
    Secretária / médico / dono de clínica gerenciam.
    """

    serializer_class = AppointmentSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        HasActiveConsent,
        IsClinicStaffOrReadOnly,
    ]

    def get_queryset(self):
        """
        Regras:

        - SAAS_ADMIN / superuser: todos os agendamentos de todas as clínicas
        - CLINIC_OWNER: todos os agendamentos da própria clínica
        - DOCTOR: apenas seus agendamentos
        - SECRETARY: apenas agendamentos do médico vinculado (doctor_for_secretary)
        """
        user = self.request.user

        base_qs = Appointment.objects.select_related(
            "clinic",
            "doctor",
            "patient",
            "patient__user",
        )

        # Admin global vê tudo
        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            return base_qs

        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)

        # Sem clínica => nada
        if not clinic:
            return base_qs.none()

        qs = base_qs.filter(clinic=clinic)

        if user.role == CustomUser.Role.DOCTOR:
            # Médico vê só a própria agenda
            qs = qs.filter(doctor=user)

        elif user.role == CustomUser.Role.SECRETARY:
            # Secretária vê apenas a agenda do médico vinculado
            doctor_id = getattr(user, "doctor_for_secretary_id", None)
            if doctor_id:
                qs = qs.filter(doctor_id=doctor_id)
            else:
                # Se não tem vínculo configurado, por segurança não mostra nada
                qs = qs.none()

        # CLINIC_OWNER continua vendo tudo da clínica
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)

        if not clinic:
            raise exceptions.ValidationError(
                "Usuários sem clínica não podem criar agendamentos."
            )

        appointment = serializer.save(clinic=clinic)
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="Appointment",
            target_id=appointment.id,
            action=AuditLog.Action.CREATE,
        )

    def perform_update(self, serializer):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)
        instance = self.get_object()
        old_status = instance.status  # guarda status anterior

        appointment = serializer.save()
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="Appointment",
            target_id=appointment.id,
            action=AuditLog.Action.UPDATE,
            changes={"id": str(instance.id), "status": appointment.status},
        )

        # Hook de WhatsApp: só dispara quando mudar PARA CONFIRMED
        if (
            old_status != appointment.status
            and appointment.status == Appointment.Status.CONFIRMED
        ):
            send_appointment_confirmation(appointment)

    def perform_destroy(self, instance):
        user = self.request.user
        clinic = getattr(self.request, "clinic", None) or getattr(user, "clinic", None)
        appointment_id = instance.id
        instance.delete()
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="Appointment",
            target_id=appointment_id,
            action=AuditLog.Action.DELETE,
        )


class ActiveClinicsView(APIView):
    """
    Endpoint PÚBLICO para o cadastro listar clínicas ativas.

    GET /api/clinics/active/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        clinics = Clinic.objects.filter(is_active=True).order_by("name")
        data = ClinicSerializer(clinics, many=True).data
        return Response(data, status=status.HTTP_200_OK)


class PublicActiveLegalDocsView(APIView):
    """
    Endpoint PÚBLICO para o cadastro carregar os textos de LGPD.

    GET /api/legal-documents/active/
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        docs = LegalDocument.objects.filter(is_active=True).order_by(
            "doc_type", "version"
        )
        data = [
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "version": doc.version,
                "content": doc.content,
            }
            for doc in docs
        ]
        return Response(data, status=status.HTTP_200_OK)


class PatientRegisterView(APIView):
    """
    Endpoint público de cadastro de paciente com fluxo de consentimento LGPD
    e verificação de e-mail via código numérico de 6 dígitos.

    - Não exige autenticação
    - Cria User (role PATIENT) + PatientProfile
    - Registra UserConsent para docs ativos
    - Gera EmailVerificationToken com código de 6 dígitos e envia e-mail
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PatientRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # serializer retorna (user, patient, email_token)
        user, patient, email_token = serializer.save()

        # Envia o e-mail de verificação (código de 6 dígitos + link)
        send_email_verification(user=user, token=email_token.token)

        return Response(
            {
                "detail": (
                    "Cadastro recebido! Enviamos um código de verificação de 6 dígitos "
                    "para o seu e-mail. Use o código para ativar o acesso."
                ),
                "user_id": str(user.id),
                "patient_id": str(patient.id),
                "email": user.email,
                "clinic_id": str(patient.clinic_id),
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    """
    Confirma o e-mail de um usuário recém-cadastrado usando
    um CÓDIGO numérico de 6 dígitos.

    POST /api/auth/verify-email/
    body: { "token": "123456" }
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        raw_token = request.data.get("token")

        token = (str(raw_token or "")).strip()

        if not token:
            return Response(
                {"detail": "Código de verificação é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not token.isdigit() or len(token) != 6:
            return Response(
                {"detail": "Código de verificação inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ev = EmailVerificationToken.objects.select_related("user").get(
                token=token,
                is_used=False,
            )
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"detail": "Código inválido ou já utilizado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verifica expiração, se configurada
        if ev.expires_at and ev.expires_at < timezone.now():
            return Response(
                {"detail": "Código expirado. Solicite um novo cadastro."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = ev.user

        # Marca token como usado
        ev.is_used = True
        ev.used_at = timezone.now()
        ev.save(update_fields=["is_used", "used_at"])

        # Ativa usuário e marca como verificado
        user.is_active = True
        user.is_verified = True
        user.save(update_fields=["is_active", "is_verified"])

        clinic = getattr(user, "clinic", None)
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="CustomUser",
            target_id=user.id,
            action=AuditLog.Action.UPDATE,
            changes={"email_verified": True},
        )

        return Response(
            {"detail": "E-mail verificado com sucesso. Você já pode fazer login."},
            status=status.HTTP_200_OK,
        )


class AppointmentRequestView(APIView):
    """
    Endpoint para o PACIENTE solicitar um horário.

    - Necessita autenticação JWT
    - Necessita consentimento ativo (HasActiveConsent)
    - Somente role=PATIENT
    """

    permission_classes = [permissions.IsAuthenticated, HasActiveConsent]

    def post(self, request, *args, **kwargs):
        user = request.user

        if user.role != CustomUser.Role.PATIENT:
            return Response(
                {"detail": "Somente pacientes podem solicitar agendamentos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AppointmentRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()

        create_audit_log(
            user=user,
            clinic=appointment.clinic,
            target_model="Appointment",
            target_id=appointment.id,
            action=AuditLog.Action.CREATE,
            changes={"status": appointment.status},
        )

        return Response(
            {
                "id": str(appointment.id),
                "status": appointment.status,
                "detail": "Solicitação de agendamento registrada com sucesso.",
            },
            status=status.HTTP_201_CREATED,
        )


class ConsentActiveDocsView(APIView):
    """
    Lista os documentos legais ATIVOS (Termos, Privacidade, etc.)
    para o usuário logado ler e aceitar.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        docs = LegalDocument.objects.filter(is_active=True).order_by(
            "doc_type", "version"
        )

        data = [
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "version": doc.version,
                "content": doc.content,
            }
            for doc in docs
        ]

        return Response(data, status=status.HTTP_200_OK)


class ConsentAcceptView(APIView):
    """
    Registra o aceite do usuário logado para TODOS os documentos ativos.

    - Idempotente: se já tiver UserConsent para algum doc, não duplica.
    - Após chamar esse endpoint, HasActiveConsent deve ficar True
      (enquanto não surgirem novas versões ativas).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        docs = LegalDocument.objects.filter(is_active=True)

        created = 0
        accepted_ids = []

        for doc in docs:
            consent, was_created = UserConsent.objects.get_or_create(
                user=user, document=doc
            )
            if was_created:
                created += 1
            accepted_ids.append(doc.id)

        clinic = getattr(user, "clinic", None)
        create_audit_log(
            user=user,
            clinic=clinic,
            target_model="LegalDocument",
            target_id="*",
            action=AuditLog.Action.UPDATE,
            changes={
                "accepted_documents": accepted_ids,
            },
        )

        return Response(
            {
                "detail": "Consentimentos registrados com sucesso.",
                "created": created,
                "total_active": docs.count(),
            },
            status=status.HTTP_201_CREATED,
        )


class StaffUserViewSet(viewsets.ModelViewSet):
    """
    CRUD de staff da clínica:

    - SAAS_ADMIN: gerencia staff de qualquer clínica.
    - CLINIC_OWNER: gerencia staff apenas da SUA clínica.
    - Roles permitidos aqui: DOCTOR, SECRETARY, CLINIC_OWNER (para SAAS_ADMIN).
    - Usa StaffUserSerializer para lidar com senha e DoctorProfile.
    """

    serializer_class = StaffUserSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        HasActiveConsent,
        IsClinicOwnerOrSaaSAdmin,
    ]

    def get_queryset(self):
        user = self.request.user

        qs = CustomUser.objects.all()

        # Nunca listamos SAAS_ADMIN aqui
        qs = qs.exclude(role=CustomUser.Role.SAAS_ADMIN)

        if user.is_superuser or user.role == CustomUser.Role.SAAS_ADMIN:
            # SAAS_ADMIN pode filtrar por ?clinic=<uuid>
            clinic_id = self.request.query_params.get("clinic")
            if clinic_id:
                qs = qs.filter(clinic_id=clinic_id)
            return qs

        # CLINIC_OWNER -> staff da própria clínica
        if user.role == CustomUser.Role.CLINIC_OWNER and user.clinic:
            return qs.filter(clinic=user.clinic)

        # Qualquer outro role não deveria chegar aqui (bloqueado por permissão),
        # mas por segurança retornamos vazio.
        return CustomUser.objects.none()


class MeView(APIView):
    """
    Retorna dados do usuário autenticado + clínica + médico de referência.

    - Usado pelo dashboard do front para exibir:
      - nome da secretária/médico/owner logado
      - informações da clínica
      - médico principal com quem a secretária está atuando
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        clinic = getattr(user, "clinic", None)

        doctor_for_secretary = None
        if user.role == CustomUser.Role.SECRETARY and clinic:
            # usa o médico configurado na secretária, se existir;
            # senão, pega o primeiro médico da clínica
            doctor = user.doctor_for_secretary or (
                CustomUser.objects.filter(
                    clinic=clinic,
                    role=CustomUser.Role.DOCTOR,
                )
                .order_by("first_name", "last_name")
                .first()
            )

            if doctor:
                doctor_for_secretary = {
                    "id": str(doctor.id),
                    # já vem com Dr. / Dra. conforme gender
                    "name": doctor.get_display_name_with_title(),
                }

        clinic_payload = None
        if clinic:
            clinic_payload = {
                "id": str(clinic.id),
                "name": clinic.name,
            }

        data = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "clinic": clinic_payload,
            "doctor_for_secretary": doctor_for_secretary,
        }

        return Response(data, status=status.HTTP_200_OK)


class LoggingTokenObtainPairView(SimpleJWTTokenObtainPairView):
    """
    Variante do TokenObtainPairView que registra LOGIN no AuditLog
    quando o JWT é obtido com sucesso.

    - Mantém exatamente o mesmo payload de resposta do SimpleJWT;
    - Usa o username enviado no corpo da requisição para identificar o usuário.
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        # Só registra LOGIN se o JWT foi gerado com sucesso
        if response.status_code == status.HTTP_200_OK:
            username = request.data.get("username")

            if username:
                try:
                    user = CustomUser.objects.get(username=username)
                except CustomUser.DoesNotExist:
                    user = None

                if user is not None:
                    clinic = getattr(user, "clinic", None)
                    create_audit_log(
                        user=user,
                        clinic=clinic,
                        target_model="CustomUser",
                        target_id=user.id,
                        action=AuditLog.Action.LOGIN,
                        changes=None,
                    )

        return response
