import json

import redis
from django.conf import settings

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

SESSION_TTL = 3600       # 1 hora de inatividade limpa a sessão
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
