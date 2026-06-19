from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LLMUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("operation", models.CharField(max_length=60)),
                ("model", models.CharField(max_length=60)),
                ("tokens_input", models.IntegerField()),
                ("tokens_output", models.IntegerField()),
                ("tokens_total", models.IntegerField()),
                ("cost_usd", models.DecimalField(decimal_places=8, max_digits=12)),
                ("latency_ms", models.IntegerField()),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Uso de LLM",
                "verbose_name_plural": "Usos de LLM",
                "ordering": ["-timestamp"],
            },
        ),
    ]
