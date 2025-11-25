# core/serializers.py
import hashlib

from rest_framework import serializers

from .models import (
    Clinic,
    PatientProfile,
    Appointment,
    LegalDocument,
    CustomUser,
    UserConsent,
    DoctorProfile,
    EmailVerificationToken,
)


# ---------- helpers de CPF ----------


def normalize_cpf(value: str) -> str:
    """
    Remove qualquer coisa que não seja dígito.
    """
    if not value:
        return ""
    return "".join(filter(str.isdigit, value))


def make_cpf_hash(value: str) -> str:
    """
    Gera hash SHA-256 do CPF normalizado.
    """
    normalized = normalize_cpf(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------- serializers principais ----------


class ClinicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clinic
        fields = ["id", "name", "schema_name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PatientProfileSerializer(serializers.ModelSerializer):
    # Opcional: exibir info básica do user vinculado
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "full_name",
            "cpf",
            "phone",
            "sex",
            "birth_date",
            "clinic",
            "user_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "clinic",  # sempre virá da clínica do usuário logado
            "user_id",
            "created_at",
            "updated_at",
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    doctor_name = serializers.CharField(
        source="doctor.get_display_name_with_title", read_only=True
    )

    class Meta:
        model = Appointment
        fields = [
            "id",
            "clinic",
            "doctor",
            "doctor_name",
            "patient",
            "patient_name",
            "start_time",
            "end_time",
            "status",
            "clinical_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "clinic",  # vem do user.clinic
            "created_at",
            "updated_at",
        ]


class PatientRegistrationSerializer(serializers.Serializer):
    """
    Fluxo de cadastro de paciente com LGPD (tela pública).

    O front envia:
      - clinic_schema_name: slug da clínica (ex: "vida_plena")
      - full_name, cpf, phone, email
      - password, password_confirm
      - sex (M/F/N), birth_date (dd/mm/aaaa ou ISO)
      - agree_terms, agree_privacy, agree_consent: booleans
    """

    clinic_schema_name = serializers.SlugField()
    full_name = serializers.CharField(max_length=255)
    cpf = serializers.CharField(max_length=14)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True, min_length=6)

    # novos campos opcionais
    sex = serializers.ChoiceField(
        choices=["M", "F", "N"],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    birth_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
    )

    agree_terms = serializers.BooleanField()
    agree_privacy = serializers.BooleanField()
    agree_consent = serializers.BooleanField()

    def validate(self, attrs):
        # 1) clínica
        schema = attrs["clinic_schema_name"]

        try:
            clinic = Clinic.objects.get(schema_name=schema, is_active=True)
        except Clinic.DoesNotExist:
            raise serializers.ValidationError(
                {"clinic_schema_name": "Clínica não encontrada ou inativa."}
            )

        attrs["clinic"] = clinic

        # 2) e-mail único
        if CustomUser.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "E-mail já cadastrado."})

        # 3) CPF único (usa hash, pq o campo real é criptografado)
        cpf_hash = make_cpf_hash(attrs["cpf"])
        if PatientProfile.objects.filter(clinic=clinic, cpf_hash=cpf_hash).exists():
            raise serializers.ValidationError({"cpf": "CPF já cadastrado."})

        # 4) senha = confirmação
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "A confirmação da senha não confere."}
            )

        # 5) LGPD – precisa marcar os 3
        if not (
            attrs["agree_terms"]
            and attrs["agree_privacy"]
            and attrs["agree_consent"]
        ):
            raise serializers.ValidationError(
                {
                    "detail": (
                        "É necessário concordar com os Termos de Uso, "
                        "Política de Privacidade e Termo de Consentimento."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        clinic = validated_data["clinic"]
        full_name = validated_data["full_name"]
        email = validated_data["email"]
        cpf = validated_data["cpf"]
        phone = validated_data["phone"]
        password = validated_data["password"]

        # novos campos opcionais
        sex = validated_data.get("sex")
        birth_date = validated_data.get("birth_date")

        # limpando helpers
        for field in [
            "clinic_schema_name",
            "password_confirm",
            "agree_terms",
            "agree_privacy",
            "agree_consent",
        ]:
            validated_data.pop(field, None)

        # User = paciente (AINDA INATIVO até confirmar o e-mail)
        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            clinic=clinic,
            role=CustomUser.Role.PATIENT,
            is_active=False,  # bloqueia login até verificar e-mail
        )
        user.set_password(password)
        user.first_name = full_name
        user.save()

        # Perfil de paciente
        patient = PatientProfile.objects.create(
            user=user,
            clinic=clinic,
            full_name=full_name,
            cpf=cpf,
            phone=phone,
            sex=sex,
            birth_date=birth_date,
        )

        # Registra consentimento para TODOS docs ativos (Termos, Privacidade, Consentimento)
        active_docs = LegalDocument.objects.filter(is_active=True)
        for doc in active_docs:
            UserConsent.objects.get_or_create(user=user, document=doc)

        # Cria token de verificação de e-mail (código de 6 dígitos)
        email_token = EmailVerificationToken.generate_code_for_user(user)

        # IMPORTANTE: como estamos usando a Serializer manualmente na view,
        # podemos devolver uma tupla customizada.
        return user, patient, email_token


class AppointmentRequestSerializer(serializers.Serializer):
    """
    Paciente solicita um horário:

    - O paciente já está autenticado (JWT, role=PATIENT)
    - clinic vem do próprio usuário
    - patient vem do patient_profile do usuário
    - ele só informa:
        - doctor_id
        - start_time
        - end_time
    """

    doctor_id = serializers.UUIDField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Usuário não autenticado.")

        if user.role != CustomUser.Role.PATIENT:
            raise serializers.ValidationError(
                "Somente pacientes podem solicitar agendamentos por este endpoint."
            )

        if not user.clinic:
            raise serializers.ValidationError(
                "Usuário não está vinculado a uma clínica."
            )

        if not hasattr(user, "patient_profile"):
            raise serializers.ValidationError(
                "Usuário não possui perfil de paciente cadastrado."
            )

        # garante que o médico existe e é da mesma clínica
        try:
            doctor = CustomUser.objects.get(
                id=attrs["doctor_id"],
                role=CustomUser.Role.DOCTOR,
                clinic=user.clinic,
            )
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(
                {"doctor_id": "Médico não encontrado nesta clínica."}
            )

        attrs["clinic"] = user.clinic
        attrs["patient"] = user.patient_profile
        attrs["doctor"] = doctor

        # valida intervalo básico
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "Horário de fim deve ser maior que o de início."}
            )

        return attrs

    def create(self, validated_data):
        clinic = validated_data["clinic"]
        patient = validated_data["patient"]
        doctor = validated_data["doctor"]
        start_time = validated_data["start_time"]
        end_time = validated_data["end_time"]

        appointment = Appointment.objects.create(
            clinic=clinic,
            doctor=doctor,
            patient=patient,
            start_time=start_time,
            end_time=end_time,
            status=Appointment.Status.REQUESTED,
            clinical_notes="",  # nada aqui vindo do paciente
        )
        return appointment


class StaffUserSerializer(serializers.ModelSerializer):
    """
    Serializer para gestão de staff da clínica (DOCTOR, SECRETARY, CLINIC_OWNER).

    - SAAS_ADMIN pode criar staff para QUALQUER clínica (via campo clinic_id).
    - CLINIC_OWNER só cria para a própria clínica.
    - Se role = DOCTOR, pode informar crm + specialty (DoctorProfile).
    """

    # password write-only
    password = serializers.CharField(
        write_only=True, required=False, allow_null=True, allow_blank=True, min_length=8
    )

    # Campo auxiliar para SAAS_ADMIN poder setar a clínica
    clinic_id = serializers.UUIDField(write_only=True, required=False)

    # Campos extras para médicos
    crm = serializers.CharField(write_only=True, required=False, allow_blank=True)
    specialty = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "role",
            "clinic",
            "clinic_id",
            "gender",
            "password",
            "crm",
            "specialty",
            "is_active",
        ]
        read_only_fields = ["id", "clinic"]
        extra_kwargs = {
            "username": {"required": False, "allow_blank": True},
            "gender": {"required": False, "allow_null": True},
        }

    def validate_role(self, value):
        """
        Não permitimos criação de SAAS_ADMIN ou PATIENT por aqui.
        """
        if value in (CustomUser.Role.SAAS_ADMIN, CustomUser.Role.PATIENT):
            raise serializers.ValidationError(
                "Este endpoint não permite criar usuários SAAS_ADMIN ou PATIENT."
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        role = attrs.get("role", None)
        clinic_id = attrs.get("clinic_id", None)

        # Username padrão = email, se não informado
        if not attrs.get("username") and attrs.get("email"):
            attrs["username"] = attrs["email"]

        if user is None or not user.is_authenticated:
            raise serializers.ValidationError("Usuário não autenticado.")

        # SAAS_ADMIN pode escolher clinic_id explicitamente
        if user.role == CustomUser.Role.SAAS_ADMIN or user.is_superuser:
            if clinic_id is None:
                raise serializers.ValidationError(
                    {"clinic_id": "Obrigatório para SAAS_ADMIN ao criar staff."}
                )
            try:
                clinic = Clinic.objects.get(id=clinic_id, is_active=True)
            except Clinic.DoesNotExist:
                raise serializers.ValidationError(
                    {"clinic_id": "Clínica não encontrada ou inativa."}
                )
            attrs["clinic"] = clinic

        # CLINIC_OWNER só mexe na própria clínica
        elif user.role == CustomUser.Role.CLINIC_OWNER:
            if not user.clinic:
                raise serializers.ValidationError(
                    "Usuário não está vinculado a uma clínica."
                )
            attrs["clinic"] = user.clinic

        else:
            # SECRETARY, DOCTOR, PATIENT não podem criar staff
            raise serializers.ValidationError(
                "Somente SAAS_ADMIN ou CLINIC_OWNER podem gerenciar staff."
            )

        # Regras DOCTOR x SECRETARY
        if role == CustomUser.Role.DOCTOR:
            # Para médicos, se vier crm/specialty vazios, a gente só aceita se depois forem preenchidos via update.
            # (se quiser, pode exigir obrigatoriedade aqui)
            pass
        else:
            # Se não é médico, não deveria mandar crm/specialty
            if attrs.get("crm") or attrs.get("specialty"):
                raise serializers.ValidationError(
                    "Campos crm/specialty só são permitidos para usuários DOCTOR."
                )

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        clinic = validated_data.pop("clinic")
        crm = validated_data.pop("crm", None)
        specialty = validated_data.pop("specialty", None)
        # remove clinic_id se ainda estiver
        validated_data.pop("clinic_id", None)

        user = CustomUser.objects.create(
            clinic=clinic,
            **validated_data,
        )
        if password:
            user.set_password(password)
            user.save()

        # Se for médico, cria DoctorProfile
        if user.role == CustomUser.Role.DOCTOR:
            DoctorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "crm": crm or "",
                    "specialty": specialty or "",
                },
            )

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        crm = validated_data.pop("crm", None)
        specialty = validated_data.pop("specialty", None)

        # Não permitimos atualizar clinic pelo serializer
        validated_data.pop("clinic", None)
        validated_data.pop("clinic_id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        # Se for médico, atualiza DoctorProfile
        if instance.role == CustomUser.Role.DOCTOR:
            DoctorProfile.objects.update_or_create(
                user=instance,
                defaults={
                    "crm": crm or "",
                    "specialty": specialty or "",
                },
            )

        return instance
