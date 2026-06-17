from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gastos", "0020_remove_gasto_nome_pessoa"),
    ]

    operations = [
        migrations.DeleteModel(name="Parcela"),
        migrations.AlterField(
            model_name="entrada",
            name="data",
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name="gasto",
            name="data_compra",
            field=models.DateField(db_index=True, help_text="Data em que a compra foi realizada"),
        ),
        migrations.AlterField(
            model_name="gasto",
            name="tipo_pagamento",
            field=models.CharField(
                choices=[
                    ("credito_avista",    "Crédito à Vista"),
                    ("credito_parcelado", "Crédito Parcelado"),
                    ("pix",               "Pix / Transferência"),
                    ("debito",            "Débito"),
                    ("emprestimo",        "Empréstimo"),
                ],
                db_index=True,
                max_length=25,
            ),
        ),
    ]
