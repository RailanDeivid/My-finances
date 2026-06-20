from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0021_remove_parcela_add_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasto",
            name="grupo_recorrente",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                default=None,
                help_text="UUID compartilhado entre as ocorrências de um gasto recorrente.",
                null=True,
            ),
        ),
    ]
