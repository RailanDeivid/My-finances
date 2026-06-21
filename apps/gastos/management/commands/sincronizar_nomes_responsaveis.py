from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.gastos.models import Responsavel

User = get_user_model()


class Command(BaseCommand):
    help = "Sincroniza o nome do responsável principal de cada usuário com o nome completo do login."

    def handle(self, *args, **options):
        atualizados = 0
        for user in User.objects.all():
            nome_correto = user.get_full_name().strip() or user.username
            atualizado = Responsavel.objects.filter(
                user=user, is_principal=True
            ).exclude(nome=nome_correto).update(nome=nome_correto)
            if atualizado:
                self.stdout.write(f"  {user.username} → '{nome_correto}'")
                atualizados += atualizado
        self.stdout.write(self.style.SUCCESS(f"\n{atualizados} responsável(is) atualizado(s)."))
