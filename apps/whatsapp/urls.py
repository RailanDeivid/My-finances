from django.urls import path
from . import views

urlpatterns = [
    path("webhook/whatsapp/", views.webhook, name="whatsapp-webhook"),
    path("webhook/health/", views.health, name="whatsapp-health"),
]
