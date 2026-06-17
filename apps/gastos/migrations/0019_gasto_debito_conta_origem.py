import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0018_investimento_tipo_investimento"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gasto",
            name="tipo_pagamento",
            field=models.CharField(
                max_length=25,
                choices=[
                    ("credito_avista",    "Crédito à Vista"),
                    ("credito_parcelado", "Crédito Parcelado"),
                    ("pix",               "Pix / Transferência"),
                    ("debito",            "Débito"),
                    ("emprestimo",        "Empréstimo"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="gasto",
            name="conta_origem",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gastos_debito",
                to="gastos.conta",
                help_text="Conta debitada (obrigatória para tipo Débito).",
            ),
        ),
    ]
