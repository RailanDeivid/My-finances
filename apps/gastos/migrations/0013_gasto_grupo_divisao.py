from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0012_normaliza_banco_slugs"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasto",
            name="grupo_divisao",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                default=None,
                help_text="UUID compartilhado entre os dois lados de um gasto dividido.",
                null=True,
            ),
        ),
    ]
