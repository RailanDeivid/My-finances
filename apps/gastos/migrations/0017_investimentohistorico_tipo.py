from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0016_investimento_liquidado"),
    ]

    operations = [
        migrations.AddField(
            model_name="investimentohistorico",
            name="tipo",
            field=models.CharField(
                max_length=15,
                choices=[
                    ("inicial",    "Aporte Inicial"),
                    ("aporte",     "Aporte"),
                    ("saque",      "Saque"),
                    ("rendimento", "Rendimento"),
                    ("liquidacao", "Liquidação"),
                ],
                default="rendimento",
            ),
        ),
    ]
