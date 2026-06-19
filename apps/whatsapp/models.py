from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


class UserProfile(models.Model):
    """Vincula um usuário do site ao seu número de WhatsApp."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="whatsapp_profile")
    whatsapp_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Número no formato internacional sem +: ex. 5511999999999",
    )

    class Meta:
        verbose_name = "Perfil WhatsApp (usuário do site)"
        verbose_name_plural = "Perfis WhatsApp (usuários do site)"

    def __str__(self):
        return f"{self.user.username} → {self.whatsapp_number or '(sem número)'}"


class WhatsAppAccess(models.Model):
    """Números autorizados a usar o agente WhatsApp. Independente dos usuários do site."""
    phone    = models.CharField(max_length=20, unique=True, verbose_name="Número", help_text="Formato: 5511999999999")
    ativo    = models.BooleanField(default=True, verbose_name="Ativo")
    is_admin = models.BooleanField(default=False, verbose_name="Admin", help_text="Admins podem gerenciar números via /ajuda")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Adicionado em")

    class Meta:
        verbose_name = "Acesso WhatsApp"
        verbose_name_plural = "Acessos WhatsApp"
        ordering = ["-criado_em"]

    def __str__(self):
        status = "✅" if self.ativo else "🚫"
        admin = " 👑" if self.is_admin else ""
        return f"{status}{admin} {self.phone}"


class LLMUsage(models.Model):
    user          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp     = models.DateTimeField(auto_now_add=True, db_index=True)
    operation     = models.CharField(max_length=60)
    model         = models.CharField(max_length=60)
    tokens_input  = models.IntegerField()
    tokens_output = models.IntegerField()
    tokens_total  = models.IntegerField()
    cost_usd      = models.DecimalField(max_digits=12, decimal_places=8)
    latency_ms    = models.IntegerField()

    class Meta:
        verbose_name = "Uso de LLM"
        verbose_name_plural = "Usos de LLM"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} · {self.operation} · ${self.cost_usd}"


@receiver(post_save, sender="whatsapp.UserProfile")
def sync_whatsapp_access(sender, instance, **kwargs):
    """Ao salvar UserProfile com telefone, garante entrada em WhatsAppAccess."""
    phone = (instance.whatsapp_number or "").strip()
    if not phone:
        return
    WhatsAppAccess.objects.get_or_create(
        phone=phone,
        defaults={"ativo": True, "is_admin": False},
    )
