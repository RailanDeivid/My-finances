from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

ADMIN_SESSION_KEY = "_admin_panel_auth"


def admin_login_view(request):
    next_url = request.POST.get("next") or request.GET.get("next") or "/painel-interno/"
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
