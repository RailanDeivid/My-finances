import json
from datetime import datetime, time

import redis
from django.conf import settings

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

SESSION_TTL = 86400      # 24h de inatividade limpa a sessão
RATE_LIMIT_WINDOW = 60   # segundos
RATE_LIMIT_MAX = 15      # mensagens por janela


def get_session(phone: str) -> dict:
    raw = _redis.get(f"session:{phone}")
    if raw:
        return json.loads(raw)
    return {
        "state": "MENU",
        "entity": None,
        "fields": {},
        "step": None,
        "options_map": {},
    }


def save_session(phone: str, data: dict):
    _redis.setex(f"session:{phone}", SESSION_TTL, json.dumps(data, ensure_ascii=False))


def clear_session(phone: str):
    _redis.delete(f"session:{phone}")


def is_rate_limited(phone: str) -> bool:
    key = f"rl:{phone}"
    pipe = _redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, RATE_LIMIT_WINDOW)
    count, _ = pipe.execute()
    return int(count) > RATE_LIMIT_MAX


def is_duplicate(message_id: str) -> bool:
    """Retorna True se o message_id já foi processado (janela de 30s)."""
    key = f"msg:{message_id}"
    inserted = _redis.set(key, "1", nx=True, ex=30)
    return inserted is None


def _seconds_until_midnight() -> int:
    from datetime import timedelta
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


def is_first_contact_today(phone: str) -> bool:
    """Retorna True na primeira mensagem do dia. Marca como visto até meia-noite."""
    key = f"greeted:{phone}:{datetime.now().strftime('%Y-%m-%d')}"
    inserted = _redis.set(key, "1", nx=True, ex=_seconds_until_midnight())
    return inserted is not None
