# core/middleware/tenant.py
from django.utils.deprecation import MiddlewareMixin


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware simples que adiciona `request.clinic` em todas as requisições.

    - Usuários autenticados: request.clinic = user.clinic
    - Anônimos: request.clinic = None
    """

    def process_request(self, request):
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            request.clinic = getattr(user, "clinic", None)
        else:
            request.clinic = None

        return None
