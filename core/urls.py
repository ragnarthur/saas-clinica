# core/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    PatientViewSet,
    AppointmentViewSet,
    StaffUserViewSet,
    PatientRegisterView,
    AppointmentRequestView,
    ActiveClinicsView,
    PublicActiveLegalDocsView,
    ConsentActiveDocsView,
    ConsentAcceptView,
    MeView,  # <- NOVO
)

router = DefaultRouter()
router.register(r"patients", PatientViewSet, basename="patient")
router.register(r"appointments", AppointmentViewSet, basename="appointment")
router.register(r"staff", StaffUserViewSet, basename="staff")

urlpatterns = [
    # ------------------ AUTENTICAÇÃO (JWT) ------------------
    # usado pelo frontend em /api/auth/login/
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # dados do usuário autenticado (secretária / médico / owner)
    # usado pelo dashboard para mostrar:
    # - nome da secretária
    # - clínica atual
    # - médico com quem a secretária está atuando
    path("auth/me/", MeView.as_view(), name="auth_me"),

    # ------------------ PÚBLICO (sem auth) ------------------
    # cadastro de paciente
    path("patients/register/", PatientRegisterView.as_view(), name="patient-register"),

    # clínicas ativas para o select do cadastro
    path("clinics/active/", ActiveClinicsView.as_view(), name="clinics-active"),

    # textos LGPD para o cadastro público
    path(
        "legal-documents/active/",
        PublicActiveLegalDocsView.as_view(),
        name="legal-docs-active",
    ),

    # ------------------ PACIENTE AUTENTICADO ------------------
    # paciente pedindo agendamento
    path(
        "appointments/request/",
        AppointmentRequestView.as_view(),
        name="appointment-request",
    ),

    # ------------------ CONSENTIMENTO (usuário logado) -------
    path(
        "consent/active-docs/",
        ConsentActiveDocsView.as_view(),
        name="consent-active-docs",
    ),
    path("consent/accept/", ConsentAcceptView.as_view(), name="consent-accept"),
]

urlpatterns += router.urls
