from .models import UserProfile

BLOCKED_MSG = (
    "⛔ Número não autorizado.\n"
    "Solicite acesso ao administrador do MyFinances."
)


def get_user_by_phone(phone: str):
    """Retorna o User vinculado ao número ou None se não cadastrado."""
    try:
        profile = UserProfile.objects.select_related("user").get(whatsapp_number=phone)
        return profile.user
    except UserProfile.DoesNotExist:
        return None
