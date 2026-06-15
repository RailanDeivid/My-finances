from django import template

register = template.Library()


@register.filter(name="brl")
def brl(value, decimals=2):
    """Formata número no padrão brasileiro: R$ 5.540,80"""
    try:
        v = float(value)
        decimals = int(decimals)
        formatted = f"{v:,.{decimals}f}"
        # US: 5,540.80 → BR: 5.540,80
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (ValueError, TypeError):
        return value
