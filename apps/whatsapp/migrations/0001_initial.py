from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("whatsapp_number", models.CharField(
                    blank=True,
                    help_text="Número no formato internacional sem +: ex. 5511999999999",
                    max_length=20,
                    unique=True,
                )),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="whatsapp_profile",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Perfil WhatsApp",
                "verbose_name_plural": "Perfis WhatsApp",
            },
        ),
    ]
