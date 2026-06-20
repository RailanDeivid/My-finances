from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.gastos.signals import criar_categorias_padrao

User = get_user_model()


class Command(BaseCommand):
    help = "Cria as categorias padrão para todos os usuários existentes"

    def handle(self, *args, **options):
        users = User.objects.all()
        total = users.count()
        for i, user in enumerate(users, 1):
            criar_categorias_padrao(user)
            self.stdout.write(f"[{i}/{total}] {user.username} — categorias sincronizadas")
        self.stdout.write(self.style.SUCCESS(f"\nConcluído: {total} usuário(s) processado(s)."))
