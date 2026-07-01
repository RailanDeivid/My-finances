import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3000


def _headers() -> dict:
    return {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}


def _base_url() -> str:
    return f"{settings.EVOLUTION_API_URL}"


def send_presence(to: str, delay_ms: int = 5000) -> None:
    """Exibe 'digitando...' no chat do WhatsApp enquanto o agente processa."""
    url = f"{_base_url()}/chat/sendPresence/{settings.EVOLUTION_INSTANCE_NAME}"
    payload = {"number": to, "delay": delay_ms, "presence": "composing"}
    try:
        with httpx.Client(timeout=20) as client:
            client.post(url, json=payload, headers=_headers())
    except Exception as e:
        logger.warning("Presence error: %s", e)


def send_message(to: str, text: str) -> None:
    """Envia texto via Evolution API. Divide em chunks se > CHUNK_SIZE."""
    url = f"{_base_url()}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"

    chunks = [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    with httpx.Client(timeout=30) as client:
        for chunk in chunks:
            try:
                client.post(url, json={"number": to, "text": chunk}, headers=_headers())
            except Exception as e:
                logger.error("Evolution API send error: %s", e)
