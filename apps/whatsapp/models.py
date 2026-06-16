from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="whatsapp_profile")
    whatsapp_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Número no formato internacional sem +: ex. 5511999999999",
    )

    class Meta:
        verbose_name = "Perfil WhatsApp"
        verbose_name_plural = "Perfis WhatsApp"

    def __str__(self):
        return f"{self.user.username} → {self.whatsapp_number or '(sem número)'}"
