from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme  # ← adicionar
from django.views.decorators.http import require_POST


from .middleware import ADMIN_SESSION_KEY


def admin_login_view(request):
    raw_next = request.POST.get("next") or request.GET.get("next") or ""
    if raw_next and url_has_allowed_host_and_scheme(raw_next, allowed_hosts={request.get_host()}):
        next_url = raw_next
    else:
        next_url = "/painel-interno/"

    error = False
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_active and user.is_staff:
            login(request, user)
            request.session[ADMIN_SESSION_KEY] = True
            return redirect(next_url)

        error = True

    return render(request, "admin/login.html", {
        "app_path": request.path,
        "next": next_url,
        "error": error,
    })


@require_POST
def admin_logout_view(request):
    logout(request)
    return redirect("/painel-interno/login/")
