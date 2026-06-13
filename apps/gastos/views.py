import json
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
)
from django.contrib import messages

from .models import Gasto, Cartao, Responsavel, Categoria, Parcela, Entrada
from .forms import GastoForm, CartaoForm, ResponsavelForm, CategoriaForm, EntradaForm


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


def _calcular_saldo_mes(mes, ano):
    """Retorna (total_entradas, total_gastos, saldo) de um determinado mês."""
    total_gastos = (
        Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)
        .aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
    )
    total_entradas = (
        Entrada.objects.filter(data__month=mes, data__year=ano)
        .aggregate(t=Sum("valor"))["t"] or Decimal("0")
    )
    return total_entradas, total_gastos, total_entradas - total_gastos


def _auto_saldo_anterior(mes, ano):
    """Cria ou atualiza o saldo_anterior do mês com base nos dados do mês anterior.
    Sempre recalcula — garante que mudanças em gastos/entradas se reflitam."""
    ref_ant = date(ano, mes, 1) - relativedelta(months=1)
    mes_ant, ano_ant = ref_ant.month, ref_ant.year

    total_entradas, total_gastos, saldo = _calcular_saldo_mes(mes_ant, ano_ant)

    if total_gastos > 0 or total_entradas != Decimal("0"):
        Entrada.objects.update_or_create(
            tipo="saldo_anterior",
            data=date(ano, mes, 1),
            auto_gerada=True,
            defaults={
                "descricao": f"Saldo de {ref_ant.strftime('%b/%Y')}",
                "valor": saldo,
            },
        )


def _recalcular_saldos_a_partir(mes, ano):
    """Recalcula em cascata todos os saldo_anterior auto-gerados para os meses
    seguintes ao mês informado. Chame após qualquer alteração em Gasto ou Entrada."""
    prox = date(ano, mes, 1) + relativedelta(months=1)

    while True:
        try:
            entrada = Entrada.objects.get(
                tipo="saldo_anterior",
                auto_gerada=True,
                data=prox,
            )
        except Entrada.DoesNotExist:
            break

        ref_ant = prox - relativedelta(months=1)
        total_entradas, total_gastos, saldo = _calcular_saldo_mes(ref_ant.month, ref_ant.year)

        entrada.valor = saldo
        entrada.descricao = f"Saldo de {ref_ant.strftime('%b/%Y')}"
        entrada.save(update_fields=["valor", "descricao"])

        prox += relativedelta(months=1)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "gastos/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano

        _auto_saldo_anterior(mes, ano)

        # Filtros
        responsavel_id = self.request.GET.get("responsavel")
        cartao_id = self.request.GET.get("cartao")
        tipo_filtro = self.request.GET.get("tipo")
        categoria_id = self.request.GET.get("categoria")

        ctx["responsaveis_lista"] = Responsavel.objects.filter(ativo=True)
        ctx["cartoes_lista"] = Cartao.objects.filter(ativo=True)
        ctx["categorias_lista"] = Categoria.objects.filter(ativo=True)
        ctx["tipos_lista"] = Gasto.TIPO_PAGAMENTO_CHOICES
        ctx["filtro_responsavel"] = responsavel_id
        ctx["filtro_cartao"] = cartao_id
        ctx["filtro_tipo"] = tipo_filtro
        ctx["filtro_categoria"] = categoria_id

        # Gastos do mês com filtros (responsável filtra só gastos)
        gastos_mes = Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)
        if responsavel_id:
            gastos_mes = gastos_mes.filter(responsavel_id=responsavel_id)
        if cartao_id:
            gastos_mes = gastos_mes.filter(cartao_id=cartao_id)
        if tipo_filtro:
            gastos_mes = gastos_mes.filter(tipo_pagamento=tipo_filtro)
        if categoria_id:
            gastos_mes = gastos_mes.filter(categoria_id=categoria_id)

        # Entradas e saldo são sempre globais — não filtram por nada
        entradas_mes = Entrada.objects.filter(data__month=mes, data__year=ano)
        gastos_mes_total = Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)

        total_entradas = entradas_mes.aggregate(t=Sum("valor"))["t"] or Decimal("0")
        total_gasto    = gastos_mes.aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        total_gasto_geral = gastos_mes_total.aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        saldo = total_entradas - total_gasto_geral

        ctx["total_entradas"] = total_entradas
        ctx["total_gasto"] = total_gasto
        ctx["saldo"] = saldo
        ctx["qtd_gastos"] = gastos_mes.count()

        # Tabela por responsável e por cartão — sem filtros (só mes/ano)
        gastos_mes_base = Gasto.objects.filter(data_compra__month=mes, data_compra__year=ano)
        ctx["tabela_por_responsavel"] = (
            gastos_mes_base.values("responsavel__id", "responsavel__nome")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )
        ctx["tabela_por_cartao"] = (
            gastos_mes_base.values("cartao__id", "cartao__nome", "cartao__cor", "cartao__tipo")
            .annotate(total=Sum("valor_total"))
            .order_by("-total")
        )

        # Por categoria (gráfico pizza)
        por_categoria = (
            gastos_mes.values("categoria__nome", "categoria__cor")
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

        # Gráfico de período: todos os meses com gastos (travado, não muda com filtro de mês)
        periodo_qs = Gasto.objects.values("data_compra__month", "data_compra__year")
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

        # Tabela combinada: entradas + gastos do mês (para "Entradas e Saídas")
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
                "tipo_label": g.get_tipo_pagamento_display(),
                "descricao": g.descricao,
                "categoria": g.categoria,
                "responsavel": str(g.responsavel),
                "cartao": g.cartao.nome,
                "valor": float(g.valor_total),
                "pk": g.pk,
                "parcelas": g.total_parcelas if g.tipo_pagamento == "credito_parcelado" else None,
                "auto_gerada": False,
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
            })

        transacoes.sort(key=lambda x: x["data"], reverse=True)
        ctx["transacoes_mes"] = transacoes
        ctx["entradas_mes"] = entradas_lista

        ctx["meses_nomes"] = meses_nomes

        # ── Tabela + Gráfico: Gastos vs Entradas — Visão Mensal ──────────
        saldo_ant_qs = (
            Entrada.objects.filter(tipo="saldo_anterior")
            .values("data__year", "data__month")
            .annotate(t=Sum("valor"))
        )
        entradas_qs = (
            Entrada.objects.exclude(tipo="saldo_anterior")
            .values("data__year", "data__month")
            .annotate(t=Sum("valor"))
        )
        gastos_qs = (
            Gasto.objects.values("data_compra__year", "data_compra__month")
            .annotate(t=Sum("valor_total"))
        )

        saldo_ant_map  = {(r["data__year"], r["data__month"]): float(r["t"] or 0) for r in saldo_ant_qs}
        entradas_map   = {(r["data__year"], r["data__month"]): float(r["t"] or 0) for r in entradas_qs}
        gastos_map     = {(r["data_compra__year"], r["data_compra__month"]): float(r["t"] or 0) for r in gastos_qs}

        todos_meses = sorted(
            set(list(saldo_ant_map) + list(entradas_map) + list(gastos_map))
        )

        # Cálculo encadeado: saldo_atual[M] vira saldo_anterior[M+1]
        # Para o primeiro mês, usa o saldo_anterior armazenado (se existir)
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
            running = saldo_atual  # saldo deste mês é o saldo_anterior do próximo

        ctx["tabela_mensal"] = tabela_mensal

        # Dados para o gráfico comparativo (derivado da mesma tabela)
        ctx["comp_labels"]   = json.dumps([c["label"]       for c in tabela_mensal])
        ctx["comp_gastos"]   = json.dumps([c["gastos"]      for c in tabela_mensal])
        ctx["comp_entradas"] = json.dumps([c["entradas"] + c["saldo_ant"] for c in tabela_mensal])
        ctx["comp_saldo"]    = json.dumps([c["saldo_atual"] for c in tabela_mensal])

        # ── Tabela Responsáveis × Meses ───────────────────────────────────
        resp_qs = (
            Gasto.objects.values(
                "responsavel__id", "responsavel__nome",
                "data_compra__year", "data_compra__month",
            ).annotate(t=Sum("valor_total"))
        )

        resp_map = {}   # {resp_id: {(y,m): total}}
        resp_nome_map = {}  # {resp_id: nome}
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

        return ctx


# ── Gastos ─────────────────────────────────────────────────────────────

class GastoListView(LoginRequiredMixin, ListView):
    model = Gasto
    template_name = "gastos/gasto_list.html"
    context_object_name = "gastos"
    paginate_by = 25

    def get_queryset(self):
        qs = Gasto.objects.select_related("responsavel", "cartao", "categoria")
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
        ctx["responsaveis"] = Responsavel.objects.filter(ativo=True)
        ctx["cartoes"] = Cartao.objects.filter(ativo=True)
        ctx["categorias"] = Categoria.objects.filter(ativo=True)
        ctx["tipos"] = Gasto.TIPO_PAGAMENTO_CHOICES
        ctx["filtros"] = self.request.GET
        ctx["total_filtrado"] = self.get_queryset().aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class GastoCreateView(LoginRequiredMixin, CreateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def form_valid(self, form):
        gasto = form.save(commit=False)
        n = gasto.total_parcelas if gasto.tipo_pagamento == "credito_parcelado" else None

        # Calcula data de início das parcelas
        data_inicio = gasto.data_compra
        if n:
            mes_ini = form.cleaned_data.get("mes_inicio")
            ano_ini = form.cleaned_data.get("ano_inicio")
            if mes_ini and ano_ini:
                try:
                    data_inicio = date(int(ano_ini), int(mes_ini), 1)
                except (ValueError, TypeError):
                    pass

        if n:
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
                )
        else:
            gasto.save()

        _recalcular_saldos_a_partir(data_inicio.month, data_inicio.year)
        messages.success(self.request, "Gasto registrado com sucesso.")
        next_url = self.request.POST.get("next") or self.success_url
        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Gasto"
        return ctx


class GastoUpdateView(LoginRequiredMixin, UpdateView):
    model = Gasto
    form_class = GastoForm
    template_name = "gastos/gasto_form.html"
    success_url = reverse_lazy("gasto-list")

    def form_valid(self, form):
        data_antiga = self.get_object().data_compra
        gasto = form.save()
        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year)
        if gasto.data_compra != data_antiga:
            _recalcular_saldos_a_partir(gasto.data_compra.month, gasto.data_compra.year)
        messages.success(self.request, "Gasto atualizado com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Gasto"
        return ctx


class GastoDeleteView(LoginRequiredMixin, DeleteView):
    model = Gasto
    template_name = "gastos/gasto_confirm_delete.html"
    success_url = reverse_lazy("gasto-list")

    def form_valid(self, form):
        mes, ano = self.object.data_compra.month, self.object.data_compra.year
        response = super().form_valid(form)
        _recalcular_saldos_a_partir(mes, ano)
        messages.success(self.request, "Gasto excluído com sucesso.")
        return response


# ── Cartões ─────────────────────────────────────────────────────────────

class CartaoListView(LoginRequiredMixin, ListView):
    model = Cartao
    template_name = "cartoes/cartao_list.html"
    context_object_name = "cartoes"

    def get_queryset(self):
        return Cartao.objects.filter(ativo=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        for cartao in ctx["cartoes"]:
            cartao.fatura_mes = Gasto.objects.filter(
                cartao=cartao,
                data_compra__month=mes,
                data_compra__year=ano,
                tipo_pagamento__in=["credito_avista", "credito_parcelado"],
            ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
            cartao.debito_mes = Gasto.objects.filter(
                cartao=cartao,
                data_compra__month=mes,
                data_compra__year=ano,
                tipo_pagamento="debito",
            ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class CartaoDetailView(LoginRequiredMixin, DetailView):
    model = Cartao
    template_name = "cartoes/cartao_detail.html"
    context_object_name = "cartao"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        ctx["gastos"] = (
            Gasto.objects.filter(cartao=self.object, data_compra__month=mes, data_compra__year=ano)
            .select_related("responsavel", "categoria")
            .order_by("-data_compra")
        )
        ctx["total_fatura"] = ctx["gastos"].aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
        return ctx


class CartaoCreateView(LoginRequiredMixin, CreateView):
    model = Cartao
    form_class = CartaoForm
    template_name = "cartoes/cartao_form.html"
    success_url = reverse_lazy("cartao-list")

    def form_valid(self, form):
        messages.success(self.request, "Cartão criado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Cartão"
        return ctx


class CartaoUpdateView(LoginRequiredMixin, UpdateView):
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


class CartaoDeleteView(LoginRequiredMixin, DeleteView):
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
            _recalcular_saldos_a_partir(mes, ano)
        messages.success(self.request, "Cartão excluído com sucesso.")
        return response


# ── Responsáveis ─────────────────────────────────────────────────────────

class ResponsavelListView(LoginRequiredMixin, ListView):
    model = Responsavel
    template_name = "responsaveis/responsavel_list.html"
    context_object_name = "responsaveis"
    queryset = Responsavel.objects.all()


class ResponsavelCreateView(LoginRequiredMixin, CreateView):
    model = Responsavel
    form_class = ResponsavelForm
    template_name = "responsaveis/responsavel_form.html"
    success_url = reverse_lazy("responsavel-list")

    def form_valid(self, form):
        messages.success(self.request, "Responsável criado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Novo Responsável"
        return ctx


class ResponsavelUpdateView(LoginRequiredMixin, UpdateView):
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


# ── Categorias ─────────────────────────────────────────────────────────

class CategoriaListView(LoginRequiredMixin, ListView):
    model = Categoria
    template_name = "categorias/categoria_list.html"
    context_object_name = "categorias"

    def get_queryset(self):
        return Categoria.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        mes, ano = _mes_ano_from_request(self.request)
        ctx["mes"] = mes
        ctx["ano"] = ano
        for cat in ctx["categorias"]:
            cat.total_gastos_mes = Gasto.objects.filter(
                categoria=cat,
                data_compra__month=mes,
                data_compra__year=ano,
            ).aggregate(t=Sum("valor_total"))["t"] or Decimal("0")
            cat.qtd_gastos_mes = Gasto.objects.filter(
                categoria=cat,
                data_compra__month=mes,
                data_compra__year=ano,
            ).count()
        return ctx


class CategoriaCreateView(LoginRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "categorias/categoria_form.html"
    success_url = reverse_lazy("categoria-list")

    def form_valid(self, form):
        messages.success(self.request, "Categoria criada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Categoria"
        ctx["icones"] = Categoria.ICONE_CHOICES
        ctx["cores"] = Categoria.CORES_CHOICES
        ctx["icones_presets"] = Categoria.PRESETS
        return ctx


class CategoriaUpdateView(LoginRequiredMixin, UpdateView):
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


# ── Entradas ─────────────────────────────────────────────────────────────

class EntradaListView(LoginRequiredMixin, ListView):
    model = Entrada
    template_name = "entradas/entrada_list.html"
    context_object_name = "entradas"
    paginate_by = 25

    def get_queryset(self):
        qs = Entrada.objects.all()
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


class EntradaCreateView(LoginRequiredMixin, CreateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        entrada = form.save()
        _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year)
        messages.success(self.request, "Entrada registrada com sucesso.")
        next_url = self.request.POST.get("next") or self.success_url
        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nova Entrada"
        return ctx


class EntradaUpdateView(LoginRequiredMixin, UpdateView):
    model = Entrada
    form_class = EntradaForm
    template_name = "entradas/entrada_form.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        data_antiga = self.get_object().data
        entrada = form.save()
        _recalcular_saldos_a_partir(data_antiga.month, data_antiga.year)
        if entrada.data != data_antiga:
            _recalcular_saldos_a_partir(entrada.data.month, entrada.data.year)
        messages.success(self.request, "Entrada atualizada com sucesso.")
        return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Entrada"
        return ctx


class EntradaDeleteView(LoginRequiredMixin, DeleteView):
    model = Entrada
    template_name = "entradas/entrada_confirm_delete.html"
    success_url = reverse_lazy("entrada-list")

    def form_valid(self, form):
        mes, ano = self.object.data.month, self.object.data.year
        response = super().form_valid(form)
        _recalcular_saldos_a_partir(mes, ano)
        messages.success(self.request, "Entrada excluída com sucesso.")
        return response


# ── Exclusão em massa ────────────────────────────────────────────────────

@login_required
def cartao_delete_all(request):
    if request.method == "POST":
        datas = list(Gasto.objects.values_list("data_compra__month", "data_compra__year").distinct())
        Gasto.objects.all().delete()
        Cartao.objects.all().delete()
        for mes, ano in set(datas):
            _recalcular_saldos_a_partir(mes, ano)
        messages.success(request, "Todos os cartões (e seus gastos) foram excluídos.")
    return HttpResponseRedirect(reverse_lazy("cartao-list"))


@login_required
def gasto_delete_all(request):
    if request.method == "POST":
        datas = list(Gasto.objects.values_list("data_compra__month", "data_compra__year").distinct())
        Gasto.objects.all().delete()
        for mes, ano in set(datas):
            _recalcular_saldos_a_partir(mes, ano)
        messages.success(request, "Todos os gastos foram excluídos.")
    return HttpResponseRedirect(reverse_lazy("gasto-list"))


@login_required
def entrada_delete_all(request):
    if request.method == "POST":
        Entrada.objects.filter(auto_gerada=False).delete()
        Entrada.objects.filter(auto_gerada=True).delete()
        messages.success(request, "Todas as entradas foram excluídas.")
    return HttpResponseRedirect(reverse_lazy("entrada-list"))


# ── API interna ─────────────────────────────────────────────────────────

@login_required
def cartoes_por_responsavel(request, responsavel_id=None):
    cartoes = Cartao.objects.filter(ativo=True).values("id", "nome", "tipo")
    return JsonResponse(list(cartoes), safe=False)
