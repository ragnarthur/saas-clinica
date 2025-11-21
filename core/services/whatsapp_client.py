# core/services/whatsapp_client.py
import json
import logging
from urllib import request as urllib_request, error as urllib_error

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _format_datetime(dt):
    """
    Formata datetime para algo amigável em pt-BR.
    Ex: 25/11/2025 às 14:30
    """
    if dt is None:
        return ""
    local_dt = timezone.localtime(dt)
    return local_dt.strftime("%d/%m/%Y às %H:%M")


def send_whatsapp_message(phone: str, message: str) -> bool:
    """
    Envia comando para o microserviço Node.

    LGPD: aqui NUNCA entra dado sensível de saúde.
    Só coisas operacionais: data/hora da consulta, nome da clínica, etc.
    """
    if not settings.WHATSAPP_ENABLED:
        logger.info("WHATSAPP_ENABLED=False, pulando envio real de WhatsApp.")
        return False

    if not phone:
        logger.warning("Telefone vazio ao tentar enviar WhatsApp.")
        return False

    url = settings.WHATSAPP_SERVICE_URL.rstrip("/") + "/api/send-message"
    payload = {"phone": phone, "message": message}
    data = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=5) as resp:
            status_code = resp.getcode()
            logger.info("WhatsApp service respondeu com status %s", status_code)
            return 200 <= status_code < 300
    except urllib_error.URLError as exc:
        logger.warning("Falha ao chamar serviço WhatsApp: %s", exc)
        return False


def send_appointment_confirmation(appointment) -> bool:
    """
    Gera a mensagem de confirmação de consulta e chama o microserviço.

    - Usa o telefone do paciente.
    - NÃO inclui diagnóstico, sintomas ou qualquer dado de saúde.
    """
    patient = appointment.patient
    clinic = appointment.clinic

    phone = getattr(patient, "phone", None)
    when_str = _format_datetime(appointment.start_time)

    message = (
        f"Sua consulta na clínica {clinic.name} foi CONFIRMADA para {when_str}. "
        f"Se não puder comparecer, entre em contato com a clínica."
    )

    logger.info(
        "Enviando confirmação de consulta via WhatsApp para %s (appointment=%s)",
        phone,
        appointment.id,
    )
    return send_whatsapp_message(phone, message)
