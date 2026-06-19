from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import LLMUsage, UserProfile, WhatsAppAccess


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    compressed_fields = False
    list_display = ("user", "whatsapp_number")
    search_fields = ("user__username", "whatsapp_number")


def _bloquear(modeladmin, request, queryset):
    queryset.update(ativo=False)
_bloquear.short_description = "🚫 Bloquear selecionados"

def _desbloquear(modeladmin, request, queryset):
    queryset.update(ativo=True)
_desbloquear.short_description = "✅ Desbloquear selecionados"

def _tornar_admin(modeladmin, request, queryset):
    queryset.update(is_admin=True)
_tornar_admin.short_description = "👑 Tornar admin"

def _remover_admin(modeladmin, request, queryset):
    queryset.update(is_admin=False)
_remover_admin.short_description = "👤 Remover admin"


@admin.register(WhatsAppAccess)
class WhatsAppAccessAdmin(ModelAdmin):
    compressed_fields = False
    list_display  = ("phone", "status_badge", "admin_badge", "criado_em")
    list_filter   = ("ativo", "is_admin")
    search_fields = ("phone",)
    actions       = [_bloquear, _desbloquear, _tornar_admin, _remover_admin]
    ordering      = ("-criado_em",)

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.ativo:
            return format_html('<span style="color:green;font-weight:bold">✅ Ativo</span>')
        return format_html('<span style="color:red;font-weight:bold">🚫 Bloqueado</span>')

    @admin.display(description="Perfil")
    def admin_badge(self, obj):
        if obj.is_admin:
            return format_html('<span style="color:orange;font-weight:bold">👑 Admin</span>')
        return format_html('<span style="color:gray">👤 Usuário</span>')


@admin.register(LLMUsage)
class LLMUsageAdmin(ModelAdmin):
    compressed_fields = False
    list_display = ("timestamp", "user", "operation", "model", "tokens_total", "cost_usd", "latency_ms")
    list_filter = ("operation", "model", "timestamp")
    search_fields = ("user__username",)
    readonly_fields = ("timestamp", "user", "operation", "model", "tokens_input", "tokens_output", "tokens_total", "cost_usd", "latency_ms")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
