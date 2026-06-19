import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).parent / "catalogos" / "financeiro.json"
_catalog: dict = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def get_catalog() -> dict:
    return _catalog


# ── Prompt compacto (~180 tokens vs ~550 anteriores) ─────────────────────────

_SYSTEM = "Extrator de intenção financeira pt-BR. JSON puro, sem markdown."

_USER = (
    "Msg: {message}\n\n"
    '{"intent":"gasto|entrada|cartao|resumo|menu|desconhecido",'
    '"fields":{"descricao":str,"valor":float,"tipo_pagamento":"credito_avista|credito_parcelado|pix|emprestimo",'
    '"total_parcelas":int,"tipo_entrada":"salario|bonus|outros",'
    '"cartao_nome_hint":str,"responsavel_nome_hint":str}}\n\n'
    "Regras:\n"
    "intent: gasto→gastei/comprei/paguei | entrada→recebi/salário | cartao→novo/cadastrar cartão | resumo→saldo/extrato\n"
    "pgto: pix→pix/transf/ted | avista→à vista | parcelado→Nx/parcelado | emprestimo→empréstimo\n"
    "valor: '5x de 100'→valor=100,parcelas=5 | '1k'→1000 | 'R$49,90'→49.9\n"
    "cartao_nome_hint: nome do cartão mencionado (nubank,inter,itaú…) ou null\n"
    "responsavel_nome_hint: 'do João'→'João', 'pra mim'→null\n"
    "null em campos não mencionados"
)


def make_intent_messages(message: str) -> list:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER.replace("{message}", message)},
    ]
