from pathlib import Path
import os
from django.templatetags.static import static
from django.urls import reverse_lazy
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-key-change-me")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.gastos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.gastos.middleware.AdminPanelMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.gastos.context_processors.modal_forms",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "myfinancesDB"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

FIXTURE_DIRS = [BASE_DIR / "fixtures"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "padrao",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

UNFOLD = {
    "SITE_TITLE": "MyFinances — Painel Admin",
    "SITE_HEADER": "MyFinances",
    "SITE_SUBHEADER": "Controle de finanças pessoal",
    "SITE_LOGO": {
        "light": lambda r: static("img/piggy-bank.svg"),
        "dark":  lambda r: static("img/piggy-bank.svg"),
    },
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "type": "image/svg+xml",
            "href": lambda r: static("img/piggy-bank.svg"),
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": True,
    "COLORS": {
        "base": {
            "50":  "249 250 251",
            "100": "243 244 246",
            "200": "229 231 235",
            "300": "209 213 219",
            "400": "156 163 175",
            "500": "107 114 128",
            "600": "75 85 99",
            "700": "55 65 81",
            "800": "31 41 55",
            "900": "17 24 39",
            "950": "10 14 23",
        },
        "primary": {
            "50":  "240 253 244",
            "100": "220 252 231",
            "200": "187 247 208",
            "300": "134 239 172",
            "400": "74 222 128",
            "500": "34 197 94",
            "600": "22 163 74",
            "700": "21 128 61",
            "800": "20 83 45",
            "900": "20 83 45",
            "950": "5 46 22",
        },
        "font": {
            "subtle-light":  "var(--color-base-500)",
            "subtle-dark":   "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark":  "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark":  "var(--color-base-100)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Gastos",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Gastos",        "icon": "receipt",        "link": reverse_lazy("admin:gastos_gasto_changelist")},
                    {"title": "Parcelas",      "icon": "payments",       "link": reverse_lazy("admin:gastos_parcela_changelist")},
                    {"title": "Categorias",    "icon": "label",          "link": reverse_lazy("admin:gastos_categoria_changelist")},
                ],
            },
            {
                "title": "Cartões e Responsáveis",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Cartões",       "icon": "credit_card",    "link": reverse_lazy("admin:gastos_cartao_changelist")},
                    {"title": "Responsáveis",  "icon": "person",         "link": reverse_lazy("admin:gastos_responsavel_changelist")},
                ],
            },
            {
                "title": "Sistema",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Usuários",      "icon": "manage_accounts","link": reverse_lazy("admin:auth_user_changelist")},
                    {"title": "Grupos",        "icon": "groups",         "link": reverse_lazy("admin:auth_group_changelist")},
                ],
            },
        ],
    },
    "TABS": [],
}
