from .forms import GastoForm, EntradaForm, PerfilForm, SenhaForm
from .models import Conta


def modal_forms(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "modal_gasto_form": GastoForm(user=request.user),
        "modal_entrada_form": EntradaForm(user=request.user),
        "perfil_form": PerfilForm(instance=request.user),
        "senha_form": SenhaForm(user=request.user),
        "contas_ativas": Conta.objects.filter(ativo=True, user=request.user),
    }
