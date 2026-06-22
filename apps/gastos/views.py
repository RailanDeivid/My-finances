import json
import re
import uuid
from collections import OrderedDict, defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import update_session_auth_hash
from django.db.models import Count, Sum, Q, F, Case, When, ExpressionWrapper, Value
from django.db.models import DecimalField as DjDecimalField
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
)
from django.contrib import messages

from django.shortcuts import get_object_or_404
from .models import Gasto, Cartao, Responsavel, Categoria, Entrada, FaturaPaga, Conta, PagamentoFeito, Investimento, InvestimentoHistorico
from .forms import GastoForm, CartaoForm, ResponsavelForm, CategoriaForm, EntradaForm, ContaForm, PerfilForm, SenhaForm, InvestimentoForm, InvestimentoAtualizarSaldoForm


_PERIODO_DEFAULT_MES = 7
_PERIODO_DEFAULT_ANO = 2026


def _safe_next_url(request, fallback="/"):
    """Valida o parâmetro POST 'next'; retorna fallback se for URL externa (previne Open Redirect)."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return str(fallback)


def _safe_json(data):
    """JSON-serializa e escapa HTML com unicode escapes para prevenir XSS em <script> |safe."""
    return (
        json.dumps(data)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )


def _mes_ano_from_request(request, prefix=""):
    """Lê mes/ano do GET param, com fallback para session (por aba) e depois para jul/2026."""
    k_mes = f"filtro_mes_{prefix}" if prefix else "filtro_mes"
    k_ano = f"filtro_ano_{prefix}" if prefix else "filtro_ano"

    mes_str = request.GET.get("mes")
    ano_str = request.GET.get("ano")

    if mes_str is not None or ano_str is not None:
        try:
            mes = int(mes_str) if mes_str else request.session.get(k_mes, _PERIODO_DEFAULT_MES)
            ano = int(ano_str) if ano_str else request.session.get(k_ano, _PERIODO_DEFAULT_ANO)
            if not (1 <= mes <= 12):
                mes = _PERIODO_DEFAULT_MES
        except (ValueError, TypeError):
            mes, ano = _PERIODO_DEFAULT_MES, _PERIODO_DEFAULT_ANO
        request.session[k_mes] = mes
        request.session[k_ano] = ano
    else:
        mes = request.session.get(k_mes, _PERIODO_DEFAULT_MES)
        ano = request.session.get(k_ano, _PERIODO_DEFAULT_ANO)

    return mes, ano


def _impacto_q(user):
    """Q que representa todos os gastos que impactam financeiramente um usuário:
    qualquer gasto cujo responsável está vinculado a este usuário (próprios ou atribuídos)."""
    return Q(responsavel__usuario_vinculado=user)


def _agg_sum(qs, field="valor_total"):
    """Atalho para .aggregate(Sum(field))["t"] or Decimal("0")."""
    return qs.aggregate(_t=Sum(field))["_t"] or Decimal("0")


def _agg_sum_compra(qs):
    """Soma valor_compra_total: para divididos usa valor_total*100/pct_divisao, senão valor_total."""
    return qs.aggregate(
        _t=Sum(
            Case(
                When(
                    grupo_divisao__isnull=False,
                    pct_divisao__gt=0,
                    then=ExpressionWrapper(
                        F('valor_total') * Value(Decimal('100')) / F('pct_divisao'),
                        output_field=DjDecimalField(max_digits=12, decimal_places=2)
                    )
                ),
                default=F('valor_total'),
                output_field=DjDecimalField(max_digits=12, decimal_places=2)
            )
        )
    )['_t'] or Decimal('0')


def _calcular_saldo_mes(mes, ano, user=None):
    qs_gasto = Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)
    qs_entrada = Entrada.objects.filter(data__month=mes, data__year=ano)
    if user is not None:
        qs_gasto = qs_gasto.filter(_impacto_q(user))
        qs_entrada = qs_entrada.filter(user=user)
    total_gastos = _agg_sum(qs_gasto)
    total_entradas = _agg_sum(qs_entrada, "valor")
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


def _debitar_conta(gasto):
    """Desconta valor do saldo da conta_origem (para tipo débito)."""
    if gasto.tipo_pagamento == "debito" and gasto.conta_origem_id:
        Conta.objects.filter(pk=gasto.conta_origem_id).update(
            saldo_atual=F("saldo_atual") - gasto.valor_total
        )


def _reverter_debito(tipo, conta_origem_id, valor):
    """Restaura o saldo da conta_origem ao reverter um débito."""
    if tipo == "debito" and conta_origem_id:
        Conta.objects.filter(pk=conta_origem_id).update(
            saldo_atual=F("saldo_atual") + valor
        )


def _creditar_conta(entrada):
    """Soma o valor da entrada no saldo da conta de recebimento."""
    if entrada.tipo != "saldo_anterior" and not entrada.auto_gerada and entrada.conta_id:
        Conta.objects.filter(pk=entrada.conta_id).update(
            saldo_atual=F("saldo_atual") + entrada.valor
        )


def _estornar_credito(tipo, conta_id, valor, auto_gerada=False):
    """Reverte o crédito de uma entrada ao editar ou excluir."""
    if tipo != "saldo_anterior" and not auto_gerada and conta_id:
        Conta.objects.filter(pk=conta_id).update(
            saldo_atual=F("saldo_atual") - valor
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


_MESES_ABREV = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

_TIPO_INV_LABELS = {
    "renda_fixa":        "Renda Fixa",
    "renda_variavel":    "Renda Variável",
    "fundo_imobiliario": "Fundo Imobiliário",
}


def _calcular_valor_parceiro(valor_meu: Decimal, pct_meu: Decimal) -> Decimal:
    pct_outro = Decimal(100) - pct_meu
    total = valor_meu * Decimal("100") / pct_meu
    return (total * pct_outro / Decimal("100")).quantize(Decimal("0.01"))


def _renumerar_e_adicionar_parcela(grupo, base, novo_total, nova_data, user):
    for i, g in enumerate(grupo, 1):
        g.descricao = f"{base} ({i}/{novo_total})"
        g.save(update_fields=["descricao"])
    ultima = grupo[-1]
    Gasto.objects.create(
        user=user,
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


class UserFormKwargsMixin:
    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw


class UserOwnedMixin(LoginRequiredMixin):
    """Restringe get_queryset() ao usuário autenticado em todas as CBVs."""
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class MesAnoMixin:
    """Disponibiliza self.mes e self.ano a partir do request e injeta no contexto.
    Cada view define session_prefix para isolar o filtro de período por aba."""
    session_prefix = ""

    def dispatch(self, request, *args, **kwargs):
        self.mes, self.ano = _mes_ano_from_request(request, prefix=self.session_prefix)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mes"] = self.mes
        ctx["ano"] = self.ano
        return ctx


class SimpleCreateMixin:
    """form_valid genérico: atribui user ao objeto e exibe mensagem de sucesso."""
    success_message = ""

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.user = self.request.user
        obj.save()
        if self.success_message:
            messages.success(self.request, self.success_message)
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))


class SimpleUpdateMixin:
    """form_valid genérico: exibe mensagem de sucesso e delega ao pai."""
    success_message = ""

    def get_success_url(self):
        return _safe_next_url(self.request, str(self.success_url))

    def form_valid(self, form):
        if self.success_message:
            messages.success(self.request, self.success_message)
        return super().form_valid(form)


SimpleDeleteMixin = SimpleUpdateMixin


def _mes_vizinhos(mes, ano):
    """Retorna (mes_ant, ano_ant, mes_prox, ano_prox) para navegação mensal."""
    ref = date(ano, mes, 1)
    ant  = ref - relativedelta(months=1)
    prox = ref + relativedelta(months=1)
    return ant.month, ant.year, prox.month, prox.year


# ── Dashboard ────────────────────────────────────────────────────────────

class DashboardView(MesAnoMixin, LoginRequiredMixin, TemplateView):
    template_name = "gastos/dashboard.html"
    session_prefix = "dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        mes, ano = self.mes, self.ano

        # Mês de início de exibição: jul para o ano padrão, jan para os demais
        _mes_ini_display    = _PERIODO_DEFAULT_MES if ano == _PERIODO_DEFAULT_ANO else 1
        todos_meses         = [(ano, m) for m in range(1, 13)]
        todos_meses_display = [(ano, m) for m in range(_mes_ini_display, 13)]

        _auto_saldo_anterior(mes, ano, user)

        ctx["anos_lista"] = list(range(2026, 2051))

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

        # Q combinado de todos os filtros ativos — aplicado a todos os querysets do dashboard
        filtros_q = Q()
        if responsavel_id:
            filtros_q &= Q(responsavel_id=responsavel_id)
        if cartao_id:
            filtros_q &= Q(cartao_id=cartao_id)
        if tipo_filtro:
            filtros_q &= Q(tipo_pagamento=tipo_filtro)
        if categoria_id:
            filtros_q &= Q(categoria_id=categoria_id)

        # Todos os gastos do mês criados pelo user (qualquer responsável)
        gastos_mes = Gasto.objects.filter(
            user=user,
            data_compra__month=mes, data_compra__year=ano,
        ).filter(filtros_q)

        # Gastos atribuídos ao user (onde o responsavel está vinculado a este login)
        gastos_atribuidos = Gasto.objects.filter(
            responsavel__usuario_vinculado=user,
            data_compra__month=mes, data_compra__year=ano,
        ).filter(filtros_q).exclude(user=user).select_related("responsavel", "cartao", "categoria", "user")

        entradas_mes = Entrada.objects.filter(user=user, data__month=mes, data__year=ano)
        # Gastos do próprio usuário atribuídos ao seu próprio responsável (exclui gastos criados para outros)
        gastos_mes_proprios = Gasto.objects.filter(
            _impacto_q(user),
            user=user,
            data_compra__month=mes,
            data_compra__year=ano,
        ).filter(filtros_q)

        _TIPOS_GASTO = ["credito_avista", "credito_parcelado", "debito", "pix"]
        total_gasto = _agg_sum(gastos_mes_proprios.filter(tipo_pagamento__in=_TIPOS_GASTO))

        contas = Conta.objects.filter(user=user, ativo=True)
        total_contas = _agg_sum(contas, "saldo_atual")
        # Saldo sem filtros (filtros não afetam o saldo real)
        total_gasto_real = _agg_sum(
            Gasto.objects.filter(_impacto_q(user), user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(tipo_pagamento__in=_TIPOS_GASTO)
        )
        saldo = total_contas - total_gasto_real

        # Total para os rodapés das tabelas Gastos e Entradas e Saídas (tudo que aparece nas linhas)
        total_gastos_tabela = _agg_sum(gastos_mes) + _agg_sum(gastos_atribuidos)

        ctx["total_gasto"] = total_gasto
        ctx["total_gastos_tabela"] = total_gastos_tabela
        ctx["saldo"] = saldo
        ctx["qtd_gastos"] = gastos_mes_proprios.filter(tipo_pagamento__in=_TIPOS_GASTO).count()

        # Mês anterior para comparação nos cards
        mes_ant, ano_ant, _, _ = _mes_vizinhos(mes, ano)

        gastos_mes_ant_qs = Gasto.objects.filter(_impacto_q(user), user=user, data_compra__month=mes_ant, data_compra__year=ano_ant)
        ctx["total_gasto_ant"]  = _agg_sum(gastos_mes_ant_qs.filter(tipo_pagamento__in=_TIPOS_GASTO))
        ctx["total_cartao_ant"] = _agg_sum(gastos_mes_ant_qs.filter(tipo_pagamento__in=["credito_avista", "credito_parcelado"]))
        ctx["total_debito_ant"] = _agg_sum(gastos_mes_ant_qs.filter(tipo_pagamento="debito"))
        ctx["total_pix_ant"]    = _agg_sum(gastos_mes_ant_qs.filter(tipo_pagamento="pix"))

        # Gastos do mês do próprio usuário, atribuídos ao seu responsável (base para cards e tabelas)
        gastos_mes_base = Gasto.objects.filter(_impacto_q(user), user=user, data_compra__month=mes, data_compra__year=ano).filter(filtros_q)

        ctx["total_cartao"] = _agg_sum(gastos_mes_base.filter(tipo_pagamento__in=["credito_avista", "credito_parcelado"]))
        ctx["total_cartao_todos"] = _agg_sum(
            Gasto.objects.filter(
                user=user,
                data_compra__month=mes,
                data_compra__year=ano,
                tipo_pagamento__in=["credito_avista", "credito_parcelado"],
            ).filter(filtros_q)
        )
        ctx["total_debito"] = _agg_sum(gastos_mes_base.filter(tipo_pagamento="debito"))
        ctx["total_pix"]    = _agg_sum(gastos_mes_base.filter(tipo_pagamento="pix"))
        ctx["tabela_por_responsavel"] = (
            Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(filtros_q)
            .exclude(responsavel__usuario_vinculado=user)
            .values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_cartao"] = (
            Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(filtros_q)
            .filter(cartao__isnull=False)
            .values("cartao__id", "cartao__nome", "cartao__cor", "cartao__tipo")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_emprestimo"] = (
            Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(filtros_q)
            .filter(tipo_pagamento="emprestimo")
            .values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_pix"] = (
            Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(filtros_q)
            .filter(tipo_pagamento="pix")
            .values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_debito"] = (
            Gasto.objects.filter(user=user, data_compra__month=mes, data_compra__year=ano)
            .filter(filtros_q)
            .filter(tipo_pagamento="debito")
            .values("conta_origem__id", "conta_origem__nome", "conta_origem__banco")
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

        # Gráfico de evolução mensal dos investimentos no dashboard — filtrado pelo ano selecionado
        MESES_PT_D = _MESES_ABREV
        todos_inv    = list(Investimento.objects.filter(user=user))
        inv_ids_dash = [i.pk for i in todos_inv]
        hist_dash = list(InvestimentoHistorico.objects.filter(
            investimento_id__in=inv_ids_dash
        ).order_by("data_movimentacao").values("investimento_id", "valor_novo", "diferenca", "tipo", "data_movimentacao"))

        # Saldo acumulado até 31/dez do ano anterior (carry-forward para o ano selecionado)
        saldo_inicio_ano = {}
        aportes_d = {}
        saques_d  = {}
        meses_saldo_ano = {}
        for r in hist_dash:
            r_ano = r["data_movimentacao"].year
            r_mes = r["data_movimentacao"].month
            chave = (r_ano, r_mes)
            tipo = r.get("tipo") or "rendimento"
            dif  = float(r["diferenca"])
            if r_ano < ano:
                saldo_inicio_ano[r["investimento_id"]] = float(r["valor_novo"])
            elif r_ano == ano:
                if chave not in meses_saldo_ano:
                    meses_saldo_ano[chave] = {}
                meses_saldo_ano[chave][r["investimento_id"]] = float(r["valor_novo"])
                if tipo in ("aporte", "inicial"):
                    aportes_d[chave] = aportes_d.get(chave, 0) + max(0, dif)
                elif tipo == "saque":
                    saques_d[chave] = saques_d.get(chave, 0) + abs(min(0, dif))

        dash_labels, dash_dados, dash_aportes_bar, dash_saques_bar = [], [], [], []
        if inv_ids_dash:
            saldo_acum_d = dict(saldo_inicio_ano)
            start_month  = _mes_ini_display
            hoje_d       = date.today()
            end_d        = date(ano, 12, 1) if ano < hoje_d.year else date(hoje_d.year, hoje_d.month, 1)
            cur = date(ano, start_month, 1)
            while cur <= end_d:
                chave = (cur.year, cur.month)
                if chave in meses_saldo_ano:
                    saldo_acum_d.update(meses_saldo_ano[chave])
                dash_labels.append(f"{MESES_PT_D[cur.month-1]}/{cur.year}")
                dash_dados.append(round(sum(saldo_acum_d.values()), 2))
                dash_aportes_bar.append(round(aportes_d.get(chave, 0), 2))
                dash_saques_bar.append(round(saques_d.get(chave, 0), 2))
                cur += relativedelta(months=1)

        ctx["dash_inv_labels"]      = _safe_json(dash_labels)
        ctx["dash_inv_dados"]       = _safe_json(dash_dados)
        ctx["dash_inv_aportes_bar"] = _safe_json(dash_aportes_bar)
        ctx["dash_inv_saques_bar"]  = _safe_json(dash_saques_bar)

        # Rosca — distribuição por tipo (investimentos ativos no dash)
        tipo_dash = defaultdict(float)
        for inv in investimentos_dash:
            tipo_dash[_TIPO_INV_LABELS.get(inv.tipo_investimento, inv.tipo_investimento)] += float(inv.saldo_atual)
        ctx["dash_rosca_labels"] = _safe_json(list(tipo_dash.keys()))
        ctx["dash_rosca_dados"]  = _safe_json([round(v, 2) for v in tipo_dash.values()])

        # Por categoria (gráfico pizza) — mês/ano selecionado, apenas gastos do próprio user
        gastos_cat_qs = Gasto.objects.filter(
            user=user,
            data_compra__year=ano,
            data_compra__month=mes,
        ).filter(filtros_q)
        por_categoria = (
            gastos_cat_qs.values("categoria__nome", "categoria__cor")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["categorias_labels"] = _safe_json([
            c["categoria__nome"] or "Sem categoria" for c in por_categoria
        ])
        ctx["categorias_valores"] = _safe_json([float(c["total"]) for c in por_categoria])
        ctx["categorias_cores"] = _safe_json([
            c["categoria__cor"] or "#888888" for c in por_categoria
        ])

        # Gráfico de período — ano selecionado, apenas gastos do próprio user
        meses_nomes = _MESES_ABREV
        periodo_qs = Gasto.objects.filter(
            user=user,
            data_compra__year=ano,
            data_compra__month__gte=_mes_ini_display,
        ).filter(filtros_q).values("data_compra__month", "data_compra__year")

        dados_periodo = {
            item["data_compra__month"]: float(item["total"] or 0)
            for item in periodo_qs.annotate(total=Sum("valor_total"))
            .values("data_compra__year", "data_compra__month", "total")
        }
        periodo_labels  = [f"{meses_nomes[m-1]}/{ano}" for _, m in todos_meses_display]
        periodo_valores = [dados_periodo.get(m, 0.0) for _, m in todos_meses_display]

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
                "tipo_pag": "recorrente" if g.grupo_recorrente else g.tipo_pagamento,
                "tipo_label": "Recorrente" if g.grupo_recorrente else g.get_tipo_pagamento_display(),
                "descricao": g.descricao,
                "categoria": g.categoria,
                "responsavel": str(g.responsavel),
                "cartao": g.cartao.nome if g.cartao else "",
                "cartao_cor": g.cartao.cor if g.cartao else "",
                "valor": float(g.valor_total),
                "pk": g.pk,
                "parcelas": g.total_parcelas if g.tipo_pagamento == "credito_parcelado" else None,
                "dividido": bool(g.grupo_divisao),
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
                "responsavel": str(e.responsavel) if e.responsavel else "",
                "cartao": "",
                "cartao_cor": "",
                "valor": float(e.valor),
                "pk": e.pk,
                "parcelas": None,
                "dividido": False,
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
                "tipo_pag": "recorrente" if g.grupo_recorrente else g.tipo_pagamento,
                "tipo_label": "Recorrente" if g.grupo_recorrente else g.get_tipo_pagamento_display(),
                "descricao": g.descricao,
                "categoria": g.categoria,
                "responsavel": str(g.responsavel),
                "cartao": g.cartao.nome if g.cartao else "",
                "cartao_cor": g.cartao.cor if g.cartao else "",
                "valor": float(g.valor_total),
                "pk": None,
                "parcelas": g.total_parcelas if g.tipo_pagamento == "credito_parcelado" else None,
                "dividido": bool(g.grupo_divisao),
                "auto_gerada": False,
                "atribuido": True,
                "atribuido_por": owner_name,
            })

        transacoes.sort(key=lambda x: x["data"], reverse=True)
        ctx["transacoes_mes"] = transacoes
        ctx["entradas_mes_lista"] = entradas_lista
        ctx["total_entradas_tabela"] = sum(float(e.valor) for e in entradas_lista)

        # Tabela: Gastos vs Entradas — Visão Mensal
        entradas_qs = (
            Entrada.objects.filter(user=user).exclude(tipo="saldo_anterior")
            .values("data__year", "data__month")
            .annotate(t=Sum("valor"))
        )
        # Gastos que impactam o usuário por mês — SEM filtros para o saldo não mudar com filtros ativos
        gastos_principal_qs = (
            Gasto.objects.filter(_impacto_q(user))
            .values("data_compra__year", "data_compra__month")
            .annotate(t=Sum("valor_total"))
        )

        entradas_map  = {(r["data__year"], r["data__month"]): float(r["t"] or 0) for r in entradas_qs}
        gastos_map    = {(r["data_compra__year"], r["data_compra__month"]): float(r["t"] or 0) for r in gastos_principal_qs}
        # Total de cartão por mês — todos os gastos do user no cartão, qualquer responsável
        cartao_map = {
            (r["data_compra__year"], r["data_compra__month"]): float(r["t"] or 0)
            for r in Gasto.objects.filter(
                user=user,
                tipo_pagamento__in=["credito_avista", "credito_parcelado"],
            ).values("data_compra__year", "data_compra__month").annotate(t=Sum("valor_total"))
        }

        # Derivar saldo de 1º de Janeiro a partir do saldo atual das contas.
        # total_contas = balance_jan1 + próprias_entradas_ytd − próprios_débitos_ytd
        # → balance_jan1 = total_contas − próprias_entradas_ytd + próprios_débitos_ytd
        _hoje = date.today()
        if ano == _hoje.year and todos_meses:
            _ent_ytd = (
                Entrada.objects.filter(
                    user=user,
                    data__year=ano,
                    data__month__lte=_hoje.month,
                ).exclude(tipo="saldo_anterior")
                .aggregate(t=Sum("valor"))["t"] or Decimal("0")
            )
            _deb_ytd = (
                Gasto.objects.filter(
                    user=user,
                    tipo_pagamento="debito",
                    data_compra__year=ano,
                    data_compra__month__lte=_hoje.month,
                ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
            )
            running = total_contas - _ent_ytd + _deb_ytd
        else:
            saldo_ant_qs = (
                Entrada.objects.filter(user=user, tipo="saldo_anterior")
                .values("data__year", "data__month")
                .annotate(t=Sum("valor"))
            )
            saldo_ant_map = {
                (r["data__year"], r["data__month"]): float(r["t"] or 0)
                for r in saldo_ant_qs
            }
            running = Decimal(str(saldo_ant_map.get(todos_meses[0], 0.0))) if todos_meses else Decimal("0")

        tabela_mensal = []
        for i, (y, m) in enumerate(todos_meses):
            k = (y, m)
            sa  = running
            ent = Decimal(str(entradas_map.get(k, 0.0)))
            gas = Decimal(str(gastos_map.get(k, 0.0)))
            car = Decimal(str(cartao_map.get(k, 0.0)))
            saldo_atual = sa + ent - gas
            tabela_mensal.append({
                "label":       f"{meses_nomes[m-1]}/{str(y)[-2:]}",
                "saldo_ant":   float(sa),
                "entradas":    float(ent),
                "gastos":      float(gas),
                "cartao":      float(car),
                "saldo_mes":   float(ent - gas),
                "saldo_atual": float(saldo_atual),
                "atual":       (y == ano and m == mes),
            })
            running = saldo_atual

        # Para exibição: apenas os meses a partir de jul no ano de início do app
        tabela_mensal_display = tabela_mensal[_mes_ini_display - 1:]
        ctx["tabela_mensal"] = tabela_mensal_display

        # Card "Saldo do Mês": usa o carry-forward da tabela para o mês selecionado
        for col in tabela_mensal:
            if col["atual"]:
                ctx["saldo"] = Decimal(str(col["saldo_atual"]))
                break

        # Gráficos "Gastos vs Receitas" e "Receitas ao Longo do Tempo" — dados totais do user, sem filtro de responsável
        ctx["comp_labels"]   = json.dumps([c["label"] for c in tabela_mensal_display])
        ctx["comp_gastos"]   = json.dumps([gastos_map.get(k, 0.0) for k in todos_meses_display])
        ctx["comp_entradas"] = json.dumps([c["entradas"] + c["saldo_ant"] for c in tabela_mensal_display])
        ctx["comp_saldo"]    = json.dumps([c["saldo_atual"] for c in tabela_mensal_display])
        ctx["comp_receitas"] = json.dumps([c["entradas"] for c in tabela_mensal_display])

        # Tabela Responsáveis × Meses — gastos criados pelo user para outros responsáveis (excluindo o próprio)
        resp_qs = (
            Gasto.objects.filter(user=user)
            .filter(filtros_q)
            .exclude(responsavel__usuario_vinculado=user)
            .values(
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
                "valores": [resp_map[rid].get(k) for k in todos_meses_display],
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
            .filter(filtros_q)
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
                "tipo": "parcelado",
                "meses": [data["meses"].get(mes_num) for _, mes_num in todos_meses_display],
            })

        # Recorrentes × Meses (mesmo ano, agrupados por grupo_recorrente)
        recorrentes_ano_qs = (
            Gasto.objects.filter(
                user=user,
                data_compra__year=ano,
                grupo_recorrente__isnull=False,
            )
            .filter(filtros_q)
            .select_related("responsavel", "cartao")
            .order_by("data_compra")
        )
        rec_map: dict = {}
        rec_order: list = []
        for g in recorrentes_ano_qs:
            key = g.grupo_recorrente
            if key not in rec_map:
                rec_map[key] = {
                    "descricao": g.descricao,
                    "responsavel": g.responsavel,
                    "cartao": g.cartao,
                    "meses": {},
                }
                rec_order.append(key)
            rec_map[key]["meses"][g.data_compra.month] = {"valor": float(g.valor_total)}

        for key in rec_order:
            data = rec_map[key]
            tabela_parcelados.append({
                "descricao": data["descricao"],
                "responsavel": data["responsavel"],
                "cartao": data["cartao"],
                "total_parcelas": None,
                "tipo": "recorrente",
                "meses": [data["meses"].get(mes_num) for _, mes_num in todos_meses_display],
            })

        ctx["tabela_parcelados"] = tabela_parcelados

        # Tabela Gastos Divididos × Meses
        split_qs = (
            Gasto.objects.filter(
                user=user,
                grupo_divisao__isnull=False,
                data_compra__year=ano,
            )
            .filter(filtros_q)
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
                "meses": [d["meses"].get(mes_num) for _, mes_num in todos_meses_display],
            })
        ctx["tabela_divididos"] = tabela_divididos

        return ctx


# ── Gastos ─────────────────────────────────────────────────────────────

class GastoListView(MesAnoMixin, UserOwnedMixin, ListView):
    model = Gasto
    template_name = "gastos/gasto_list.html"
    session_prefix = "gastos"
    context_object_name = "gastos"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("responsavel", "cartao", "categoria")
        qs = qs.filter(data_compra__month=self.mes, data_compra__year=self.ano)
        responsavel = self.request.GET.get("responsavel")
        cartao = self.request.GET.get("cartao")
        categoria = self.request.GET.get("categoria")
        tipo = self.request.GET.get("tipo")
        busca = self.request.GET.get("busca", "").strip()
        if responsavel:
            qs = qs.filter(responsavel_id=responsavel)
        if cartao:
            qs = qs.filter(cartao_id=cartao)
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        if tipo:
            if tipo == "recorrente":
                qs = qs.filter(grupo_recorrente__isnull=False)
            elif tipo == "credito_avista":
                qs = qs.filter(tipo_pagamento="credito_avista", grupo_recorrente__isnull=True)
            else:
                qs = qs.filter(tipo_pagamento=tipo)
        if busca:
            qs = qs.filter(descricao__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["responsaveis"] = Responsavel.objects.filter(ativo=True, user=self.request.user)
        ctx["cartoes"] = Cartao.objects.filter(ativo=True, user=self.request.user)
        ctx["categorias"] = Categoria.objects.filter(ativo=True, user=self.request.user)
        ctx["tipos"] = Gasto.TIPO_PAGAMENTO_CHOICES
        ctx["filtros"] = self.request.GET
        ctx["total_filtrado"] = _agg_sum(self.object_list)
        return ctx


class GastoCreateView(UserFormKwargsMixin, UserOwnedMixin, CreateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def get_initial(self):
        hoje = date.today()
        initial = {"mes_inicio": hoje.month, "ano_inicio": hoje.year}
        resp = Responsavel.objects.filter(user=self.request.user, usuario_vinculado=self.request.user).first()
        if resp:
            initial["responsavel"] = resp.pk
        return initial

    def form_valid(self, form):
        gasto = form.save(commit=False)
        gasto.user = self.request.user

        # tipo "recorrente" é um alias de UI: salva como credito_avista e força recorrente=True
        if gasto.tipo_pagamento == "recorrente":
            gasto.tipo_pagamento = "credito_avista"
            form.cleaned_data["recorrente"] = True

        n = gasto.total_parcelas if gasto.tipo_pagamento == "credito_parcelado" else None

        data_inicio = gasto.data_compra
        mes_ini = form.cleaned_data.get("mes_inicio")
        ano_ini = form.cleaned_data.get("ano_inicio")
        if mes_ini and ano_ini:
            try:
                data_inicio = date(int(ano_ini), int(mes_ini), 1)
            except (ValueError, TypeError):
                pass

        recorrente = form.cleaned_data.get("recorrente")
        _rec_val = form.cleaned_data.get("recorrente_meses") or "12"
        if _rec_val == "sempre":
            _fim = date(2050, 12, 1)
            _ini = data_inicio if recorrente else date.today().replace(day=1)
            recorrente_meses = (_fim.year - _ini.year) * 12 + (_fim.month - _ini.month) + 1
        else:
            recorrente_meses = int(_rec_val)
        grupo_recorrente_id = uuid.uuid4() if recorrente else None

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
                conta_origem=gasto.conta_origem,
                responsavel=responsavel,
                categoria=gasto.categoria,
                observacao=gasto.observacao,
                total_parcelas=n,
                user=self.request.user,
                grupo_divisao=grupo,
                pct_divisao=pct,
                grupo_recorrente=grupo_recorrente_id,
                cartao_adicional=gasto.cartao_adicional,
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
            elif grupo_recorrente_id:
                for i in range(recorrente_meses):
                    g = Gasto.objects.create(
                        descricao=desc,
                        data_compra=data_inicio + relativedelta(months=i),
                        **kwargs_base,
                    )
                    if i == 0:
                        _debitar_conta(g)
            else:
                g = Gasto.objects.create(descricao=desc, data_compra=data_inicio, **kwargs_base)
                _debitar_conta(g)

        if n:
            if grupo_id:
                _criar_gastos(gasto.responsavel, valor_meu,   pct_meu,   grupo_id)
                _criar_gastos(dividir_com,       valor_outro, pct_outro, grupo_id)
            else:
                _criar_gastos(gasto.responsavel, gasto.valor_total, None, None)
        else:
            if grupo_id:
                _criar_gastos(gasto.responsavel, valor_meu,   pct_meu,   grupo_id)
                _criar_gastos(dividir_com,       valor_outro, pct_outro, grupo_id)
            elif grupo_recorrente_id:
                _criar_gastos(gasto.responsavel, gasto.valor_total, None, None)
            else:
                gasto.data_compra = data_inicio
                gasto.save()
                _debitar_conta(gasto)

        _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year, self.request.user)
        usuario_atribuido = gasto.responsavel.usuario_vinculado
        if usuario_atribuido and usuario_atribuido != self.request.user:
            _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year, usuario_atribuido)
        if grupo_recorrente_id:
            label = "até dez/2050" if _rec_val == "sempre" else f"{recorrente_meses} meses"
            messages.success(self.request, f"Gasto recorrente criado ({label}).")
        elif grupo_id:
            messages.success(self.request, "Gasto dividido e registrado para os dois responsáveis.")
        else:
            messages.success(self.request, "Gasto registrado com sucesso.")
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))

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


class GastoUpdateView(UserFormKwargsMixin, UserOwnedMixin, UpdateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def _is_divisao_main(self, obj):
        """Retorna True se este gasto é o lado 'próprio' de um split (responsável vinculado ao user logado)."""
        if not obj or not obj.grupo_divisao:
            return False
        vinculado = obj.responsavel.usuario_vinculado
        return vinculado is None or vinculado == self.request.user

    def get_initial(self):
        initial = super().get_initial()
        obj = self.object or self.get_object()
        if obj and obj.data_compra:
            initial["mes_inicio"] = obj.data_compra.month
            initial["ano_inicio"] = obj.data_compra.year
        if obj and obj.tipo_pagamento == "credito_parcelado":
            m = _PARCELA_GROUP_RE.match(obj.descricao)
            if m:
                initial["descricao"] = m.group(1).strip()
        if obj and obj.grupo_divisao:
            # Parceiro = outro responsável (diferente do atual) no mesmo grupo
            parceiro = (
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=obj.grupo_divisao,
                ).exclude(pk=obj.pk).exclude(responsavel=obj.responsavel).first()
            )
            initial["dividir_gasto"] = True
            if parceiro:
                initial["dividir_com"] = parceiro.responsavel_id
            initial["pct_responsavel"] = str(obj.pct_divisao or 50)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object and self.object.grupo_recorrente:
            form.initial["tipo_pagamento"] = "recorrente"
        return form

    def form_valid(self, form):
        old = self.object
        data_antiga = old.data_compra
        old_tipo = old.tipo_pagamento
        old_conta_id = old.conta_origem_id
        old_valor = old.valor_total
        # Captura ANTES de form.save pois old is gasto (mesmo objeto Python)
        old_descricao = old.descricao
        old_grupo_parcelado = (
            _encontrar_grupo_parcelado(old, self.request.user)
            if old.tipo_pagamento == "credito_parcelado" else []
        )

        # Reverte débito anterior antes de salvar
        _reverter_debito(old_tipo, old_conta_id, old_valor)

        gasto = form.save(commit=False)

        # "recorrente" é alias de UI: converte para credito_avista
        if gasto.tipo_pagamento == "recorrente":
            gasto.tipo_pagamento = "credito_avista"

        # Aplica mes_inicio/ano_inicio como data_compra para crédito à vista
        if gasto.tipo_pagamento == "credito_avista":
            mes_ini = form.cleaned_data.get("mes_inicio")
            ano_ini = form.cleaned_data.get("ano_inicio")
            if mes_ini and ano_ini:
                try:
                    gasto.data_compra = date(int(ano_ini), int(mes_ini), 1)
                except (ValueError, TypeError):
                    pass

        # Atualiza pct_divisao se o formulário enviou pct_responsavel (edição do lado principal)
        pct_responsavel_raw = form.cleaned_data.get("pct_responsavel")
        if pct_responsavel_raw and gasto.grupo_divisao:
            new_pct = int(pct_responsavel_raw)
            if gasto.pct_divisao != new_pct:
                gasto.pct_divisao = new_pct

        # Propaga descrição para todo o grupo parcelado
        if old.tipo_pagamento == "credito_parcelado":
            m_old = _PARCELA_GROUP_RE.match(old_descricao)
            if m_old:
                old_base = m_old.group(1).strip()
                new_base = gasto.descricao.strip()
                # Restaura o sufixo "(X/N)" na parcela que está sendo salva
                gasto.descricao = f"{new_base} ({m_old.group(2)}/{m_old.group(3)})"
                if new_base != old_base:
                    # Atualiza todas as outras parcelas do mesmo responsável
                    for p in old_grupo_parcelado:
                        if p.pk == gasto.pk:
                            continue
                        m_p = _PARCELA_GROUP_RE.match(p.descricao)
                        if m_p:
                            p.descricao = f"{new_base} ({m_p.group(2)}/{m_p.group(3)})"
                            p.save(update_fields=["descricao"])
                    # Se dividido: propaga para o outro lado (todas as parcelas)
                    if old.grupo_divisao:
                        for p in Gasto.objects.filter(
                            user=self.request.user,
                            grupo_divisao=old.grupo_divisao,
                        ).exclude(responsavel=old.responsavel):
                            m_p = _PARCELA_GROUP_RE.match(p.descricao)
                            if m_p:
                                p.descricao = f"{new_base} ({m_p.group(2)}/{m_p.group(3)})"
                                p.save(update_fields=["descricao"])

        gasto.save()

        # Propaga descrição para recorrentes futuros (mesmo grupo_recorrente)
        if gasto.grupo_recorrente and gasto.descricao != old_descricao:
            Gasto.objects.filter(
                user=self.request.user,
                grupo_recorrente=gasto.grupo_recorrente,
                data_compra__gte=gasto.data_compra,
            ).exclude(pk=gasto.pk).update(descricao=gasto.descricao)

        # Aplica novo débito
        _debitar_conta(gasto)

        usuario_atribuido = gasto.responsavel.usuario_vinculado

        # Sincroniza com o outro lado do split (se existir) — exclui o próprio responsável para
        # não pegar outra parcela do mesmo responsável em grupos de parcelado+dividido
        if gasto.grupo_divisao:
            parceiro = (
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=gasto.grupo_divisao,
                    data_compra__month=data_antiga.month,
                    data_compra__year=data_antiga.year,
                )
                .exclude(pk=gasto.pk)
                .exclude(responsavel=gasto.responsavel)
                .first()
            )
            if parceiro:
                pct_meu   = Decimal(gasto.pct_divisao or 50)
                pct_outro = Decimal(100) - pct_meu
                novo_valor_parceiro = _calcular_valor_parceiro(gasto.valor_total, pct_meu)
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

        # Propaga valor para os próximos meses (recorrente ou dividido)
        aplicar_escopo = self.request.POST.get("aplicar_escopo", "apenas_este")
        if aplicar_escopo == "este_e_proximos":
            novo_valor = gasto.valor_total
            pct_meu = Decimal(gasto.pct_divisao or 50)
            if gasto.grupo_recorrente:
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_recorrente=gasto.grupo_recorrente,
                    responsavel=gasto.responsavel,
                    data_compra__gt=gasto.data_compra,
                ).update(valor_total=novo_valor)
                if gasto.grupo_divisao:
                    valor_parceiro = _calcular_valor_parceiro(novo_valor, pct_meu)
                    Gasto.objects.filter(
                        user=self.request.user,
                        grupo_recorrente=gasto.grupo_recorrente,
                        data_compra__gt=gasto.data_compra,
                    ).exclude(responsavel=gasto.responsavel).update(valor_total=valor_parceiro)
            elif gasto.grupo_divisao:
                valor_parceiro = _calcular_valor_parceiro(novo_valor, pct_meu)
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=gasto.grupo_divisao,
                    responsavel=gasto.responsavel,
                    data_compra__gt=gasto.data_compra,
                ).update(valor_total=novo_valor)
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=gasto.grupo_divisao,
                    data_compra__gt=gasto.data_compra,
                ).exclude(responsavel=gasto.responsavel).update(valor_total=valor_parceiro)

        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, self.request.user)
        if gasto.data_compra != data_antiga:
            _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year, self.request.user)
        if usuario_atribuido and usuario_atribuido != self.request.user:
            _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, usuario_atribuido)
            if gasto.data_compra != data_antiga:
                _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year, usuario_atribuido)
        if aplicar_escopo == "este_e_proximos" and (gasto.grupo_recorrente or gasto.grupo_divisao):
            messages.success(self.request, "Gasto atualizado e alterações aplicadas aos próximos meses.")
        else:
            messages.success(self.request, "Gasto atualizado com sucesso.")
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Gasto"
        ctx["is_edit"] = True
        gasto = self.object
        ctx["is_divisao_main"] = self._is_divisao_main(gasto)
        if gasto.grupo_divisao:
            ctx["parceiro_divisao"] = (
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_divisao=gasto.grupo_divisao,
                ).exclude(responsavel=gasto.responsavel).first()
            )
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
    next_url = _safe_next_url(request, reverse_lazy("gasto-update", kwargs={"pk": pk}))

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
            pct_meu = Decimal(gasto.pct_divisao)
            novo_valor_parceiro = _calcular_valor_parceiro(novo_valor, pct_meu)
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

    nova_data = grupo[-1].data_compra + relativedelta(months=1)
    _renumerar_e_adicionar_parcela(grupo, base, novo_total, nova_data, request.user)

    # Se é gasto dividido, repete a operação para o outro lado do split
    if grupo[-1].grupo_divisao:
        outro_grupo = list(
            Gasto.objects.filter(
                user=request.user,
                grupo_divisao=grupo[-1].grupo_divisao,
            )
            .exclude(responsavel=grupo[-1].responsavel)
            .order_by("data_compra")
        )
        if outro_grupo:
            _renumerar_e_adicionar_parcela(outro_grupo, base, novo_total, nova_data, request.user)

    _recalcular_saldos_a_partir(nova_data.month, nova_data.year, request.user)
    messages.success(request, f"Parcela {novo_total}/{novo_total} adicionada ao grupo.")
    return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))


@login_required
def gasto_parcelas_delete_from(request, pk):
    """Exclui a parcela pk e todas as seguintes do mesmo grupo."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))

    gasto = get_object_or_404(Gasto, pk=pk, user=request.user)
    grupo = _encontrar_grupo_parcelado(gasto, request.user)
    if not grupo:
        messages.error(request, "Grupo de parcelas não encontrado.")
        return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": pk}))

    data_ref = gasto.data_compra
    anteriores = [p for p in grupo if p.data_compra < data_ref]
    a_excluir = [p for p in grupo if p.data_compra >= data_ref]

    count = len(a_excluir)
    for p in a_excluir:
        _reverter_debito(p.tipo_pagamento, p.conta_origem_id, p.valor_total)
        p.delete()

    _recalcular_saldos_a_partir(data_ref.month, data_ref.year, request.user)
    messages.success(request, f"{count} parcela(s) excluída(s) a partir de {data_ref.strftime('%b/%Y')}.")

    if anteriores:
        return HttpResponseRedirect(reverse_lazy("gasto-update", kwargs={"pk": anteriores[-1].pk}))
    return HttpResponseRedirect(reverse_lazy("gasto-list"))


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
        # Salva info do débito antes de deletar
        _reverter_debito(gasto.tipo_pagamento, gasto.conta_origem_id, gasto.valor_total)

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

        # Exclusão de recorrentes: "apenas_este" ou "este_e_proximos"
        delete_mode = self.request.POST.get("delete_mode", "apenas_este")
        if gasto.grupo_recorrente and delete_mode == "este_e_proximos":
            proximos = list(
                Gasto.objects.filter(
                    user=self.request.user,
                    grupo_recorrente=gasto.grupo_recorrente,
                    data_compra__gte=gasto.data_compra,
                ).exclude(pk=gasto.pk)
            )
            for p in proximos:
                _reverter_debito(p.tipo_pagamento, p.conta_origem_id, p.valor_total)
                p.delete()

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
        msg = "Gasto recorrente excluído (este e os próximos)." if (gasto.grupo_recorrente and delete_mode == "este_e_proximos") else "Gasto excluído com sucesso."
        messages.success(self.request, msg)
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))


# ── Cartões ─────────────────────────────────────────────────────────────

class CartaoListView(MesAnoMixin, UserOwnedMixin, ListView):
    model = Cartao
    template_name = "cartoes/cartao_list.html"
    session_prefix = "cartoes"
    context_object_name = "cartoes"

    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = self.mes, self.ano
        user = self.request.user
        qs_faturas = Gasto.objects.filter(
            user=user,
            data_compra__month=mes,
            data_compra__year=ano,
            tipo_pagamento__in=["credito_avista", "credito_parcelado"],
            cartao__isnull=False,
        )
        fatura_map = {
            r["cartao_id"]: r["t"]
            for r in qs_faturas.values("cartao_id").annotate(t=Sum("valor_total"))
        }
        adicional_map = {
            r["cartao_id"]: r["t"]
            for r in qs_faturas.filter(cartao_adicional=True).values("cartao_id").annotate(t=Sum("valor_total"))
        }
        for cartao in ctx["cartoes"]:
            cartao.fatura_mes = fatura_map.get(cartao.pk) or Decimal("0")
            cartao.adicional_mes = adicional_map.get(cartao.pk) or Decimal("0")
        return ctx


class CartaoDetailView(MesAnoMixin, UserOwnedMixin, DetailView):
    model = Cartao
    template_name = "cartoes/cartao_detail.html"
    context_object_name = "cartao"
    session_prefix = "cartoes"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = self.mes, self.ano
        request = self.request

        tipo_cartao = request.GET.get("tipo_cartao", "")
        responsavel_id = request.GET.get("responsavel_filtro", "")

        qs = (
            Gasto.objects.filter(
                cartao=self.object, user=request.user,
                data_compra__month=mes, data_compra__year=ano,
            )
            .select_related("responsavel", "categoria")
            .order_by("-data_compra")
        )
        if tipo_cartao == "principal":
            qs = qs.filter(cartao_adicional=False)
        elif tipo_cartao == "adicional":
            qs = qs.filter(cartao_adicional=True)
        if responsavel_id:
            qs = qs.filter(responsavel_id=responsavel_id)

        ctx["gastos"] = qs
        ctx["total_fatura"]    = _agg_sum(qs)
        ctx["total_adicional"] = _agg_sum(qs.filter(cartao_adicional=True))
        ctx["mes_ant"], ctx["ano_ant"], ctx["mes_prox"], ctx["ano_prox"] = _mes_vizinhos(mes, ano)
        ctx["responsaveis"] = Responsavel.objects.filter(user=request.user, ativo=True).order_by("nome")
        ctx["filtro_tipo_cartao"] = tipo_cartao
        ctx["filtro_responsavel"] = responsavel_id
        return ctx


class CartaoCreateView(SimpleCreateMixin, UserOwnedMixin, CreateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "cartoes/cartao_form.html"
    success_url = reverse_lazy("cartao-list")
    success_message = "Cartão criado com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Cartão"
        return ctx


class CartaoUpdateView(SimpleUpdateMixin, UserOwnedMixin, UpdateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "cartoes/cartao_form.html"
    success_url = reverse_lazy("cartao-list")
    success_message = "Cartão atualizado com sucesso."

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

class ResponsavelListView(MesAnoMixin, UserOwnedMixin, ListView):
    model = Responsavel
    template_name = "responsaveis/responsavel_list.html"
    context_object_name = "responsaveis"
    session_prefix = "responsaveis"

    def get_queryset(self):
        # Exclui o próprio responsável do login (principal ou vinculado ao mesmo user)
        return (
            super().get_queryset()
            .filter(is_principal=False)
            .exclude(usuario_vinculado=self.request.user)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        mes, ano = self.mes, self.ano

        responsavel_id = self.request.GET.get("responsavel")
        cartao_id = self.request.GET.get("cartao")
        ctx["filtro_responsavel"] = responsavel_id
        ctx["filtro_cartao"] = cartao_id
        ctx["cartoes_lista"] = Cartao.objects.filter(ativo=True, user=user)

        gastos_mes = (
            Gasto.objects.filter(_impacto_q(user), data_compra__month=mes, data_compra__year=ano)
            .values("responsavel__id")
            .annotate(total=Sum("valor_total"))
        )
        ctx["gastos_por_resp"] = {r["responsavel__id"]: r["total"] for r in gastos_mes}
        ctx["mes_atual"] = mes
        ctx["ano_atual"] = ano

        # Gastos detalhados por responsável para as tabelas (exclui o próprio login)
        gastos_q = Q(
            user=user,
            data_compra__month=mes,
            data_compra__year=ano,
            responsavel__is_principal=False,
        )
        gastos_q &= ~Q(responsavel__usuario_vinculado=user)
        if responsavel_id:
            gastos_q &= Q(responsavel_id=responsavel_id)
        if cartao_id:
            gastos_q &= Q(cartao_id=cartao_id)

        gastos_qs = (
            Gasto.objects.filter(gastos_q)
            .select_related("responsavel", "cartao")
            .order_by("-data_compra", "descricao")
        )

        gastos_por_resp_tabela = defaultdict(list)
        totais_por_resp = defaultdict(Decimal)
        for g in gastos_qs:
            m = _PARCELA_GROUP_RE.match(g.descricao)
            if m:
                parcela_num = int(m.group(2))
                parcela_total = int(m.group(3))
                desc_base = m.group(1).strip()
            else:
                parcela_num = None
                parcela_total = g.total_parcelas
                desc_base = g.descricao
            gastos_por_resp_tabela[g.responsavel_id].append({
                "pk": g.pk,
                "descricao": desc_base,
                "tipo_pagamento": g.tipo_pagamento,
                "tipo_label": g.get_tipo_pagamento_display(),
                "parcela_num": parcela_num,
                "parcela_total": parcela_total,
                "cartao": g.cartao,
                "valor_total": g.valor_total,
                "data_compra": g.data_compra,
            })
            totais_por_resp[g.responsavel_id] += g.valor_total

        ctx["gastos_por_resp_tabela"] = dict(gastos_por_resp_tabela)
        ctx["totais_por_resp"] = dict(totais_por_resp)

        # IDs de responsáveis marcados como "acerto pago" no mês/ano filtrado
        ctx["acertos_ids"] = set(
            PagamentoFeito.objects.filter(user=user, mes=mes, ano=ano, tipo="acerto")
            .values_list("responsavel_id", flat=True)
        )

        return ctx


class ResponsavelCreateView(SimpleCreateMixin, UserOwnedMixin, CreateView):
    model = Responsavel
    form_class = ResponsavelForm
    template_name = "responsaveis/responsavel_form.html"
    success_url = reverse_lazy("responsavel-list")
    success_message = "Responsável criado com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Responsável"
        return ctx


class ResponsavelUpdateView(SimpleUpdateMixin, UserOwnedMixin, UpdateView):
    model = Responsavel
    form_class = ResponsavelForm
    template_name = "responsaveis/responsavel_form.html"
    success_url = reverse_lazy("responsavel-list")
    success_message = "Responsável atualizado com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Responsável"
        return ctx


class ResponsavelDeleteView(UserOwnedMixin, DeleteView):
    model = Responsavel
    template_name = "responsaveis/responsavel_confirm_delete.html"
    success_url = reverse_lazy("responsavel-list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        resp = self.object
        ctx["gastos_proprios_count"] = Gasto.objects.filter(responsavel=resp, user=self.request.user).count()
        ctx["tem_gastos_externos"] = Gasto.objects.filter(responsavel=resp).exclude(user=self.request.user).exists()
        return ctx

    def form_valid(self, form):
        resp = self.object
        if Gasto.objects.filter(responsavel=resp).exclude(user=self.request.user).exists():
            messages.error(self.request, "Este responsável possui gastos atribuídos por outro usuário e não pode ser excluído.")
            return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))
        datas = list(
            Gasto.objects.filter(responsavel=resp, user=self.request.user)
            .values_list("data_compra__month", "data_compra__year").distinct()
        )
        Gasto.objects.filter(responsavel=resp, user=self.request.user).delete()
        response = super().form_valid(form)
        for mes, ano in set(datas):
            _recalcular_saldos_a_partir(mes, ano, self.request.user)
        messages.success(self.request, "Responsável excluído com sucesso.")
        return response


# ── Categorias ─────────────────────────────────────────────────────────

class CategoriaFormMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["icones"] = Categoria.ICONE_CHOICES
        ctx["cores"] = Categoria.CORES_CHOICES
        ctx["icones_presets"] = Categoria.PRESETS
        return ctx


class CategoriaListView(UserOwnedMixin, ListView):
    model = Categoria
    template_name = "categorias/categoria_list.html"
    context_object_name = "categorias"


class CategoriaCreateView(SimpleCreateMixin, CategoriaFormMixin, UserOwnedMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "categorias/categoria_form.html"
    success_url = reverse_lazy("categoria-list")
    success_message = "Categoria criada com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Categoria"
        return ctx


class CategoriaUpdateView(SimpleUpdateMixin, CategoriaFormMixin, UserOwnedMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "categorias/categoria_form.html"
    success_url = reverse_lazy("categoria-list")
    success_message = "Categoria atualizada com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Categoria"
        return ctx


class CategoriaDeleteView(SimpleDeleteMixin, UserOwnedMixin, DeleteView):
    model = Categoria
    template_name = "categorias/categoria_confirm_delete.html"
    success_url = reverse_lazy("categoria-list")
    success_message = "Categoria excluída com sucesso."


# ── Entradas ─────────────────────────────────────────────────────────────

class EntradaListView(MesAnoMixin, UserOwnedMixin, ListView):
    model = Entrada
    template_name = "entradas/entrada_list.html"
    context_object_name = "entradas"
    session_prefix = "entradas"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("conta", "responsavel")
        qs = qs.filter(data__month=self.mes, data__year=self.ano)
        tipo = self.request.GET.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtros"] = self.request.GET
        ctx["total_filtrado"] = _agg_sum(self.get_queryset(), "valor")
        ctx["tipos_entrada"] = Entrada.TIPO_CHOICES
        por_tipo = {
            t: _agg_sum(self.get_queryset().filter(tipo=t), "valor")
            for t, _ in Entrada.TIPO_CHOICES
            if t != "saldo_anterior"
        }
        ctx["totais_por_tipo"] = por_tipo
        return ctx


class EntradaCreateView(UserFormKwargsMixin, UserOwnedMixin, CreateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def get_initial(self):
        initial = super().get_initial()
        resp = Responsavel.objects.filter(user=self.request.user, usuario_vinculado=self.request.user).first()
        if resp:
            initial["responsavel"] = resp.pk
        return initial

    def form_valid(self, form):
        is_recorrente = form.cleaned_data.get("recorrente", False)
        entrada = form.save(commit=False)
        entrada.user = self.request.user
        entrada.recorrente = is_recorrente

        if is_recorrente:
            entrada.data = entrada.data.replace(day=1)
            grupo_id = uuid.uuid4()
            entrada.grupo_recorrente = grupo_id
            entrada.auto_gerada = False
            entrada.save()
            _creditar_conta(entrada)
            _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year, self.request.user)

            fim = date(2050, 12, 1)
            proximo = entrada.data + relativedelta(months=1)
            bulk = []
            while proximo <= fim:
                bulk.append(Entrada(
                    tipo=entrada.tipo,
                    descricao=entrada.descricao,
                    valor=entrada.valor,
                    data=proximo,
                    conta=entrada.conta,
                    responsavel=entrada.responsavel,
                    auto_gerada=True,
                    recorrente=True,
                    grupo_recorrente=grupo_id,
                    user=self.request.user,
                ))
                proximo += relativedelta(months=1)
            Entrada.objects.bulk_create(bulk)
            total = len(bulk) + 1
            messages.success(self.request, f"Entrada recorrente criada — {total} meses gerados até dez/2050.")
        else:
            entrada.save()
            _creditar_conta(entrada)
            _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year, self.request.user)
            messages.success(self.request, "Entrada registrada com sucesso.")

        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Entrada"
        return ctx


class EntradaUpdateView(UserFormKwargsMixin, UserOwnedMixin, UpdateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        old_tipo      = self.object.tipo
        old_conta_id  = self.object.conta_id
        old_valor     = self.object.valor
        old_auto      = self.object.auto_gerada
        data_antiga   = self.object.data
        entrada = form.save()
        _estornar_credito(old_tipo, old_conta_id, old_valor, old_auto)
        _creditar_conta(entrada)
        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year, self.request.user)
        if entrada.data != data_antiga:
            _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year, self.request.user)
        messages.success(self.request, "Entrada atualizada com sucesso.")
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Entrada"
        return ctx


class EntradaDeleteView(UserOwnedMixin, DeleteView):
    model = Entrada
    template_name = "entradas/entrada_confirm_delete.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        mes, ano     = self.object.data.month, self.object.data.year
        tipo         = self.object.tipo
        conta_id     = self.object.conta_id
        valor        = self.object.valor
        auto_gerada  = self.object.auto_gerada
        _estornar_credito(tipo, conta_id, valor, auto_gerada)
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
    if request.method == "POST":
        form = PerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso.")
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
    return HttpResponseRedirect(_safe_next_url(request, "/"))


@login_required
def senha_update(request):
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
    return HttpResponseRedirect(_safe_next_url(request, "/"))


# ── API interna ─────────────────────────────────────────────────────────

@login_required
def cartoes_por_responsavel(request, responsavel_id=None):
    if responsavel_id:
        get_object_or_404(Responsavel, pk=responsavel_id, user=request.user)
    cartoes = Cartao.objects.filter(ativo=True, user=request.user).values("id", "nome", "tipo")
    return JsonResponse(list(cartoes), safe=False)


@login_required
def categoria_criar_ajax(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método inválido."}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Dados inválidos."}, status=400)
    nome = (body.get("nome") or "").strip()
    cor = (body.get("cor") or "#888888").strip()
    icone = (body.get("icone") or "").strip()
    if not nome:
        return JsonResponse({"ok": False, "error": "Nome é obrigatório."})
    if len(nome) > 100:
        return JsonResponse({"ok": False, "error": "Nome muito longo (máx 100 caracteres)."})
    import re as _re
    if not _re.match(r"^#[0-9A-Fa-f]{6}$", cor):
        cor = "#888888"
    valid_icones = {val for val, _ in Categoria.ICONE_CHOICES}
    if icone not in valid_icones:
        icone = ""
    existing = Categoria.objects.filter(user=request.user, nome__iexact=nome).first()
    if existing:
        return JsonResponse({"ok": True, "id": existing.pk, "nome": existing.nome, "created": False})
    cat = Categoria.objects.create(user=request.user, nome=nome, cor=cor, icone=icone, ativo=True)
    return JsonResponse({"ok": True, "id": cat.pk, "nome": cat.nome, "created": True})


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
    return HttpResponseRedirect(_safe_next_url(request, reverse_lazy("dashboard")))


@login_required
def pagamento_toggle(request, tipo, responsavel_id):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    if tipo not in ("pix", "emprestimo", "acerto"):
        from django.http import Http404
        raise Http404
    responsavel = get_object_or_404(Responsavel, pk=responsavel_id, user=request.user)
    mes, ano = _mes_ano_from_request(request)
    obj, created = PagamentoFeito.objects.get_or_create(
        tipo=tipo, responsavel=responsavel, mes=mes, ano=ano, user=request.user
    )
    if not created:
        obj.delete()
    return HttpResponseRedirect(_safe_next_url(request, reverse_lazy("dashboard")))


# ── Contas ─────────────────────────────────────────────────────────────

class ContaListView(UserOwnedMixin, ListView):
    model = Conta
    template_name = "contas/conta_list.html"
    context_object_name = "contas"

    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


class ContaCreateView(SimpleCreateMixin, UserOwnedMixin, CreateView):
    model = Conta
    form_class = ContaForm
    template_name = "contas/conta_form.html"
    success_url = reverse_lazy("conta-list")
    success_message = "Conta criada com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Conta"
        return ctx


class ContaUpdateView(SimpleUpdateMixin, UserOwnedMixin, UpdateView):
    model = Conta
    form_class = ContaForm
    template_name = "contas/conta_form.html"
    success_url = reverse_lazy("conta-list")
    success_message = "Conta atualizada com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Conta"
        return ctx


class ContaDeleteView(SimpleDeleteMixin, UserOwnedMixin, DeleteView):
    model = Conta
    template_name = "contas/conta_confirm_delete.html"
    success_url = reverse_lazy("conta-list")
    success_message = "Conta excluída com sucesso."


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
        MESES_PT = _MESES_ABREV

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

        ctx["chart_labels"]      = _safe_json(all_labels)
        ctx["chart_dados"]       = _safe_json(all_dados)
        ctx["chart_aportes_bar"] = _safe_json(all_aportes_bar)
        ctx["chart_saques_bar"]  = _safe_json(all_saques_bar)
        ctx["chart_por_conta"]   = _safe_json(conta_series)
        ctx["contas_com_inv"]  = [
            {"id": c.pk, "nome": c.nome}
            for c in ctx["contas"]
            if c.pk in {i.conta_id for i in todos}
        ]

        # Gráfico de rosca — distribuição por tipo (apenas ativos)
        tipo_totais = defaultdict(float)
        for inv in ativos:
            tipo_totais[_TIPO_INV_LABELS.get(inv.tipo_investimento, inv.tipo_investimento)] += float(inv.saldo_atual)
        ctx["rosca_labels"] = _safe_json(list(tipo_totais.keys()))
        ctx["rosca_dados"]  = _safe_json([round(v, 2) for v in tipo_totais.values()])

        return ctx


class InvestimentoCreateView(UserFormKwargsMixin, LoginRequiredMixin, CreateView):
    model = Investimento
    form_class = InvestimentoForm
    success_url = reverse_lazy("investimento-list")

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
        return HttpResponseRedirect(_safe_next_url(self.request, self.success_url))

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
        ctx["chart_labels"] = _safe_json(labels)
        ctx["chart_dados"]  = _safe_json(dados)
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
