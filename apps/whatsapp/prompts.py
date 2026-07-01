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
    '{"intent":"gasto|entrada|cartao|resumo|consulta|menu|desconhecido",'
    '"fields":{'
    '"descricao":str,"valor":float,'
    '"tipo_pagamento":"credito_avista|credito_parcelado|recorrente|pix|debito|ajuste_fatura",'
    '"total_parcelas":int,"tipo_entrada":"salario|bonus|outros",'
    '"cartao_nome_hint":str,"responsavel_nome_hint":str,'
    '"responsavel2_nome_hint":str,"pct_divisao":int,'
    '"categoria_hint":str,"data_compra_hint":str,'
    '"recorrente_flag":bool,"ajuste_tipo_hint":"desconto|adicao",'
    '"cartao_adicional_hint":bool,'
    '"consulta_tipo":"responsavel|cartao","mes_ano_hint":str}}\n\n'
    "Regras:\n"
    "intent: gasto→gastei/comprei/paguei/desconto ou ajuste na fatura | entrada→recebi/salário | "
    "cartao→cadastrar cartão | resumo→pergunta sobre 'eu/minha/meu' saldo ou quanto EU gastei, sem "
    "citar nome de pessoa nem de cartão | consulta→pergunta que cita o NOME de uma pessoa específica "
    "(ex: 'quanto a Ana gastou em julho') OU o nome de um CARTÃO específico (ex: 'total do cartão "
    "nubank em junho') — se não houver nome citado, é sempre resumo, nunca consulta\n"
    "IMPORTANTE: intent só pode ser gasto|entrada|cartao|resumo|consulta|menu|desconhecido — 'ajuste_fatura' "
    "NUNCA é um intent, é sempre um valor de tipo_pagamento dentro de intent='gasto'\n"
    "pgto: pix→pix/transf/ted | avista→à vista/no crédito | parcelado→Nx/parcelado | debito→débito/no débito | "
    "recorrente→assinatura/mensalidade/todo mês/recorrente | ajuste_fatura→desconto/estorno/ajuste na fatura\n"
    "valor: '5x de 100'→valor=500,parcelas=5 | '1k'→1000 | 'R$49,90'→49.9\n"
    "cartao_nome_hint: nome do cartão (nubank,inter,latam pass…) ou null\n"
    "responsavel_nome_hint: dono principal do gasto/consulta ('para o railan'→'railan', 'pra mim'→null, "
    "'da minha esposa'→ null se não souber o nome, use o termo dito ex:'esposa' só se não houver nome)\n"
    "responsavel2_nome_hint: segundo responsável se dividido ('dividido entre railan e pablo'→pablo)\n"
    "pct_divisao: % do responsavel1 (60/40→60, meio a meio→50, null se não dividido)\n"
    "categoria_hint: categoria do gasto pelo contexto (supermercado→Supermercado, lanche→Lanche, gasolina→Combustível…) ou null\n"
    "data_compra_hint: data de um gasto sendo registrado ('ontem', 'dia 15', '15/06', 'hoje') ou null\n"
    "recorrente_flag: true se pix/débito mencionado como recorrente/todo mês, senão null\n"
    "ajuste_tipo_hint: 'desconto' se abate/reduz a fatura, 'adicao' se soma/cobra a mais, senão null\n"
    "cartao_adicional_hint: true se menciona cartão adicional/extra, senão null\n"
    "consulta_tipo: só para intent=consulta — 'responsavel' se pergunta é sobre uma pessoa, "
    "'cartao' se é sobre um cartão\n"
    "mes_ano_hint: só para intent=consulta — mês perguntado como string ('julho', 'esse mês', "
    "'06/2026', 'mês passado') ou null (assume mês atual)\n"
    "null em campos não mencionados"
)


def make_intent_messages(message: str) -> list:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER.replace("{message}", message)},
    ]
