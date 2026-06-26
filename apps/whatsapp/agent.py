import json
import logging
import random
import re
import time
import uuid as _uuid
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Sum
from openai import OpenAI

from apps.gastos.models import Cartao, Categoria, Conta, Entrada, Gasto, Responsavel
from .prompts import get_catalog, make_intent_messages
from .session import clear_session, get_session, is_first_contact_today, save_session

logger = logging.getLogger(__name__)
_llm = OpenAI(api_key=settings.OPENAI_KEY)
_catalog = get_catalog()


def _build_map(section: str) -> dict:
    result = {}
    for key, aliases in _catalog[section].items():
        for alias in aliases:
            result[alias.lower()] = key
    return result


# ── Textos fixos ──────────────────────────────────────────────────────────────

MENU_OPTIONS = (
    "O que deseja fazer?\n\n"
    "1️⃣  Registrar gasto\n"
    "2️⃣  Registrar entrada\n"
    "3️⃣  📊 Relatórios\n"
    "4️⃣  Cadastrar cartão\n\n"
    "_Ou me conte diretamente, ex: \"gastei 50 no mercado no pix\"_"
)

MENU_TEXT = MENU_OPTIONS

RELATORIO_MENU_TEXT = (
    "📊 *Relatórios*\n\n"
    "1️⃣  Resumo do mês\n"
    "2️⃣  Gastos por cartão\n"
    "3️⃣  Gastos por cartão específico\n"
    "4️⃣  Saldos em contas\n"
    "5️⃣  Saldo em conta específica\n"
    "6️⃣  Gastos por responsável\n\n"
    "_Digite 0 ou *menu* para voltar_"
)

_MSG_SPLIT = "\x00SPLIT\x00"

_GREETINGS = {
    "manha": [
        "Bom dia, *{name}*! Vamos começar bem o dia?",
        "Oi, *{name}*! Bom dia! No que posso ajudar?",
        "Bom dia, *{name}*! Pronto pra organizar as finanças?",
    ],
    "tarde": [
        "Boa tarde, *{name}*! No que posso ajudar?",
        "Oi, *{name}*! Boa tarde! Bora registrar alguma coisa?",
        "Eae, *{name}*! Boa tarde! O que vamos fazer hoje?",
    ],
    "noite": [
        "Boa noite, *{name}*! Vamos fechar as contas do dia?",
        "Oi, *{name}*! Boa noite! No que posso ajudar?",
        "Eae, *{name}*! Boa noite! Bora registrar?",
    ],
    "madrugada": [
        "Ainda acordado, *{name}*? Bora registrar logo e descansar!",
        "Oi, *{name}*! Noite coruja! No que posso ajudar?",
    ],
    "fds": [
        "Eae, *{name}*! Curtindo o fim de semana? No que posso ajudar?",
        "Oi, *{name}*! Fim de semana e já gerenciando as finanças?",
        "Olá, *{name}*! Bom descanso! O que precisa registrar?",
    ],
}


def _first_name(user) -> str:
    name = (user.first_name or user.username or "").strip()
    return name.split()[0].capitalize() if name else "você"


def _choose_greeting(name: str) -> str:
    hora     = __import__("datetime").datetime.now().hour
    dia_sem  = date.today().weekday()
    if dia_sem >= 5:
        pool = _GREETINGS["fds"]
    elif hora < 5:
        pool = _GREETINGS["madrugada"]
    elif hora < 12:
        pool = _GREETINGS["manha"]
    elif hora < 18:
        pool = _GREETINGS["tarde"]
    else:
        pool = _GREETINGS["noite"]
    return random.choice(pool).format(name=name)


_RETURN_GREETINGS = [
    "Eae, *{name}*! Que bom ter você de volta.",
    "Oi, *{name}*! De volta por aqui.",
    "Olá, *{name}*! Bom te ver de novo.",
    "Eae, *{name}*! Precisando de mais alguma coisa?",
]


def welcome_message(user, phone: str = "", push_name: str = "") -> str:
    name = (push_name.split()[0].capitalize() if push_name.strip()
            else _first_name(user))
    if phone and not is_first_contact_today(phone):
        greeting = random.choice(_RETURN_GREETINGS).format(name=name)
    else:
        greeting = _choose_greeting(name)
    return f"{greeting}{_MSG_SPLIT}{MENU_OPTIONS}"


CANCEL_WORDS = {"cancelar", "sair", "parar", "stop", "menu", "início", "inicio", "voltar"}


# ── Mapeamentos de choices ────────────────────────────────────────────────────

TIPO_PAG_MAP = {
    "1": "credito_avista", "2": "credito_parcelado", "3": "pix",
    "4": "debito",
    **_build_map("tipo_pagamento"),
    "credito_avista": "credito_avista", "credito_parcelado": "credito_parcelado",
    "debito": "debito",
}

TIPO_ENT_MAP = {
    "1": "salario", "2": "bonus", "3": "outros",
    **_build_map("tipo_entrada"),
}

BANDEIRA_MAP = {
    "1": "visa",       "visa": "visa",
    "2": "mastercard", "mastercard": "mastercard",
    "3": "elo",        "elo": "elo",
    "4": "amex",       "amex": "amex", "american express": "amex",
    "5": "outro",      "outro": "outro", "outros": "outro",
}

TIPO_PAG_LABEL = {
    "credito_avista":    "Crédito à vista",
    "credito_parcelado": "Crédito parcelado",
    "pix":               "Pix / Transferência",
    "debito":            "Débito",
}

TIPO_ENT_LABEL  = {"salario": "Salário", "bonus": "Bônus", "outros": "Outros"}
BANDEIRA_LABEL  = {
    "visa": "Visa", "mastercard": "Mastercard", "elo": "Elo",
    "amex": "American Express", "outro": "Outro",
}

# ── Passos por entidade ───────────────────────────────────────────────────────

GASTO_STEPS = [
    "valor",
    "descricao",
    "tipo_pagamento",
    "total_parcelas",   # skip unless parcelado
    "cartao_id",        # skip unless credito
    "conta_origem_id",  # skip unless debito
    "responsavel_id",
    "categoria_id",     # always asked (mandatory)
    "dividido",         # yes/no (skip if only 1 responsavel)
    "responsavel2_id",  # skip unless dividido
    "pct_divisao",      # skip unless dividido
    "data_compra",
]
ENTRADA_STEPS = ["tipo_entrada", "valor", "descricao_entrada", "conta_id", "responsavel_id"]
CARTAO_STEPS  = ["nome_cartao", "bandeira", "limite", "dia_fechamento"]

QUESTIONS = {
    "valor":          "💵 Qual o valor? _(ex: 49,90 ou 1.500)_",
    "descricao":      "📝 Qual a descrição?\n_(ex: Netflix, Mercado, Gasolina)_",
    "tipo_pagamento": (
        "💳 Tipo de pagamento?\n\n"
        "1 · Crédito à vista\n"
        "2 · Crédito parcelado\n"
        "3 · Pix / Transferência\n"
        "4 · Débito"
    ),
    "total_parcelas":   "🔢 Quantas parcelas?",
    "dividido":         "👥 Gasto dividido?\n\n1 · Sim\n2 · Não",
    "pct_divisao":      "📊 Como dividir?\n\n1 · 50/50 — Meio a meio\n2 · 60/40\n3 · 70/30\n_Ou digite o % do 1º responsável (ex: 65)_",
    "data_compra":      "📅 Data da compra?\n_(hoje, ontem, dia 15, 15/06 — ou *0* para hoje)_",
    "tipo_entrada":     "💰 Tipo de entrada?\n\n1 · Salário\n2 · Bônus\n3 · Outros",
    "descricao_entrada":"📝 Descrição? _(ou *0* para pular)_",
    "nome_cartao":      "📛 Nome do cartão? _(ex: Nubank, Inter, C6)_",
    "bandeira":         "💳 Bandeira?\n\n1 · Visa\n2 · Mastercard\n3 · Elo\n4 · American Express\n5 · Outro",
    "limite":           "💰 Limite do cartão? _(ou *0* para pular)_",
    "dia_fechamento":   "📅 Dia de fechamento da fatura? _(ou *0* para pular)_",
}


# ── Utilitários ───────────────────────────────────────────────────────────────

def _brl(value) -> str:
    v = float(value)
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _meses_pt():
    return ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]


def _date_to_str(d: date) -> str:
    return d.isoformat()


def _str_to_date(s) -> date | None:
    if isinstance(s, date):
        return s
    if isinstance(s, str):
        try:
            return date.fromisoformat(s)
        except ValueError:
            pass
    return None


def _parse_date(text: str, today: date) -> tuple[bool, date | None]:
    """Interpreta datas em pt-BR. Retorna (ok, date)."""
    t = text.strip().lower()
    if t in ("0", "hoje", "agora"):
        return True, today
    if t == "ontem":
        return True, today - relativedelta(days=1)
    if t == "anteontem":
        return True, today - relativedelta(days=2)
    # "dia 15" ou só "15"
    m = re.match(r"^(?:dia\s+)?(\d{1,2})$", t)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            try:
                return True, date(today.year, today.month, day)
            except ValueError:
                pass
    # "15/06" ou "15-06"
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})$", t)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        try:
            return True, date(today.year, month, day)
        except ValueError:
            pass
    # "15/06/2026" ou "15-06-2026"
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$", t)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return True, date(year, month, day)
        except ValueError:
            pass
    return False, None


def _billing_start(cartao, data_compra: date) -> date:
    """Retorna o 1º dia do mês de faturamento conforme fechamento do cartão.
    Se a data de compra >= dia_fechamento, a fatura é do mês seguinte.
    Sem fechamento definido → padrão próximo mês (por configuração).
    """
    if cartao and cartao.dia_fechamento:
        if data_compra.day >= cartao.dia_fechamento:
            return date(data_compra.year, data_compra.month, 1) + relativedelta(months=1)
        else:
            return date(data_compra.year, data_compra.month, 1)
    # Sem fechamento → próximo mês como padrão
    return date(data_compra.year, data_compra.month, 1) + relativedelta(months=1)


# ── Regras de pulo de passo ───────────────────────────────────────────────────

def _should_skip(step: str, fields: dict) -> bool:
    tipo = fields.get("tipo_pagamento")
    if step == "total_parcelas":
        return tipo != "credito_parcelado"
    if step == "cartao_id":
        return tipo not in {"credito_avista", "credito_parcelado"}
    if step == "conta_origem_id":
        return tipo != "debito"
    if step == "responsavel2_id":
        return not fields.get("dividido")
    if step == "pct_divisao":
        return not fields.get("dividido")
    return False


# ── Perguntas dinâmicas ───────────────────────────────────────────────────────

def _question_for_step(step: str, user, session: dict) -> str | None:
    if step == "cartao_id":
        cartoes = list(Cartao.objects.filter(user=user, ativo=True).values("id", "nome", "bandeira"))
        if not cartoes:
            return None
        opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(cartoes))
        session["options_map"]["cartao_id"] = {str(i+1): c["id"] for i, c in enumerate(cartoes)}
        session["options_map"]["cartao_nome_map"] = {c["nome"].lower(): c["id"] for c in cartoes}
        session["options_map"]["cartao_bandeira_map"] = {
            c.get("bandeira", "").lower(): c["id"] for c in cartoes if c.get("bandeira")
        }
        return f"💳 Qual cartão?\n\n{opts}"

    if step == "conta_origem_id":
        contas = list(Conta.objects.filter(user=user, ativo=True).values("id", "nome"))
        if not contas:
            return None
        opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(contas))
        session["options_map"]["conta_origem_id"] = {str(i+1): c["id"] for i, c in enumerate(contas)}
        session["options_map"]["conta_origem_nome_map"] = {c["nome"].lower(): c["id"] for c in contas}
        return f"🏦 Qual conta débito?\n\n{opts}"

    if step == "categoria_id":
        cats = list(Categoria.objects.filter(user=user, ativo=True).values("id", "nome"))
        if not cats:
            return None
        opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(cats))
        session["options_map"]["categoria_id"] = {str(i+1): c["id"] for i, c in enumerate(cats)}
        session["options_map"]["cat_nome_map"] = {c["nome"].lower(): c["id"] for c in cats}
        return f"🏷️ Categoria?\n\n{opts}\n\n_*0* para pular_"

    if step == "responsavel_id":
        resps = list(Responsavel.objects.filter(user=user, ativo=True).values("id", "nome"))
        if not resps:
            return None
        opts = "\n".join(f"{i+1} · {r['nome']}" for i, r in enumerate(resps))
        session["options_map"]["responsavel_id"] = {str(i+1): r["id"] for i, r in enumerate(resps)}
        session["options_map"]["resp_nome_map"] = {r["nome"].lower(): r["id"] for r in resps}
        return f"👤 Responsável?\n\n{opts}"

    if step == "dividido":
        n_resps = Responsavel.objects.filter(user=user, ativo=True).count()
        if n_resps <= 1:
            return None  # não tem com quem dividir
        return QUESTIONS["dividido"]

    if step == "responsavel2_id":
        resp1_id = session["fields"].get("responsavel_id")
        resps = list(
            Responsavel.objects.filter(user=user, ativo=True)
            .exclude(id=resp1_id)
            .values("id", "nome")
        )
        if not resps:
            return None
        opts = "\n".join(f"{i+1} · {r['nome']}" for i, r in enumerate(resps))
        session["options_map"]["responsavel2_id"] = {str(i+1): r["id"] for i, r in enumerate(resps)}
        session["options_map"]["resp2_nome_map"] = {r["nome"].lower(): r["id"] for r in resps}
        return f"👥 Dividir com quem?\n\n{opts}"

    if step == "conta_id":
        contas = list(Conta.objects.filter(user=user, ativo=True).values("id", "nome"))
        if not contas:
            return None
        opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(contas))
        session["options_map"]["conta_id"] = {str(i+1): c["id"] for i, c in enumerate(contas)}
        session["options_map"]["conta_nome_map"] = {c["nome"].lower(): c["id"] for c in contas}
        return f"🏦 Em qual conta foi recebido? _(ou *0* para pular)_\n\n{opts}"

    return QUESTIONS.get(step)


# ── Parser de campo ───────────────────────────────────────────────────────────

def _parse_field(step: str, text: str, session: dict):
    t = text.strip()
    today = date.today()

    if step == "valor":
        normalized = t.replace(".", "").replace(",", ".")
        try:
            v = float(normalized)
            return (True, v) if v > 0 else (False, None)
        except ValueError:
            return False, None

    if step == "descricao":
        return (True, t) if t else (False, None)

    if step == "tipo_pagamento":
        val = TIPO_PAG_MAP.get(t.lower())
        return (True, val) if val else (False, None)

    if step == "total_parcelas":
        try:
            n = int(t)
            return (True, n) if 2 <= n <= 120 else (False, None)
        except ValueError:
            return False, None

    if step == "cartao_id":
        opts = session.get("options_map", {})
        if t in opts.get("cartao_id", {}):
            return True, opts["cartao_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("cartao_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        for band, pk in opts.get("cartao_bandeira_map", {}).items():
            if band and (t_low in band or band in t_low):
                return True, pk
        return False, None

    if step == "conta_origem_id":
        opts = session.get("options_map", {})
        if t in opts.get("conta_origem_id", {}):
            return True, opts["conta_origem_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("conta_origem_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "categoria_id":
        if t == "0":
            return True, None
        opts = session.get("options_map", {})
        if t in opts.get("categoria_id", {}):
            return True, opts["categoria_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("cat_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "responsavel_id":
        opts = session.get("options_map", {})
        if t in opts.get("responsavel_id", {}):
            return True, opts["responsavel_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("resp_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "dividido":
        if t in ("1", "s", "sim", "yes", "ok"):
            return True, True
        if t in ("2", "n", "não", "nao", "no"):
            return True, False
        return False, None

    if step == "responsavel2_id":
        opts = session.get("options_map", {})
        if t in opts.get("responsavel2_id", {}):
            return True, opts["responsavel2_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("resp2_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "pct_divisao":
        if t == "1":
            return True, 50
        if t == "2":
            return True, 60
        if t == "3":
            return True, 70
        try:
            pct = int(t)
            return (True, pct) if 1 <= pct <= 99 else (False, None)
        except ValueError:
            return False, None

    if step == "data_compra":
        ok, d = _parse_date(t, today)
        return (ok, _date_to_str(d) if ok and d else None)

    if step == "tipo_entrada":
        val = TIPO_ENT_MAP.get(t.lower())
        return (True, val) if val else (False, None)

    if step == "descricao_entrada":
        return True, (None if t == "0" else t)

    if step == "conta_id":
        if t == "0":
            return True, None
        opts = session.get("options_map", {})
        if t in opts.get("conta_id", {}):
            return True, opts["conta_id"][t]
        t_low = t.lower()
        for nome, pk in opts.get("conta_nome_map", {}).items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "nome_cartao":
        return True, t

    if step == "bandeira":
        val = BANDEIRA_MAP.get(t.lower())
        return (True, val) if val else (False, None)

    if step in ("limite", "dia_fechamento"):
        if t == "0":
            return True, None
        try:
            return True, float(t.replace(",", "."))
        except ValueError:
            return False, None

    return True, t


def _error_for_step(step: str) -> str:
    msgs = {
        "valor":           "❌ Valor inválido. Digite apenas o número. _(ex: 150 ou 49,90)_",
        "tipo_pagamento":  "❌ Digite 1, 2, 3, 4 ou 5.",
        "total_parcelas":  "❌ Digite o número de parcelas (mínimo 2).",
        "tipo_entrada":    "❌ Digite 1, 2 ou 3.",
        "bandeira":        "❌ Digite 1, 2, 3, 4 ou 5.",
        "cartao_id":       "❌ Digite o número do cartão.",
        "conta_origem_id": "❌ Digite o número da conta.",
        "categoria_id":    "❌ Digite o número da categoria ou *0* para pular.",
        "responsavel_id":  "❌ Digite o número do responsável.",
        "dividido":        "❌ Digite 1 para Sim ou 2 para Não.",
        "responsavel2_id": "❌ Digite o número do segundo responsável.",
        "pct_divisao":     "❌ Digite 1, 2, 3 ou um percentual (ex: 60).",
        "conta_id":        "❌ Digite o número da conta ou *0* para pular.",
        "data_compra":     "❌ Formato inválido. Use: hoje, ontem, dia 15, 15/06 ou 0 para hoje.",
        "limite":          "❌ Digite o valor ou *0* para pular.",
        "dia_fechamento":  "❌ Digite o dia (1-31) ou *0* para pular.",
    }
    return msgs.get(step, "❌ Valor inválido. Tente novamente.")


# ── Confirmação ───────────────────────────────────────────────────────────────

def _build_confirm(entity: str, fields: dict) -> str:
    lines = ["📋 *Confirmar?*\n"]
    if entity == "gasto":
        tipo      = fields.get("tipo_pagamento", "")
        parcelas  = f" {fields['total_parcelas']}x" if fields.get("total_parcelas") else ""
        cartao    = f" · {fields.get('cartao_nome', '')}" if fields.get("cartao_nome") else ""
        conta_org = f"\n• Conta débito: {fields.get('conta_origem_nome', '')}" if fields.get("conta_origem_nome") else ""
        cat       = f"\n• Categoria: {fields.get('categoria_nome', '')}" if fields.get("categoria_nome") else ""
        data_c    = _str_to_date(fields.get("data_compra"))
        data_txt  = f"\n• Data da compra: {data_c.strftime('%d/%m/%Y')}" if data_c else ""

        valor_total = fields.get("valor", 0)
        dividido    = fields.get("dividido", False)
        if dividido and fields.get("responsavel2_id"):
            pct = int(fields.get("pct_divisao") or 50)
            pct2 = 100 - pct
            v1 = float(Decimal(str(valor_total)) * Decimal(pct) / 100)
            v2 = float(valor_total) - v1
            div_txt = (
                f"\n• *Dividido:* {pct}/{pct2}\n"
                f"  → {fields.get('responsavel_nome', '')}: {_brl(v1)} ({pct}%)\n"
                f"  → {fields.get('responsavel2_nome', '')}: {_brl(v2)} ({pct2}%)"
            )
        else:
            div_txt = ""

        lines += [
            f"• Valor: {_brl(valor_total)}",
            f"• Descrição: {fields.get('descricao', '')}",
            f"• Tipo: {TIPO_PAG_LABEL.get(tipo, '')}{parcelas}{cartao}{conta_org}{cat}",
            f"• Responsável: {fields.get('responsavel_nome', '')}{div_txt}{data_txt}",
        ]

    elif entity == "entrada":
        desc_txt  = f"\n• Descrição: {fields['descricao_entrada']}" if fields.get("descricao_entrada") else ""
        conta_txt = f"\n• Conta: {fields.get('conta_nome', '')}" if fields.get("conta_nome") else ""
        lines += [
            f"• Tipo: {TIPO_ENT_LABEL.get(fields.get('tipo_entrada', ''), '')}",
            f"• Valor: {_brl(fields.get('valor', 0))}{desc_txt}{conta_txt}",
            f"• Responsável: {fields.get('responsavel_nome', '')}",
        ]

    elif entity == "cartao":
        limite_txt = f"\n• Limite: {_brl(fields['limite'])}" if fields.get("limite") else ""
        fech_txt   = f"\n• Fechamento: dia {int(fields['dia_fechamento'])}" if fields.get("dia_fechamento") else ""
        lines += [
            f"• Nome: {fields.get('nome_cartao', '')}",
            f"• Bandeira: {BANDEIRA_LABEL.get(fields.get('bandeira', ''), '')}{limite_txt}{fech_txt}",
        ]

    lines += ["", "1 · ✅ Confirmar\n2 · ❌ Cancelar"]
    return "\n".join(lines)


# ── Salvamento ────────────────────────────────────────────────────────────────

def _save_gasto(user, fields: dict) -> str:
    from apps.gastos.views import _recalcular_saldos_a_partir

    tipo  = fields["tipo_pagamento"]
    n     = fields.get("total_parcelas") if tipo == "credito_parcelado" else None
    cartao = Cartao.objects.filter(id=fields["cartao_id"]).first() if fields.get("cartao_id") else None

    responsavel = (
        Responsavel.objects.filter(id=fields["responsavel_id"]).first()
        if fields.get("responsavel_id")
        else (Responsavel.objects.filter(user=user, is_principal=True).first()
              or Responsavel.objects.filter(user=user, ativo=True).first())
    )
    if not responsavel:
        return "❌ Nenhum responsável cadastrado. Cadastre um responsável antes de registrar gastos."

    categoria  = Categoria.objects.filter(id=fields["categoria_id"]).first() if fields.get("categoria_id") else None
    conta_orig = Conta.objects.filter(id=fields["conta_origem_id"]).first() if fields.get("conta_origem_id") else None

    descricao   = fields["descricao"]
    valor_total = Decimal(str(fields["valor"]))
    data_compra = _str_to_date(fields.get("data_compra")) or date.today()

    # Mês de faturamento correto conforme fechamento do cartão
    if tipo in ("credito_avista", "credito_parcelado"):
        data_inicio = _billing_start(cartao, data_compra)
    else:
        data_inicio = date(data_compra.year, data_compra.month, 1)

    # Divisão
    dividido      = fields.get("dividido", False)
    responsavel2  = Responsavel.objects.filter(id=fields["responsavel2_id"]).first() if fields.get("responsavel2_id") else None
    pct           = int(fields.get("pct_divisao") or 50)
    grupo_id      = _uuid.uuid4() if (dividido and responsavel2) else None

    def _criar(resp, valor, pct_val, grupo):
        base = dict(
            valor_total=valor, tipo_pagamento=tipo,
            cartao=cartao, conta_origem=conta_orig,
            responsavel=resp, categoria=categoria,
            grupo_divisao=grupo,
            pct_divisao=pct_val,
            user=user,
        )
        if n:
            Gasto.objects.create(descricao=f"{descricao} (1/{n})", data_compra=data_inicio, total_parcelas=n, **base)
            for i in range(2, n + 1):
                Gasto.objects.create(
                    descricao=f"{descricao} ({i}/{n})",
                    data_compra=data_inicio + relativedelta(months=i - 1),
                    total_parcelas=n, **base,
                )
        else:
            Gasto.objects.create(descricao=descricao, data_compra=data_inicio, **base)

    mes_ref, ano_ref = data_inicio.month, data_inicio.year
    tipo_str  = f"parcelado em {n}x" if n else TIPO_PAG_LABEL.get(tipo, tipo)
    cartao_txt = f" · {cartao.nome}" if cartao else ""

    if grupo_id and responsavel2:
        valor1 = (valor_total * Decimal(pct) / 100).quantize(Decimal("0.01"))
        valor2 = valor_total - valor1
        pct2   = 100 - pct
        _criar(responsavel, valor1, pct, grupo_id)
        _criar(responsavel2, valor2, pct2, grupo_id)
        _recalcular_saldos_a_partir(mes_ref, ano_ref, user)
        if responsavel2.usuario_vinculado and responsavel2.usuario_vinculado != user:
            _recalcular_saldos_a_partir(mes_ref, ano_ref, responsavel2.usuario_vinculado)
        if responsavel.usuario_vinculado and responsavel.usuario_vinculado != user:
            _recalcular_saldos_a_partir(mes_ref, ano_ref, responsavel.usuario_vinculado)
        return (
            f"✅ *Gasto dividido registrado!*\n"
            f"{descricao} · {_brl(valor_total)} · {tipo_str}{cartao_txt}\n\n"
            f"• {responsavel.nome}: {_brl(valor1)} ({pct}%)\n"
            f"• {responsavel2.nome}: {_brl(valor2)} ({pct2}%)\n"
            f"_Fatura: {_meses_pt()[mes_ref-1]}/{ano_ref}_"
        )
    else:
        _criar(responsavel, valor_total, None, None)
        _recalcular_saldos_a_partir(mes_ref, ano_ref, user)
        if responsavel.usuario_vinculado and responsavel.usuario_vinculado != user:
            _recalcular_saldos_a_partir(mes_ref, ano_ref, responsavel.usuario_vinculado)
        return (
            f"✅ *Gasto registrado!*\n"
            f"{descricao} · {_brl(valor_total)} · {tipo_str}{cartao_txt}\n"
            f"_Fatura: {_meses_pt()[mes_ref-1]}/{ano_ref}_"
        )


def _save_entrada(user, fields: dict) -> str:
    from apps.gastos.views import _recalcular_saldos_a_partir

    responsavel = Responsavel.objects.filter(id=fields["responsavel_id"]).first() if fields.get("responsavel_id") else None
    conta       = Conta.objects.filter(id=fields["conta_id"]).first() if fields.get("conta_id") else None
    valor       = Decimal(str(fields["valor"]))
    hoje        = date.today()

    Entrada.objects.create(
        tipo=fields["tipo_entrada"],
        descricao=fields.get("descricao_entrada") or "",
        valor=valor, data=hoje,
        responsavel=responsavel, conta=conta, user=user,
    )
    _recalcular_saldos_a_partir(hoje.month, hoje.year, user)
    return f"✅ *Entrada registrada!*\n{TIPO_ENT_LABEL.get(fields['tipo_entrada'], '')} · {_brl(valor)}"


def _save_cartao(user, fields: dict) -> str:
    Cartao.objects.create(
        nome=fields["nome_cartao"],
        bandeira=fields.get("bandeira", "outro"),
        limite=Decimal(str(fields["limite"])) if fields.get("limite") else None,
        dia_fechamento=int(fields["dia_fechamento"]) if fields.get("dia_fechamento") else None,
        user=user,
    )
    return f"✅ *Cartão criado!*\n{fields['nome_cartao']} · {BANDEIRA_LABEL.get(fields.get('bandeira', ''), '')}"


# ── Relatórios ────────────────────────────────────────────────────────────────

def _resumo(user) -> str:
    hoje = date.today()
    mes, ano = hoje.month, hoje.year
    mp = _meses_pt()
    total_ent = Entrada.objects.filter(
        user=user, data__month=mes, data__year=ano,
    ).exclude(tipo="saldo_anterior").aggregate(t=Sum("valor"))["t"] or Decimal("0")
    total_gas = Gasto.objects.filter(
        user=user, data_compra__month=mes, data_compra__year=ano,
    ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
    saldo = total_ent - total_gas
    saldo_icon = "📈" if saldo >= 0 else "📉"
    saldo_color = "+" if saldo >= 0 else ""
    return (
        f"📊 *{mp[mes-1]}/{ano}*\n\n"
        f"💰 Receitas:  {_brl(total_ent)}\n"
        f"💸 Gastos:    {_brl(total_gas)}\n"
        f"{saldo_icon} Saldo:     {saldo_color}{_brl(abs(saldo))}"
        + (" _(negativo)_" if saldo < 0 else "")
    )


def _rel_gastos_cartoes(user) -> str:
    hoje = date.today()
    mes, ano = hoje.month, hoje.year
    mp = _meses_pt()
    rows = (
        Gasto.objects.filter(
            user=user, data_compra__month=mes, data_compra__year=ano,
            tipo_pagamento__in=["credito_avista", "credito_parcelado"],
        )
        .values("cartao__nome")
        .annotate(total=Sum("valor_total"))
        .order_by("-total")
    )
    if not rows:
        return f"📊 *Gastos por Cartão — {mp[mes-1]}/{ano}*\n\nNenhum gasto no cartão este mês."
    lines = [f"📊 *Gastos por Cartão — {mp[mes-1]}/{ano}*\n"]
    for r in rows:
        lines.append(f"• {r['cartao__nome'] or 'Sem cartão'}: {_brl(r['total'])}")
    return "\n".join(lines)


def _rel_gastos_cartao_especifico(user, cartao_id) -> str:
    hoje = date.today()
    mes, ano = hoje.month, hoje.year
    mp = _meses_pt()
    cartao = Cartao.objects.filter(id=cartao_id, user=user).first()
    if not cartao:
        return "❌ Cartão não encontrado."
    total = (
        Gasto.objects.filter(user=user, cartao_id=cartao_id,
                             data_compra__month=mes, data_compra__year=ano)
        .aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
    )
    gastos = list(
        Gasto.objects.filter(user=user, cartao_id=cartao_id,
                             data_compra__month=mes, data_compra__year=ano)
        .order_by("-data_compra")[:10]
    )
    lines = [f"💳 *{cartao.nome} — {mp[mes-1]}/{ano}*\n", f"Total: {_brl(total)}\n"]
    for g in gastos:
        lines.append(f"• {g.descricao}: {_brl(g.valor_total)}")
    if not gastos:
        lines.append("Nenhum gasto neste período.")
    return "\n".join(lines)


def _rel_saldos_contas(user) -> str:
    contas = Conta.objects.filter(user=user, ativo=True).order_by("nome")
    if not contas:
        return "🏦 *Saldos em Contas*\n\nNenhuma conta cadastrada."
    lines = ["🏦 *Saldos em Contas*\n"]
    total = Decimal("0")
    for c in contas:
        saldo = c.saldo_atual or Decimal("0")
        total += saldo
        emoji = "📈" if saldo >= 0 else "📉"
        lines.append(f"{emoji} {c.nome}: {_brl(saldo)}")
    lines.append(f"\n💰 *Total: {_brl(total)}*")
    return "\n".join(lines)


def _rel_saldo_conta_especifica(user, conta_id) -> str:
    conta = Conta.objects.filter(id=conta_id, user=user).first()
    if not conta:
        return "❌ Conta não encontrada."
    saldo = conta.saldo_atual or Decimal("0")
    emoji = "📈" if saldo >= 0 else "📉"
    return (
        f"🏦 *{conta.nome}*\n"
        f"Tipo: {conta.get_tipo_display()}\n"
        f"{emoji} Saldo atual: {_brl(saldo)}"
    )


def _rel_gastos_responsavel(user) -> str:
    hoje = date.today()
    mes, ano = hoje.month, hoje.year
    mp = _meses_pt()
    rows = (
        Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
        .values("responsavel__nome")
        .annotate(total=Sum("valor_total"))
        .order_by("-total")
    )
    if not rows:
        return f"👤 *Gastos por Responsável — {mp[mes-1]}/{ano}*\n\nNenhum gasto neste mês."
    lines = [f"👤 *Gastos por Responsável — {mp[mes-1]}/{ano}*\n"]
    for r in rows:
        lines.append(f"• {r['responsavel__nome'] or 'Sem responsável'}: {_brl(r['total'])}")
    return "\n".join(lines)


def _question_rel_cartao(user, session: dict) -> str | None:
    cartoes = list(Cartao.objects.filter(user=user, ativo=True).values("id", "nome"))
    if not cartoes:
        return None
    opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(cartoes))
    session["options_map"]["rel_cartao_id"] = {str(i+1): c["id"] for i, c in enumerate(cartoes)}
    return f"💳 Qual cartão?\n\n{opts}"


def _question_rel_conta(user, session: dict) -> str | None:
    contas = list(Conta.objects.filter(user=user, ativo=True).values("id", "nome"))
    if not contas:
        return None
    opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(contas))
    session["options_map"]["rel_conta_id"] = {str(i+1): c["id"] for i, c in enumerate(contas)}
    return f"🏦 Qual conta?\n\n{opts}"


# ── LLM ───────────────────────────────────────────────────────────────────────

_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4o":      (5.00 / 1_000_000, 15.00 / 1_000_000),
}


def _save_llm_usage(user, operation: str, model: str, usage, latency_ms: int) -> None:
    try:
        from .models import LLMUsage
        price_in, price_out = _MODEL_PRICING.get(model, (0.0, 0.0))
        cost = Decimal(str(usage.prompt_tokens * price_in + usage.completion_tokens * price_out))
        LLMUsage.objects.create(
            user=user, operation=operation, model=model,
            tokens_input=usage.prompt_tokens, tokens_output=usage.completion_tokens,
            tokens_total=usage.total_tokens, cost_usd=cost, latency_ms=latency_ms,
        )
    except Exception as e:
        logger.warning("Falha ao salvar LLMUsage: %s", e)


def _call_llm_intent(message: str, user=None) -> dict:
    try:
        t0 = time.monotonic()
        resp = _llm.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=make_intent_messages(message),
            response_format={"type": "json_object"},
            temperature=float(settings.OPENAI_TEMPERATURE),
            max_tokens=400,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        _save_llm_usage(user, "intent_extraction", settings.OPENAI_MODEL, resp.usage, latency_ms)
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error("LLM error: %s", e)
        return {"intent": "desconhecido", "fields": {}}


# ── Máquina de estados ────────────────────────────────────────────────────────

def _steps_for(entity: str) -> list:
    return {"gasto": GASTO_STEPS, "entrada": ENTRADA_STEPS, "cartao": CARTAO_STEPS}.get(entity, [])


def _next_step(entity: str, fields: dict, after: str | None = None) -> str | None:
    steps = _steps_for(entity)
    start = (steps.index(after) + 1) if after and after in steps else 0
    for step in steps[start:]:
        if not _should_skip(step, fields) and step not in fields:
            return step
    return None


def _resolve_hints(entity: str, extracted_fields: dict, user) -> dict:
    """Resolve hints de nomes e datas para IDs e valores concretos."""
    today = date.today()

    # Cartão
    cartao_hint = extracted_fields.pop("cartao_nome_hint", None)
    if cartao_hint and entity == "gasto":
        cartoes = list(Cartao.objects.filter(user=user, ativo=True).values("id", "nome", "bandeira"))
        hint_low = cartao_hint.lower()
        for c in cartoes:
            if hint_low in c["nome"].lower() or c["nome"].lower() in hint_low:
                extracted_fields["cartao_id"]   = c["id"]
                extracted_fields["cartao_nome"] = c["nome"]
                break
        if "cartao_id" not in extracted_fields:
            for c in cartoes:
                if hint_low in (c.get("bandeira") or "").lower():
                    extracted_fields["cartao_id"]   = c["id"]
                    extracted_fields["cartao_nome"] = c["nome"]
                    break

    # Responsável 1
    resp_hint = extracted_fields.pop("responsavel_nome_hint", None)
    if resp_hint:
        resps = list(Responsavel.objects.filter(user=user, ativo=True).values("id", "nome"))
        hint_low = resp_hint.lower()
        for r in resps:
            if hint_low in r["nome"].lower() or r["nome"].lower() in hint_low:
                extracted_fields["responsavel_id"]   = r["id"]
                extracted_fields["responsavel_nome"] = r["nome"]
                break

    # Responsável 2 (gasto dividido)
    resp2_hint = extracted_fields.pop("responsavel2_nome_hint", None)
    if resp2_hint and entity == "gasto":
        resps = list(Responsavel.objects.filter(user=user, ativo=True).values("id", "nome"))
        hint_low = resp2_hint.lower()
        for r in resps:
            if hint_low in r["nome"].lower() or r["nome"].lower() in hint_low:
                extracted_fields["responsavel2_id"]   = r["id"]
                extracted_fields["responsavel2_nome"] = r["nome"]
                extracted_fields["dividido"]           = True
                break

    # Percentual de divisão da NLP
    pct_raw = extracted_fields.pop("pct_divisao", None)
    if pct_raw is not None and entity == "gasto":
        try:
            extracted_fields["pct_divisao"] = int(pct_raw)
        except (ValueError, TypeError):
            pass

    # Categoria
    cat_hint = extracted_fields.pop("categoria_hint", None)
    if cat_hint and entity == "gasto":
        cats = list(Categoria.objects.filter(user=user, ativo=True).values("id", "nome"))
        hint_low = cat_hint.lower()
        for c in cats:
            if hint_low in c["nome"].lower() or c["nome"].lower() in hint_low:
                extracted_fields["categoria_id"]   = c["id"]
                extracted_fields["categoria_nome"] = c["nome"]
                break

    # Data da compra
    data_hint = extracted_fields.pop("data_compra_hint", None)
    if data_hint and entity == "gasto":
        ok, parsed = _parse_date(str(data_hint), today)
        if ok and parsed:
            extracted_fields["data_compra"] = _date_to_str(parsed)

    return extracted_fields


def process_message(phone: str, user, text: str, push_name: str = "") -> str:
    text      = text.strip()
    text_lower = text.lower()

    if text_lower in CANCEL_WORDS:
        clear_session(phone)
        return f"Ok, operação cancelada. ✋\n\n{MENU_OPTIONS}"

    session = get_session(phone)
    state   = session["state"]

    # ── MENU ─────────────────────────────────────────────────────────────────
    if state == "MENU":
        direct = {"1": "gasto", "2": "entrada", "3": "relatorio", "4": "cartao"}.get(text)

        if direct == "relatorio":
            session["state"] = "RELATORIO_MENU"
            save_session(phone, session)
            return RELATORIO_MENU_TEXT

        if direct:
            entity           = direct
            extracted_fields = {}
        else:
            # Saudações simples → responde sem chamar o LLM
            _saudacoes = {
                "oi", "olá", "ola", "oi!", "olá!", "hi", "hello", "hey",
                "bom dia", "boa tarde", "boa noite", "eae", "eaí", "e aí",
                "tudo bem", "tudo bom", "oi tudo bem", "boa", "salve",
            }
            if text_lower in _saudacoes or text_lower.rstrip("!? ") in _saudacoes:
                clear_session(phone)
                return welcome_message(user, phone, push_name)

            result  = _call_llm_intent(text, user=user)
            intent  = result.get("intent", "desconhecido")

            if intent == "resumo":
                clear_session(phone)
                return _resumo(user)
            if intent == "menu":
                clear_session(phone)
                return welcome_message(user, phone, push_name)
            if intent not in ("gasto", "entrada", "cartao"):
                clear_session(phone)
                return welcome_message(user, phone, push_name)

            entity = intent
            llm_fields = result.get("fields", {}) or {}
            extracted_fields = {k: v for k, v in llm_fields.items() if v is not None}
            extracted_fields = _resolve_hints(entity, extracted_fields, user)

        session = {
            "state": "COLLECTING",
            "entity": entity,
            "fields": extracted_fields,
            "step": None,
            "options_map": {},
        }

        first_step = _next_step(entity, extracted_fields)
        if not first_step:
            session["state"] = "CONFIRMING"
            save_session(phone, session)
            return _build_confirm(entity, extracted_fields)

        # Auto-skip steps with no data (no cartões, no categorias, etc.)
        while first_step:
            q = _question_for_step(first_step, user, session)
            if q is not None:
                break
            extracted_fields[first_step] = None
            first_step = _next_step(entity, extracted_fields, after=first_step)

        if not first_step:
            session["state"] = "CONFIRMING"
            save_session(phone, session)
            return _build_confirm(entity, extracted_fields)

        session["step"] = first_step
        save_session(phone, session)
        intro = {"gasto": "📝 *Novo gasto*", "entrada": "💰 *Nova entrada*", "cartao": "💳 *Novo cartão*"}
        q = _question_for_step(first_step, user, session)
        return f"{intro[entity]}\n\n{q}"

    # ── RELATORIO_MENU ────────────────────────────────────────────────────────
    if state == "RELATORIO_MENU":
        if text == "0" or text_lower in {"menu", "voltar", "inicio", "início"}:
            clear_session(phone)
            return MENU_OPTIONS

        actions = {
            "1": lambda: _resumo(user),
            "2": lambda: _rel_gastos_cartoes(user),
            "4": lambda: _rel_saldos_contas(user),
            "6": lambda: _rel_gastos_responsavel(user),
        }

        if text in actions:
            clear_session(phone)
            return actions[text]() + f"\n\n{MENU_OPTIONS}"

        if text == "3":
            q = _question_rel_cartao(user, session)
            if not q:
                clear_session(phone)
                return "Nenhum cartão cadastrado." + f"\n\n{MENU_OPTIONS}"
            session["rel_tipo"] = "cartao"
            session["state"]    = "RELATORIO_SUB"
            save_session(phone, session)
            return q

        if text == "5":
            q = _question_rel_conta(user, session)
            if not q:
                clear_session(phone)
                return "Nenhuma conta cadastrada." + f"\n\n{MENU_OPTIONS}"
            session["rel_tipo"] = "conta"
            session["state"]    = "RELATORIO_SUB"
            save_session(phone, session)
            return q

        return RELATORIO_MENU_TEXT

    # ── RELATORIO_SUB ─────────────────────────────────────────────────────────
    if state == "RELATORIO_SUB":
        rel_tipo = session.get("rel_tipo")
        opts     = session.get("options_map", {})

        if rel_tipo == "cartao":
            cartao_map = opts.get("rel_cartao_id", {})
            cartao_id  = cartao_map.get(text)
            if not cartao_id:
                t_low = text.lower()
                for c in Cartao.objects.filter(user=user, ativo=True).values("id", "nome"):
                    if t_low in c["nome"].lower() or c["nome"].lower() in t_low:
                        cartao_id = c["id"]
                        break
            if cartao_id:
                clear_session(phone)
                return _rel_gastos_cartao_especifico(user, cartao_id) + f"\n\n{MENU_OPTIONS}"
            return "❌ Digite o número do cartão listado."

        if rel_tipo == "conta":
            conta_map = opts.get("rel_conta_id", {})
            conta_id  = conta_map.get(text)
            if not conta_id:
                t_low = text.lower()
                for c in Conta.objects.filter(user=user, ativo=True).values("id", "nome"):
                    if t_low in c["nome"].lower() or c["nome"].lower() in t_low:
                        conta_id = c["id"]
                        break
            if conta_id:
                clear_session(phone)
                return _rel_saldo_conta_especifica(user, conta_id) + f"\n\n{MENU_OPTIONS}"
            return "❌ Digite o número da conta listada."

        clear_session(phone)
        return MENU_OPTIONS

    # ── COLLECTING ───────────────────────────────────────────────────────────
    if state == "COLLECTING":
        step   = session["step"]
        entity = session["entity"]
        fields = session["fields"]

        ok, value = _parse_field(step, text, session)
        if not ok:
            save_session(phone, session)
            return _error_for_step(step)

        # Enriquece campos de confirmação com nomes legíveis
        if step == "cartao_id" and value is not None:
            c = Cartao.objects.filter(id=value).first()
            if c:
                fields["cartao_nome"] = c.nome
        if step == "conta_origem_id" and value is not None:
            c = Conta.objects.filter(id=value).first()
            if c:
                fields["conta_origem_nome"] = c.nome
        if step == "categoria_id" and value is not None:
            c = Categoria.objects.filter(id=value).first()
            if c:
                fields["categoria_nome"] = c.nome
        if step == "responsavel_id" and value is not None:
            r = Responsavel.objects.filter(id=value).first()
            if r:
                fields["responsavel_nome"] = r.nome
        if step == "responsavel2_id" and value is not None:
            r = Responsavel.objects.filter(id=value).first()
            if r:
                fields["responsavel2_nome"] = r.nome
        if step == "conta_id" and value is not None:
            c = Conta.objects.filter(id=value).first()
            if c:
                fields["conta_nome"] = c.nome

        fields[step] = value
        session["fields"] = fields

        next_step = _next_step(entity, fields, after=step)

        # Auto-skip sem dados disponíveis
        while next_step:
            q = _question_for_step(next_step, user, session)
            if q is not None:
                break
            fields[next_step] = None
            next_step = _next_step(entity, fields, after=next_step)

        if not next_step:
            session["state"] = "CONFIRMING"
            save_session(phone, session)
            return _build_confirm(entity, fields)

        session["step"] = next_step
        save_session(phone, session)
        return _question_for_step(next_step, user, session) or ""

    # ── CONFIRMING ───────────────────────────────────────────────────────────
    if state == "CONFIRMING":
        entity = session["entity"]
        fields = session["fields"]

        if text in ("1", "s", "sim", "ok", "confirmar", "yes"):
            clear_session(phone)
            try:
                if entity == "gasto":
                    return _save_gasto(user, fields) + f"\n\n{MENU_OPTIONS}"
                if entity == "entrada":
                    return _save_entrada(user, fields) + f"\n\n{MENU_OPTIONS}"
                if entity == "cartao":
                    return _save_cartao(user, fields) + f"\n\n{MENU_OPTIONS}"
            except Exception as e:
                logger.error("Erro ao salvar %s: %s", entity, e)
                return f"❌ Erro ao salvar. Tente novamente.\n\n{MENU_OPTIONS}"

        if text in ("2", "n", "não", "nao", "cancelar"):
            clear_session(phone)
            return f"❌ Cancelado.\n\n{MENU_OPTIONS}"

        return _build_confirm(entity, fields)

    clear_session(phone)
    return welcome_message(user, phone, push_name)
