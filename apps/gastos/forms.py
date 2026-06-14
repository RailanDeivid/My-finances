from django import forms
from django.contrib.auth import get_user_model
from .models import Gasto, Cartao, Responsavel, Categoria, Entrada, Conta

User = get_user_model()

import datetime as _dt

_MESES = [
    (1,"Janeiro"),(2,"Fevereiro"),(3,"Março"),(4,"Abril"),
    (5,"Maio"),(6,"Junho"),(7,"Julho"),(8,"Agosto"),
    (9,"Setembro"),(10,"Outubro"),(11,"Novembro"),(12,"Dezembro"),
]
_ANO_ATUAL = _dt.date.today().year
_ANOS = [(y, y) for y in range(_ANO_ATUAL, _ANO_ATUAL + 7)]


class GastoForm(forms.ModelForm):
    mes_inicio = forms.ChoiceField(
        choices=_MESES, required=False, label="Mês da 1ª Parcela",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_mes_inicio"}),
    )
    ano_inicio = forms.ChoiceField(
        choices=_ANOS, required=False, label="Ano",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_ano_inicio"}),
    )

    class Meta:
        model = Gasto
        fields = [
            "descricao", "valor_total", "data_compra", "tipo_pagamento",
            "total_parcelas", "cartao", "responsavel", "categoria", "observacao",
        ]
        widgets = {
            "descricao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Mercado, Farmácia..."}),
            "valor_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0,00"}),
            "data_compra": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "tipo_pagamento": forms.Select(attrs={"class": "form-control", "id": "id_tipo_pagamento"}),
            "total_parcelas": forms.NumberInput(attrs={"class": "form-control", "min": "2", "max": "60"}),
            "cartao": forms.Select(attrs={"class": "form-control", "id": "id_cartao"}),
            "responsavel": forms.Select(attrs={"class": "form-control", "id": "id_responsavel"}),
            "categoria": forms.Select(attrs={"class": "form-control"}),
            "observacao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["categoria"].empty_label = "— Sem categoria —"
        self.fields["total_parcelas"].required = False
        self.fields["cartao"].required = False
        self.fields["cartao"].empty_label = "— Sem cartão —"
        if user is not None:
            self.fields["cartao"].queryset = Cartao.objects.filter(ativo=True, user=user)
            self.fields["responsavel"].queryset = Responsavel.objects.filter(ativo=True, user=user)
            self.fields["categoria"].queryset = Categoria.objects.filter(ativo=True, user=user)
        else:
            self.fields["cartao"].queryset = Cartao.objects.filter(ativo=True)
            self.fields["responsavel"].queryset = Responsavel.objects.filter(ativo=True)
            self.fields["categoria"].queryset = Categoria.objects.filter(ativo=True)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_pagamento")
        parcelas = cleaned.get("total_parcelas")
        from .models import Gasto as _Gasto
        if tipo in _Gasto.TIPOS_CARTAO and not cleaned.get("cartao"):
            self.add_error("cartao", "Selecione um cartão para este tipo de pagamento.")
        if tipo not in _Gasto.TIPOS_CARTAO:
            cleaned["cartao"] = None
            cleaned["total_parcelas"] = None
            cleaned["mes_inicio"] = None
            cleaned["ano_inicio"] = None
        if tipo == "credito_parcelado" and not parcelas:
            self.add_error("total_parcelas", "Informe o número de parcelas para compra parcelada.")
        if tipo != "credito_parcelado":
            cleaned["total_parcelas"] = None
            cleaned["mes_inicio"] = None
            cleaned["ano_inicio"] = None
        return cleaned


class CartaoForm(forms.ModelForm):
    class Meta:
        model = Cartao
        fields = ["nome", "bandeira", "limite", "dia_fechamento", "dia_vencimento", "cor", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "bandeira": forms.Select(attrs={"class": "form-control"}),
            "limite": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "dia_fechamento": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "31"}),
            "dia_vencimento": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "31"}),
            "cor": forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["limite"].required = False
        self.fields["dia_fechamento"].required = False
        self.fields["dia_vencimento"].required = False


class ResponsavelForm(forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ["nome", "ativo", "usuario_vinculado"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "usuario_vinculado": forms.Select(attrs={"class": "form-control"}),
        }
        labels = {
            "usuario_vinculado": "Vinculado ao login",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["usuario_vinculado"].required = False
        self.fields["usuario_vinculado"].empty_label = "— Não vinculado —"


class CategoriaForm(forms.ModelForm):
    NOME_CHOICES = [("", "— Selecione uma categoria —")] + [
        (nome, f"{icone} {nome}") for nome, icone, cor in Categoria.PRESETS
    ]

    class Meta:
        model = Categoria
        fields = ["nome", "icone", "cor", "ativo"]
        widgets = {
            "nome": forms.Select(attrs={"class": "form-control", "id": "id_nome"}),
            "icone": forms.HiddenInput(),
            "cor": forms.HiddenInput(),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].widget.choices = self.NOME_CHOICES


class EntradaForm(forms.ModelForm):
    class Meta:
        model = Entrada
        fields = ["tipo", "descricao", "valor", "data", "conta"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "descricao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Salário junho..."}),
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0,00"}),
            "data": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "conta": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        choices = [c for c in Entrada.TIPO_CHOICES if c[0] != "saldo_anterior"]
        self.fields["tipo"].choices = choices
        self.fields["conta"].required = False
        self.fields["conta"].empty_label = "— Sem conta —"
        if user is not None:
            self.fields["conta"].queryset = Conta.objects.filter(ativo=True, user=user)
        else:
            self.fields["conta"].queryset = Conta.objects.filter(ativo=True)


class ContaForm(forms.ModelForm):
    class Meta:
        model = Conta
        fields = ["nome", "banco", "tipo", "saldo_atual", "cor", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "banco": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Nubank, Itaú..."}),
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "saldo_atual": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0,00"}),
            "cor": forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "id": "pf_username"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "id": "pf_nome"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "id": "pf_sobrenome"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "id": "pf_email"}),
        }
        labels = {
            "username": "Usuário",
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "email": "E-mail",
        }


class SenhaForm(forms.Form):
    senha_atual = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "pf_senha_atual", "placeholder": "••••••••"}),
    )
    nova_senha = forms.CharField(
        label="Nova senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "pf_nova_senha", "placeholder": "••••••••"}),
    )
    confirmar_senha = forms.CharField(
        label="Confirmar nova senha",
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "pf_confirmar_senha", "placeholder": "••••••••"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_senha_atual(self):
        senha = self.cleaned_data.get("senha_atual")
        if not self.user.check_password(senha):
            raise forms.ValidationError("Senha atual incorreta.")
        return senha

    def clean(self):
        cleaned = super().clean()
        nova = cleaned.get("nova_senha")
        confirmar = cleaned.get("confirmar_senha")
        if nova and confirmar and nova != confirmar:
            self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned
