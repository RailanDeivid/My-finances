import os
from .base import *

DEBUG = False

_sk = os.environ.get("SECRET_KEY", "")
if not _sk or "insecure" in _sk:
    raise RuntimeError(
        "SECRET_KEY env var must be set to a secure value in production."
    )
SECRET_KEY = _sk

_hosts = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
# "web" é o hostname interno do Docker usado pelo evolution-api para webhook
ALLOWED_HOSTS = _hosts + ["web"]

# Sem manifest — o app já usa ?v=N para cache bust; evita exigir collectstatic a cada deploy
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# HTTPS / cookies seguros
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
