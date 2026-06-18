from django.utils.functional import SimpleLazyObject
from .forms import GastoForm, EntradaForm, PerfilForm, SenhaForm
from .models import Conta, Responsavel


def modal_forms(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "modal_gasto_form":      SimpleLazyObject(lambda: GastoForm(user=request.user)),
        "modal_entrada_form":    SimpleLazyObject(lambda: EntradaForm(user=request.user)),
        "perfil_form":           SimpleLazyObject(lambda: PerfilForm(instance=request.user)),
        "senha_form":            SimpleLazyObject(lambda: SenhaForm(user=request.user)),
        "contas_ativas":         SimpleLazyObject(lambda: Conta.objects.filter(ativo=True, user=request.user)),
        "responsaveis_ativos":   SimpleLazyObject(lambda: Responsavel.objects.filter(user=request.user, ativo=True, is_principal=False)),
        "responsavel_principal": SimpleLazyObject(lambda: Responsavel.objects.filter(user=request.user, is_principal=True).first()),
    }
