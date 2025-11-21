# core/management/commands/seed_demo_clinics.py
from datetime import timedelta
import itertools

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Clinic,
    CustomUser,
    Appointment,
    DoctorProfile,
    PatientProfile,
    LegalDocument,
    UserConsent,
)


class Command(BaseCommand):
    """
    Popula o banco com dados de teste para o SaaS de clínicas.

    - 2 usuários SAAS_ADMIN (super admins do sistema)
    - 3 clínicas
      - 2 CLINIC_OWNER por clínica (donos/admins)
      - 3 SECRETARY por clínica (cada uma vinculada a um médico)
      - 3 DOCTOR por clínica (com DoctorProfile)
      - 20 pacientes por médico (CustomUser + PatientProfile) com nomes fictícios
      - ~10 agendamentos por médico
    - Cria documentos legais DEMO e aplica UserConsent para todos os usuários
      (para ambiente de desenvolvimento, eliminando o 403 de consentimento LGPD).

    Uso:
        python manage.py seed_demo_clinics
    """

    help = "Cria dados fake pra testar o SaaS de clínicas."

    def handle(self, *args, **options):
        # usado para gerar CPFs/nomes únicos de pacientes
        self.patient_counter = 1

        self.stdout.write(self.style.WARNING("Criando usuários SAAS_ADMIN..."))
        self._create_saas_admins()

        self.stdout.write(self.style.WARNING("Criando clínicas e times..."))
        clinics_with_prefix = self._create_clinics()

        User = get_user_model()

        for idx, (clinic, prefix) in enumerate(clinics_with_prefix, start=1):
            self.stdout.write(f"Clínica: {clinic.name} ({clinic.schema_name})")
            self._create_clinic_team(User, clinic, prefix, idx)

        self.stdout.write(self.style.WARNING("Criando agendamentos de teste..."))
        self._create_appointments()

        self.stdout.write(
            self.style.WARNING("Garantindo consentimento LGPD fake para DEV...")
        )
        self._ensure_demo_legal_docs_and_consents()

        self.stdout.write(self.style.SUCCESS("Seed concluído com sucesso!"))

    # ------------- helpers principais -------------

    def _create_saas_admins(self):
        """
        Cria 2 admins gerais do SaaS (role=SAAS_ADMIN).
        Eles podem ser usados pra acessar o painel de super admin.
        """
        User = get_user_model()
        saas_admins_data = [
            ("saas_admin1", "saas_admin1@example.com"),
            ("saas_admin2", "saas_admin2@example.com"),
        ]

        for username, email in saas_admins_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "role": CustomUser.Role.SAAS_ADMIN,
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            if created:
                user.set_password("teste123")  # senha padrão para dev
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [+] Criado SAAS_ADMIN {username} / senha: teste123"
                    )
                )
            else:
                self.stdout.write(f"  [=] SAAS_ADMIN {username} já existia")

    def _create_clinics(self):
        """
        Cria 3 clínicas de exemplo.

        Usa `schema_name` como identificador único (tenant).
        O `prefix` é usado apenas para gerar usernames.
        """
        clinics_config = [
            {
                "name": "Clínica Vida Plena",
                "schema_name": "vida_plena",
            },
            {
                "name": "Clínica Bem Estar",
                "schema_name": "bem_estar",
            },
            {
                "name": "Clínica Horizonte Saúde",
                "schema_name": "horizonte_saude",
            },
        ]

        clinics_with_prefix = []

        for cfg in clinics_config:
            clinic, created = Clinic.objects.get_or_create(
                schema_name=cfg["schema_name"],
                defaults={
                    "name": cfg["name"],
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  [+] Clínica criada: {clinic.name}")
                )
            else:
                self.stdout.write(f"  [=] Clínica já existia: {clinic.name}")

            prefix = cfg["schema_name"]
            clinics_with_prefix.append((clinic, prefix))

        return clinics_with_prefix

    def _create_clinic_team(
        self,
        User,
        clinic: Clinic,
        prefix: str,
        clinic_index: int,
    ):
        """
        Para cada clínica:
        - 2 CLINIC_OWNER (donos/admins da clínica)
        - 3 DOCTOR (+ DoctorProfile)
        - 3 SECRETARY (cada uma vinculada a um médico específico)
        - 20 pacientes por médico (CustomUser + PatientProfile) com nomes fictícios
        """

        # -------- helper para título Dr/Dra --------
        def build_doctor_display_name(first_name: str, last_name: str, gender: str) -> str:
            """
            gender: 'M' ou 'F'
            Retorna, por ex.: 'Dr. João Silva' ou 'Dra. Maria Souza'
            """
            prefix_title = "Dra." if gender == "F" else "Dr."
            full = f"{first_name} {last_name}".strip()
            return f"{prefix_title} {full}"

        # -------- Donos/Admins da clínica (CLINIC_OWNER) --------
        for i in range(1, 3):  # 2 owners
            username = f"{prefix}_owner{i}"
            email = f"{username}@example.com"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "clinic": clinic,
                    "role": CustomUser.Role.CLINIC_OWNER,
                },
            )
            if created:
                user.set_password("teste123")
                user.first_name = f"Owner {i}"
                user.last_name = clinic.name
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"    [+] CLINIC_OWNER: {username} / senha: teste123"
                    )
                )
            else:
                self.stdout.write(f"    [=] CLINIC_OWNER já existia: {username}")

        # -------- Médicos + DoctorProfile --------
        # nomes fictícios com gênero controlado
        doctor_seed = [
            {"first_name": "Carlos", "last_name": "Almeida", "gender": "M"},
            {"first_name": "Fernanda", "last_name": "Souza", "gender": "F"},
            {"first_name": "Rafael", "last_name": "Pereira", "gender": "M"},
        ]

        doctors = []

        for i, seed in enumerate(doctor_seed, start=1):
            username = f"{prefix}_dr{i}"
            email = f"{username}@example.com"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "clinic": clinic,
                    "role": CustomUser.Role.DOCTOR,
                },
            )

            # mesmo se já existir, garantimos nomes e clínica/role certos
            user.clinic = clinic
            user.role = CustomUser.Role.DOCTOR
            user.first_name = seed["first_name"]
            user.last_name = seed["last_name"]
            if created:
                user.set_password("teste123")
            user.save()

            display_name = build_doctor_display_name(
                seed["first_name"], seed["last_name"], seed["gender"]
            )

            # cria/atualiza o DoctorProfile
            DoctorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "crm": f"CRM{clinic_index:02d}{i:03d}",
                    "specialty": "Clínico Geral",
                    # se você tiver um campo gender no DoctorProfile, descomente:
                    # "gender": seed["gender"],
                },
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"    [+] DOCTOR: {username} / senha: teste123 ({display_name})"
                )
            )

            doctors.append(user)

        # -------- Secretárias (cada uma amarrada a um médico) --------
        secretary_seed = [
            {"first_name": "Juliana", "last_name": "Ramos"},     # atende dr1
            {"first_name": "Bruno", "last_name": "Lima"},        # atende dr2
            {"first_name": "Patrícia", "last_name": "Oliveira"}, # atende dr3
        ]

        secretaries = []

        for i, seed in enumerate(secretary_seed, start=1):
            username = f"{prefix}_secretaria{i}"
            email = f"{username}@example.com"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "clinic": clinic,
                    "role": CustomUser.Role.SECRETARY,
                },
            )

            # médico correspondente (secretária1->dr1, etc.)
            doctor = doctors[(i - 1) % len(doctors)]

            # mesmo se já existir, garantimos tudo certinho
            user.clinic = clinic
            user.role = CustomUser.Role.SECRETARY
            user.first_name = seed["first_name"]
            user.last_name = seed["last_name"]
            # aqui assumo que CustomUser tem o campo doctor_for_secretary
            user.doctor_for_secretary = doctor

            if created:
                user.set_password("teste123")

            user.save()

            secretaries.append(user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"    [+] SECRETARY: {username} / senha: teste123 "
                    f"(atua com {doctor.username})"
                )
            )

        # -------- Pacientes (20 por médico) --------
        for doctor in doctors:
            self._create_patients_for_doctor(User, clinic, doctor)

    def _create_patients_for_doctor(self, User, clinic: Clinic, doctor: CustomUser):
        """
        Cria 20 pacientes fictícios para um médico específico.

        Usa listas de nomes brasileiros para ficar mais real.
        """

        first_names = [
            "Ana",
            "Bruno",
            "Carla",
            "Diego",
            "Eduarda",
            "Felipe",
            "Gabriela",
            "Henrique",
            "Isabela",
            "João",
            "Karina",
            "Lucas",
            "Mariana",
            "Nicolas",
            "Otávio",
            "Patrícia",
            "Rafael",
            "Sara",
            "Thiago",
            "Vitória",
        ]

        last_names = [
            "Silva",
            "Souza",
            "Oliveira",
            "Santos",
            "Pereira",
            "Costa",
            "Rodrigues",
            "Almeida",
            "Gomes",
            "Barbosa",
        ]

        created_count = 0

        for i in range(1, 21):  # 20 pacientes por médico
            # escolhe nome/sobrenome pseudo-aleatoriamente baseado no contador global
            idx = (self.patient_counter - 1) % len(first_names)
            jdx = (self.patient_counter - 1) % len(last_names)
            first_name = first_names[idx]
            last_name = last_names[jdx]
            full_name = f"{first_name} {last_name}"

            username = f"{doctor.username}_pac{i}"
            email = f"{username}@example.com"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "clinic": clinic,
                    "role": CustomUser.Role.PATIENT,
                },
            )
            if created:
                user.set_password("teste123")
                user.first_name = first_name
                user.last_name = last_name
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"        [+] PATIENT user criado: {username} / senha: teste123"
                    )
                )

            # cpf único simples só pra seed (não é CPF real)
            cpf = f"{self.patient_counter:011d}"
            phone = f"(34) 9{self.patient_counter:08d}"[:20]

            patient_profile, pp_created = PatientProfile.objects.get_or_create(
                user=user,
                defaults={
                    "clinic": clinic,
                    "full_name": full_name,
                    "cpf": cpf,
                    "phone": phone,
                },
            )
            if pp_created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"        [+] PatientProfile criado para {username} (CPF {cpf}, {full_name})"
                    )
                )

            self.patient_counter += 1
            created_count += 1

        self.stdout.write(
            f"    [=] {created_count} pacientes associados ao médico {doctor.username}."
        )

    def _create_appointments(self):
        """
        Cria alguns agendamentos distribuídos entre médicos/pacientes.

        - usa timezone.now() como referência
        - usa start_time / end_time
        - patient = PatientProfile
        """
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # alterna entre alguns status válidos
        status_cycle = itertools.cycle(
            [
                Appointment.Status.REQUESTED,
                Appointment.Status.CONFIRMED,
                Appointment.Status.CANCELED_BY_PATIENT,
                Appointment.Status.CANCELED_BY_CLINIC,
            ]
        )

        User = get_user_model()
        doctors = User.objects.filter(
            role=CustomUser.Role.DOCTOR
        ).select_related("clinic")

        if not doctors.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum médico encontrado, pulando criação de appointments."
                )
            )
            return

        total_created = 0

        for doctor in doctors:
            # pega 20 pacientes da mesma clínica
            patients = PatientProfile.objects.filter(
                clinic=doctor.clinic
            ).order_by("id")[:20]
            if not patients:
                continue

            for slot, patient in enumerate(patients[:10]):  # 10 agendamentos por médico
                status = next(status_cycle)

                start_time = now + timedelta(
                    days=slot // 3,
                    hours=slot % 3 + 9,
                )
                end_time = start_time + timedelta(minutes=30)

                appt, created = Appointment.objects.get_or_create(
                    clinic=doctor.clinic,
                    doctor=doctor,
                    patient=patient,
                    start_time=start_time,
                    defaults={
                        "end_time": end_time,
                        "status": status,
                        "clinical_notes": "",
                    },
                )
                if created:
                    total_created += 1

        self.stdout.write(
            self.style.SUCCESS(f"  [+] {total_created} agendamentos criados.")
        )

    # ------------- LGPD DEMO -------------

    def _ensure_demo_legal_docs_and_consents(self):
        """
        Ambiente de DEV:

        - garante que existam documentos legais ativos (Termos, Privacidade, Consentimento)
        - cria UserConsent para TODOS os usuários para TODOS esses documentos

        Isso faz user.has_active_consent == True e elimina o 403 nas rotas protegidas.
        NÃO usar essa lógica em produção.
        """
        docs = self._ensure_demo_legal_docs()
        if not docs:
            self.stdout.write(
                "Nenhum LegalDocument ativo encontrado; nada para consentir."
            )
            return

        users = CustomUser.objects.all()
        created_count = 0

        for user in users:
            for doc in docs:
                _, created = UserConsent.objects.get_or_create(
                    user=user,
                    document=doc,
                )
                if created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  [+] {created_count} registros de UserConsent criados para DEV."
            )
        )

    def _ensure_demo_legal_docs(self):
        """
        Cria (se não existirem) 3 documentos legais demo e marca todos como ativos.
        """
        docs_config = [
            (
                "1.0",
                LegalDocument.DocType.TERMS,
                "Termos de Uso DEMO - não usar em produção.",
            ),
            (
                "1.0",
                LegalDocument.DocType.PRIVACY,
                "Política de Privacidade DEMO - não usar em produção.",
            ),
            (
                "1.0",
                LegalDocument.DocType.CONSENT,
                "Termo de Consentimento Médico DEMO - não usar em produção.",
            ),
        ]

        docs = []

        for version, doc_type, content in docs_config:
            doc, created = LegalDocument.objects.get_or_create(
                version=version,
                doc_type=doc_type,
                defaults={
                    "content": content,
                    "is_active": True,
                },
            )
            # garante que está ativo
            if not doc.is_active:
                doc.is_active = True
                doc.save(update_fields=["is_active"])

            docs.append(doc)

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  [+] LegalDocument criado: {doc}")
                )
            else:
                self.stdout.write(f"  [=] LegalDocument já existia: {doc}")

        return docs
