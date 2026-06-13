# Meus Gastos

App web pessoal de controle de gastos com cartões de crédito/débito.
Permite registrar gastos de múltiplos responsáveis (ex: mãe, irmão) em múltiplos cartões,
com suporte a parcelamento, categorias, datas de fechamento e dashboard de resumo.

## Como rodar o projeto

1. Clone o repositório
2. Copie `.env.example` para `.env` e configure as variáveis
3. Execute: `docker-compose up --build`
4. Acesse o app: http://localhost:8001
5. Painel admin: http://localhost:8001/admin

### Carregar dados iniciais

```bash
docker-compose exec web python manage.py loaddata responsaveis_iniciais
docker-compose exec web python manage.py loaddata categorias_iniciais
```

### Criar superusuário

```bash
docker-compose exec web python manage.py createsuperuser
```

## Rodando localmente (sem Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edite o .env com DB_HOST=localhost
python manage.py migrate
python manage.py loaddata responsaveis_iniciais categorias_iniciais
python manage.py createsuperuser
python manage.py runserver
```

## Funcionalidades

- **Dashboard** — resumo mensal com gráficos de pizza (categorias) e barras (evolução)
- **Gastos** — listagem completa com filtros por mês, responsável, cartão, categoria e tipo
- **Cartões** — visão agrupada por cartão com indicador de fatura mensal
- **Parcelamento** — gera parcelas automaticamente para compras parceladas
- **Responsáveis** — CRUD para gerenciar quem realizou o gasto
- **Categorias** — CRUD para classificar os gastos

## Portas

| Serviço | Porta |
|---------|-------|
| App web | 8001  |
| Banco (PostgreSQL) | 5433 |

