from django import forms
from .models import Gasto, Cartao, Responsavel, Categoria, Entrada

_MESES = [
    (1,"Janeiro"),(2,"Fevereiro"),(3,"Março"),(4,"Abril"),
    (5,"Maio"),(6,"Junho"),(7,"Julho"),(8,"Agosto"),
    (9,"Setembro"),(10,"Outubro"),(11,"Novembro"),(12,"Dezembro"),
]
_ANOS = [(y, y) for y in range(2023, 2031)]


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
        super().__init__(*args, **kwargs)
        self.fields["categoria"].empty_label = "— Sem categoria —"
        self.fields["total_parcelas"].required = False
        self.fields["cartao"].queryset = Cartao.objects.filter(ativo=True)
        self.fields["responsavel"].queryset = Responsavel.objects.filter(ativo=True)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_pagamento")
        parcelas = cleaned.get("total_parcelas")
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
        fields = ["nome", "bandeira", "tipo", "limite", "dia_fechamento", "dia_vencimento", "cor", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "bandeira": forms.Select(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-control", "id": "id_tipo_cartao"}),
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
        fields = ["nome", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


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
        fields = ["tipo", "descricao", "valor", "data"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-control"}),
            "descricao": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Salário junho..."}),
            "valor": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0,00"}),
            "data": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [c for c in Entrada.TIPO_CHOICES if c[0] != "saldo_anterior"]
        self.fields["tipo"].choices = choices
