from django.urls import path
from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),

    # Gastos
    path("gastos/", views.GastoListView.as_view(), name="gasto-list"),
    path("gastos/novo/", views.GastoCreateView.as_view(), name="gasto-create"),
    path("gastos/<int:pk>/editar/", views.GastoUpdateView.as_view(), name="gasto-update"),
    path("gastos/<int:pk>/excluir/", views.GastoDeleteView.as_view(), name="gasto-delete"),

    # Cartões
    path("cartoes/", views.CartaoListView.as_view(), name="cartao-list"),
    path("cartoes/novo/", views.CartaoCreateView.as_view(), name="cartao-create"),
    path("cartoes/<int:pk>/", views.CartaoDetailView.as_view(), name="cartao-detail"),
    path("cartoes/<int:pk>/editar/", views.CartaoUpdateView.as_view(), name="cartao-update"),
    path("cartoes/<int:pk>/excluir/", views.CartaoDeleteView.as_view(), name="cartao-delete"),

    # Responsáveis
    path("responsaveis/", views.ResponsavelListView.as_view(), name="responsavel-list"),
    path("responsaveis/novo/", views.ResponsavelCreateView.as_view(), name="responsavel-create"),
    path("responsaveis/<int:pk>/editar/", views.ResponsavelUpdateView.as_view(), name="responsavel-update"),

    # Categorias
    path("categorias/", views.CategoriaListView.as_view(), name="categoria-list"),
    path("categorias/novo/", views.CategoriaCreateView.as_view(), name="categoria-create"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria-update"),

    # Entradas
    path("entradas/", views.EntradaListView.as_view(), name="entrada-list"),
    path("entradas/nova/", views.EntradaCreateView.as_view(), name="entrada-create"),
    path("entradas/<int:pk>/editar/", views.EntradaUpdateView.as_view(), name="entrada-update"),
    path("entradas/<int:pk>/excluir/", views.EntradaDeleteView.as_view(), name="entrada-delete"),

    # Exclusão em massa
    path("gastos/excluir-tudo/", views.gasto_delete_all, name="gasto-delete-all"),
    path("entradas/excluir-tudo/", views.entrada_delete_all, name="entrada-delete-all"),
    path("cartoes/excluir-tudo/", views.cartao_delete_all, name="cartao-delete-all"),

    # API interna
    path("api/cartoes-por-responsavel/<int:responsavel_id>/", views.cartoes_por_responsavel, name="api-cartoes"),
]
