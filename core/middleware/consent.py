# core/middleware/consent.py
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


EXEMPT_PATH_PREFIXES = [
    "/admin/",
    "/auth/login/",
    "/auth/register/",
    "/api/auth/login/",
    "/api/auth/register/",
    "/api/legal-documents/active/",
    "/api/user-consents/",
    "/health/",
    "/static/",
    "/media/",
]


class ConsentRequiredMiddleware(MiddlewareMixin):
    """
    Middleware que bloqueia requisições autenticadas se o usuário
    ainda não aceitou TODOS os documentos legais ativos.

    Usa o helper user.has_active_consent definido em CustomUser.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        path = request.path

        # Libera caminhos técnicos / auth / estáticos
        for prefix in EXEMPT_PATH_PREFIXES:
            if path.startswith(prefix):
                return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            # Anônimos não são bloqueados aqui (login/registro tratam à parte)
            return None

        # Opcional: liberar super admin SaaS
        if getattr(user, "role", None) == "SAAS_ADMIN":
            return None

        if not getattr(user, "has_active_consent", True):
            return JsonResponse(
                {
                    "detail": "CONSENT_REQUIRED",
                    "code": "consent_required",
                },
                status=403,
            )

        return None
