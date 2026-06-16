import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .access_control import BLOCKED_MSG, get_user_by_phone
from .agent import MENU_TEXT, process_message
from .evolution import send_message
from .session import is_rate_limited

logger = logging.getLogger(__name__)

RATE_LIMIT_MSG = "⏳ Muitas mensagens em pouco tempo. Aguarde um instante."


def _extract_payload(data: dict) -> tuple[str | None, str | None]:
    """Extrai (phone, message_text) do payload da Evolution API."""
    try:
        key = data["data"]["key"]
        if key.get("fromMe"):
            return None, None

        remote_jid = key.get("remoteJid", "")
        if "@g.us" in remote_jid:   # ignorar grupos
            return None, None

        phone = remote_jid.split("@")[0]

        msg = data["data"].get("message", {})
        text = (
            msg.get("conversation")
            or msg.get("extendedTextMessage", {}).get("text")
            or ""
        ).strip()

        if not text:
            return None, None

        return phone, text
    except (KeyError, TypeError):
        return None, None


@csrf_exempt
@require_POST
def webhook(request):
    import json as _json

    try:
        payload = _json.loads(request.body)
    except _json.JSONDecodeError:
        return JsonResponse({"status": "ok"})

    event = payload.get("event", "")
    if event != "messages.upsert":
        return JsonResponse({"status": "ok"})

    phone, text = _extract_payload(payload)
    if not phone or not text:
        return JsonResponse({"status": "ok"})

    # Controle de acesso
    user = get_user_by_phone(phone)
    if not user:
        send_message(phone, BLOCKED_MSG)
        return JsonResponse({"status": "ok"})

    # Rate limit
    if is_rate_limited(phone):
        send_message(phone, RATE_LIMIT_MSG)
        return JsonResponse({"status": "ok"})

    # Processa e responde
    try:
        response_text = process_message(phone, user, text)
        send_message(phone, response_text)
    except Exception as e:
        logger.error("Webhook process error phone=%s: %s", phone, e)
        send_message(phone, f"❌ Erro interno. Tente novamente.\n\n{MENU_TEXT}")

    return JsonResponse({"status": "ok"})


@csrf_exempt
def health(request):
    return JsonResponse({"status": "ok", "service": "whatsapp-bot"})
