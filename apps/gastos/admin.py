from django.contrib import admin
from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    Gasto, Cartao, Responsavel, Categoria, Entrada,
    Conta, Investimento, InvestimentoHistorico, FaturaPaga, PagamentoFeito,
)

User = get_user_model()

admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(ModelAdmin, BaseUserAdmin):
    compressed_fields = False
    form = UserChangeForm
    add_form = UserCreationForm
    readonly_fields = ['password_change_link']
    fieldsets = (
        (None, {'fields': ('username', 'password_change_link')}),
        ('Informações pessoais', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets

    def password_change_link(self, obj):
        if obj and obj.pk:
            return format_html(
                '<a href="../password/" style="color:#16a34a;font-weight:600;font-size:14px;">'
                '🔑 Alterar senha deste usuário</a>'
            )
        return '—'
    password_change_link.short_description = 'Senha'


def excluir_gastos_selecionados(modeladmin, request, queryset):
    total, _ = queryset.delete()
    django_messages.success(request, f"⚠️ {total} gasto(s) excluído(s).")

excluir_gastos_selecionados.short_description = "⚠️ Excluir gastos selecionados"


def excluir_entradas_selecionadas(modeladmin, request, queryset):
    total, _ = queryset.delete()
    django_messages.success(request, f"⚠️ {total} entrada(s) excluída(s).")

excluir_entradas_selecionadas.short_description = "⚠️ Excluir entradas selecionadas"


@admin.register(Gasto)
class GastoAdmin(ModelAdmin):
    list_display = ["descricao", "valor_total", "tipo_pagamento", "cartao", "responsavel", "categoria", "data_compra", "user"]
    list_filter = ["tipo_pagamento", "cartao", "responsavel", "categoria", "data_compra", "user"]
    search_fields = ["descricao", "observacao"]
    date_hierarchy = "data_compra"
    readonly_fields = ["criado_em", "atualizado_em"]
    actions = ["delete_selected", excluir_gastos_selecionados]


@admin.register(Cartao)
class CartaoAdmin(ModelAdmin):
    list_display = ["nome", "bandeira", "tipo", "limite", "dia_fechamento", "ativo", "user"]
    list_filter = ["tipo", "bandeira", "ativo", "user"]
    search_fields = ["nome"]


@admin.register(Responsavel)
class ResponsavelAdmin(ModelAdmin):
    list_display = ["nome", "ativo", "is_principal", "user", "usuario_vinculado", "criado_em"]
    list_filter = ["ativo", "is_principal", "user"]
    search_fields = ["nome"]


@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ["nome", "icone", "cor", "ativo", "user"]
    list_filter = ["ativo", "user"]
    search_fields = ["nome"]


@admin.register(Entrada)
class EntradaAdmin(ModelAdmin):
    list_display = ["tipo", "descricao", "valor", "data", "conta", "auto_gerada", "user"]
    list_filter = ["tipo", "auto_gerada", "user"]
    search_fields = ["descricao"]
    date_hierarchy = "data"
    actions = ["delete_selected", excluir_entradas_selecionadas]


@admin.register(Conta)
class ContaAdmin(ModelAdmin):
    list_display = ["nome", "banco", "tipo", "saldo_atual", "ativo", "user"]
    list_filter = ["banco", "tipo", "ativo", "user"]
    search_fields = ["nome"]
    readonly_fields = ["criado_em"]


@admin.register(Investimento)
class InvestimentoAdmin(ModelAdmin):
    list_display = ["descricao", "tipo_investimento", "conta", "saldo_inicial", "saldo_atual", "liquidado", "user"]
    list_filter = ["tipo_investimento", "liquidado", "user"]
    search_fields = ["descricao"]
    readonly_fields = ["criado_em", "atualizado_em"]


@admin.register(InvestimentoHistorico)
class InvestimentoHistoricoAdmin(ModelAdmin):
    list_display = ["investimento", "tipo", "valor_anterior", "valor_novo", "diferenca", "data_movimentacao"]
    list_filter = ["tipo"]
    readonly_fields = ["data_movimentacao"]


@admin.register(FaturaPaga)
class FaturaPagaAdmin(ModelAdmin):
    list_display = ["cartao", "mes", "ano", "user"]
    list_filter = ["user", "ano"]


@admin.register(PagamentoFeito)
class PagamentoFeitoAdmin(ModelAdmin):
    list_display = ["tipo", "responsavel", "mes", "ano", "user"]
    list_filter = ["tipo", "user", "ano"]
