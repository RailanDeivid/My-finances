from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0003_userprofile_ativo_is_admin"),
    ]

    operations = [
        # Remove os campos que foram adicionados ao UserProfile por engano
        migrations.RemoveField(model_name="userprofile", name="ativo"),
        migrations.RemoveField(model_name="userprofile", name="is_admin"),

        # Cria tabela separada para controle de acesso do agente WhatsApp
        migrations.CreateModel(
            name="WhatsAppAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=20, unique=True, verbose_name="Número", help_text="Formato: 5511999999999")),
                ("ativo", models.BooleanField(default=True, verbose_name="Ativo")),
                ("is_admin", models.BooleanField(default=False, verbose_name="Admin", help_text="Admins podem gerenciar números via /ajuda")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Adicionado em")),
            ],
            options={
                "verbose_name": "Acesso WhatsApp",
                "verbose_name_plural": "Acessos WhatsApp",
                "ordering": ["-criado_em"],
            },
        ),
    ]
