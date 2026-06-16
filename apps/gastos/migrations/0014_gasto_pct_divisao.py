from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0013_gasto_grupo_divisao"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasto",
            name="pct_divisao",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Percentual desta parte no gasto dividido (ex: 60 = 60%).",
                null=True,
            ),
        ),
    ]
