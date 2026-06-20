from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


def criar_categorias_padrao(user):
    from .models import Categoria
    for nome, icone, cor in Categoria.PRESETS:
        Categoria.objects.get_or_create(
            user=user,
            nome=nome,
            defaults={"icone": icone, "cor": cor, "ativo": True},
        )


@receiver(post_save, sender=User)
def setup_novo_usuario(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import Responsavel
    nome = instance.get_full_name().strip() or instance.username
    Responsavel.objects.get_or_create(
        user=instance,
        is_principal=True,
        defaults={"nome": nome, "ativo": True},
    )
    criar_categorias_padrao(instance)
