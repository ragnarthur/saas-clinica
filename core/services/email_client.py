from django.conf import settings
from django.core.mail import send_mail


def send_email_verification(*, user, token: str) -> None:
    """
    Envia um e-mail simples com link de verificação.

    Em produção, troque o `send_mail` por integração com o provider
    que você for usar (SendGrid, Amazon SES, etc.).
    """
    subject = "Confirme seu e-mail - DocFlowMed"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@docflowmed.local")

    # Exemplo de URL - ajuste para o domínio real do frontend
    verify_url = f"http://localhost:5173/verify-email?token={token}"

    message = (
        f"Olá, {user.first_name or user.email}!\n\n"
        "Recebemos um pedido de cadastro na plataforma DocFlowMed.\n"
        "Para concluir o processo e ativar seu acesso, clique no link abaixo:\n\n"
        f"{verify_url}\n\n"
        "Se você não fez esse cadastro, pode ignorar este e-mail."
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=True,  # em dev não queremos quebrar o fluxo
        )
    except Exception:
        # Em dev você pode logar isso; por enquanto deixamos silencioso.
        pass
