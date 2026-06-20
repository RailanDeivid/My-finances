import json
import logging
import random
import time
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Sum
from openai import OpenAI

from apps.gastos.models import Cartao, Entrada, Gasto, Responsavel
from .prompts import get_catalog, make_intent_messages
from .session import clear_session, get_session, is_first_contact_today, save_session

logger = logging.getLogger(__name__)
_llm = OpenAI(api_key=settings.OPENAI_KEY)
_catalog = get_catalog()


def _build_map(section: str) -> dict:
    """Constrói dict alias→chave a partir do catalog (arrays diretos)."""
    result = {}
    for key, aliases in _catalog[section].items():
        for alias in aliases:
            result[alias.lower()] = key
    return result


# ── Texto fixo ────────────────────────────────────────────────────────────────

MENU_OPTIONS = (
    "O que deseja fazer?\n\n"
    "1️⃣  Registrar gasto\n"
    "2️⃣  Registrar entrada\n"
    "3️⃣  Ver resumo do mês\n"
    "4️⃣  Cadastrar cartão\n\n"
    "_Ou me conte diretamente, ex: \"gastei 50 no mercado no pix\"_"
)

MENU_TEXT = MENU_OPTIONS  # compat — usado em confirmações e erros

_MSG_SPLIT = "\x00SPLIT\x00"  # separador interno para envio em 2 mensagens

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
    now = date.today()
    hora = __import__("datetime").datetime.now().hour
    dia_semana = now.weekday()  # 0=seg … 6=dom

    if dia_semana >= 5:
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
    # Prioridade: pushName do WhatsApp → first_name do Django → username
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
    "1": "credito_avista", "2": "credito_parcelado", "3": "pix", "4": "emprestimo",
    **_build_map("tipo_pagamento"),
    "credito_avista": "credito_avista", "credito_parcelado": "credito_parcelado",
}

TIPO_ENT_MAP = {
    "1": "salario", "2": "bonus", "3": "outros",
    **_build_map("tipo_entrada"),
}

BANDEIRA_MAP = {
    "1": "visa",        "visa": "visa",
    "2": "mastercard",  "mastercard": "mastercard",
    "3": "elo",         "elo": "elo",
    "4": "amex",        "amex": "amex", "american express": "amex",
    "5": "outro",       "outro": "outro", "outros": "outro",
}

TIPO_PAG_LABEL = {
    "credito_avista": "Crédito à vista",
    "credito_parcelado": "Crédito parcelado",
    "pix": "Pix / Transferência",
    "emprestimo": "Empréstimo",
}

TIPO_ENT_LABEL = {"salario": "Salário", "bonus": "Bônus", "outros": "Outros"}
BANDEIRA_LABEL = {
    "visa": "Visa", "mastercard": "Mastercard", "elo": "Elo",
    "amex": "American Express", "outro": "Outro",
}

# ── Passos por entidade ───────────────────────────────────────────────────────

GASTO_STEPS = ["descricao", "valor", "tipo_pagamento", "total_parcelas", "cartao_id", "responsavel_id"]
ENTRADA_STEPS = ["tipo_entrada", "valor", "descricao_entrada", "responsavel_id"]
CARTAO_STEPS = ["nome_cartao", "bandeira", "limite", "dia_fechamento"]

QUESTIONS = {
    "descricao":       "📝 Qual a descrição?\n_(ex: Netflix, Mercado, Conta de luz)_",
    "valor":           "💵 Qual o valor? _(ex: 49,90)_",
    "tipo_pagamento":  "💳 Tipo de pagamento?\n\n1 · Crédito à vista\n2 · Crédito parcelado\n3 · Pix / Transferência\n4 · Empréstimo",
    "total_parcelas":  "🔢 Quantas parcelas?",
    "tipo_entrada":    "💰 Tipo de entrada?\n\n1 · Salário\n2 · Bônus\n3 · Outros",
    "descricao_entrada": "📝 Descrição? _(ou *0* para pular)_",
    "nome_cartao":     "📛 Nome do cartão? _(ex: Nubank, Inter, C6)_",
    "bandeira":        "💳 Bandeira?\n\n1 · Visa\n2 · Mastercard\n3 · Elo\n4 · American Express\n5 · Outro",
    "limite":          "💰 Limite do cartão? _(ou *0* para pular)_",
    "dia_fechamento":  "📅 Dia de fechamento da fatura? _(ou *0* para pular)_",
}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _brl(value) -> str:
    v = float(value)
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _should_skip(step: str, fields: dict) -> bool:
    if step == "total_parcelas":
        return fields.get("tipo_pagamento") != "credito_parcelado"
    if step == "cartao_id":
        return fields.get("tipo_pagamento") not in {"credito_avista", "credito_parcelado"}
    return False


def _question_for_step(step: str, user, session: dict) -> str | None:
    if step == "cartao_id":
        cartoes = list(Cartao.objects.filter(user=user, ativo=True).values("id", "nome", "bandeira"))
        if not cartoes:
            return None
        opts = "\n".join(f"{i+1} · {c['nome']}" for i, c in enumerate(cartoes))
        session["options_map"]["cartao_id"] = {
            str(i+1): c["id"] for i, c in enumerate(cartoes)
        }
        # índice nome→id e bandeira→id para match por texto
        session["options_map"]["cartao_nome_map"] = {
            c["nome"].lower(): c["id"] for c in cartoes
        }
        session["options_map"]["cartao_bandeira_map"] = {}
        for c in cartoes:
            b = c.get("bandeira", "").lower()
            if b and b not in session["options_map"]["cartao_bandeira_map"]:
                session["options_map"]["cartao_bandeira_map"][b] = c["id"]
        return f"💳 Qual cartão?\n\n{opts}"

    if step == "responsavel_id":
        resps = list(Responsavel.objects.filter(user=user, ativo=True).values("id", "nome"))
        if not resps:
            return None
        opts = "\n".join(f"{i+1} · {r['nome']}" for i, r in enumerate(resps))
        session["options_map"]["responsavel_id"] = {str(i+1): r["id"] for i, r in enumerate(resps)}
        session["options_map"]["resp_nome_map"] = {
            r["nome"].lower(): r["id"] for r in resps
        }
        return f"👤 Responsável?\n\n{opts}"

    return QUESTIONS.get(step)


def _parse_field(step: str, text: str, session: dict):
    """Retorna (ok: bool, value). value=None significa campo pulado (opcional)."""
    t = text.strip()

    if step == "descricao":
        return True, t if t else (False, None)

    if step == "valor":
        normalized = t.replace(".", "").replace(",", ".")
        try:
            v = float(normalized)
            return (v >= 0, v) if v >= 0 else (False, None)
        except ValueError:
            return False, None

    if step == "tipo_pagamento":
        val = TIPO_PAG_MAP.get(t.lower())
        return (True, val) if val else (False, None)

    if step == "total_parcelas":
        try:
            n = int(t)
            return (True, n) if 1 <= n <= 120 else (False, None)
        except ValueError:
            return False, None

    if step == "cartao_id":
        opts = session.get("options_map", {})
        # por número
        if t in opts.get("cartao_id", {}):
            return True, opts["cartao_id"][t]
        # por nome exato ou parcial
        t_low = t.lower()
        nome_map = opts.get("cartao_nome_map", {})
        for nome, pk in nome_map.items():
            if t_low in nome or nome in t_low:
                return True, pk
        # por bandeira (ex: "elo", "nubank" como bandeira)
        bandeira_map = opts.get("cartao_bandeira_map", {})
        for bandeira, pk in bandeira_map.items():
            if t_low in bandeira or bandeira in t_low:
                return True, pk
        return False, None

    if step == "responsavel_id":
        opts = session.get("options_map", {})
        if t in opts.get("responsavel_id", {}):
            return True, opts["responsavel_id"][t]
        t_low = t.lower()
        resp_map = opts.get("resp_nome_map", {})
        for nome, pk in resp_map.items():
            if t_low in nome or nome in t_low:
                return True, pk
        return False, None

    if step == "tipo_entrada":
        val = TIPO_ENT_MAP.get(t.lower())
        return (True, val) if val else (False, None)

    if step == "descricao_entrada":
        return True, (None if t == "0" else t)

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
        "valor": "❌ Valor inválido. Digite somente o número. _(ex: 150 ou 49,90)_",
        "tipo_pagamento": "❌ Digite 1, 2, 3 ou 4.",
        "total_parcelas": "❌ Digite um número entre 1 e 120.",
        "tipo_entrada": "❌ Digite 1, 2 ou 3.",
        "bandeira": "❌ Digite 1, 2, 3, 4 ou 5.",
        "cartao_id": "❌ Digite o número correspondente ao cartão.",
        "responsavel_id": "❌ Digite o número correspondente ao responsável.",
        "limite": "❌ Digite o valor ou *0* para pular.",
        "dia_fechamento": "❌ Digite o dia (1-31) ou *0* para pular.",
    }
    return msgs.get(step, "❌ Valor inválido. Tente novamente.")


# ── Confirmação ───────────────────────────────────────────────────────────────

def _build_confirm(entity: str, fields: dict) -> str:
    lines = ["📋 *Confirmar?*\n"]
    if entity == "gasto":
        parcelas_txt = f" · {fields['total_parcelas']}x" if fields.get("total_parcelas") else ""
        cartao_txt = f" · {fields.get('cartao_nome', '')}" if fields.get("cartao_nome") else ""
        lines += [
            f"• Descrição: {fields.get('descricao', '')}",
            f"• Valor: {_brl(fields.get('valor', 0))}{parcelas_txt}",
            f"• Tipo: {TIPO_PAG_LABEL.get(fields.get('tipo_pagamento', ''), '')}{cartao_txt}",
            f"• Responsável: {fields.get('responsavel_nome', '')}",
        ]
    elif entity == "entrada":
        desc_txt = f"\n• Descrição: {fields['descricao_entrada']}" if fields.get("descricao_entrada") else ""
        lines += [
            f"• Tipo: {TIPO_ENT_LABEL.get(fields.get('tipo_entrada', ''), '')}",
            f"• Valor: {_brl(fields.get('valor', 0))}{desc_txt}",
            f"• Responsável: {fields.get('responsavel_nome', '')}",
        ]
    elif entity == "cartao":
        limite_txt = f"\n• Limite: {_brl(fields['limite'])}" if fields.get("limite") else ""
        fech_txt = f"\n• Fechamento: dia {int(fields['dia_fechamento'])}" if fields.get("dia_fechamento") else ""
        lines += [
            f"• Nome: {fields.get('nome_cartao', '')}",
            f"• Bandeira: {BANDEIRA_LABEL.get(fields.get('bandeira', ''), '')}{limite_txt}{fech_txt}",
        ]
    lines += ["", "1 · ✅ Confirmar\n2 · ❌ Cancelar"]
    return "\n".join(lines)


# ── Salvamento ────────────────────────────────────────────────────────────────

def _save_gasto(user, fields: dict) -> str:
    from apps.gastos.views import _recalcular_saldos_a_partir

    tipo = fields["tipo_pagamento"]
    n = fields.get("total_parcelas") if tipo == "credito_parcelado" else None
    cartao = Cartao.objects.filter(id=fields["cartao_id"]).first() if fields.get("cartao_id") else None
    responsavel = Responsavel.objects.filter(id=fields["responsavel_id"]).first() if fields.get("responsavel_id") else None
    hoje = date.today()
    descricao = fields["descricao"]
    valor = Decimal(str(fields["valor"]))

    if n:
        data_inicio = date(hoje.year, hoje.month, 1)
        Gasto.objects.create(
            descricao=f"{descricao} (1/{n})", valor_total=valor, tipo_pagamento=tipo,
            cartao=cartao, responsavel=responsavel, data_compra=data_inicio,
            total_parcelas=n, user=user,
        )
        for i in range(2, n + 1):
            Gasto.objects.create(
                descricao=f"{descricao} ({i}/{n})", valor_total=valor, tipo_pagamento=tipo,
                cartao=cartao, responsavel=responsavel,
                data_compra=data_inicio + relativedelta(months=i - 1),
                total_parcelas=n, user=user,
            )
        _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year, user)
        tipo_str = f"parcelado em {n}x"
    else:
        Gasto.objects.create(
            descricao=descricao, valor_total=valor, tipo_pagamento=tipo,
            cartao=cartao, responsavel=responsavel, data_compra=hoje, user=user,
        )
        _recalcular_saldos_a_partir(hoje.month, hoje.year, user)
        tipo_str = TIPO_PAG_LABEL.get(tipo, tipo)

    cartao_txt = f" · {cartao.nome}" if cartao else ""
    return f"✅ *Gasto registrado!*\n{descricao} · {_brl(valor)} · {tipo_str}{cartao_txt}"


def _save_entrada(user, fields: dict) -> str:
    from apps.gastos.views import _recalcular_saldos_a_partir

    responsavel = Responsavel.objects.filter(id=fields["responsavel_id"]).first() if fields.get("responsavel_id") else None
    valor = Decimal(str(fields["valor"]))
    hoje = date.today()

    Entrada.objects.create(
        tipo=fields["tipo_entrada"],
        descricao=fields.get("descricao_entrada") or "",
        valor=valor, data=hoje, responsavel=responsavel, user=user,
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


# ── Resumo do mês ─────────────────────────────────────────────────────────────

def _resumo(user) -> str:
    hoje = date.today()
    mes, ano = hoje.month, hoje.year
    meses_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

    total_ent = Entrada.objects.filter(
        user=user, data__month=mes, data__year=ano
    ).exclude(tipo="saldo_anterior").aggregate(t=Sum("valor"))["t"] or Decimal("0")

    total_gas = Gasto.objects.filter(
        user=user, data_compra__month=mes, data_compra__year=ano
    ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")

    saldo = total_ent - total_gas

    saldo_icon = "📈" if saldo >= 0 else "📉"
    saldo_color = "+" if saldo >= 0 else ""

    return (
        f"📊 *{meses_pt[mes-1]}/{ano}*\n\n"
        f"💰 Receitas:  {_brl(total_ent)}\n"
        f"💸 Gastos:    {_brl(total_gas)}\n"
        f"{saldo_icon} Saldo:     {saldo_color}{_brl(abs(saldo))}"
        + (" _(negativo)_" if saldo < 0 else "")
    )


# ── Preços por modelo (USD por token) ────────────────────────────────────────

_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":        (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4o":             (5.00 / 1_000_000, 15.00 / 1_000_000),
    "gpt-4-turbo":        (10.00 / 1_000_000, 30.00 / 1_000_000),
    "gpt-3.5-turbo":      (0.50 / 1_000_000, 1.50 / 1_000_000),
}


def _save_llm_usage(user, operation: str, model: str, usage, latency_ms: int) -> None:
    try:
        from .models import LLMUsage
        price_in, price_out = _MODEL_PRICING.get(model, (0.0, 0.0))
        cost = Decimal(str(usage.prompt_tokens * price_in + usage.completion_tokens * price_out))
        LLMUsage.objects.create(
            user=user,
            operation=operation,
            model=model,
            tokens_input=usage.prompt_tokens,
            tokens_output=usage.completion_tokens,
            tokens_total=usage.total_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.warning("Falha ao salvar LLMUsage: %s", e)


# ── LLM ───────────────────────────────────────────────────────────────────────

def _call_llm_intent(message: str, user=None) -> dict:
    try:
        t0 = time.monotonic()
        resp = _llm.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=make_intent_messages(message),
            response_format={"type": "json_object"},
            temperature=float(settings.OPENAI_TEMPERATURE),
            max_tokens=300,
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
    return None  # todos coletados


def process_message(phone: str, user, text: str, push_name: str = "") -> str:
    text = text.strip()
    text_lower = text.lower()

    # ── Cancelar em qualquer estado ──────────────────────────────────────────
    if text_lower in CANCEL_WORDS:
        clear_session(phone)
        return f"Ok, operação cancelada. ✋\n\n{MENU_OPTIONS}"

    session = get_session(phone)
    state = session["state"]

    # ── MENU ─────────────────────────────────────────────────────────────────
    if state == "MENU":
        direct = {"1": "gasto", "2": "entrada", "3": "cartao", "4": "resumo"}.get(text)
        if direct == "resumo":
            clear_session(phone)
            return _resumo(user)

        if direct:
            entity = direct
            extracted_fields = {}
        else:
            # NLP
            result = _call_llm_intent(text, user=user)
            intent = result.get("intent", "desconhecido")

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

        # Tenta resolver cartão pelo hint antes de montar a sessão
        cartao_hint = extracted_fields.pop("cartao_nome_hint", None)
        if cartao_hint and entity == "gasto":
            cartoes = list(Cartao.objects.filter(user=user, ativo=True).values("id", "nome", "bandeira"))
            hint_low = cartao_hint.lower()
            for c in cartoes:
                if hint_low in c["nome"].lower() or c["nome"].lower() in hint_low:
                    extracted_fields["cartao_id"] = c["id"]
                    extracted_fields["cartao_nome"] = c["nome"]
                    break
            if "cartao_id" not in extracted_fields:
                for c in cartoes:
                    if hint_low in c.get("bandeira", "").lower():
                        extracted_fields["cartao_id"] = c["id"]
                        extracted_fields["cartao_nome"] = c["nome"]
                        break

        # Tenta resolver responsável pelo hint
        resp_hint = extracted_fields.pop("responsavel_nome_hint", None)
        if resp_hint:
            resps = list(Responsavel.objects.filter(user=user, ativo=True).values("id", "nome"))
            hint_low = resp_hint.lower()
            for r in resps:
                if hint_low in r["nome"].lower() or r["nome"].lower() in hint_low:
                    extracted_fields["responsavel_id"] = r["id"]
                    extracted_fields["responsavel_nome"] = r["nome"]
                    break

        session = {
            "state": "COLLECTING",
            "entity": entity,
            "fields": extracted_fields,
            "step": None,
            "options_map": {},
        }

        # avança para o primeiro passo não preenchido
        first_step = _next_step(entity, extracted_fields)
        if not first_step:
            # LLM preencheu tudo — pede confirmação
            session["state"] = "CONFIRMING"
            save_session(phone, session)
            return _build_confirm(entity, extracted_fields)

        q = _question_for_step(first_step, user, session)
        if q is None:
            # campo dinâmico sem dados (ex: sem cartões) → pula
            extracted_fields[first_step] = None
            first_step = _next_step(entity, extracted_fields, after=first_step)

        session["step"] = first_step
        save_session(phone, session)

        intro = {"gasto": "📝 *Novo gasto*", "entrada": "💰 *Nova entrada*", "cartao": "💳 *Novo cartão*"}
        return f"{intro[entity]}\n\n{_question_for_step(first_step, user, session) or ''}"

    # ── COLLECTING ───────────────────────────────────────────────────────────
    if state == "COLLECTING":
        step = session["step"]
        entity = session["entity"]
        fields = session["fields"]

        ok, value = _parse_field(step, text, session)
        if not ok:
            save_session(phone, session)  # preserva options_map
            return _error_for_step(step)

        # guarda nome legível para cartão/responsável na confirmação
        if step == "cartao_id" and value is not None:
            cartao = Cartao.objects.filter(id=value).first()
            if cartao:
                fields["cartao_nome"] = cartao.nome
        if step == "responsavel_id" and value is not None:
            resp = Responsavel.objects.filter(id=value).first()
            if resp:
                fields["responsavel_nome"] = resp.nome

        fields[step] = value
        session["fields"] = fields

        next_step = _next_step(entity, fields, after=step)

        # pula passos dinâmicos sem dados disponíveis
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

    # fallback
    clear_session(phone)
    return welcome_message(user, phone, push_name)
