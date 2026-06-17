from django.utils.functional import SimpleLazyObject
from .forms import GastoForm, EntradaForm, PerfilForm, SenhaForm
from .models import Conta


def modal_forms(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "modal_gasto_form":   SimpleLazyObject(lambda: GastoForm(user=request.user)),
        "modal_entrada_form": SimpleLazyObject(lambda: EntradaForm(user=request.user)),
        "perfil_form":        SimpleLazyObject(lambda: PerfilForm(instance=request.user)),
        "senha_form":         SimpleLazyObject(lambda: SenhaForm(user=request.user)),
        "contas_ativas":      SimpleLazyObject(lambda: Conta.objects.filter(ativo=True, user=request.user)),
    }
