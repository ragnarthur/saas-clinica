# core/services/email_client.py
from django.conf import settings
from django.core.mail import send_mail


def build_frontend_url(path: str) -> str:
    """
    Monta URLs para o frontend com base no FRONTEND_BASE_URL do settings.
    Garante que não teremos // duplicada.
    """
    base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


def send_email_verification(*, user, token: str) -> None:
    """
    Envia um e-mail com código de 6 dígitos + link de verificação.

    Em produção, você pode trocar o send_mail por um provider externo
    (SendGrid, Amazon SES, etc). Aqui focamos em algo direto e testável.
    """
    app_name = getattr(settings, "APP_NAME", "DocFlowMed")
    subject = f"Confirme seu e-mail - {app_name}"
    from_email = getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        f"{app_name} <no-reply@docflowmed.local>",
    )

    # exemplo: http://localhost:5173/verify-email?token=123456
    verify_url = build_frontend_url(f"verify-email?token={token}")

    message = (
        f"Olá, {user.first_name or user.email}!\n\n"
        f"Recebemos um pedido de cadastro na plataforma {app_name}.\n\n"
        "Use o código abaixo para confirmar seu e-mail:\n\n"
        f"    {token}\n\n"
        "Você também pode clicar no link abaixo para confirmar diretamente:\n\n"
        f"{verify_url}\n\n"
        "Se você não fez esse cadastro, pode ignorar este e-mail.\n"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=True,  # em dev, não queremos quebrar o fluxo se o SMTP falhar
        )
    except Exception:
        # Se quiser, adicione logs aqui depois.
        pass
