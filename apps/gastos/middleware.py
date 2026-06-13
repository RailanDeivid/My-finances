from django.shortcuts import redirect

ADMIN_SESSION_KEY = "_admin_panel_auth"
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
