from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0024_gasto_cartao_adicional"),
    ]

    operations = [
        migrations.AddField(
            model_name="gasto",
            name="ajuste_tipo",
            field=models.CharField(
                blank=True,
                choices=[("desconto", "Desconto"), ("adicao", "Adição")],
                help_text="Apenas para tipo 'Ajuste de Fatura': desconto ou adição.",
                max_length=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="gasto",
            name="tipo_pagamento",
            field=models.CharField(
                choices=[
                    ("credito_avista",    "Crédito à Vista"),
                    ("credito_parcelado", "Crédito Parcelado"),
                    ("recorrente",        "Compra Recorrente"),
                    ("pix",               "Pix / Transferência"),
                    ("debito",            "Débito"),
                    ("emprestimo",        "Empréstimo"),
                    ("ajuste_fatura",     "Ajuste de Fatura"),
                ],
                db_index=True,
                max_length=25,
            ),
        ),
    ]
