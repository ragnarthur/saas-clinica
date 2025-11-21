# core/tests.py
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Clinic,
    LegalDocument,
    CustomUser,
    PatientProfile,
    Appointment,
    UserConsent,
)


class PatientRegistrationAndAuthTests(APITestCase):
    """
    Testes do fluxo público de cadastro de paciente + login JWT.
    Não usamos admin em nenhum momento.
    """

    def setUp(self):
        # Cria uma clínica ativa
        self.clinic = Clinic.objects.create(
            name="Clínica Vida Plena",
            schema_name="clinica_vida_plena",
            is_active=True,
        )

        # Cria documentos legais ativos (Termos + Privacidade)
        self.terms = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.TERMS,
            content="Termos de Uso v1.0",
            is_active=True,
        )
        self.privacy = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.PRIVACY,
            content="Política de Privacidade v1.0",
            is_active=True,
        )

        self.register_url = reverse("patient_register")
        self.login_url = reverse("token_obtain_pair")

    def test_patient_registration_creates_user_patient_and_consents(self):
        """
        Deve:
        - Registrar paciente via /api/auth/register/
        - Criar User (role PATIENT) vinculado à clínica
        - Criar PatientProfile
        - Criar UserConsent para Termos e Privacidade ativos
        - Permitir login JWT com email+senha
        """
        payload = {
            "clinic_schema": self.clinic.schema_name,
            "email": "paciente@example.com",
            "password": "SenhaForte123",
            "full_name": "Paciente de Teste",
            "cpf": "123.456.789-00",
            "phone": "(34) 99999-0000",
            "accepted_terms_version": "1.0",
            "accepted_privacy_version": "1.0",
        }

        # 1) Cadastro
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        email = payload["email"]

        # Verifica se User foi criado
        user = CustomUser.objects.filter(email=email).first()
        self.assertIsNotNone(user, "Usuário não foi criado.")
        self.assertEqual(user.role, CustomUser.Role.PATIENT)
        self.assertEqual(user.clinic, self.clinic)

        # Verifica se PatientProfile foi criado
        patient = PatientProfile.objects.filter(cpf=payload["cpf"]).first()
        self.assertIsNotNone(patient, "PatientProfile não foi criado.")
        self.assertEqual(patient.clinic, self.clinic)

        # Verifica consents
        consents = UserConsent.objects.filter(user=user)
        self.assertEqual(consents.count(), 2, "Devia ter 2 registros de consentimento.")

        # 2) Login JWT
        login_payload = {
            "username": email,  # SimpleJWT usa username por padrão
            "password": payload["password"],
        }
        login_response = self.client.post(
            self.login_url, login_payload, format="json"
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)
        self.assertIn("refresh", login_response.data)


class AppointmentCreationTests(APITestCase):
    """
    Testes de criação de agendamento via API,
    usando SECRETARY autenticado por JWT.
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(
            name="Clínica Exemplo",
            schema_name="clinica_exemplo",
            is_active=True,
        )

        # Sem documentos ativos aqui -> HasActiveConsent libera o acesso
        # (não há nada para consentir ainda)

        # Cria um médico
        self.doctor = CustomUser.objects.create_user(
            username="doctor1",
            email="doctor1@example.com",
            password="SenhaDoc123",
            clinic=self.clinic,
            role=CustomUser.Role.DOCTOR,
        )

        # Cria uma secretária (vai ser a usuária autenticada)
        self.secretary = CustomUser.objects.create_user(
            username="secretary1",
            email="secretary1@example.com",
            password="SenhaSec123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        # Cria um paciente (sem user vinculado mesmo, é opcional)
        self.patient = PatientProfile.objects.create(
            clinic=self.clinic,
            full_name="Paciente Agendável",
            cpf="987.654.321-00",
            phone="(34) 98888-0000",
        )

        self.login_url = reverse("token_obtain_pair")
        self.appointments_url = reverse("appointment-list")

        # Faz login como secretária e guarda o token
        login_payload = {
            "username": self.secretary.username,
            "password": "SenhaSec123",
        }
        login_response = self.client.post(
            self.login_url, login_payload, format="json"
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.access_token = login_response.data["access"]

    def test_secretary_can_create_appointment_for_clinic(self):
        """
        Secretária autenticada deve conseguir criar um Appointment para
        pacientes e médicos da mesma clínica.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(minutes=30)

        payload = {
            "doctor": str(self.doctor.id),
            "patient": str(self.patient.id),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "status": "REQUESTED",
            "clinical_notes": "Consulta de rotina.",
        }

        response = self.client.post(self.appointments_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        appointment = Appointment.objects.first()
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.clinic, self.clinic)
        self.assertEqual(appointment.doctor, self.doctor)
        self.assertEqual(appointment.patient, self.patient)


class ClinicIsolationTests(APITestCase):
    """
    Garante que cada clínica só enxerga seus próprios pacientes
    na rota /api/patients/.
    """

    def setUp(self):
        # Cria duas clínicas distintas
        self.clinic_a = Clinic.objects.create(
            name="Clínica A",
            schema_name="clinica_a",
            is_active=True,
        )
        self.clinic_b = Clinic.objects.create(
            name="Clínica B",
            schema_name="clinica_b",
            is_active=True,
        )

        # Nenhum documento ativo -> HasActiveConsent libera geral
        # (isso aqui é só ambiente de teste)

        # Secretárias para cada clínica
        self.secretary_a = CustomUser.objects.create_user(
            username="sec_a",
            email="sec_a@example.com",
            password="SenhaA123",
            clinic=self.clinic_a,
            role=CustomUser.Role.SECRETARY,
        )
        self.secretary_b = CustomUser.objects.create_user(
            username="sec_b",
            email="sec_b@example.com",
            password="SenhaB123",
            clinic=self.clinic_b,
            role=CustomUser.Role.SECRETARY,
        )

        # Pacientes em cada clínica
        self.patient_a = PatientProfile.objects.create(
            clinic=self.clinic_a,
            full_name="Paciente A",
            cpf="111.111.111-11",
            phone="(34) 90000-0001",
        )
        self.patient_b = PatientProfile.objects.create(
            clinic=self.clinic_b,
            full_name="Paciente B",
            cpf="222.222.222-22",
            phone="(34) 90000-0002",
        )

        self.login_url = reverse("token_obtain_pair")
        self.patients_url = reverse("patient-list")

    def _get_token_for_user(self, username, password):
        resp = self.client.post(
            self.login_url, {"username": username, "password": password}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data["access"]

    def test_secretary_sees_only_patients_from_own_clinic(self):
        # Secretária A
        token_a = self._get_token_for_user("sec_a", "SenhaA123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        resp_a = self.client.get(self.patients_url, format="json")
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_a.data), 1)
        self.assertEqual(resp_a.data[0]["full_name"], "Paciente A")

        # Secretária B
        token_b = self._get_token_for_user("sec_b", "SenhaB123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_b}")
        resp_b = self.client.get(self.patients_url, format="json")
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_b.data), 1)
        self.assertEqual(resp_b.data[0]["full_name"], "Paciente B")


class ConsentPermissionTests(APITestCase):
    """
    Valida a permissão HasActiveConsent:

    - Usuário com consentimento para docs ativos acessa normally
    - Quando surge nova versão de Termos, acesso deve ser bloqueado (403)
      até ele aceitar a nova versão.
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(
            name="Clínica LGPD",
            schema_name="clinica_lgpd",
            is_active=True,
        )

        # v1 dos documentos
        self.terms_v1 = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.TERMS,
            content="Termos v1",
            is_active=True,
        )
        self.privacy_v1 = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.PRIVACY,
            content="Privacidade v1",
            is_active=True,
        )

        # Cria secretária que já aceitou v1
        self.secretary = CustomUser.objects.create_user(
            username="sec_lgpd",
            email="sec_lgpd@example.com",
            password="SenhaLGPD123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        UserConsent.objects.create(user=self.secretary, document=self.terms_v1)
        UserConsent.objects.create(user=self.secretary, document=self.privacy_v1)

        self.login_url = reverse("token_obtain_pair")
        self.patients_url = reverse("patient-list")

        # Login inicial
        resp = self.client.post(
            self.login_url,
            {"username": "sec_lgpd", "password": "SenhaLGPD123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.access_token = resp.data["access"]

    def test_access_allowed_with_current_consents(self):
        """
        Com Termos/Privacidade v1 ativos e aceitos, acesso deve ser permitido.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")
        resp = self.client.get(self.patients_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_access_blocked_when_new_terms_version_appears(self):
        """
        Quando surge nova versão de Termos (v2) e ela vira ativa,
        o usuário que só aceitou v1 deve ser bloqueado (403).
        """
        # Cria nova versão de Termos (v2) e desativa a v1
        self.terms_v1.is_active = False
        self.terms_v1.save()

        self.terms_v2 = LegalDocument.objects.create(
            version="2.0",
            doc_type=LegalDocument.DocType.TERMS,
            content="Termos v2 - atualizados",
            is_active=True,
        )
        # Privacidade v1 continua ativa -> agora temos 2 docs ativos:
        # - Terms v2 (não aceito)
        # - Privacy v1 (já aceito)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")
        resp = self.client.get(self.patients_url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Consentimento atualizado obrigatório", str(resp.data))


class ConsentEndpointsTests(APITestCase):
    """
    Testa os endpoints de consentimento:

    - /api/auth/consent/active/
    - /api/auth/consent/accept/
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(
            name="Clínica Consent API",
            schema_name="clinica_consent_api",
            is_active=True,
        )

        # Documentos ativos
        self.terms = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.TERMS,
            content="Termos v1 - texto...",
            is_active=True,
        )
        self.privacy = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.PRIVACY,
            content="Privacidade v1 - texto...",
            is_active=True,
        )

        # Secretária SEM consentimentos
        self.user = CustomUser.objects.create_user(
            username="sec_consent",
            email="sec_consent@example.com",
            password="SenhaConsent123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        self.login_url = reverse("token_obtain_pair")
        self.consent_active_url = reverse("consent_active")
        self.consent_accept_url = reverse("consent_accept")
        self.patients_url = reverse("patient-list")

        # Login
        resp = self.client.post(
            self.login_url,
            {"username": "sec_consent", "password": "SenhaConsent123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.access_token = resp.data["access"]

    def test_consent_flow_enables_access(self):
        """
        1) Sem consent -> rota protegida dá 403
        2) GET /auth/consent/active/ lista docs
        3) POST /auth/consent/accept/ registra consentimentos
        4) Depois disso, rota protegida passa a responder 200
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        # 1) Sem consent -> bloqueia
        resp_blocked = self.client.get(self.patients_url, format="json")
        self.assertEqual(resp_blocked.status_code, status.HTTP_403_FORBIDDEN)

        # 2) Lista docs ativos
        resp_docs = self.client.get(self.consent_active_url, format="json")
        self.assertEqual(resp_docs.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_docs.data), 2)

        # 3) Aceita docs
        resp_accept = self.client.post(self.consent_accept_url, format="json")
        self.assertEqual(resp_accept.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserConsent.objects.filter(user=self.user).count(), 2)

        # 4) Agora deve conseguir acessar rota protegida
        resp_allowed = self.client.get(self.patients_url, format="json")
        self.assertEqual(resp_allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_allowed.data), 0)


class StaffUserAPITests(APITestCase):
    """
    Testa o endpoint /api/staff/ para gestão de usuários da clínica.

    - CLINIC_OWNER cria médico (DOCTOR) com DoctorProfile
    - SAAS_ADMIN consegue criar staff para qualquer clínica
    """

    def setUp(self):
        # Clínica
        self.clinic = Clinic.objects.create(
            name="Clínica Staff",
            schema_name="clinica_staff",
            is_active=True,
        )

        # Docs legais ativos
        self.terms = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.TERMS,
            content="Termos Staff",
            is_active=True,
        )
        self.privacy = LegalDocument.objects.create(
            version="1.0",
            doc_type=LegalDocument.DocType.PRIVACY,
            content="Privacidade Staff",
            is_active=True,
        )

        # Dono da clínica (CLINIC_OWNER)
        self.owner = CustomUser.objects.create_user(
            username="owner_staff",
            email="owner_staff@example.com",
            password="SenhaOwner123",
            clinic=self.clinic,
            role=CustomUser.Role.CLINIC_OWNER,
        )
        UserConsent.objects.create(user=self.owner, document=self.terms)
        UserConsent.objects.create(user=self.owner, document=self.privacy)

        # SAAS_ADMIN
        self.saas_admin = CustomUser.objects.create_superuser(
            username="saas_admin_staff",
            email="saas_admin_staff@example.com",
            password="SenhaAdmin123",
        )
        self.saas_admin.role = CustomUser.Role.SAAS_ADMIN
        self.saas_admin.save()

        self.login_url = reverse("token_obtain_pair")
        self.staff_url = reverse("staff-list")

    def _get_token(self, username, password):
        resp = self.client.post(
            self.login_url, {"username": username, "password": password}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data["access"]

    def test_clinic_owner_can_create_doctor_with_profile(self):
        """
        CLINIC_OWNER autenticado com consentimento deve conseguir criar
        um DOCTOR para a própria clínica, incluindo crm e specialty.
        """
        token = self._get_token("owner_staff", "SenhaOwner123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        payload = {
            "email": "dr.novo@example.com",
            "password": "SenhaDocNova123",
            "first_name": "Novo",
            "last_name": "Médico",
            "role": "DOCTOR",
            "crm": "CRM-99999",
            "specialty": "Dermatologia",
        }

        resp = self.client.post(self.staff_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        user = CustomUser.objects.filter(email="dr.novo@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, CustomUser.Role.DOCTOR)
        self.assertEqual(user.clinic, self.clinic)
        self.assertTrue(user.check_password("SenhaDocNova123"))

        # Verifica DoctorProfile
        self.assertTrue(hasattr(user, "doctor_profile"))
        self.assertEqual(user.doctor_profile.crm, "CRM-99999")
        self.assertEqual(user.doctor_profile.specialty, "Dermatologia")
