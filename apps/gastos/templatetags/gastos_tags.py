from django import template
from django.utils.html import escape, mark_safe

register = template.Library()

_BADGE_TIPO_MAP = {
    "credito_avista":    ("badge-avista",      "À Vista"),
    "credito_parcelado": ("badge-parcelado",   "Parcelado"),
    "pix":               ("badge-pix",         "Pix"),
    "debito":            ("badge-debito",       "Débito"),
    "recorrente":        ("badge-recorrente",  "Recorrente"),
    "ajuste_fatura":     ("badge-ajuste",      "Ajuste"),
}


@register.simple_tag
def badge_tipo(tipo_pag, fallback_label=""):
    """Renderiza o badge colorido de tipo de pagamento.
    Para tipos conhecidos usa o label curto do mapa; fallback_label é usado só em tipos desconhecidos.
    """
    if tipo_pag in _BADGE_TIPO_MAP:
        cls, texto = _BADGE_TIPO_MAP[tipo_pag]
        return mark_safe(f'<span class="badge {cls}">{texto}</span>')
    texto = escape(fallback_label if fallback_label else (tipo_pag or "—"))
    return mark_safe(f'<span class="badge badge-outro">{texto}</span>')


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


@register.filter(name="pct_diff")
def pct_diff(atual, anterior):
    """Retorna variação percentual entre atual e anterior. Ex: 120|pct_diff:100 → 20"""
    try:
        a, b = float(atual), float(anterior)
        if b == 0:
            return None
        return round(((a - b) / b) * 100, 1)
    except (ValueError, TypeError):
        return None


@register.filter(name="abs_val")
def abs_val(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value


@register.filter(name="get_item")
def get_item(dictionary, key):
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter(name="pct_of")
def pct_of(parte, total):
    """Percentual de parte sobre total. Ex: 30|pct_of:100 → 30.0"""
    try:
        t = float(total)
        if t == 0:
            return None
        return round((float(parte) / t) * 100, 1)
    except (ValueError, TypeError):
        return None
