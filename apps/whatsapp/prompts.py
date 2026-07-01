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
    '"consulta_tipo":"responsavel|cartao|categoria|conta|investimento","mes_ano_hint":str,'
    '"conta_nome_hint":str,'
    '"serie_mensal":bool,"mes_ano_fim_hint":str,'
    '"resumo_metrica":"saldo|gastos|receitas|cartao|completo",'
    '"consulta_formato":"total|lista"}}\n\n'
    "Regras:\n"
    "intent: gasto→gastei/comprei/paguei/desconto ou ajuste na fatura | entrada→recebi/salário | "
    "cartao→cadastrar cartão | resumo→pergunta sobre 'eu/minha/meu' saldo/gasto/receita, sem citar nome "
    "de pessoa, cartão, categoria ou conta — pode ter mês específico ou mês a mês (ex: 'qual meu saldo em "
    "julho', 'meu saldo mês a mês até dezembro', 'meus gastos totais até dez') | consulta→pergunta que "
    "cita o NOME de uma pessoa (ex: 'quanto a Ana gastou em julho'), de um CARTÃO (ex: 'total do cartão "
    "nubank em junho'), de uma CATEGORIA (ex: 'quanto gastei em supermercado em julho'), de uma CONTA "
    "(ex: 'qual o saldo da minha conta nubank') ou pergunta sobre INVESTIMENTOS (ex: 'quanto tenho "
    "investido', 'saldo dos meus investimentos') — se não houver nome/tema citado, é sempre resumo, nunca "
    "consulta. REGRA CRÍTICA: se cartao_nome_hint, responsavel_nome_hint, categoria_hint ou "
    "conta_nome_hint for preenchido, OU a pergunta for sobre investimentos, o intent OBRIGATORIAMENTE é "
    "'consulta', nunca 'resumo'\n"
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
    "categoria_hint: categoria do gasto/consulta pelo contexto (supermercado→Supermercado, lanche→Lanche, "
    "gasolina→Combustível…) ou null\n"
    "conta_nome_hint: nome da conta bancária citada numa consulta de saldo (nubank, inter, c6…) ou null\n"
    "data_compra_hint: data de um gasto sendo registrado ('ontem', 'dia 15', '15/06', 'hoje') ou null\n"
    "recorrente_flag: true se pix/débito mencionado como recorrente/todo mês, senão null\n"
    "ajuste_tipo_hint: 'desconto' se abate/reduz a fatura, 'adicao' se soma/cobra a mais, senão null\n"
    "cartao_adicional_hint: true se menciona cartão adicional/extra, senão null\n"
    "consulta_tipo: só para intent=consulta — 'responsavel' (pessoa), 'cartao', 'categoria', 'conta' "
    "(saldo de conta bancária) ou 'investimento'\n"
    "mes_ano_hint: para intent=consulta OU resumo — mês perguntado como string ('julho', 'esse mês', "
    "'06/2026', 'mês passado'); se serie_mensal=true, é o mês INICIAL do período; null = mês atual\n"
    "serie_mensal: true se a pergunta pede quebra mês a mês / mensal / mês por mês / evolução "
    "('mês a mês', 'todo mês', 'mês por mês', 'de X até Y'), senão null\n"
    "mes_ano_fim_hint: só quando serie_mensal=true — mês FINAL do período citado ('até dez/2026', "
    "'até dezembro') como string, ou null se não citado (assume 12 meses a partir do mês inicial)\n"
    "resumo_metrica: só para intent=resumo — qual valor da visão mensal a pessoa quer: 'saldo' (saldo "
    "atual/quanto sobrou), 'gastos' (total gasto), 'receitas' (total recebido), 'cartao' (gastos totais "
    "nos cartões), ou 'completo' (saldo anterior + receitas + gastos + saldo atual + cartões, a visão "
    "inteira) se não especificar ou pedir 'resumo'/'extrato' geral\n"
    "consulta_formato: só para consulta_tipo=responsavel — 'lista' se pede os ITENS/lançamentos "
    "individuais (ex: 'quais são os gastos da Ana', 'lista de gastos do Pablo', 'quais gastos foram "
    "lançados pra Daniela', 'me mostra os gastos dela', 'detalha os gastos'), 'total' se pergunta só o "
    "valor total (ex: 'quanto a Ana gastou', 'qual o total') — 'total' se não especificar\n"
    "null em campos não mencionados"
)


_CONTEXTO = (
    "\n\nContexto da última consulta (use só se esta mensagem for uma continuação/pergunta de "
    "acompanhamento — ex: só um nome, 'e da/do X', 'e em [mês]', 'e o [cartão]', 'e só os gastos?'; "
    "NÃO use para registrar gasto/entrada/cartão novo. Se a mensagem perguntar sobre 'eu/minha/meu' "
    "(sem nome/tema específico), o intent é sempre 'resumo' — mas ainda pode reaproveitar mês/período/"
    "métrica do contexto se fizer sentido como continuação, só NUNCA reaproveite cartao_nome_hint/"
    "responsavel_nome_hint/categoria_hint/conta_nome_hint num resumo, pois resumo é sempre sobre o "
    "próprio usuário): {context}\n"
    "Exemplo 1 (troca de pessoa) — contexto tem responsavel_nome_hint='pablo', serie_mensal=true, "
    "mes_ano_fim_hint='dez/2026', mensagem é só 'e da daniela?'. Resposta "
    "(SEMPRE no formato intent + fields aninhado, nunca campos soltos):\n"
    '{"intent":"consulta","fields":{"responsavel_nome_hint":"daniela","consulta_tipo":"responsavel",'
    '"serie_mensal":true,"mes_ano_hint":null,"mes_ano_fim_hint":"dez/2026"}}\n'
    "Exemplo 2 (troca de métrica no resumo) — contexto tem resumo_metrica='saldo', serie_mensal=true, "
    "mes_ano_fim_hint='dez/2026', mensagem é só 'e os gastos?'. Resposta:\n"
    '{"intent":"resumo","fields":{"resumo_metrica":"gastos","serie_mensal":true,"mes_ano_hint":null,'
    '"mes_ano_fim_hint":"dez/2026"}}'
)


def make_intent_messages(message: str, context: dict | None = None) -> list:
    user_content = _USER.replace("{message}", message)
    if context:
        user_content += _CONTEXTO.replace("{context}", json.dumps(context, ensure_ascii=False))
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]
