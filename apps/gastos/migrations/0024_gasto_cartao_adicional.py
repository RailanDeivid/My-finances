from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0023_entrada_recorrente"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasto",
            name="cartao_adicional",
            field=models.BooleanField(
                default=False,
                help_text="Indica se o gasto foi realizado em um cartão adicional.",
            ),
        ),
    ]
