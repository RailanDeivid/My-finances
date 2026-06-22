import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).parent / "catalogos" / "financeiro.json"
_catalog: dict = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def get_catalog() -> dict:
    return _catalog


# ── Prompt compacto (~250 tokens) ────────────────────────────────────────────

_SYSTEM = "Extrator de intenção financeira pt-BR. JSON puro, sem markdown."

_USER = (
    "Msg: {message}\n\n"
    '{"intent":"gasto|entrada|cartao|resumo|menu|desconhecido",'
    '"fields":{'
    '"descricao":str,"valor":float,'
    '"tipo_pagamento":"credito_avista|credito_parcelado|pix|emprestimo|debito",'
    '"total_parcelas":int,"tipo_entrada":"salario|bonus|outros",'
    '"cartao_nome_hint":str,"responsavel_nome_hint":str,'
    '"responsavel2_nome_hint":str,"pct_divisao":int,'
    '"categoria_hint":str,"data_compra_hint":str}}\n\n'
    "Regras:\n"
    "intent: gasto→gastei/comprei/paguei | entrada→recebi/salário | cartao→cadastrar cartão | resumo→saldo/extrato\n"
    "pgto: pix→pix/transf/ted | avista→à vista/no crédito | parcelado→Nx/parcelado | debito→débito/no débito | emprestimo→empréstimo\n"
    "valor: '5x de 100'→valor=500,parcelas=5 | '1k'→1000 | 'R$49,90'→49.9\n"
    "cartao_nome_hint: nome do cartão (nubank,inter,latam pass…) ou null\n"
    "responsavel_nome_hint: dono principal do gasto ('para o railan'→'railan', 'pra mim'→null)\n"
    "responsavel2_nome_hint: segundo responsável se dividido ('dividido entre railan e pablo'→pablo)\n"
    "pct_divisao: % do responsavel1 (60/40→60, meio a meio→50, null se não dividido)\n"
    "categoria_hint: categoria do gasto pelo contexto (supermercado→Supermercado, lanche→Lanche, gasolina→Combustível…) ou null\n"
    "data_compra_hint: data mencionada como string ('ontem', 'dia 15', '15/06', 'hoje') ou null\n"
    "null em campos não mencionados"
)


def make_intent_messages(message: str) -> list:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER.replace("{message}", message)},
    ]
