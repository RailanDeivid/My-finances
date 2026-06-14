from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('gastos', '0005_responsavel_is_principal'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gasto',
            name='cartao',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='gastos',
                to='gastos.cartao',
            ),
        ),
    ]
