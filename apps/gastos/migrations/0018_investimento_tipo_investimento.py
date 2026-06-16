from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0017_investimentohistorico_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="investimento",
            name="tipo_investimento",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("renda_fixa",        "Renda Fixa"),
                    ("renda_variavel",    "Renda Variável"),
                    ("fundo_imobiliario", "Fundo Imobiliário"),
                ],
                default="renda_fixa",
                verbose_name="Tipo de Investimento",
            ),
        ),
    ]
