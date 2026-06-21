import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0022_gasto_grupo_recorrente"),
    ]

    operations = [
        migrations.AddField(
            model_name="entrada",
            name="recorrente",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entrada",
            name="grupo_recorrente",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
