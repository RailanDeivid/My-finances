from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from apps.gastos.admin_views import admin_login_view, admin_logout_view

admin.site.site_url = "/"
admin.site.site_header = "MyFinances — Painel Interno"
admin.site.site_title = "Painel Interno"
admin.site.index_title = "Painel de Administração"

urlpatterns = [
    # Login/logout próprios do painel interno — antes de admin.site.urls para ter prioridade
    path("painel-interno/login/", admin_login_view, name="admin-panel-login"),
    path("painel-interno/logout/", admin_logout_view, name="admin-panel-logout"),
    path("painel-interno/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.gastos.urls")),
]
