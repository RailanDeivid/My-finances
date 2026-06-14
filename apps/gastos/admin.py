from django.contrib import admin
from django.contrib import messages as django_messages
from unfold.admin import ModelAdmin, TabularInline
from .models import Gasto, Parcela, Cartao, Responsavel, Categoria, Entrada


def excluir_todos_gastos(modeladmin, request, queryset):
    total = Gasto.objects.count()
    Gasto.objects.all().delete()
    django_messages.success(request, f"{total} gasto(s) excluído(s) com sucesso.")

excluir_todos_gastos.short_description = "⚠️ Excluir TODOS os gastos do banco"


def excluir_todas_entradas(modeladmin, request, queryset):
    total = Entrada.objects.count()
    Entrada.objects.all().delete()
    django_messages.success(request, f"{total} entrada(s) excluída(s) com sucesso.")

excluir_todas_entradas.short_description = "⚠️ Excluir TODAS as entradas do banco"


class ParcelaInline(TabularInline):
    model = Parcela
    extra = 0
    readonly_fields = ["numero", "valor", "data_vencimento"]
    fields = ["numero", "valor", "data_vencimento", "pago", "data_pagamento"]


@admin.register(Gasto)
class GastoAdmin(ModelAdmin):
    list_display = ["descricao", "valor_total", "tipo_pagamento", "cartao", "responsavel", "categoria", "data_compra"]
    list_filter = ["tipo_pagamento", "cartao", "responsavel", "categoria", "data_compra"]
    search_fields = ["descricao", "observacao"]
    date_hierarchy = "data_compra"
    readonly_fields = ["criado_em", "atualizado_em"]
    inlines = [ParcelaInline]
    actions = ["delete_selected", excluir_todos_gastos]


@admin.register(Cartao)
class CartaoAdmin(ModelAdmin):
    list_display = ["nome", "bandeira", "tipo", "limite", "dia_fechamento", "ativo"]
    list_filter = ["tipo", "bandeira", "ativo"]
    search_fields = ["nome"]


@admin.register(Responsavel)
class ResponsavelAdmin(ModelAdmin):
    list_display = ["nome", "ativo", "user", "usuario_vinculado", "criado_em"]
    list_filter = ["ativo", "user"]
    search_fields = ["nome"]


@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ["nome", "icone", "cor", "ativo"]
    search_fields = ["nome"]


@admin.register(Entrada)
class EntradaAdmin(ModelAdmin):
    list_display = ["get_tipo_display", "descricao", "valor", "data", "responsavel", "auto_gerada"]
    list_filter = ["tipo", "responsavel", "auto_gerada"]
    search_fields = ["descricao"]
    date_hierarchy = "data"
    actions = ["delete_selected", excluir_todas_entradas]


@admin.register(Parcela)
class ParcelaAdmin(ModelAdmin):
    list_display = ["gasto", "numero", "valor", "data_vencimento", "pago", "data_pagamento"]
    list_filter = ["pago", "data_vencimento"]
