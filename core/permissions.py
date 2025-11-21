# core/permissions.py
from rest_framework.permissions import BasePermission

from .models import CustomUser


class HasActiveConsent(BasePermission):
    """
    Garante que o usuário aceitou os documentos legais ativos (LGPD).

    A ideia:
    - Usuário precisa ter UserConsent para TODOS os LegalDocument.is_active=True
    - Superuser e SAAS_ADMIN podem passar mesmo sem consent (suporte, auditoria, etc.)
    """

    message = (
        "Consentimento atualizado obrigatório para continuar usando o sistema."
    )

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # Suporte / SaaS admin passa direto
        if getattr(user, "is_superuser", False) or getattr(
            user, "role", None
        ) == CustomUser.Role.SAAS_ADMIN:
            return True

        # Helper definido no modelo
        if hasattr(user, "has_active_consent"):
            return user.has_active_consent

        return True
