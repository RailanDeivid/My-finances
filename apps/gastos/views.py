import json
import re
import uuid
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import update_session_auth_hash
from django.db.models import Sum, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
)
from django.contrib import messages

from django.shortcuts import get_object_or_404
from .models import Gasto, Cartao, Responsavel, Categoria, Entrada, FaturaPaga, Conta, PagamentoFeito, Investimento, InvestimentoHistorico
from .forms import GastoForm, CartaoForm, ResponsavelForm, CategoriaForm, EntradaForm, ContaForm, PerfilForm, SenhaForm, InvestimentoForm, InvestimentoAtualizarSaldoForm


def _mes_ano_from_request(request):
    hoje = date.today()
    try:
        mes = int(request.GET.get("mes", hoje.month))
        ano = int(request.GET.get("ano", hoje.year))
        if not (1 <= mes <= 12):
            mes = hoje.month
    except (ValueError, TypeError):
        mes, ano = hoje.month, hoje.year
    return mes, ano


def _impacto_q(user):
    """Q que representa todos os gastos que impactam financeiramente um usuário:
    os próprios (responsável principal) + os atribuídos por outros usuários."""
    return (
        Q(user=user, responsavel__is_principal=True) |
        (Q(responsavel__usuario_vinculado=user) & ~Q(user=user))
    )


def _calcular_saldo_mes(mes, ano, user=None):
    qs_gasto = Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)
    qs_entrada = Entrada.objects.filter(data__month=mes, data__year=ano)
    if user is not None:
        qs_gasto = qs_gasto.filter(_impacto_q(user))
        qs_entrada = qs_entrada.filter(user=user)
    total_gastos = qs_gasto.aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
    total_entradas = qs_entrada.aggregate(t=Sum("valor"))["t"] or Decimal("0")
    return total_entradas, total_gastos, total_entradas - total_gastos


def _auto_saldo_anterior(mes, ano, user=None):
    ref_ant = date(ano, mes, 1) - relativedelta(months=1)
    mes_ant, ano_ant = ref_ant.month, ref_ant.year

    total_entradas, total_gastos, saldo = _calcular_saldo_mes(mes_ant, ano_ant, user)

    if total_gastos > 0 or total_entradas != Decimal("0"):
        lookup = {"tipo": "saldo_anterior", "data": date(ano, mes, 1), "auto_gerada": True}
        if user is not None:
            lookup["user"] = user
        Entrada.objects.update_or_create(
            **lookup,
            defaults={
                "descricao": f"Saldo de {ref_ant.strftime('%b/%Y')}",
                "valor": saldo,
            },
        )


def _recalcular_saldos_a_partir(mes, ano, user=None):
    prox = date(ano, mes, 1) + relativedelta(months=1)

    while True:
        qs = Entrada.objects.filter(tipo="saldo_anterior", auto_gerada=True, data=prox)
        if user is not None:
            qs = qs.filter(user=user)
        try:
            entrada = qs.get()
        except Entrada.DoesNotExist:
            break

        ref_ant = prox - relativedelta(months=1)
        total_entradas, total_gastos, saldo = _calcular_saldo_mes(ref_ant.month, ref_ant.year, user)

        entrada.valor = saldo
        entrada.descricao = f"Saldo de {ref_ant.strftime('%b/%Y')}"
        entrada.save(update_fields=["valor", "descricao"])

        prox += relativedelta(months=1)


class UserOwnedMixin(LoginRequiredMixin):
    """Restringe get_queryset() ao usuário autenticado em todas as CBVs."""
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


# ── Dashboard ────────────────────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "gastos/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano

        # Garante que todo usuário tem um responsável principal
        if not Responsavel.objects.filter(user=user, is_principal=True).exists():
            nome = user.get_full_name().strip() or user.username
            Responsavel.objects.get_or_create(
                user=user,
                is_principal=True,
                defaults={"nome": nome, "ativo": True},
            )

        _auto_saldo_anterior(mes, ano, user)

        ctx["anos_lista"] = list(range(2026, 2037))

        # Filtros
        responsavel_id = self.request.GET.get("responsavel")
        cartao_id = self.request.GET.get("cartao")
        tipo_filtro = self.request.GET.get("tipo")
        categoria_id = self.request.GET.get("categoria")

        ctx["responsaveis_lista"] = Responsavel.objects.filter(ativo=True, user=user)
        ctx["cartoes_lista"] = Cartao.objects.filter(ativo=True, user=user)
        ctx["categorias_lista"] = Categoria.objects.filter(ativo=True, user=user)
        ctx["tipos_lista"] = Gasto.TIPO_PAGAMENTO_CHOICES
        ctx["filtro_responsavel"] = responsavel_id
        ctx["filtro_cartao"] = cartao_id
        ctx["filtro_tipo"] = tipo_filtro
        ctx["filtro_categoria"] = categoria_id

        # Gastos do mês do próprio user
        gastos_mes = Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
        if responsavel_id:
            gastos_mes = gastos_mes.filter(responsavel_id=responsavel_id)
        if cartao_id:
            gastos_mes = gastos_mes.filter(cartao_id=cartao_id)
        if tipo_filtro:
            gastos_mes = gastos_mes.filter(tipo_pagamento=tipo_filtro)
        if categoria_id:
            gastos_mes = gastos_mes.filter(categoria_id=categoria_id)

        # Gastos atribuídos ao user (onde o responsavel está vinculado a este login)
        gastos_atribuidos = Gasto.objects.filter(
            responsavel__usuario_vinculado=user,
            data_compra__month=mes, data_compra__year=ano,
        ).exclude(user=user).select_related("responsavel", "cartao", "categoria", "user")

        entradas_mes = Entrada.objects.filter(user=user, data__month=mes, data__year=ano)
        # Gastos que impactam este usuário: próprios (principal) + atribuídos por outros
        gastos_mes_proprios = Gasto.objects.filter(
            _impacto_q(user),
            data_compra__month=mes,
            data_compra__year=ano,
        )

        total_entradas = entradas_mes.aggregate(t=Sum("valor"))["t"] or Decimal("0")
        total_gasto = gastos_mes_proprios.aggregate(t=Sum("valor_total"))["t"] or Decimal("0")

        contas = Conta.objects.filter(user=user, ativo=True)
        total_contas = contas.aggregate(t=Sum("saldo_atual"))["t"] or Decimal("0")
        saldo = total_contas - total_gasto

        ctx["total_entradas"] = total_entradas
        ctx["total_gasto"] = total_gasto
        ctx["saldo"] = saldo
        ctx["qtd_gastos"] = gastos_mes_proprios.count()

        # Tabela por responsável e por cartão — inclui atribuídos
        gastos_mes_base = Gasto.objects.filter(_impacto_q(user), data_compra__month=mes, data_compra__year=ano)
        ctx["tabela_por_responsavel"] = (
            gastos_mes_base.values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_cartao"] = (
            gastos_mes_base.filter(cartao__isnull=False)
            .values("cartao__id", "cartao__nome", "cartao__cor", "cartao__tipo")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_emprestimo"] = (
            gastos_mes_base.filter(tipo_pagamento="emprestimo")
            .values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_pix"] = (
            gastos_mes_base.filter(tipo_pagamento="pix")
            .values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["faturas_pagas_ids"] = set(
            FaturaPaga.objects.filter(user=user, mes=mes, ano=ano)
            .values_list("cartao_id", flat=True)
        )
        ctx["pagamentos_pix_ids"] = set(
            PagamentoFeito.objects.filter(user=user, mes=mes, ano=ano, tipo="pix")
            .values_list("responsavel_id", flat=True)
        )
        ctx["pagamentos_emp_ids"] = set(
            PagamentoFeito.objects.filter(user=user, mes=mes, ano=ano, tipo="emprestimo")
            .values_list("responsavel_id", flat=True)
        )

        ctx["contas"] = contas
        ctx["total_contas"] = total_contas

        # Investimentos (independente de filtro de período)
        investimentos_dash = list(Investimento.objects.filter(user=user, liquidado=False).select_related("conta"))
        ctx["investimentos_dash"] = investimentos_dash
        ctx["inv_total_atual"] = sum(i.saldo_atual for i in investimentos_dash)

        # Gráfico de evolução mensal dos investimentos no dashboard (carry-forward + barras)
        from collections import OrderedDict
        MESES_PT_D = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        todos_inv    = list(Investimento.objects.filter(user=user))
        inv_ids_dash = [i.pk for i in todos_inv]
        hist_dash = InvestimentoHistorico.objects.filter(
            investimento_id__in=inv_ids_dash
        ).order_by("data_movimentacao").values("investimento_id", "valor_novo", "diferenca", "tipo", "data_movimentacao")

        meses_saldo  = OrderedDict()
        aportes_d    = {}   # {chave: total}
        saques_d     = {}   # {chave: total}
        for r in hist_dash:
            chave = (r["data_movimentacao"].year, r["data_movimentacao"].month)
            if chave not in meses_saldo:
                meses_saldo[chave] = {}
            meses_saldo[chave][r["investimento_id"]] = float(r["valor_novo"])
            tipo = r.get("tipo") or "rendimento"
            dif  = float(r["diferenca"])
            if tipo in ("aporte", "inicial"):
                aportes_d[chave] = aportes_d.get(chave, 0) + max(0, dif)
            elif tipo == "saque":
                saques_d[chave] = saques_d.get(chave, 0) + abs(min(0, dif))

        dash_labels, dash_dados, dash_aportes_bar, dash_saques_bar = [], [], [], []
        if meses_saldo:
            saldo_acum_d = {}
            primeiro_d   = min(meses_saldo.keys())
            ultimo_d     = (date.today().year, date.today().month)
            cur = date(primeiro_d[0], primeiro_d[1], 1)
            end = date(ultimo_d[0], ultimo_d[1], 1)
            while cur <= end:
                chave = (cur.year, cur.month)
                if chave in meses_saldo:
                    saldo_acum_d.update(meses_saldo[chave])
                dash_labels.append(f"{MESES_PT_D[cur.month-1]}/{cur.year}")
                dash_dados.append(round(sum(saldo_acum_d.values()), 2))
                dash_aportes_bar.append(round(aportes_d.get(chave, 0), 2))
                dash_saques_bar.append(round(saques_d.get(chave, 0), 2))
                cur += relativedelta(months=1)

        ctx["dash_inv_labels"]      = json.dumps(dash_labels)
        ctx["dash_inv_dados"]       = json.dumps(dash_dados)
        ctx["dash_inv_aportes_bar"] = json.dumps(dash_aportes_bar)
        ctx["dash_inv_saques_bar"]  = json.dumps(dash_saques_bar)

        # Rosca — distribuição por tipo (investimentos ativos no dash)
        from collections import defaultdict
        LABEL_MAP_D = {
            "renda_fixa":        "Renda Fixa",
            "renda_variavel":    "Renda Variável",
            "fundo_imobiliario": "Fundo Imobiliário",
        }
        tipo_dash = defaultdict(float)
        for inv in investimentos_dash:
            tipo_dash[LABEL_MAP_D.get(inv.tipo_investimento, inv.tipo_investimento)] += float(inv.saldo_atual)
        ctx["dash_rosca_labels"] = json.dumps(list(tipo_dash.keys()))
        ctx["dash_rosca_dados"]  = json.dumps([round(v, 2) for v in tipo_dash.values()])

        # Por categoria (gráfico pizza) — inclui atribuídos, respeita filtros ativos
        gastos_cat_qs = Gasto.objects.filter(_impacto_q(user), data_compra__month=mes, data_compra__year=ano)
        if responsavel_id:
            gastos_cat_qs = gastos_cat_qs.filter(responsavel_id=responsavel_id)
        if cartao_id:
            gastos_cat_qs = gastos_cat_qs.filter(cartao_id=cartao_id)
        if tipo_filtro:
            gastos_cat_qs = gastos_cat_qs.filter(tipo_pagamento=tipo_filtro)
        if categoria_id:
            gastos_cat_qs = gastos_cat_qs.filter(categoria_id=categoria_id)
        por_categoria = (
            gastos_cat_qs.values("categoria__nome", "categoria__cor")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["categorias_labels"] = json.dumps([
            c["categoria__nome"] or "Sem categoria" for c in por_categoria
        ])
        ctx["categorias_valores"] = json.dumps([float(c["total"]) for c in por_categoria])
        ctx["categorias_cores"] = json.dumps([
            c["categoria__cor"] or "#888888" for c in por_categoria
        ])

        # Gráfico de período — inclui atribuídos
        periodo_qs = Gasto.objects.filter(_impacto_q(user)).values("data_compra__month", "data_compra__year")
        if responsavel_id:
            periodo_qs = periodo_qs.filter(responsavel_id=responsavel_id)
        if cartao_id:
            periodo_qs = periodo_qs.filter(cartao_id=cartao_id)
        if categoria_id:
            periodo_qs = periodo_qs.filter(categoria_id=categoria_id)
        if tipo_filtro:
            periodo_qs = periodo_qs.filter(tipo_pagamento=tipo_filtro)

        meses_com_dados = (
            periodo_qs
            .annotate(total=Sum("valor_total"))
            .order_by("data_compra__year", "data_compra__month")
            .values("data_compra__year", "data_compra__month", "total")
        )

        meses_nomes = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        periodo_labels = []
        periodo_valores = []
        for item in meses_com_dados:
            m = item["data_compra__month"]
            a = item["data_compra__year"]
            periodo_labels.append(f"{meses_nomes[m-1]}/{a}")
            periodo_valores.append(float(item["total"] or 0))

        if not periodo_labels:
            hoje = date.today()
            for i in range(2, -1, -1):
                ref = date(hoje.year, hoje.month, 1) - relativedelta(months=i)
                periodo_labels.append(f"{meses_nomes[ref.month-1]}/{ref.year}")
                periodo_valores.append(0.0)

        ctx["periodo_labels"] = json.dumps(periodo_labels)
        ctx["periodo_valores"] = json.dumps(periodo_valores)

        # Tabela combinada: entradas + gastos + gastos atribuídos
        gastos_lista = list(
            gastos_mes.select_related("responsavel", "cartao", "categoria")
            .order_by("-data_compra", "-criado_em")
        )
        entradas_lista = list(entradas_mes.order_by("-data", "-criado_em"))

        transacoes = []
        for g in gastos_lista:
            transacoes.append({
                "data": g.data_compra,
                "tipo": "gasto",
                "tipo_pag": g.tipo_pagamento,
                "tipo_label": g.get_tipo_pagamento_display(),
                "descricao": g.descricao,
                "categoria": g.categoria,
                "responsavel": str(g.responsavel),
                "cartao": g.cartao.nome if g.cartao else "",
                "valor": float(g.valor_total),
                "pk": g.pk,
                "parcelas": g.total_parcelas if g.tipo_pagamento == "credito_parcelado" else None,
                "auto_gerada": False,
                "atribuido": False,
                "atribuido_por": "",
            })
        for e in entradas_lista:
            transacoes.append({
                "data": e.data,
                "tipo": "entrada",
                "tipo_label": e.get_tipo_display(),
                "descricao": e.descricao or "",
                "categoria": None,
                "responsavel": "",
                "cartao": "",
                "valor": float(e.valor),
                "pk": e.pk,
                "parcelas": None,
                "auto_gerada": e.auto_gerada,
                "atribuido": False,
                "atribuido_por": "",
            })
        for g in gastos_atribuidos:
            owner_name = g.user.get_full_name() if g.user else "outro usuário"
            if not owner_name.strip():
                owner_name = g.user.username if g.user else "outro usuário"
            transacoes.append({
                "data": g.data_compra,
                "tipo": "gasto",
                "tipo_pag": g.tipo_pagamento,
                "tipo_label": g.get_tipo_pagamento_display(),
                "descricao": g.descricao,
                "categoria": g.categoria,
                "responsavel": str(g.responsavel),
                "cartao": g.cartao.nome if g.cartao else "",
                "valor": float(g.valor_total),
                "pk": None,
                "parcelas": g.total_parcelas if g.tipo_pagamento == "credito_parcelado" else None,
                "auto_gerada": False,
                "atribuido": True,
                "atribuido_por": owner_name,
            })

        transacoes.sort(key=lambda x: x["data"], reverse=True)
        ctx["transacoes_mes"] = transacoes

        # Tabela: Gastos vs Entradas — Visão Mensal
        saldo_ant_qs = (
            Entrada.objects.filter(user=user, tipo="saldo_anterior")
            .values("data__year", "data__month")
            .annotate(t=Sum("valor"))
        )
        entradas_qs = (
            Entrada.objects.filter(user=user).exclude(tipo="saldo_anterior")
            .values("data__year", "data__month")
            .annotate(t=Sum("valor"))
        )
        # Gastos que impactam o usuário (próprios principal + atribuídos) por mês
        gastos_principal_qs = (
            Gasto.objects.filter(_impacto_q(user))
            .values("data_compra__year", "data_compra__month")
            .annotate(t=Sum("valor_total"))
        )

        saldo_ant_map = {(r["data__year"], r["data__month"]): float(r["t"] or 0) for r in saldo_ant_qs}
        entradas_map  = {(r["data__year"], r["data__month"]): float(r["t"] or 0) for r in entradas_qs}
        gastos_map    = {(r["data_compra__year"], r["data_compra__month"]): float(r["t"] or 0) for r in gastos_principal_qs}

        # Apenas os 12 meses do ano selecionado, independente de ter dados
        todos_meses = [(ano, m) for m in range(1, 13)]

        tabela_mensal = []
        running = Decimal(str(saldo_ant_map.get(todos_meses[0], 0.0))) if todos_meses else Decimal("0")

        for i, (y, m) in enumerate(todos_meses):
            k = (y, m)
            sa  = running
            ent = Decimal(str(entradas_map.get(k, 0.0)))
            gas = Decimal(str(gastos_map.get(k, 0.0)))
            saldo_atual = sa + ent - gas
            tabela_mensal.append({
                "label":       f"{meses_nomes[m-1]}/{str(y)[-2:]}",
                "saldo_ant":   float(sa),
                "entradas":    float(ent),
                "gastos":      float(gas),
                "saldo_atual": float(saldo_atual),
                "atual":       (y == ano and m == mes),
            })
            running = saldo_atual

        ctx["tabela_mensal"] = tabela_mensal

        # Gráfico ⑥ "Gastos vs Receitas" — inclui atribuídos, segue filtros ativos
        gastos_filtrado_qs = Gasto.objects.filter(_impacto_q(user))
        if responsavel_id:
            gastos_filtrado_qs = gastos_filtrado_qs.filter(responsavel_id=responsavel_id)
        if cartao_id:
            gastos_filtrado_qs = gastos_filtrado_qs.filter(cartao_id=cartao_id)
        if tipo_filtro:
            gastos_filtrado_qs = gastos_filtrado_qs.filter(tipo_pagamento=tipo_filtro)
        if categoria_id:
            gastos_filtrado_qs = gastos_filtrado_qs.filter(categoria_id=categoria_id)

        gastos_filtrado_map = {
            (r["data_compra__year"], r["data_compra__month"]): float(r["t"] or 0)
            for r in gastos_filtrado_qs.values("data_compra__year", "data_compra__month").annotate(t=Sum("valor_total"))
        }

        ctx["comp_labels"]   = json.dumps([c["label"] for c in tabela_mensal])
        ctx["comp_gastos"]   = json.dumps([gastos_filtrado_map.get(k, 0.0) for k in todos_meses])
        ctx["comp_entradas"] = json.dumps([c["entradas"] + c["saldo_ant"] for c in tabela_mensal])
        ctx["comp_saldo"]    = json.dumps([c["saldo_atual"] for c in tabela_mensal])
        ctx["comp_receitas"] = json.dumps([c["entradas"] for c in tabela_mensal])

        # Tabela Responsáveis × Meses — inclui atribuídos
        resp_qs = (
            Gasto.objects.filter(_impacto_q(user)).values(
                "responsavel__id", "responsavel__nome",
                "data_compra__year", "data_compra__month",
            ).annotate(t=Sum("valor_total"))
        )

        resp_map = {}
        resp_nome_map = {}
        for item in resp_qs:
            rid   = item["responsavel__id"]
            rname = item["responsavel__nome"]
            k     = (item["data_compra__year"], item["data_compra__month"])
            resp_nome_map[rid] = rname
            resp_map.setdefault(rid, {})[k] = float(item["t"] or 0)

        tabela_resp_meses = [
            {
                "nome": resp_nome_map[rid],
                "valores": [resp_map[rid].get(k) for k in todos_meses],
            }
            for rid in sorted(resp_nome_map, key=lambda r: resp_nome_map[r])
        ]
        ctx["tabela_resp_meses"] = tabela_resp_meses

        # Tabela Parcelados × Meses
        _parcela_re = re.compile(r'\s*\((\d+)/(\d+)\)$')
        parcelados_ano_qs = (
            Gasto.objects.filter(
                user=user,
                data_compra__year=ano,
                tipo_pagamento="credito_parcelado",
            )
            .select_related("responsavel", "cartao")
            .order_by("data_compra")
        )

        series_map = {}
        series_order = []
        for g in parcelados_ano_qs:
            m = _parcela_re.search(g.descricao)
            if m:
                parcela_num = int(m.group(1))
                total = int(m.group(2))
                desc_base = g.descricao[:m.start()]
            else:
                parcela_num = 1
                total = g.total_parcelas or 1
                desc_base = g.descricao

            serie_key = (desc_base, g.responsavel_id, g.cartao_id, total)
            if serie_key not in series_map:
                series_map[serie_key] = {
                    "descricao": desc_base,
                    "responsavel": g.responsavel,
                    "cartao": g.cartao,
                    "total_parcelas": total,
                    "meses": {},
                }
                series_order.append(serie_key)
            series_map[serie_key]["meses"][g.data_compra.month] = {
                "parcela_num": parcela_num,
                "valor": float(g.valor_total),
            }

        tabela_parcelados = []
        for key in series_order:
            data = series_map[key]
            tabela_parcelados.append({
                "descricao": data["descricao"],
                "responsavel": data["responsavel"],
                "cartao": data["cartao"],
                "total_parcelas": data["total_parcelas"],
                "meses": [data["meses"].get(mes_num) for _, mes_num in todos_meses],
            })
        ctx["tabela_parcelados"] = tabela_parcelados

        # Tabela Gastos Divididos × Meses
        from collections import defaultdict
        split_qs = (
            Gasto.objects.filter(
                user=user,
                grupo_divisao__isnull=False,
                data_compra__year=ano,
            )
            .select_related("responsavel", "cartao")
            .order_by("data_compra")
        )

        # agrupa por UUID de divisão para descobrir "dividido com"
        grupos_div = defaultdict(list)
        for g in split_qs:
            grupos_div[str(g.grupo_divisao)].append(g)

        div_series_map = {}
        div_series_order = []
        for grupo_uuid, gastos_grupo in grupos_div.items():
            # mapa responsavel_id → responsavel para este grupo
            resp_no_grupo = {g.responsavel_id: g.responsavel for g in gastos_grupo}

            # Exibe apenas o lado "principal" do split (menor pk = criado primeiro)
            main_resp_id = min(gastos_grupo, key=lambda x: x.pk).responsavel_id

            for g in gastos_grupo:
                if g.responsavel_id != main_resp_id:
                    continue  # ignora o outro lado do split

                match = _parcela_re.search(g.descricao)
                if match:
                    parcela_num = int(match.group(1))
                    total = int(match.group(2))
                    desc_base = g.descricao[:match.start()]
                else:
                    parcela_num = 1
                    total = g.total_parcelas or 1
                    desc_base = g.descricao

                if grupo_uuid not in div_series_map:
                    outros = [r for rid, r in resp_no_grupo.items() if rid != g.responsavel_id]
                    div_series_map[grupo_uuid] = {
                        "descricao": desc_base,
                        "responsavel": g.responsavel,
                        "dividido_com": outros[0] if outros else None,
                        "cartao": g.cartao,
                        "tipo_pagamento": g.tipo_pagamento,
                        "total_parcelas": total if g.tipo_pagamento == "credito_parcelado" else None,
                        "pct_meu": g.pct_divisao,
                        "meses": {},
                    }
                    div_series_order.append(grupo_uuid)

                div_series_map[grupo_uuid]["meses"][g.data_compra.month] = {
                    "parcela_num": parcela_num,
                    "valor": float(g.valor_total),
                    "is_parcelado": g.tipo_pagamento == "credito_parcelado",
                }

        tabela_divididos = []
        for grupo_uuid in div_series_order:
            d = div_series_map[grupo_uuid]
            pct_meu   = d["pct_meu"] or 50
            pct_outro = 100 - pct_meu
            tabela_divididos.append({
                "descricao":      d["descricao"],
                "responsavel":    d["responsavel"],
                "dividido_com":   d["dividido_com"],
                "cartao":         d["cartao"],
                "tipo_pagamento": d["tipo_pagamento"],
                "total_parcelas": d["total_parcelas"],
                "pct_meu":        pct_meu,
                "pct_outro":      pct_outro,
                "meses": [d["meses"].get(mes_num) for _, mes_num in todos_meses],
            })
        ctx["tabela_divididos"] = tabela_divididos

        return ctx


# ── Gastos ─────────────────────────────────────────────────────────────

class GastoListView(UserOwnedMixin, ListView):
    model = Gasto
    template_name = "gastos/gasto_list.html"
    context_object_name = "gastos"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("responsavel", "cartao", "categoria")
        mes = self.request.GET.get("mes")
        ano = self.request.GET.get("ano")
        responsavel = self.request.GET.get("responsavel")
        cartao = self.request.GET.get("cartao")
        categoria = self.request.GET.get("categoria")
        tipo = self.request.GET.get("tipo")

        if mes and ano:
            try:
                qs = qs.filter(data_compra__month=int(mes), data_compra__year=int(ano))
            except ValueError:
                pass
        else:
            # Sem filtro de mês: oculta parcelas 2, 3, ..., N — mostra só a 1ª de cada grupo
            qs = qs.exclude(descricao__iregex=r'\(([2-9]|\d{2,})/\d+\)\s*$')
        if responsavel:
            qs = qs.filter(responsavel_id=responsavel)
        if cartao:
            qs = qs.filter(cartao_id=cartao)
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        if tipo:
            qs = qs.filter(tipo_pagamento=tipo)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = date.today()
        ctx["mes"] = self.request.GET.get("mes", hoje.month)
        ctx["ano"] = self.request.GET.get("ano", hoje.year)
        ctx["responsaveis"] = Responsavel.objects.filter(ativo=True, user=self.request.user)
        ctx["cartoes"] = Cartao.objects.filter(ativo=True, user=self.request.user)
        ctx["categorias"] = Categoria.objects.filter(ativo=True, user=self.request.user)
        ctx["tipos"] = Gasto.TIPO_PAGAMENTO_CHOICES
        ctx["filtros"] = self.request.GET
        ctx["total_filtrado"] = self.get_queryset().aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class GastoCreateView(UserOwnedMixin, CreateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def get_initial(self):
        hoje = date.today()
        return {"mes_inicio": hoje.month, "ano_inicio": hoje.year}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        gasto = form.save(commit=False)
        gasto.user = self.request.user
        n = gasto.total_parcelas if gasto.tipo_pagamento == "credito_parcelado" else None

        data_inicio = gasto.data_compra
        if n:
            mes_ini = form.cleaned_data.get("mes_inicio")
            ano_ini = form.cleaned_data.get("ano_inicio")
            if mes_ini and ano_ini:
                try:
                    data_inicio = date(int(ano_ini), int(mes_ini), 1)
                except (ValueError, TypeError):
                    pass

        dividir = form.cleaned_data.get("dividir_gasto")
        dividir_com = form.cleaned_data.get("dividir_com")
        grupo_id = uuid.uuid4() if (dividir and dividir_com) else None

        valor_original = gasto.valor_total
        pct_meu = int(form.cleaned_data.get("pct_responsavel") or 50)
        pct_outro = 100 - pct_meu

        if grupo_id:
            valor_meu   = (valor_original * Decimal(pct_meu)   / 100).quantize(Decimal("0.01"))
            valor_outro = (valor_original * Decimal(pct_outro) / 100).quantize(Decimal("0.01"))
            # ajusta arredondamento: garante que a soma bate
            if valor_meu + valor_outro != valor_original:
                valor_outro = valor_original - valor_meu

        def _criar_gastos(responsavel, valor, pct, grupo):
            kwargs_base = dict(
                valor_total=valor,
                tipo_pagamento=gasto.tipo_pagamento,
                cartao=gasto.cartao,
                responsavel=responsavel,
                categoria=gasto.categoria,
                observacao=gasto.observacao,
                total_parcelas=n,
                user=self.request.user,
                grupo_divisao=grupo,
                pct_divisao=pct,
            )
            desc = gasto.descricao
            if n:
                Gasto.objects.create(descricao=f"{desc} (1/{n})", data_compra=data_inicio, **kwargs_base)
                for i in range(2, n + 1):
                    Gasto.objects.create(
                        descricao=f"{desc} ({i}/{n})",
                        data_compra=data_inicio + relativedelta(months=i - 1),
                        **kwargs_base,
                    )
            else:
                Gasto.objects.create(descricao=desc, data_compra=data_inicio, **kwargs_base)

        if n:
            if grupo_id:
                _criar_gastos(gasto.responsavel, valor_meu,   pct_meu,   grupo_id)
                _criar_gastos(dividir_com,       valor_outro, pct_outro, grupo_id)
            else:
                descricao_base = gasto.descricao
                gasto.descricao = f"{descricao_base} (1/{n})"
                gasto.data_compra = data_inicio
                gasto.save()
                for i in range(2, n + 1):
                    Gasto.objects.create(
                        descricao=f"{descricao_base} ({i}/{n})",
                        valor_total=gasto.valor_total,
                        tipo_pagamento=gasto.tipo_pagamento,
                        cartao=gasto.cartao,
                        responsavel=gasto.responsavel,
                        categoria=gasto.categoria,
                        data_compra=data_inicio + relativedelta(months=i - 1),
                        observacao=gasto.observacao,
                        total_parcelas=n,
                        user=self.request.user,
                    )
        else:
            if grupo_id:
                _criar_gastos(gasto.responsavel, valor_meu,   pct_meu,   grupo_id)
                _criar_gastos(dividir_com,       valor_outro, pct_outro, grupo_id)
            else:
                gasto.save()

        _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year, self.request.user)
        usuario_atribuido = gasto.responsavel.usuario_vinculado
        if usuario_atribuido and usuario_atribuido != self.request.user:
            _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year, usuario_atribuido)
        if grupo_id:
            messages.success(self.request, "Gasto dividido e registrado para os dois responsáveis.")
        else:
            messages.success(self.request, "Gasto registrado com sucesso.")
        next_url = self.request.POST.get("next") or self.success_url
        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Gasto"
        return ctx


_PARCELA_GROUP_RE = re.compile(r'^(.*?)\s*\((\d+)/(\d+)\)$')


def _encontrar_grupo_parcelado(gasto, user):
    """Retorna todas as parcelas do mesmo grupo, ordenadas pela data."""
    m = _PARCELA_GROUP_RE.match(gasto.descricao)
    if not m:
        return []
    base, total = m.group(1), int(m.group(3))
    padroes = [f"{base} ({i}/{total})" for i in range(1, total + 1)]
    return list(
        Gasto.objects.filter(
            user=user,
            descricao__in=padroes,
            responsavel=gasto.responsavel,
            tipo_pagamento="credito_parcelado",
        ).order_by("data_compra")
    )


class GastoUpdateView(UserOwnedMixin, UpdateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        data_antiga = self.get_object().data_compra
        gasto = form.save()
        usuario_atribuido = gasto.responsavel.usuario_vinculado

        # Sincroniza com o outro lado do split (se existir)
        if gasto.grupo_divisao:
            parceiro = (
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=gasto.grupo_divisao,
                    data_compra__month=data_antiga.month,
                    data_compra__year=data_antiga.year,
                )
                .exclude(pk=gasto.pk)
                .first()
            )
            if parceiro:
                pct_meu   = Decimal(gasto.pct_divisao or 50)
                pct_outro = Decimal(100) - pct_meu
                # Recalcula o valor do parceiro proporcionalmente
                total_compra   = (gasto.valor_total * Decimal("100") / pct_meu)
                novo_valor_parceiro = (total_compra * pct_outro / Decimal("100")).quantize(Decimal("0.01"))
                parceiro.descricao      = gasto.descricao
                parceiro.data_compra    = gasto.data_compra
                parceiro.tipo_pagamento = gasto.tipo_pagamento
                parceiro.total_parcelas = gasto.total_parcelas
                parceiro.categoria      = gasto.categoria
                parceiro.valor_total    = novo_valor_parceiro
                parceiro.pct_divisao    = int(pct_outro)
                parceiro.save(update_fields=[
                    "descricao", "data_compra", "tipo_pagamento",
                    "total_parcelas", "categoria", "valor_total", "pct_divisao",
                ])

        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, self.request.user)
        if gasto.data_compra != data_antiga:
            _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year, self.request.user)
        if usuario_atribuido and usuario_atribuido != self.request.user:
            _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, usuario_atribuido)
            if gasto.data_compra != data_antiga:
                _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year, usuario_atribuido)
        messages.success(self.request, "Gasto atualizado com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Gasto"
        gasto = self.object
        if gasto.tipo_pagamento == "credito_parcelado":
            grupo = _encontrar_grupo_parcelado(gasto, self.request.user)
            if len(grupo) > 1:
                ctx["parcelas_grupo"] = grupo
            ctx["parcelado_edit"] = True
        else:
            ctx["parcelado_edit"] = False
        return ctx


@login_required
def gasto_parcela_valor(request, pk):
    """Atualiza apenas o valor_total de uma parcela específica, sincronizando o split."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))

    gasto = get_object_or_404(Gasto, pk=pk, user=request.user)
    next_url = request.POST.get("next") or reverse_lazy("gasto-update", kwargs={"pk": pk})

    try:
        novo_valor = Decimal(request.POST["valor_total"].replace(",", "."))
        if novo_valor <= 0:
            raise ValueError
    except Exception:
        messages.error(request, "Valor inválido.")
        return HttpResponseRedirect(next_url)

    gasto.valor_total = novo_valor
    gasto.save(update_fields=["valor_total"])

    if gasto.grupo_divisao and gasto.pct_divisao:
        mes, ano = gasto.data_compra.month, gasto.data_compra.year
        parceiro = (
            Gasto.objects.filter(
                user=request.user,
                grupo_divisao=gasto.grupo_divisao,
                data_compra__month=mes,
                data_compra__year=ano,
            )
            .exclude(pk=gasto.pk)
            .first()
        )
        if parceiro:
            pct_meu   = Decimal(gasto.pct_divisao)
            pct_outro = Decimal(100) - pct_meu
            total_compra        = novo_valor * Decimal("100") / pct_meu
            novo_valor_parceiro = (total_compra * pct_outro / Decimal("100")).quantize(Decimal("0.01"))
            parceiro.valor_total = novo_valor_parceiro
            parceiro.save(update_fields=["valor_total"])

    _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year, request.user)
    messages.success(request, "Valor da parcela atualizado.")
    return HttpResponseRedirect(next_url)


@login_required
def gasto_parcela_add(request, pk):
    """Adiciona uma parcela extra ao grupo de um gasto parcelado."""
    gasto_ref = get_object_or_404(Gasto, pk=pk, user=request.user)
    grupo = _encontrar_grupo_parcelado(gasto_ref, request.user)
    if not grupo:
        messages.error(request, "Grupo de parcelas não encontrado.")
        return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))

    m = _PARCELA_GROUP_RE.match(gasto_ref.descricao)
    base = m.group(1)
    total_atual = len(grupo)
    novo_total = total_atual + 1

    # renomeia parcelas do lado principal
    for i, g in enumerate(grupo, 1):
        g.descricao = f"{base} ({i}/{novo_total})"
        g.save(update_fields=["descricao"])

    ultima = grupo[-1]
    nova_data = ultima.data_compra + relativedelta(months=1)
    Gasto.objects.create(
        user=request.user,
        descricao=f"{base} ({novo_total}/{novo_total})",
        valor_total=ultima.valor_total,
        data_compra=nova_data,
        tipo_pagamento="credito_parcelado",
        total_parcelas=novo_total,
        cartao=ultima.cartao,
        responsavel=ultima.responsavel,
        categoria=ultima.categoria,
        pct_divisao=ultima.pct_divisao,
        grupo_divisao=ultima.grupo_divisao,
    )

    # Se é gasto dividido, repete a operação para o outro lado do split
    if ultima.grupo_divisao:
        outro_grupo = list(
            Gasto.objects.filter(
                user=request.user,
                grupo_divisao=ultima.grupo_divisao,
            )
            .exclude(responsavel=ultima.responsavel)
            .order_by("data_compra")
        )
        if outro_grupo:
            for i, g in enumerate(outro_grupo, 1):
                g.descricao = f"{base} ({i}/{novo_total})"
                g.save(update_fields=["descricao"])
            ultima_outro = outro_grupo[-1]
            Gasto.objects.create(
                user=request.user,
                descricao=f"{base} ({novo_total}/{novo_total})",
                valor_total=ultima_outro.valor_total,
                data_compra=nova_data,
                tipo_pagamento="credito_parcelado",
                total_parcelas=novo_total,
                cartao=ultima_outro.cartao,
                responsavel=ultima_outro.responsavel,
                categoria=ultima_outro.categoria,
                pct_divisao=ultima_outro.pct_divisao,
                grupo_divisao=ultima_outro.grupo_divisao,
            )

    _recalcular_saldos_a_partir(nova_data.month, nova_data.year, request.user)
    messages.success(request, f"Parcela {novo_total}/{novo_total} adicionada ao grupo.")
    return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))


class GastoDeleteView(UserOwnedMixin, DeleteView):
    model = Gasto
    template_name = "gastos/gasto_confirm_delete.html"
    success_url = reverse_lazy("gasto-list")

    def form_valid(self, form):
        gasto = self.object
        mes, ano = gasto.data_compra.month, gasto.data_compra.year
        usuario_atribuido = gasto.responsavel.usuario_vinculado
        grupo_divisao = gasto.grupo_divisao
        responsavel_pk = gasto.responsavel_id

        # Extrai base da descrição para renumerar parcelas restantes
        m = _PARCELA_GROUP_RE.match(gasto.descricao)
        base_desc = m.group(1) if m else None

        # Encontra o parceiro do split ANTES de deletar
        parceiro = None
        parceiro_resp_pk = None
        if grupo_divisao:
            parceiro = (
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=grupo_divisao,
                    data_compra__month=mes,
                    data_compra__year=ano,
                )
                .exclude(responsavel_id=responsavel_pk)
                .first()
            )
            if parceiro:
                parceiro_resp_pk = parceiro.responsavel_id

        response = super().form_valid(form)  # deleta o gasto principal

        if parceiro:
            parceiro.delete()

        # Renumera parcelas restantes de ambos os lados
        if grupo_divisao and base_desc:
            for resp_pk in filter(None, [responsavel_pk, parceiro_resp_pk]):
                restantes = list(
                    Gasto.objects.filter(
                        user=self.request.user,
                        grupo_divisao=grupo_divisao,
                        responsavel_id=resp_pk,
                    ).order_by("data_compra")
                )
                if not restantes:
                    continue
                novo_total = len(restantes)
                for i, g in enumerate(restantes, 1):
                    g.descricao = f"{base_desc} ({i}/{novo_total})"
                    g.save(update_fields=["descricao"])

        _recalcular_saldos_a_partir(mes, ano, self.request.user)
        if usuario_atribuido and usuario_atribuido != self.request.user:
            _recalcular_saldos_a_partir(mes, ano, usuario_atribuido)
        messages.success(self.request, "Gasto excluído com sucesso.")
        return response


# ── Cartões ─────────────────────────────────────────────────────────────

class CartaoListView(UserOwnedMixin, ListView):
    model = Cartao
    template_name = "cartoes/cartao_list.html"
    context_object_name = "cartoes"

    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        user = self.request.user
        for cartao in ctx["cartoes"]:
            cartao.fatura_mes = Gasto.objects.filter(
                cartao=cartao,
                user=user,
                data_compra__month=mes,
                data_compra__year=ano,
                tipo_pagamento__in=["credito_avista", "credito_parcelado"],
            ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class CartaoDetailView(UserOwnedMixin, DetailView):
    model = Cartao
    template_name = "cartoes/cartao_detail.html"
    context_object_name = "cartao"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        ctx["gastos"] = (
            Gasto.objects.filter(
                cartao=self.object, user=self.request.user,
                data_compra__month=mes, data_compra__year=ano,
            )
            .select_related("responsavel", "categoria")
            .order_by("-data_compra")
        )
        ctx["total_fatura"] = ctx["gastos"].aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class CartaoCreateView(UserOwnedMixin, CreateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "cartoes/cartao_form.html"
    success_url = reverse_lazy("cartao-list")

    def form_valid(self, form):
        cartao = form.save(commit=False)
        cartao.user = self.request.user
        cartao.save()
        messages.success(self.request, "Cartão criado com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Cartão"
        return ctx


class CartaoUpdateView(UserOwnedMixin, UpdateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "cartoes/cartao_form.html"
    success_url = reverse_lazy("cartao-list")

    def form_valid(self, form):
        messages.success(self.request, "Cartão atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Cartão"
        return ctx


class CartaoDeleteView(UserOwnedMixin, DeleteView):
    model = Cartao
    template_name = "cartoes/cartao_confirm_delete.html"
    success_url = reverse_lazy("cartao-list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["qtd_gastos"] = self.object.gastos.count()
        return ctx

    def form_valid(self, form):
        gastos = list(self.object.gastos.all())
        datas = {(g.data_compra.month, g.data_compra.year) for g in gastos}
        self.object.gastos.all().delete()
        response = super().form_valid(form)
        for mes, ano in datas:
            _recalcular_saldos_a_partir(mes, ano, self.request.user)
        messages.success(self.request, "Cartão excluído com sucesso.")
        return response


# ── Responsáveis ─────────────────────────────────────────────────────────

class ResponsavelListView(UserOwnedMixin, ListView):
    model = Responsavel
    template_name = "responsaveis/responsavel_list.html"
    context_object_name = "responsaveis"

    def get_queryset(self):
        return super().get_queryset().filter(is_principal=False)


class ResponsavelCreateView(UserOwnedMixin, CreateView):
    model = Responsavel
    form_class = ResponsavelForm
    template_name = "responsaveis/responsavel_form.html"
    success_url = reverse_lazy("responsavel-list")

    def form_valid(self, form):
        responsavel = form.save(commit=False)
        responsavel.user = self.request.user
        responsavel.save()
        messages.success(self.request, "Responsável criado com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Responsável"
        return ctx


class ResponsavelUpdateView(UserOwnedMixin, UpdateView):
    model = Responsavel
    form_class = ResponsavelForm
    template_name = "responsaveis/responsavel_form.html"
    success_url = reverse_lazy("responsavel-list")

    def form_valid(self, form):
        messages.success(self.request, "Responsável atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Responsável"
        return ctx


class ResponsavelDeleteView(UserOwnedMixin, DeleteView):
    model = Responsavel
    template_name = "responsaveis/responsavel_confirm_delete.html"
    success_url = reverse_lazy("responsavel-list")

    def form_valid(self, form):
        messages.success(self.request, "Responsável excluído com sucesso.")
        return super().form_valid(form)


# ── Categorias ─────────────────────────────────────────────────────────

class CategoriaListView(UserOwnedMixin, ListView):
    model = Categoria
    template_name = "categorias/categoria_list.html"
    context_object_name = "categorias"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        user = self.request.user
        for cat in ctx["categorias"]:
            cat.total_gastos_mes = Gasto.objects.filter(
                categoria=cat,
                user=user,
                data_compra__month=mes,
                data_compra__year=ano,
            ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
            cat.qtd_gastos_mes = Gasto.objects.filter(
                categoria=cat,
                user=user,
                data_compra__month=mes,
                data_compra__year=ano,
            ).count()
        return ctx


class CategoriaCreateView(UserOwnedMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "categorias/categoria_form.html"
    success_url = reverse_lazy("categoria-list")

    def form_valid(self, form):
        categoria = form.save(commit=False)
        categoria.user = self.request.user
        categoria.save()
        messages.success(self.request, "Categoria criada com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Categoria"
        ctx["icones"] = Categoria.ICONE_CHOICES
        ctx["cores"] = Categoria.CORES_CHOICES
        ctx["icones_presets"] = Categoria.PRESETS
        return ctx


class CategoriaUpdateView(UserOwnedMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "categorias/categoria_form.html"
    success_url = reverse_lazy("categoria-list")

    def form_valid(self, form):
        messages.success(self.request, "Categoria atualizada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Categoria"
        ctx["icones"] = Categoria.ICONE_CHOICES
        ctx["cores"] = Categoria.CORES_CHOICES
        ctx["icones_presets"] = Categoria.PRESETS
        return ctx


class CategoriaDeleteView(UserOwnedMixin, DeleteView):
    model = Categoria
    template_name = "categorias/categoria_confirm_delete.html"
    success_url = reverse_lazy("categoria-list")

    def form_valid(self, form):
        messages.success(self.request, "Categoria excluída com sucesso.")
        return super().form_valid(form)


# ── Entradas ─────────────────────────────────────────────────────────────

class EntradaListView(UserOwnedMixin, ListView):
    model = Entrada
    template_name = "entradas/entrada_list.html"
    context_object_name = "entradas"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        mes = self.request.GET.get("mes")
        ano = self.request.GET.get("ano")
        if mes and ano:
            try:
                qs = qs.filter(data__month=int(mes), data__year=int(ano))
            except ValueError:
                pass
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = date.today()
        ctx["mes"] = self.request.GET.get("mes", hoje.month)
        ctx["ano"] = self.request.GET.get("ano", hoje.year)
        ctx["filtros"] = self.request.GET
        ctx["total_filtrado"] = self.get_queryset().aggregate(t=Sum("valor"))["t"] or Decimal("0")
        return ctx


class EntradaCreateView(UserOwnedMixin, CreateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        entrada = form.save(commit=False)
        entrada.user = self.request.user
        entrada.save()
        _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year, self.request.user)
        messages.success(self.request, "Entrada registrada com sucesso.")
        next_url = self.request.POST.get("next") or self.success_url
        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Entrada"
        return ctx


class EntradaUpdateView(UserOwnedMixin, UpdateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        data_antiga = self.get_object().data
        entrada = form.save()
        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, self.request.user)
        if entrada.data != data_antiga:
            _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year, self.request.user)
        messages.success(self.request, "Entrada atualizada com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Entrada"
        return ctx


class EntradaDeleteView(UserOwnedMixin, DeleteView):
    model = Entrada
    template_name = "entradas/entrada_confirm_delete.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        mes, ano = self.object.data.month, self.object.data.year
        response = super().form_valid(form)
        _recalcular_saldos_a_partir(mes, ano, self.request.user)
        messages.success(self.request, "Entrada excluída com sucesso.")
        return response


# ── Exclusão em massa ────────────────────────────────────────────────────

@login_required
def cartao_delete_all(request):
    if request.method == "POST":
        datas = list(
            Gasto.objects.filter(user=request.user)
            .values_list("data_compra__month", "data_compra__year").distinct()
        )
        Gasto.objects.filter(user=request.user).delete()
        Cartao.objects.filter(user=request.user).delete()
        for mes, ano in set(datas):
            _recalcular_saldos_a_partir(mes, ano, request.user)
        messages.success(request, "Todos os cartões (e seus gastos) foram excluídos.")
    return HttpResponseRedirect(reverse_lazy("cartao-list"))


@login_required
def gasto_delete_all(request):
    if request.method == "POST":
        datas = list(
            Gasto.objects.filter(user=request.user)
            .values_list("data_compra__month", "data_compra__year").distinct()
        )
        Gasto.objects.filter(user=request.user).delete()
        for mes, ano in set(datas):
            _recalcular_saldos_a_partir(mes, ano, request.user)
        messages.success(request, "Todos os gastos foram excluídos.")
    return HttpResponseRedirect(reverse_lazy("gasto-list"))


@login_required
def entrada_delete_all(request):
    if request.method == "POST":
        Entrada.objects.filter(user=request.user, auto_gerada=False).delete()
        Entrada.objects.filter(user=request.user, auto_gerada=True).delete()
        messages.success(request, "Todas as entradas foram excluídas.")
    return HttpResponseRedirect(reverse_lazy("entrada-list"))


# ── Perfil ─────────────────────────────────────────────────────────────

@login_required
def perfil_update(request):
    next_url = request.POST.get("next") or "/"
    if request.method == "POST":
        form = PerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso.")
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
    return HttpResponseRedirect(next_url)


@login_required
def senha_update(request):
    next_url = request.POST.get("next") or "/"
    if request.method == "POST":
        form = SenhaForm(request.user, request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data["nova_senha"])
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Senha alterada com sucesso.")
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
    return HttpResponseRedirect(next_url)


# ── API interna ─────────────────────────────────────────────────────────

@login_required
def cartoes_por_responsavel(request, responsavel_id=None):
    cartoes = Cartao.objects.filter(ativo=True, user=request.user).values("id", "nome", "tipo")
    return JsonResponse(list(cartoes), safe=False)


@login_required
def fatura_toggle_pago(request, cartao_id):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    cartao = get_object_or_404(Cartao, pk=cartao_id, user=request.user)
    mes, ano = _mes_ano_from_request(request)
    obj, created = FaturaPaga.objects.get_or_create(
        cartao=cartao, mes=mes, ano=ano, user=request.user
    )
    if not created:
        obj.delete()
    next_url = request.POST.get("next") or reverse_lazy("dashboard")
    return HttpResponseRedirect(next_url)


@login_required
def pagamento_toggle(request, tipo, responsavel_id):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    if tipo not in ("pix", "emprestimo"):
        from django.http import Http404
        raise Http404
    responsavel = get_object_or_404(Responsavel, pk=responsavel_id, user=request.user)
    mes, ano = _mes_ano_from_request(request)
    obj, created = PagamentoFeito.objects.get_or_create(
        tipo=tipo, responsavel=responsavel, mes=mes, ano=ano, user=request.user
    )
    if not created:
        obj.delete()
    next_url = request.POST.get("next") or reverse_lazy("dashboard")
    return HttpResponseRedirect(next_url)


# ── Contas ─────────────────────────────────────────────────────────────

class ContaListView(UserOwnedMixin, ListView):
    model = Conta
    template_name = "contas/conta_list.html"
    context_object_name = "contas"

    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


class ContaCreateView(UserOwnedMixin, CreateView):
    model = Conta
    form_class = ContaForm
    template_name = "contas/conta_form.html"
    success_url = reverse_lazy("conta-list")

    def form_valid(self, form):
        conta = form.save(commit=False)
        conta.user = self.request.user
        conta.save()
        messages.success(self.request, "Conta criada com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Conta"
        return ctx


class ContaUpdateView(UserOwnedMixin, UpdateView):
    model = Conta
    form_class = ContaForm
    template_name = "contas/conta_form.html"
    success_url = reverse_lazy("conta-list")

    def form_valid(self, form):
        messages.success(self.request, "Conta atualizada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Conta"
        return ctx


class ContaDeleteView(UserOwnedMixin, DeleteView):
    model = Conta
    template_name = "contas/conta_confirm_delete.html"
    success_url = reverse_lazy("conta-list")

    def form_valid(self, form):
        messages.success(self.request, "Conta excluída com sucesso.")
        return super().form_valid(form)


class ContaDetailView(UserOwnedMixin, DetailView):
    model = Conta
    template_name = "contas/conta_detail.html"
    context_object_name = "conta"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conta = self.object
        entradas = Entrada.objects.filter(
            conta=conta, user=self.request.user
        ).order_by("-data", "-criado_em").select_related("responsavel")
        ctx["entradas"] = entradas
        ctx["total_entradas"] = entradas.aggregate(t=Sum("valor"))["t"] or 0
        ctx["qtd_entradas"] = entradas.count()
        return ctx


# ── Investimentos ────────────────────────────────────────────────────────────

class InvestimentoListView(LoginRequiredMixin, TemplateView):
    template_name = "investimentos/investimento_list.html"

    def _build_series(self, historico_qs, inv_conta_map, inv_inicial_map):
        """
        Reconstrói a evolução patrimonial mensal com carry-forward.
        inv_conta_map:   {inv_pk: conta_id}
        inv_inicial_map: {inv_pk: saldo_inicial}
        Retorna (labels, dados_patrimonio, aportes_bar, saques_bar, conta_series).
        conta_series[id] = {"labels", "dados", "aportes_bar", "saques_bar"}
        """
        from collections import OrderedDict
        MESES_PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

        registros = list(
            historico_qs.order_by("data_movimentacao")
            .values("investimento_id", "valor_novo", "diferenca", "tipo", "data_movimentacao")
        )
        if not registros:
            return [], [], [], [], {}

        meses_geral   = OrderedDict()   # {chave: {inv_pk: ultimo_valor}}
        aportes_g     = {}              # {chave: valor_total_aportes}
        saques_g      = {}              # {chave: valor_total_saques}
        meses_conta   = {}
        aportes_conta = {}
        saques_conta  = {}

        for r in registros:
            dt       = r["data_movimentacao"]
            chave    = (dt.year, dt.month)
            inv_pk   = r["investimento_id"]
            val      = float(r["valor_novo"])
            dif      = float(r["diferenca"])
            tipo     = r.get("tipo") or "rendimento"
            conta_id = inv_conta_map.get(inv_pk)

            # Linha de patrimônio (último valor por inv por mês)
            if chave not in meses_geral:
                meses_geral[chave] = {}
            meses_geral[chave][inv_pk] = val

            # Barras globais
            if tipo in ("aporte", "inicial"):
                aportes_g[chave] = aportes_g.get(chave, 0) + max(0, dif)
            elif tipo == "saque":
                saques_g[chave]  = saques_g.get(chave, 0)  + abs(min(0, dif))

            # Séries por conta
            if conta_id is not None:
                if conta_id not in meses_conta:
                    meses_conta[conta_id]   = OrderedDict()
                    aportes_conta[conta_id] = {}
                    saques_conta[conta_id]  = {}
                if chave not in meses_conta[conta_id]:
                    meses_conta[conta_id][chave] = {}
                meses_conta[conta_id][chave][inv_pk] = val
                if tipo in ("aporte", "inicial"):
                    aportes_conta[conta_id][chave] = aportes_conta[conta_id].get(chave, 0) + max(0, dif)
                elif tipo == "saque":
                    saques_conta[conta_id][chave]  = saques_conta[conta_id].get(chave, 0)  + abs(min(0, dif))

        from dateutil.relativedelta import relativedelta as _rd
        primeiro = min(meses_geral.keys())
        hoje     = date.today()
        ultimo   = (hoje.year, hoje.month)

        def _mes_range(inicio, fim):
            cur = date(inicio[0], inicio[1], 1)
            end = date(fim[0], fim[1], 1)
            while cur <= end:
                yield (cur.year, cur.month)
                cur += _rd(months=1)

        saldo_acum = {}
        all_labels, all_dados, all_aportes_bar, all_saques_bar = [], [], [], []

        for chave in _mes_range(primeiro, ultimo):
            if chave in meses_geral:
                saldo_acum.update(meses_geral[chave])
            ano, mes = chave
            all_labels.append(f"{MESES_PT[mes-1]}/{ano}")
            all_dados.append(round(sum(saldo_acum.values()), 2))
            all_aportes_bar.append(round(aportes_g.get(chave, 0), 2))
            all_saques_bar.append(round(saques_g.get(chave, 0), 2))

        conta_series = {}
        for conta_id, meses in meses_conta.items():
            pri_c = min(meses.keys())
            s_c   = {}
            lab_c, dat_c, apo_bar_c, saq_bar_c = [], [], [], []
            for chave in _mes_range(pri_c, ultimo):
                if chave in meses:
                    s_c.update(meses[chave])
                ano, mes = chave
                lab_c.append(f"{MESES_PT[mes-1]}/{ano}")
                dat_c.append(round(sum(s_c.values()), 2))
                apo_bar_c.append(round(aportes_conta[conta_id].get(chave, 0), 2))
                saq_bar_c.append(round(saques_conta[conta_id].get(chave, 0), 2))
            conta_series[conta_id] = {
                "labels": lab_c, "dados": dat_c,
                "aportes_bar": apo_bar_c, "saques_bar": saq_bar_c,
            }

        return all_labels, all_dados, all_aportes_bar, all_saques_bar, conta_series

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        todos = list(Investimento.objects.filter(user=user).select_related("conta"))
        ativos     = [i for i in todos if not i.liquidado]
        liquidados = [i for i in todos if i.liquidado]
        ctx["investimentos"]  = ativos
        ctx["liquidados"]     = liquidados
        ctx["contas"] = Conta.objects.filter(user=user, ativo=True)
        ctx["form"] = InvestimentoForm(user)
        ctx["total_inicial"] = sum(i.saldo_inicial for i in ativos)
        ctx["total_atual"]   = sum(i.saldo_atual   for i in ativos)
        ctx["total_rentab"]  = ctx["total_atual"] - ctx["total_inicial"]

        # Dados para o gráfico — usa todos (ativos + liquidados) para mostrar histórico completo
        inv_ids          = [i.pk for i in todos]
        inv_conta_map    = {i.pk: i.conta_id   for i in todos}
        inv_inicial_map  = {i.pk: float(i.saldo_inicial) for i in todos}
        historico_qs = InvestimentoHistorico.objects.filter(investimento_id__in=inv_ids)

        all_labels, all_dados, all_aportes_bar, all_saques_bar, conta_series = self._build_series(
            historico_qs, inv_conta_map, inv_inicial_map
        )

        ctx["chart_labels"]      = json.dumps(all_labels)
        ctx["chart_dados"]       = json.dumps(all_dados)
        ctx["chart_aportes_bar"] = json.dumps(all_aportes_bar)
        ctx["chart_saques_bar"]  = json.dumps(all_saques_bar)
        ctx["chart_por_conta"]   = json.dumps(conta_series)
        ctx["contas_com_inv"]  = [
            {"id": c.pk, "nome": c.nome}
            for c in ctx["contas"]
            if c.pk in {i.conta_id for i in todos}
        ]

        # Gráfico de rosca — distribuição por tipo (apenas ativos)
        from collections import defaultdict
        LABEL_MAP = {
            "renda_fixa":        "Renda Fixa",
            "renda_variavel":    "Renda Variável",
            "fundo_imobiliario": "Fundo Imobiliário",
        }
        tipo_totais = defaultdict(float)
        for inv in ativos:
            tipo_totais[LABEL_MAP.get(inv.tipo_investimento, inv.tipo_investimento)] += float(inv.saldo_atual)
        ctx["rosca_labels"] = json.dumps(list(tipo_totais.keys()))
        ctx["rosca_dados"]  = json.dumps([round(v, 2) for v in tipo_totais.values()])

        return ctx


class InvestimentoCreateView(LoginRequiredMixin, CreateView):
    model = Investimento
    form_class = InvestimentoForm
    success_url = reverse_lazy("investimento-list")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        inv = form.save(commit=False)
        inv.user = self.request.user
        inv.saldo_atual = inv.saldo_inicial
        inv.save()
        InvestimentoHistorico.objects.create(
            investimento=inv,
            valor_anterior=Decimal("0"),
            valor_novo=inv.saldo_inicial,
            diferenca=inv.saldo_inicial,
            tipo="inicial",
            motivo="Aporte inicial",
        )
        messages.success(self.request, "Investimento criado com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Corrija os erros abaixo.")
        return HttpResponseRedirect(reverse_lazy("investimento-list"))


class InvestimentoDeleteView(LoginRequiredMixin, DeleteView):
    model = Investimento
    template_name = "investimentos/investimento_confirm_delete.html"
    success_url = reverse_lazy("investimento-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Investimento excluído.")
        return super().form_valid(form)


class InvestimentoDetailView(LoginRequiredMixin, DetailView):
    model = Investimento
    template_name = "investimentos/investimento_detail.html"
    context_object_name = "inv"

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user).select_related("conta")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        inv = self.object
        historico = inv.historico.all()
        ctx["historico"] = historico
        ctx["form_saldo"] = InvestimentoAtualizarSaldoForm(
            initial={"novo_saldo": inv.saldo_atual}
        )

        conta_id = self.request.GET.get("conta_filtro", "")
        ctx["conta_filtro"] = conta_id
        ctx["contas_disponiveis"] = Conta.objects.filter(user=self.request.user, ativo=True)

        chart_qs = historico.order_by("data_movimentacao")
        labels = [h.data_movimentacao.strftime("%d/%m/%Y %H:%M") for h in chart_qs]
        dados  = [float(h.valor_novo) for h in chart_qs]
        ctx["chart_labels"] = json.dumps(labels)
        ctx["chart_dados"]  = json.dumps(dados)
        return ctx


@login_required
def investimento_liquidar(request, pk):
    if request.method != "POST":
        return HttpResponseRedirect(reverse_lazy("investimento-detail", kwargs={"pk": pk}))
    inv = get_object_or_404(Investimento, pk=pk, user=request.user)
    if inv.liquidado:
        messages.info(request, "Investimento já liquidado.")
        return HttpResponseRedirect(reverse_lazy("investimento-list"))

    from django.utils import timezone
    InvestimentoHistorico.objects.create(
        investimento=inv,
        valor_anterior=inv.saldo_atual,
        valor_novo=Decimal("0"),
        diferenca=-inv.saldo_atual,
        tipo="liquidacao",
        motivo="Liquidação / Saque total",
    )
    inv.liquidado = True
    inv.data_liquidacao = timezone.now()
    inv.saldo_atual = Decimal("0")
    inv.save(update_fields=["liquidado", "data_liquidacao", "saldo_atual", "atualizado_em"])
    messages.success(request, f'Investimento "{inv.descricao}" liquidado com sucesso.')
    return HttpResponseRedirect(reverse_lazy("investimento-list"))


@login_required
def investimento_atualizar_saldo(request, pk):
    inv = get_object_or_404(Investimento, pk=pk, user=request.user)
    if request.method != "POST":
        return HttpResponseRedirect(reverse_lazy("investimento-detail", kwargs={"pk": pk}))

    form = InvestimentoAtualizarSaldoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Dados inválidos. Verifique o formulário.")
        return HttpResponseRedirect(reverse_lazy("investimento-detail", kwargs={"pk": pk}))

    valor  = form.cleaned_data["valor"]
    tipo   = form.cleaned_data["tipo"]
    motivo = form.cleaned_data.get("motivo", "")

    if tipo == "ajuste_saldo":
        novo_saldo = valor
    elif tipo == "saque":
        novo_saldo = inv.saldo_atual - valor
    else:  # aporte ou rendimento
        novo_saldo = inv.saldo_atual + valor

    InvestimentoHistorico.objects.create(
        investimento=inv,
        valor_anterior=inv.saldo_atual,
        valor_novo=novo_saldo,
        diferenca=novo_saldo - inv.saldo_atual,
        tipo=tipo,
        motivo=motivo,
    )
    inv.saldo_atual = novo_saldo
    inv.save(update_fields=["saldo_atual", "atualizado_em"])
    messages.success(request, "Saldo atualizado com sucesso.")
    return HttpResponseRedirect(reverse_lazy("investimento-detail", kwargs={"pk": pk}))
