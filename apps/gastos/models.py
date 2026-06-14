from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from dateutil.relativedelta import relativedelta

User = get_user_model()


class Responsavel(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)
    is_principal = models.BooleanField(
        default=False,
        help_text="Responsável principal gerado automaticamente para o dono da conta.",
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, related_name="responsaveis",
    )
    usuario_vinculado = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="responsaveis_vinculados",
        help_text="Gastos deste responsável aparecem no dashboard do login vinculado com uma tag.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Responsável"
        verbose_name_plural = "Responsáveis"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Cartao(models.Model):
    TIPO_CHOICES = [
        ("credito", "Crédito"),
    ]
    BANDEIRA_CHOICES = [
        ("visa", "Visa"),
        ("mastercard", "Mastercard"),
        ("elo", "Elo"),
        ("amex", "American Express"),
        ("hipercard", "Hipercard"),
        ("outro", "Outro"),
    ]

    nome = models.CharField(max_length=100)
    bandeira = models.CharField(max_length=20, choices=BANDEIRA_CHOICES, default="visa")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default="credito")
    limite = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dia_fechamento = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Dia do mês em que a fatura fecha (1-31). Apenas para cartões de crédito."
    )
    dia_vencimento = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Dia do mês em que a fatura vence (1-31)."
    )
    cor = models.CharField(max_length=7, default="#6C63FF", help_text="Cor hex para exibição no app")
    ativo = models.BooleanField(default=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, related_name="cartoes",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cartão"
        verbose_name_plural = "Cartões"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"


class Categoria(models.Model):
    # (nome, icone_lucide, cor_padrão) — usado no formulário
    PRESETS = [
        ("Supermercado",  "shopping-cart",  "#22c55e"),
        ("Alimentação",   "utensils",       "#f97316"),
        ("Restaurante",   "utensils",       "#ef4444"),
        ("Café",          "coffee",         "#eab308"),
        ("Bar/Bebida",    "wine",           "#8b5cf6"),
        ("Transporte",    "car",            "#3b82f6"),
        ("Combustível",   "fuel",           "#f97316"),
        ("Uber/Taxi",     "map-pin",        "#eab308"),
        ("Viagem",        "plane",          "#06b6d4"),
        ("Hotel",         "building",       "#14b8a6"),
        ("Farmácia",      "pill",           "#22c55e"),
        ("Saúde",         "heart-pulse",    "#ef4444"),
        ("Educação",      "graduation-cap", "#6366f1"),
        ("Livros",        "book-open",      "#8b5cf6"),
        ("Lazer",         "tv",             "#ec4899"),
        ("Games",         "gamepad-2",      "#6366f1"),
        ("Música",        "music",          "#8b5cf6"),
        ("Vestuário",     "shirt",          "#64748b"),
        ("Calçados",      "shopping-bag",   "#78716c"),
        ("Casa",          "home",           "#f59e0b"),
        ("Manutenção",    "wrench",         "#78716c"),
        ("Energia",       "zap",            "#eab308"),
        ("Água",          "droplets",       "#06b6d4"),
        ("Celular",       "smartphone",     "#3b82f6"),
        ("Tecnologia",    "laptop",         "#6366f1"),
        ("Assinaturas",   "credit-card",    "#64748b"),
        ("Pet",           "paw-print",      "#f97316"),
        ("Beleza",        "sparkles",       "#ec4899"),
        ("Presentes",     "gift",           "#ef4444"),
        ("Academia",      "dumbbell",       "#22c55e"),
        ("Outros",        "wallet",         "#888888"),
    ]

    ICONE_CHOICES = [
        ("shopping-cart",   "Supermercado"),
        ("utensils",        "Alimentação / Restaurante"),
        ("coffee",          "Café"),
        ("wine",            "Bar / Bebida"),
        ("car",             "Transporte / Carro"),
        ("fuel",            "Combustível"),
        ("map-pin",         "Uber / Taxi"),
        ("plane",           "Viagem"),
        ("building",        "Hotel / Construção"),
        ("pill",            "Farmácia"),
        ("heart-pulse",     "Saúde"),
        ("heart",           "Bem-estar"),
        ("graduation-cap",  "Educação"),
        ("book-open",       "Livros"),
        ("tv",              "Streaming / Lazer"),
        ("gamepad-2",       "Games"),
        ("music",           "Música"),
        ("shirt",           "Vestuário"),
        ("shopping-bag",    "Calçados / Compras"),
        ("home",            "Casa"),
        ("wrench",          "Manutenção"),
        ("zap",             "Energia"),
        ("droplets",        "Água"),
        ("smartphone",      "Celular"),
        ("laptop",          "Tecnologia"),
        ("credit-card",     "Assinaturas"),
        ("paw-print",       "Pet"),
        ("sparkles",        "Beleza"),
        ("gift",            "Presentes"),
        ("dumbbell",        "Academia"),
        ("briefcase",       "Trabalho"),
        ("baby",            "Filhos"),
        ("bus",             "Ônibus"),
        ("receipt",         "Contas"),
        ("banknote",        "Finanças"),
        ("shield",          "Seguro"),
        ("camera",          "Fotografia"),
        ("star",            "Especial"),
        ("package",         "Encomendas"),
        ("wallet",          "Outros"),
    ]

    CORES_CHOICES = [
        ("#ef4444", "Vermelho"),
        ("#f97316", "Laranja"),
        ("#eab308", "Amarelo"),
        ("#22c55e", "Verde"),
        ("#16a34a", "Verde Escuro"),
        ("#06b6d4", "Ciano"),
        ("#3b82f6", "Azul"),
        ("#6366f1", "Índigo"),
        ("#8b5cf6", "Roxo"),
        ("#ec4899", "Rosa"),
        ("#14b8a6", "Teal"),
        ("#f59e0b", "Âmbar"),
        ("#84cc16", "Lima"),
        ("#64748b", "Cinza Azul"),
        ("#78716c", "Marrom"),
        ("#888888", "Cinza"),
    ]

    nome = models.CharField(max_length=100)
    icone = models.CharField(max_length=50, blank=True, choices=ICONE_CHOICES)
    cor = models.CharField(max_length=7, default="#888888", choices=CORES_CHOICES)
    ativo = models.BooleanField(default=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, related_name="categorias",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Entrada(models.Model):
    TIPO_CHOICES = [
        ("salario", "Salário"),
        ("bonus", "Bônus"),
        ("outros", "Outros"),
        ("saldo_anterior", "Saldo Mês Anterior"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="salario")
    descricao = models.CharField(max_length=255, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField()
    conta = models.ForeignKey(
        "Conta", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="entradas", help_text="Conta bancária de recebimento.",
    )
    responsavel = models.ForeignKey(
        "Responsavel", on_delete=models.SET_NULL, null=True, blank=True, related_name="entradas"
    )
    auto_gerada = models.BooleanField(default=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, related_name="entradas_proprias",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Entrada"
        verbose_name_plural = "Entradas"
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()} — R$ {self.valor} ({self.data})"


class Gasto(models.Model):
    TIPO_PAGAMENTO_CHOICES = [
        ("credito_avista", "Crédito à Vista"),
        ("credito_parcelado", "Crédito Parcelado"),
        ("pix", "Pix / Transferência"),
        ("emprestimo", "Empréstimo"),
    ]

    TIPOS_CARTAO = {"credito_avista", "credito_parcelado"}

    descricao = models.CharField(max_length=255)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    tipo_pagamento = models.CharField(max_length=25, choices=TIPO_PAGAMENTO_CHOICES)
    cartao = models.ForeignKey(
        "Cartao", on_delete=models.PROTECT, related_name="gastos",
        null=True, blank=True,
    )
    nome_pessoa = models.CharField(
        max_length=150, blank=True, default="",
        help_text="Nome da pessoa destinatária (para 'Pagamento a Pessoa').",
    )
    responsavel = models.ForeignKey(
        "Responsavel", on_delete=models.PROTECT, related_name="gastos"
    )
    categoria = models.ForeignKey(
        "Categoria", on_delete=models.SET_NULL, null=True, blank=True, related_name="gastos"
    )
    data_compra = models.DateField(help_text="Data em que a compra foi realizada")
    observacao = models.TextField(blank=True)
    total_parcelas = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Número total de parcelas. Preencher apenas se parcelado."
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, related_name="gastos_proprios",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gasto"
        verbose_name_plural = "Gastos"
        ordering = ["-data_compra", "-criado_em"]

    def __str__(self):
        return f"{self.descricao} — R$ {self.valor_total} ({self.data_compra})"

class Parcela(models.Model):
    gasto = models.ForeignKey(
        "Gasto", on_delete=models.CASCADE, related_name="parcelas"
    )
    numero = models.PositiveSmallIntegerField(help_text="Ex: 1 de 12")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField()
    pago = models.BooleanField(default=False)
    data_pagamento = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Parcela"
        verbose_name_plural = "Parcelas"
        ordering = ["data_vencimento"]

    def __str__(self):
        return f"Parcela {self.numero}/{self.gasto.total_parcelas} — {self.gasto.descricao}"


class FaturaPaga(models.Model):
    cartao = models.ForeignKey(
        Cartao, on_delete=models.CASCADE, related_name="faturas_pagas"
    )
    mes = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="faturas_pagas"
    )

    class Meta:
        verbose_name = "Fatura Paga"
        verbose_name_plural = "Faturas Pagas"
        unique_together = ("cartao", "mes", "ano", "user")

    def __str__(self):
        return f"{self.cartao.nome} — {self.mes}/{self.ano}"


class Conta(models.Model):
    TIPO_CHOICES = [
        ("corrente", "Conta Corrente"),
        ("poupanca", "Poupança"),
        ("salario", "Conta Salário"),
        ("investimento", "Investimento"),
        ("digital", "Conta Digital"),
        ("outro", "Outro"),
    ]

    nome = models.CharField(max_length=100)
    banco = models.CharField(max_length=100, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="corrente")
    saldo_atual = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cor = models.CharField(max_length=7, default="#3b82f6")
    ativo = models.BooleanField(default=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="contas"
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Conta"
        verbose_name_plural = "Contas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class PagamentoFeito(models.Model):
    TIPO_CHOICES = [("pix", "Pix"), ("emprestimo", "Empréstimo")]
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    responsavel = models.ForeignKey(
        Responsavel, on_delete=models.CASCADE, related_name="pagamentos_feitos"
    )
    mes = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="pagamentos_feitos"
    )

    class Meta:
        verbose_name = "Pagamento Feito"
        verbose_name_plural = "Pagamentos Feitos"
        unique_together = ("tipo", "responsavel", "mes", "ano", "user")

    def __str__(self):
        return f"{self.tipo} — {self.responsavel.nome} {self.mes}/{self.ano}"
