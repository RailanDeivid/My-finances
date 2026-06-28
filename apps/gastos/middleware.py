import traceback as tb

from django.shortcuts import redirect

ADMIN_SESSION_KEY = "_admin_panel_auth"


# Paths que não devem gerar log de erro (assets, health-checks, etc.)
_SKIP_ERROR_PATHS = ("/static/", "/favicon", "/painel-interno/jsi18n/")


def _registrar_erro(request, exception=None, status_code=500, tipo="500"):
    """Grava um LogErro de forma silenciosa — nunca lança exceção."""
    try:
        from apps.gastos.models import LogErro
        user = None
        try:
            if request.user.is_authenticated:
                user = request.user
        except Exception:
            pass

        LogErro.objects.create(
            tipo=tipo,
            path=request.path[:500],
            method=request.method,
            status_code=status_code,
            exception_type=type(exception).__name__ if exception else "",
            exception_message=str(exception)[:2000] if exception else "",
            traceback=tb.format_exc()[:5000] if exception else "",
            user=user,
        )
    except Exception:
        pass


class ErrorLoggingMiddleware:
    """Captura erros 500 (exceções não tratadas e respostas 5xx) e grava em LogErro."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exception_logged = False

    def __call__(self, request):
        self._exception_logged = False
        response = self.get_response(request)

        # Captura 5xx que passaram por view de erro sem exceção (ex: raise Http500 explícito)
        if (
            response.status_code >= 500
            and not self._exception_logged
            and not any(request.path.startswith(p) for p in _SKIP_ERROR_PATHS)
        ):
            _registrar_erro(request, status_code=response.status_code)

        return response

    def process_exception(self, request, exception):
        if any(request.path.startswith(p) for p in _SKIP_ERROR_PATHS):
            return None
        self._exception_logged = True
        _registrar_erro(request, exception=exception, status_code=500)
        return None  # deixa o Django tratar normalmente



ADMIN_PREFIX = "/painel-interno/"
ADMIN_LOGIN = "/painel-interno/login/"


class AdminPanelMiddleware:
    """
    Garante que o Painel Interno tenha login próprio, independente da sessão do app.
    Qualquer acesso a /painel-interno/* exige que o usuário tenha logado
    especificamente pela tela do painel interno.
    """

    EXEMPT_PATHS = (
        "/painel-interno/login/",
        "/painel-interno/jsi18n/",
        "/painel-interno/password_reset/",
        "/painel-interno/autocomplete/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_protected(request.path):
            if not request.session.get(ADMIN_SESSION_KEY, False):
                return redirect(f"{ADMIN_LOGIN}?next={request.path}")

        response = self.get_response(request)

        # Após login bem-sucedido no painel interno: marca a sessão
        if (
            request.path.rstrip("/") == ADMIN_LOGIN.rstrip("/")
            and request.method == "POST"
            and getattr(response, "status_code", None) == 302
            and request.user.is_authenticated
            and request.user.is_staff
        ):
            request.session[ADMIN_SESSION_KEY] = True
            request.session.modified = True

        return response

    def _is_protected(self, path):
        if not path.startswith(ADMIN_PREFIX):
            return False
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return False
        return True
