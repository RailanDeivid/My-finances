from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def criar_responsavel_para_usuario(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import Responsavel
    nome = instance.get_full_name().strip() or instance.username
    Responsavel.objects.get_or_create(
        user=instance,
        is_principal=True,
        defaults={"nome": nome, "ativo": True},
    )
