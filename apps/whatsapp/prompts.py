INTENT_SYSTEM = """Você é um assistente financeiro. Extraia a intenção e campos da mensagem em português.
Responda APENAS com JSON válido, sem markdown, sem explicações."""

INTENT_USER = """Analise a mensagem e retorne JSON:
{
  "intent": "gasto|entrada|cartao|resumo|menu|cancelar|desconhecido",
  "fields": {
    "descricao": "string ou null",
    "valor": numero_decimal_ou_null,
    "tipo_pagamento": "credito_avista|credito_parcelado|pix|emprestimo|null",
    "total_parcelas": numero_inteiro_ou_null,
    "tipo_entrada": "salario|bonus|outros|null",
    "cartao_nome_hint": "nome parcial do cartão mencionado ou null",
    "responsavel_nome_hint": "nome da pessoa mencionada como responsável ou null"
  }
}

Regras de intent:
- "gastei", "comprei", "paguei", "compras" → intent=gasto
- "recebi", "salário", "entrada" → intent=entrada
- "novo cartão", "cadastrar cartão" → intent=cartao
- "resumo", "extrato", "saldo" → intent=resumo
- "menu", "início", "voltar" → intent=menu
- "cancelar", "sair", "parar" → intent=cancelar

Regras de tipo_pagamento:
- parcelado / xN / NxM / em Nx / parcelas → credito_parcelado
- à vista / avista / crédito sem parcelamento → credito_avista
- pix / transferência / ted / doc → pix
- empréstimo → emprestimo

Regras de valor:
- "155 reias/reais" → 155.0
- "R$49,90" → 49.9
- "5x de 144" → valor=144.0 (valor por parcela), total_parcelas=5
- "1k" → 1000.0

Regras de cartao_nome_hint:
- Extraia qualquer nome de cartão mencionado: "latam pass", "nubank", "inter", "itaú", "elo"
- Se mencionar bandeira (elo, visa, master) sem nome, retorne a bandeira como hint
- Se não mencionar cartão, retorne null

Regras de responsavel_nome_hint:
- "do João", "da Maria", "do railan" → extraia o nome ("João", "Maria", "railan")
- "pra mim", "meu" → retorne null (não tem como saber quem é)
- Se não mencionar pessoa, retorne null

Mensagem: {message}"""


def make_intent_messages(message: str) -> list:
    return [
        {"role": "system", "content": INTENT_SYSTEM},
        {"role": "user", "content": INTENT_USER.format(message=message)},
    ]
