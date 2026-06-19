from .models import UserProfile, WhatsAppAccess

BLOCKED_MSG = (
    "⛔ Número não autorizado.\n"
    "Solicite acesso ao administrador do MyFinances."
)


def _normalize(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 11 and not digits.startswith("55"):
        digits = "55" + digits
    return digits


def is_authorized(phone: str) -> bool:
    return WhatsAppAccess.objects.filter(phone=_normalize(phone), ativo=True).exists()


def is_admin(phone: str) -> bool:
    return WhatsAppAccess.objects.filter(phone=_normalize(phone), ativo=True, is_admin=True).exists()


def get_user_by_phone(phone: str):
    """Retorna o User do site vinculado ao número (via UserProfile), ou None."""
    number = _normalize(phone)
    if not WhatsAppAccess.objects.filter(phone=number, ativo=True).exists():
        return None
    try:
        profile = UserProfile.objects.select_related("user").get(whatsapp_number=number)
        return profile.user
    except UserProfile.DoesNotExist:
        return None


def add_number(phone: str, added_by: str) -> str:
    number = _normalize(phone)
    if WhatsAppAccess.objects.filter(phone=number).exists():
        return f"⚠️ O número {number} já está cadastrado."
    WhatsAppAccess.objects.create(phone=number, ativo=True, is_admin=False)
    return f"✅ Número {number} adicionado com sucesso."


def block_number(phone: str, blocked_by: str) -> str:
    number = _normalize(phone)
    updated = WhatsAppAccess.objects.filter(phone=number, ativo=True).update(ativo=False)
    if not updated:
        obj = WhatsAppAccess.objects.filter(phone=number).first()
        if obj:
            return f"⚠️ O número {number} já está bloqueado."
        return f"⚠️ Número {number} não encontrado."
    return f"🚫 Número {number} bloqueado com sucesso."


def delete_number(phone: str, deleted_by: str) -> str:
    number = _normalize(phone)
    deleted, _ = WhatsAppAccess.objects.filter(phone=number).delete()
    if not deleted:
        return f"⚠️ Número {number} não encontrado."
    return f"🗑️ Número {number} removido permanentemente."


def list_numbers() -> str:
    entries = WhatsAppAccess.objects.order_by("phone")
    if not entries.exists():
        return "Nenhum número cadastrado."
    lines = ["📋 *Números cadastrados:*\n"]
    for e in entries:
        status = "✅" if e.ativo else "🚫"
        admin = " 👑" if e.is_admin else ""
        lines.append(f"{status}{admin} {e.phone}")
    return "\n".join(lines)
