import logging
import threading
from dataclasses import dataclass

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .access_control import BLOCKED_MSG, get_user_by_phone
from .agent import MENU_TEXT, _MSG_SPLIT, process_message
from .evolution import send_message, send_presence
from .session import is_duplicate, is_rate_limited

logger = logging.getLogger(__name__)

RATE_LIMIT_MSG = "⏳ Muitas mensagens em pouco tempo. Aguarde um instante."


# ── Payload estruturado ───────────────────────────────────────────────────────

@dataclass
class _MessagePayload:
    phone: str
    text: str
    push_name: str = ""


def _parse_payload(data: dict) -> _MessagePayload | None:
    """Extrai phone, text e pushName do payload da Evolution API."""
    try:
        msg_data = data.get("data", {})
        key = msg_data.get("key", {})

        if key.get("fromMe"):
            return None

        remote_jid = key.get("remoteJid", "")
        if "@g.us" in remote_jid:
            return None

        phone = remote_jid.split("@")[0]
        push_name = msg_data.get("pushName", "") or ""

        msg = msg_data.get("message", {}) or {}
        text = (
            msg.get("conversation")
            or (msg.get("extendedTextMessage") or {}).get("text")
            or ""
        ).strip()

        if not phone or not text:
            return None

        return _MessagePayload(phone=phone, text=text, push_name=push_name)

    except (KeyError, TypeError, AttributeError):
        return None


# ── Digitando contínuo (para de quando a resposta é enviada) ─────────────────

def _keep_typing(phone: str, stop: threading.Event) -> None:
    while not stop.is_set():
        send_presence(phone)
        stop.wait(3)


# ── Webhook ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def webhook(request):
    import json as _json

    try:
        payload = _json.loads(request.body)
    except _json.JSONDecodeError:
        return JsonResponse({"status": "ok"})

    if payload.get("event") != "messages.upsert":
        return JsonResponse({"status": "ok"})

    parsed = _parse_payload(payload)
    if not parsed:
        return JsonResponse({"status": "ok"})

    # Deduplicação — Evolution API pode disparar o mesmo evento 2x
    message_id = payload.get("data", {}).get("key", {}).get("id", "")
    if message_id and is_duplicate(message_id):
        return JsonResponse({"status": "ok"})

    phone, text, push_name = parsed.phone, parsed.text, parsed.push_name

    # Controle de acesso
    user = get_user_by_phone(phone)
    if not user:
        send_message(phone, BLOCKED_MSG)
        return JsonResponse({"status": "ok"})

    # Rate limit
    if is_rate_limited(phone):
        send_message(phone, RATE_LIMIT_MSG)
        return JsonResponse({"status": "ok"})

    # Digita enquanto processa
    stop_typing = threading.Event()
    typing_thread = threading.Thread(
        target=_keep_typing, args=(phone, stop_typing), daemon=True
    )
    typing_thread.start()

    try:
        response_text = process_message(phone, user, text, push_name=push_name)
        for part in response_text.split(_MSG_SPLIT):
            if part.strip():
                send_message(phone, part.strip())
    except Exception as e:
        logger.error("Webhook error phone=%s: %s", phone, e)
        send_message(phone, f"❌ Erro interno. Tente novamente.\n\n{MENU_TEXT}")
    finally:
        stop_typing.set()
        typing_thread.join(timeout=5)

    return JsonResponse({"status": "ok"})


@csrf_exempt
def health(request):
    return JsonResponse({"status": "ok", "service": "whatsapp-bot"})
