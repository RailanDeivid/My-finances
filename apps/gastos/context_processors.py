from .forms import GastoForm, EntradaForm


def modal_forms(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "modal_gasto_form": GastoForm(),
        "modal_entrada_form": EntradaForm(),
    }
