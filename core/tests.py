# core/tests.py
from datetime import timedelta
import hashlib

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from fernet_fields import EncryptedTextField

from .models import (
    Appointment,
    Clinic,
    CustomUser,
    LegalDocument,
    PatientProfile,
    UserConsent,
    AuditLog,
)


class PatientRegistrationAndAuthTests(APITestCase):
    """
    Testes do fluxo público de cadastro de paciente + login JWT.

    Fluxo coberto:
    - POST /api/patients/register/
    - POST /api/auth/login/ (JWT)
    """

    def setUp(self):
        # Clínica ativa
        self.clinic = Clinic.objects.create(
            name="Clínica Vida Plena",
            schema_name="clinica_vida_plena",
            is_active=True,
        )

        # Documentos legais ativos
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

        self.register_url = reverse("patient-register")
        self.login_url = reverse("token_obtain_pair")

    def test_patient_registration_creates_user_patient_and_consents(self):
        """
        Deve:
        - Registrar paciente via /api/patients/register/
        - Criar User (role PATIENT) vinculado à clínica
        - Criar PatientProfile
        - Criar UserConsent para docs ativos
        - Permitir login JWT com email+senha
        """
        payload = {
            "clinic_schema_name": self.clinic.schema_name,
            "full_name": "Paciente de Teste",
            "cpf": "123.456.789-00",
            "phone": "(34) 99999-0000",
            "email": "paciente@example.com",
            "password": "SenhaForte123",
            "password_confirm": "SenhaForte123",
            "agree_terms": True,
            "agree_privacy": True,
            "agree_consent": True,
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

        # Verifica se PatientProfile foi criado usando o HASH do CPF
        normalized = "".join(filter(str.isdigit, payload["cpf"]))
        expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        patient = PatientProfile.objects.filter(cpf_hash=expected_hash).first()

        self.assertIsNotNone(patient, "PatientProfile não foi criado.")
        self.assertEqual(patient.clinic, self.clinic)
        # ORM devolve o CPF descriptografado corretamente
        self.assertEqual(patient.cpf, payload["cpf"])

        # Verifica consents (2 docs ativos: Termos + Privacidade)
        consents = UserConsent.objects.filter(user=user)
        self.assertEqual(
            consents.count(), 2, "Devia ter 2 registros de consentimento."
        )

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

        # Cria um médico
        self.doctor = CustomUser.objects.create_user(
            username="doctor1",
            email="doctor1@example.com",
            password="SenhaDoc123",
            clinic=self.clinic,
            role=CustomUser.Role.DOCTOR,
        )

        # Cria uma secretária (usuária autenticada)
        self.secretary = CustomUser.objects.create_user(
            username="secretary1",
            email="secretary1@example.com",
            password="SenhaSec123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        # Cria um paciente (sem user vinculado)
        self.patient = PatientProfile.objects.create(
            clinic=self.clinic,
            full_name="Paciente Agendável",
            cpf="987.654.321-00",
            phone="(34) 98888-0000",
        )

        self.login_url = reverse("token_obtain_pair")
        self.appointments_url = reverse("appointment-list")

        # Login como secretária
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
        Secretária autenticada deve conseguir criar um Appointment
        para pacientes e médicos da mesma clínica.
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

class MeViewTests(APITestCase):
    """
    Testa o endpoint /api/auth/me/:

    - SECRETARY com doctor_for_secretary configurado recebe o médico certo;
    - SECRETARY sem vínculo cai no fallback (primeiro médico da clínica);
    - DOCTOR recebe dados próprios + clínica, sem doctor_for_secretary;
    - CLINIC_OWNER idem;
    - Usuário sem clínica volta com clinic = None e doctor_for_secretary = None.
    """

    def setUp(self):
        # Clínica principal para os testes
        self.clinic = Clinic.objects.create(
            name="Clínica AuthMe",
            schema_name="clinica_authme",
            is_active=True,
        )

        self.login_url = reverse("token_obtain_pair")
        self.me_url = reverse("auth_me")

        # Dois médicos na mesma clínica, com nomes pensados pra testar a ordenação
        self.doctor_ana = CustomUser.objects.create_user(
            username="dr_ana",
            email="dr_ana@example.com",
            password="SenhaDocAna123",
            clinic=self.clinic,
            role=CustomUser.Role.DOCTOR,
            first_name="Ana",
            last_name="Silva",
            gender=CustomUser.Gender.FEMALE,
        )
        self.doctor_carlos = CustomUser.objects.create_user(
            username="dr_carlos",
            email="dr_carlos@example.com",
            password="SenhaDocCarlos123",
            clinic=self.clinic,
            role=CustomUser.Role.DOCTOR,
            first_name="Carlos",
            last_name="Almeida",
            gender=CustomUser.Gender.MALE,
        )

        # Secretária com vínculo explícito ao dr_carlos
        self.secretary_linked = CustomUser.objects.create_user(
            username="sec_vinculada",
            email="sec_vinculada@example.com",
            password="SenhaSecVinc123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
            doctor_for_secretary=self.doctor_carlos,
        )

        # Secretária sem vínculo -> deve cair no fallback (primeiro médico por nome: Ana)
        self.secretary_no_link = CustomUser.objects.create_user(
            username="sec_sem_vinculo",
            email="sec_sem_vinculo@example.com",
            password="SenhaSecSemV123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        # Dono da clínica
        self.owner = CustomUser.objects.create_user(
            username="owner_authme",
            email="owner_authme@example.com",
            password="SenhaOwnerAuth123",
            clinic=self.clinic,
            role=CustomUser.Role.CLINIC_OWNER,
            first_name="Owner",
            last_name="AuthMe",
        )

        # Usuário sem clínica (pra testar clinic = null)
        self.user_no_clinic = CustomUser.objects.create_user(
            username="user_noclinic",
            email="user_noclinic@example.com",
            password="SenhaNoClinic123",
            clinic=None,
            role=CustomUser.Role.SECRETARY,
        )

    def _get_token(self, username: str, password: str) -> str:
        resp = self.client.post(
            self.login_url,
            {"username": username, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data["access"]

    def test_secretary_with_doctor_for_secretary_receives_linked_doctor(self):
        """
        SECRETARY com doctor_for_secretary configurado deve receber esse médico,
        com nome já formatado (Dr./Dra. + nome completo).
        """
        token = self._get_token("sec_vinculada", "SenhaSecVinc123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.me_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # clinic payload
        self.assertIsNotNone(resp.data["clinic"])
        self.assertEqual(resp.data["clinic"]["name"], self.clinic.name)

        # doctor_for_secretary payload
        dfs = resp.data["doctor_for_secretary"]
        self.assertIsNotNone(dfs)
        self.assertEqual(dfs["id"], str(self.doctor_carlos.id))
        # get_display_name_with_title -> "Dr. Carlos Almeida"
        self.assertEqual(dfs["name"], "Dr. Carlos Almeida")

    def test_secretary_without_link_uses_first_doctor_of_clinic(self):
        """
        SECRETARY sem doctor_for_secretary deve usar o fallback:
        primeiro médico da clínica em ordem (first_name, last_name).
        No setUp, isso é a dra. Ana Silva.
        """
        token = self._get_token("sec_sem_vinculo", "SenhaSecSemV123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.me_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        dfs = resp.data["doctor_for_secretary"]
        self.assertIsNotNone(dfs)
        self.assertEqual(dfs["id"], str(self.doctor_ana.id))
        # get_display_name_with_title -> "Dra. Ana Silva"
        self.assertEqual(dfs["name"], "Dra. Ana Silva")

    def test_doctor_payload_has_clinic_and_no_doctor_for_secretary(self):
        """
        DOCTOR deve receber o payload da clínica normalmente,
        mas doctor_for_secretary precisa ser None.
        """
        token = self._get_token("dr_carlos", "SenhaDocCarlos123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.me_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.assertEqual(resp.data["role"], CustomUser.Role.DOCTOR)
        self.assertIsNotNone(resp.data["clinic"])
        self.assertIsNone(resp.data["doctor_for_secretary"])

    def test_clinic_owner_has_clinic_and_no_doctor_for_secretary(self):
        """
        CLINIC_OWNER também deve receber clinic preenchido
        e doctor_for_secretary = None.
        """
        token = self._get_token("owner_authme", "SenhaOwnerAuth123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.me_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.assertEqual(resp.data["role"], CustomUser.Role.CLINIC_OWNER)
        self.assertIsNotNone(resp.data["clinic"])
        self.assertIsNone(resp.data["doctor_for_secretary"])

    def test_user_without_clinic_returns_null_clinic_and_no_doctor(self):
        """
        Usuário sem clínica vinculada deve receber clinic = None
        e doctor_for_secretary = None (independente da role).
        """
        token = self._get_token("user_noclinic", "SenhaNoClinic123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.me_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.assertIsNone(resp.data["clinic"])
        self.assertIsNone(resp.data["doctor_for_secretary"])


class AppointmentIsolationTests(APITestCase):
    """
    Garante que o multi-tenant está funcionando para agendamentos (/api/appointments/):

    - Secretária vê apenas os agendamentos:
        - da sua clínica; e
        - do médico vinculado em doctor_for_secretary.

    - Médico vê apenas os próprios agendamentos, mesmo se houver outros médicos
      na mesma clínica ou em outras clínicas.
    """

    def setUp(self):
        # Duas clínicas (tenants) diferentes
        self.clinic_a = Clinic.objects.create(
            name="Clínica A",
            schema_name="clinica_a_isolamento",
            is_active=True,
        )
        self.clinic_b = Clinic.objects.create(
            name="Clínica B",
            schema_name="clinica_b_isolamento",
            is_active=True,
        )

        # Médicos em clínicas diferentes
        self.doctor_a = CustomUser.objects.create_user(
            username="doc_a",
            email="doc_a@example.com",
            password="SenhaDocA123",
            clinic=self.clinic_a,
            role=CustomUser.Role.DOCTOR,
        )
        self.doctor_b = CustomUser.objects.create_user(
            username="doc_b",
            email="doc_b@example.com",
            password="SenhaDocB123",
            clinic=self.clinic_b,
            role=CustomUser.Role.DOCTOR,
        )

        # Secretárias, cada uma vinculada a um médico e clínica
        self.secretary_a = CustomUser.objects.create_user(
            username="sec_a_appt",
            email="sec_a_appt@example.com",
            password="SenhaSecA123",
            clinic=self.clinic_a,
            role=CustomUser.Role.SECRETARY,
            doctor_for_secretary=self.doctor_a,
        )
        self.secretary_b = CustomUser.objects.create_user(
            username="sec_b_appt",
            email="sec_b_appt@example.com",
            password="SenhaSecB123",
            clinic=self.clinic_b,
            role=CustomUser.Role.SECRETARY,
            doctor_for_secretary=self.doctor_b,
        )

        # Pacientes em cada clínica
        self.patient_a = PatientProfile.objects.create(
            clinic=self.clinic_a,
            full_name="Paciente A Isolamento",
            cpf="333.333.333-33",
            phone="(34) 91111-0001",
        )
        self.patient_b = PatientProfile.objects.create(
            clinic=self.clinic_b,
            full_name="Paciente B Isolamento",
            cpf="444.444.444-44",
            phone="(34) 92222-0002",
        )

        # Alguns horários de exemplo
        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        # 2 agendamentos do médico A (clínica A)
        self.appt_a1 = Appointment.objects.create(
            clinic=self.clinic_a,
            doctor=self.doctor_a,
            patient=self.patient_a,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=1, minutes=30),
            status=Appointment.Status.CONFIRMED,
            clinical_notes="Consulta A1",
        )
        self.appt_a2 = Appointment.objects.create(
            clinic=self.clinic_a,
            doctor=self.doctor_a,
            patient=self.patient_a,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=3, minutes=30),
            status=Appointment.Status.REQUESTED,
            clinical_notes="Consulta A2",
        )

        # 1 agendamento do médico B (clínica B)
        self.appt_b1 = Appointment.objects.create(
            clinic=self.clinic_b,
            doctor=self.doctor_b,
            patient=self.patient_b,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=2, minutes=30),
            status=Appointment.Status.CONFIRMED,
            clinical_notes="Consulta B1",
        )

        self.login_url = reverse("token_obtain_pair")
        self.appointments_url = reverse("appointment-list")

    def _get_token(self, username: str, password: str) -> str:
        resp = self.client.post(
            self.login_url,
            {"username": username, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data["access"]

    def test_secretary_sees_only_appointments_from_linked_doctor_and_clinic(self):
        """
        Secretária da clínica A, vinculada ao doutor A, deve ver apenas
        os agendamentos de doctor_a na clínica_a.
        """
        token = self._get_token("sec_a_appt", "SenhaSecA123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.appointments_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        # Convertemos IDs retornados em set para facilitar a comparação
        returned_ids = {item["id"] for item in resp.data}

        self.assertSetEqual(
            returned_ids,
            {str(self.appt_a1.id), str(self.appt_a2.id)},
            msg="Secretária A não deve enxergar agendamentos de outras clínicas/médicos.",
        )
        self.assertNotIn(str(self.appt_b1.id), returned_ids)

    def test_doctor_sees_only_their_own_appointments(self):
        """
        Médico A deve ver apenas os próprios agendamentos, mesmo que existam
        agendamentos de outros médicos em outras clínicas.
        """
        token = self._get_token("doc_a", "SenhaDocA123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get(self.appointments_url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        returned_ids = {item["id"] for item in resp.data}

        self.assertSetEqual(
            returned_ids,
            {str(self.appt_a1.id), str(self.appt_a2.id)},
            msg="Médico A não deve enxergar agendamentos de outros médicos.",
        )
        self.assertNotIn(str(self.appt_b1.id), returned_ids)



class ConsentPermissionTests(APITestCase):
    """
    Valida a permissão HasActiveConsent:

    - Usuário com consentimento para docs ativos acessa normalmente;
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

        # Secretária que já aceitou v1
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
        # Privacidade v1 continua ativa

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")
        resp = self.client.get(self.patients_url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Consentimento atualizado obrigatório", str(resp.data))


class ConsentEndpointsTests(APITestCase):
    """
    Testa os endpoints de consentimento:

    - GET  /api/consent/active-docs/
    - POST /api/consent/accept/
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
        self.consent_active_url = reverse("consent-active-docs")
        self.consent_accept_url = reverse("consent-accept")
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
        2) GET  /consent/active-docs/ lista docs
        3) POST /consent/accept/ registra consentimentos
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

    - CLINIC_OWNER cria médico (DOCTOR) com DoctorProfile.
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

class AuthAuditLogTests(APITestCase):
    """
    Garante que o login JWT via /api/auth/login/ gera um AuditLog
    com ação LOGIN, vinculado ao usuário e à clínica correta.
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(
            name="Clínica Audit Login",
            schema_name="clinica_audit_login",
            is_active=True,
        )

        self.user = CustomUser.objects.create_user(
            username="user_login_audit",
            email="user_login_audit@example.com",
            password="SenhaLoginAudit123",
            clinic=self.clinic,
            role=CustomUser.Role.SECRETARY,
        )

        self.login_url = reverse("token_obtain_pair")

    def test_successful_login_creates_audit_log_entry(self):
        payload = {
            "username": "user_login_audit",
            "password": "SenhaLoginAudit123",
        }

        resp = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn("access", resp.data)

        log = AuditLog.objects.filter(
            actor=self.user,
            action=AuditLog.Action.LOGIN,
            target_model="CustomUser",
            target_object_id=str(self.user.id),
            clinic=self.clinic,
        ).first()

        self.assertIsNotNone(
            log,
            "Era esperado um registro de AuditLog de LOGIN após autenticação bem-sucedida.",
        )

class EncryptionTests(TestCase):
    """
    Testes de baixo nível para criptografia:

    - CPF: armazenado criptografado + hash único;
    - clinical_notes: EncryptedTextField com roundtrip correto.
    """

    def setUp(self):
        self.clinic = Clinic.objects.create(
            name="Clínica Teste",
            schema_name="clinica_teste",
            is_active=True,
        )

    def test_cpf_encrypted_and_hash_unique(self):
        """
        Garante que:
        - o CPF é armazenado criptografado,
        - o hash é calculado corretamente,
        - o hash impede duplicidade de CPF.
        """
        user1 = CustomUser.objects.create_user(
            username="paciente1@example.com",
            email="paciente1@example.com",
            password="senha123",
            clinic=self.clinic,
            role=CustomUser.Role.PATIENT,
        )

        patient1 = PatientProfile.objects.create(
            user=user1,
            clinic=self.clinic,
            full_name="Paciente Um",
            cpf="123.456.789-09",
            phone="(34) 99999-0000",
        )

        # ORM devolve o texto original
        self.assertEqual(patient1.cpf, "123.456.789-09")

        # Hash salvo bate com o esperado (CPF normalizado só com dígitos)
        normalized = "12345678909"
        expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        self.assertEqual(patient1.cpf_hash, expected_hash)

        # Tentativa de cadastrar outro paciente com o MESMO CPF -> IntegrityError
        user2 = CustomUser.objects.create_user(
            username="paciente2@example.com",
            email="paciente2@example.com",
            password="senha123",
            clinic=self.clinic,
            role=CustomUser.Role.PATIENT,
        )

        with self.assertRaises(IntegrityError):
            PatientProfile.objects.create(
                user=user2,
                clinic=self.clinic,
                full_name="Paciente Dois",
                cpf="123.456.789-09",
                phone="(34) 98888-0000",
            )

    def test_clinical_notes_encrypted_field_roundtrip(self):
        """
        Garante que o campo clinical_notes é um EncryptedTextField
        e que salvar/buscar mantém o conteúdo intacto.
        """
        doctor = CustomUser.objects.create_user(
            username="medico@example.com",
            email="medico@example.com",
            password="senha123",
            clinic=self.clinic,
            role=CustomUser.Role.DOCTOR,
            first_name="Carlos",
            last_name="Almeida",
            gender=CustomUser.Gender.MALE,
        )

        user_patient = CustomUser.objects.create_user(
            username="paciente3@example.com",
            email="paciente3@example.com",
            password="senha123",
            clinic=self.clinic,
            role=CustomUser.Role.PATIENT,
        )

        patient = PatientProfile.objects.create(
            user=user_patient,
            clinic=self.clinic,
            full_name="Paciente Três",
            cpf="987.654.321-00",
            phone="(34) 97777-0000",
        )

        secret_text = "Paciente relata dor de cabeça há 3 dias."

        appt = Appointment.objects.create(
            clinic=self.clinic,
            doctor=doctor,
            patient=patient,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(minutes=30),
            status=Appointment.Status.CONFIRMED,
            clinical_notes=secret_text,
        )

        # O campo no modelo é de fato um EncryptedTextField
        field = Appointment._meta.get_field("clinical_notes")
        self.assertIsInstance(field, EncryptedTextField)

        # Roundtrip: o texto lido da base é igual ao que foi salvo
        appt_db = Appointment.objects.get(id=appt.id)
        self.assertEqual(appt_db.clinical_notes, secret_text)
