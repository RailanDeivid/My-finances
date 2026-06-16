import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3000


def send_message(to: str, text: str):
    """Envia texto via Evolution API. Divide em chunks se > CHUNK_SIZE."""
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}

    chunks = [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    with httpx.Client(timeout=15) as client:
        for chunk in chunks:
            payload = {
                "number": to,
                "options": {"delay": 500, "presence": "composing"},
                "textMessage": {"text": chunk},
            }
            try:
                client.post(url, json=payload, headers=headers)
            except Exception as e:
                logger.error("Evolution API send error: %s", e)
