from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0002_llmusage"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="ativo",
            field=models.BooleanField(default=True, help_text="Desative para bloquear acesso ao agente"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="is_admin",
            field=models.BooleanField(default=False, help_text="Admins podem adicionar/bloquear/deletar números via WhatsApp"),
        ),
    ]
