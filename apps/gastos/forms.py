from django import forms
from django.contrib.auth import get_user_model
from .models import Gasto, Cartao, Responsavel, Categoria, Entrada, Conta, Investimento
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

import datetime as _dt
from decimal import Decimal

_MESES = [
    (1,"Janeiro"),(2,"Fevereiro"),(3,"Março"),(4,"Abril"),
    (5,"Maio"),(6,"Junho"),(7,"Julho"),(8,"Agosto"),
    (9,"Setembro"),(10,"Outubro"),(11,"Novembro"),(12,"Dezembro"),
]
_ANOS = [(y, y) for y in range(2026, 2051)]


class FormControlMixin:
    """Aplica automaticamente form-control em todos os campos que não sejam hidden ou checkbox."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.HiddenInput, forms.CheckboxInput)):
                continue
            widget.attrs.setdefault("class", "form-control")


class GastoForm(FormControlMixin, forms.ModelForm):
    mes_inicio = forms.ChoiceField(
        choices=_MESES, required=False, label="Mês da 1ª Parcela",
        widget=forms.Select(attrs={"id": "id_mes_inicio"}),
    )
    ano_inicio = forms.ChoiceField(
        choices=_ANOS, required=False, label="Ano",
        widget=forms.Select(attrs={"id": "id_ano_inicio"}),
    )

    class Meta:
        model = Gasto
        fields = [
            "descricao", "valor_total", "data_compra", "tipo_pagamento",
            "total_parcelas", "cartao", "conta_origem", "responsavel", "categoria", "observacao",
            "cartao_adicional", "ajuste_tipo",
        ]
        widgets = {
            "descricao":      forms.TextInput(attrs={"placeholder": "Ex: Mercado, Farmácia..."}),
            "valor_total":    forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
            "data_compra":    forms.DateInput(attrs={"type": "date"}),
            "tipo_pagamento": forms.Select(attrs={"id": "id_tipo_pagamento"}),
            "total_parcelas": forms.NumberInput(attrs={"min": "2", "max": "60"}),
            "cartao":         forms.Select(attrs={"id": "id_cartao"}),
            "conta_origem":   forms.Select(attrs={"id": "id_conta_origem"}),
            "responsavel":    forms.Select(attrs={"id": "id_responsavel"}),
            "categoria":      forms.Select(),
            "observacao":     forms.Textarea(attrs={"rows": 3}),
            "ajuste_tipo":    forms.Select(attrs={"id": "id_ajuste_tipo"}),
        }

    _PCT_CHOICES = [(p, f"{p}%") for p in range(10, 100, 10)]

    recorrente = forms.BooleanField(
        required=False,
        label="Compra Recorrente",
        widget=forms.CheckboxInput(attrs={"id": "id_recorrente"}),
    )
    recorrente_meses = forms.ChoiceField(
        choices=(
            [("sempre", "Sempre (até 2050)")]
            + [(str(i), f"{i} meses") for i in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 24, 36, 48, 60]]
        ),
        initial="12",
        required=False,
        label="Repetir por",
        widget=forms.Select(attrs={"id": "id_recorrente_meses", "class": "form-control"}),
    )

    dividir_gasto = forms.BooleanField(
        required=False,
        label="Dividir este gasto",
        widget=forms.CheckboxInput(attrs={"id": "id_dividir_gasto"}),
    )
    dividir_com = forms.ModelChoiceField(
        queryset=Responsavel.objects.none(),
        required=False,
        label="Dividir com",
        empty_label="— Selecione o responsável —",
        widget=forms.Select(attrs={"id": "id_dividir_com", "class": "form-control"}),
    )
    pct_responsavel = forms.ChoiceField(
        choices=_PCT_CHOICES,
        initial=50,
        required=False,
        label="Minha parte",
        widget=forms.Select(attrs={"id": "id_pct_responsavel", "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["categoria"].empty_label = "— Sem categoria —"
        self.fields["total_parcelas"].required = False
        self.fields["cartao"].required = False
        self.fields["cartao"].empty_label = "— Sem cartão —"
        self.fields["conta_origem"].required = False
        self.fields["conta_origem"].empty_label = "— Selecione a conta —"
        self.fields["ajuste_tipo"].required = False
        self.fields["responsavel"].required = False
        kw = {"ativo": True}
        if user is not None:
            kw["user"] = user
        self.fields["cartao"].queryset       = Cartao.objects.filter(**kw)
        self.fields["responsavel"].queryset  = Responsavel.objects.filter(**kw)
        self.fields["categoria"].queryset    = Categoria.objects.filter(**kw)
        self.fields["dividir_com"].queryset  = Responsavel.objects.filter(**kw)
        self.fields["conta_origem"].queryset = Conta.objects.filter(**kw)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_pagamento")
        parcelas = cleaned.get("total_parcelas")
        # "recorrente" é tratado como credito_avista para fins de validação
        tipo_val = "credito_avista" if tipo == "recorrente" else tipo

        TIPOS_COM_CARTAO = Gasto.TIPOS_CARTAO | {"ajuste_fatura"}

        if tipo_val in TIPOS_COM_CARTAO and not cleaned.get("cartao"):
            self.add_error("cartao", "Selecione um cartão para este tipo de pagamento.")
        if tipo_val not in TIPOS_COM_CARTAO:
            cleaned["cartao"] = None
            cleaned["total_parcelas"] = None
            cleaned["mes_inicio"] = None
            cleaned["ano_inicio"] = None
        if tipo_val == "credito_parcelado" and not parcelas:
            self.add_error("total_parcelas", "Informe o número de parcelas para compra parcelada.")
        # Débito: exige conta_origem
        if tipo_val == "debito":
            if not cleaned.get("conta_origem"):
                self.add_error("conta_origem", "Selecione a conta de débito.")
        else:
            cleaned["conta_origem"] = None
        if tipo_val != "credito_parcelado":
            cleaned["total_parcelas"] = None
        if tipo_val not in ("credito_parcelado", "credito_avista", "ajuste_fatura", "pix"):
            cleaned["mes_inicio"] = None
            cleaned["ano_inicio"] = None
        # Responsável: obrigatório para todos exceto ajuste_fatura (auto-atribuído)
        if not cleaned.get("responsavel"):
            if tipo_val == "ajuste_fatura":
                primary = Responsavel.objects.filter(
                    user=self.user, usuario_vinculado=self.user
                ).first() if self.user else None
                if primary:
                    cleaned["responsavel"] = primary
                else:
                    self.add_error("responsavel", "Selecione um responsável.")
            else:
                self.add_error("responsavel", "Selecione um responsável.")

        # Ajuste de fatura: exige ajuste_tipo; limpa campos irrelevantes
        if tipo_val == "ajuste_fatura":
            if not cleaned.get("ajuste_tipo"):
                self.add_error("ajuste_tipo", "Selecione se é desconto ou adição.")
        else:
            cleaned["ajuste_tipo"] = None
        return cleaned


class CartaoForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Cartao
        fields = ["nome", "bandeira", "limite", "dia_fechamento", "dia_vencimento", "cor", "ativo"]
        widgets = {
            "nome":           forms.TextInput(),
            "bandeira":       forms.Select(),
            "limite":         forms.NumberInput(attrs={"step": "0.01"}),
            "dia_fechamento": forms.NumberInput(attrs={"min": "1", "max": "31"}),
            "dia_vencimento": forms.NumberInput(attrs={"min": "1", "max": "31"}),
            "cor":            forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "ativo":          forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["limite"].required = False
        self.fields["dia_fechamento"].required = False
        self.fields["dia_vencimento"].required = False


class ResponsavelForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Responsavel
        fields = ["nome", "ativo", "usuario_vinculado"]
        widgets = {
            "nome":              forms.TextInput(),
            "ativo":             forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "usuario_vinculado": forms.Select(),
        }
        labels = {
            "usuario_vinculado": "Vinculado ao login",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["usuario_vinculado"].required = False
        self.fields["usuario_vinculado"].empty_label = "— Não vinculado —"


class CategoriaForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome", "icone", "cor", "ativo"]
        widgets = {
            "nome":  forms.TextInput(attrs={"id": "id_nome", "placeholder": "Nome da categoria..."}),
            "icone": forms.HiddenInput(),
            "cor":   forms.HiddenInput(),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EntradaForm(FormControlMixin, forms.ModelForm):
    recorrente = forms.BooleanField(required=False, label="Repetir todo mês")

    class Meta:
        model = Entrada
        fields = ["tipo", "descricao", "valor", "data", "conta"]
        widgets = {
            "tipo":     forms.Select(),
            "descricao": forms.TextInput(attrs={"placeholder": "Ex: Salário junho..."}),
            "valor":    forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
            "data":     forms.DateInput(attrs={"type": "date"}),
            "conta":    forms.Select(),
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


class ContaForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Conta
        fields = ["nome", "banco", "tipo", "saldo_atual", "cor", "ativo"]
        widgets = {
            "nome":       forms.TextInput(),
            "banco":      forms.Select(),
            "tipo":       forms.Select(),
            "saldo_atual": forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
            "cor":        forms.TextInput(attrs={"class": "form-control form-control-color", "type": "color"}),
            "ativo":      forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PerfilForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username":   forms.TextInput(attrs={"id": "pf_username"}),
            "first_name": forms.TextInput(attrs={"id": "pf_nome"}),
            "last_name":  forms.TextInput(attrs={"id": "pf_sobrenome"}),
            "email":      forms.EmailInput(attrs={"id": "pf_email"}),
        }
        labels = {
            "username":   "Usuário",
            "first_name": "Nome",
            "last_name":  "Sobrenome",
            "email":      "E-mail",
        }


class SenhaForm(FormControlMixin, forms.Form):
    senha_atual = forms.CharField(
        label="Senha atual",
        widget=forms.PasswordInput(attrs={"id": "pf_senha_atual", "placeholder": "••••••••"}),
    )
    nova_senha = forms.CharField(
        label="Nova senha",
        widget=forms.PasswordInput(attrs={"id": "pf_nova_senha", "placeholder": "••••••••"}),
    )
    confirmar_senha = forms.CharField(
        label="Confirmar nova senha",
        widget=forms.PasswordInput(attrs={"id": "pf_confirmar_senha", "placeholder": "••••••••"}),
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
        if nova:
            try:
                validate_password(nova, self.user)
            except forms.ValidationError as e:
                self.add_error("nova_senha", e)
        return cleaned



class InvestimentoForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Investimento
        fields = ["conta", "tipo_investimento", "descricao", "saldo_inicial"]
        widgets = {
            "conta":              forms.Select(),
            "tipo_investimento":  forms.Select(),
            "descricao":          forms.TextInput(attrs={"placeholder": "Ex: Tesouro Direto, CDB Banco X..."}),
            "saldo_inicial":      forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
        }
        labels = {
            "conta":              "Conta Bancária",
            "tipo_investimento":  "Tipo de Investimento",
            "descricao":          "Descrição",
            "saldo_inicial":      "Saldo Inicial Aportado (R$)",
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conta"].queryset = Conta.objects.filter(user=user, ativo=True)


class InvestimentoAtualizarSaldoForm(FormControlMixin, forms.Form):
    TIPO_CHOICES = [
        ("rendimento",    "Rendimento"),
        ("aporte",        "Aporte"),
        ("saque",         "Saque"),
        ("ajuste_saldo",  "Ajuste de Saldo"),
    ]
    tipo = forms.ChoiceField(
        label="Tipo de movimentação",
        choices=TIPO_CHOICES,
        widget=forms.Select(),
    )
    valor = forms.DecimalField(
        label="Valor (R$)",
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
    )
    motivo = forms.CharField(
        label="Observação (opcional)",
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ex: Rendimento de maio, Novo aporte..."}),
    )
