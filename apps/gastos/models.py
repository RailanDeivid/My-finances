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
        # Alimentação
        ("Supermercado",  "shopping-cart",  "#22c55e"),
        ("Alimentação",   "utensils",       "#f97316"),
        ("Café",          "coffee",         "#eab308"),
        ("Bar / Bebida",  "wine",           "#8b5cf6"),
        ("Pizza",         "pizza",          "#ef4444"),
        ("Lanche",        "sandwich",       "#f59e0b"),
        ("Dieta",         "salad",          "#22c55e"),
        ("Açougue",       "beef",           "#dc2626"),
        ("Peixaria",      "fish",           "#06b6d4"),
        ("Padaria",       "cake",           "#eab308"),
        ("Sorvete",       "ice-cream-2",    "#ec4899"),
        ("Doces",         "cookie",         "#f472b6"),
        # Transporte
        ("Carro",         "car",            "#3b82f6"),
        ("Combustível",   "fuel",           "#f97316"),
        ("Uber / Taxi",   "map-pin",        "#eab308"),
        ("Viagem",        "plane",          "#06b6d4"),
        ("Ônibus",        "bus",            "#f97316"),
        ("Trem / Metrô",  "train",          "#64748b"),
        ("Bicicleta",     "bike",           "#22c55e"),
        ("Navio",         "ship",           "#0ea5e9"),
        ("GPS / Rota",    "navigation",     "#06b6d4"),
        # Moradia
        ("Casa",          "home",           "#f59e0b"),
        ("Apartamento",   "building-2",     "#14b8a6"),
        ("Manutenção",    "wrench",         "#78716c"),
        ("Móveis",        "sofa",           "#f59e0b"),
        ("Decoração",     "lamp",           "#a855f7"),
        ("Climatização",  "thermometer",    "#38bdf8"),
        ("Energia",       "zap",            "#eab308"),
        ("Água",          "droplets",       "#06b6d4"),
        ("Gás",           "flame",          "#f97316"),
        ("Limpeza",       "trash-2",        "#64748b"),
        # Saúde
        ("Farmácia",      "pill",           "#22c55e"),
        ("Saúde",         "heart-pulse",    "#ef4444"),
        ("Bem-estar",     "heart",          "#ec4899"),
        ("Médico",        "stethoscope",    "#3b82f6"),
        ("Academia",      "dumbbell",       "#22c55e"),
        # Educação
        ("Educação",      "graduation-cap", "#6366f1"),
        ("Livros",        "book-open",      "#8b5cf6"),
        # Lazer
        ("Lazer",         "tv",             "#ec4899"),
        ("Games",         "gamepad-2",      "#6366f1"),
        ("Música",        "music",          "#8b5cf6"),
        # Vestuário
        ("Vestuário",     "shirt",          "#64748b"),
        ("Calçados",      "shopping-bag",   "#78716c"),
        # Tecnologia
        ("Celular",       "smartphone",     "#3b82f6"),
        ("Tecnologia",    "laptop",         "#6366f1"),
        ("Assinaturas",   "credit-card",    "#64748b"),
        # Pessoal
        ("Pet",           "paw-print",      "#f97316"),
        ("Beleza",        "sparkles",       "#ec4899"),
        ("Presentes",     "gift",           "#ef4444"),
        # Outros
        ("Outros",        "wallet",         "#888888"),
    ]

    ICONE_CHOICES = [
        # Alimentação
        ("shopping-cart",   "Supermercado"),
        ("utensils",        "Alimentação"),
        ("coffee",          "Café"),
        ("wine",            "Bar / Bebida"),
        ("pizza",           "Pizza"),
        ("sandwich",        "Lanche"),
        ("salad",           "Dieta"),
        ("beef",            "Açougue"),
        ("fish",            "Peixaria"),
        ("cake",            "Padaria"),
        ("ice-cream-2",     "Sorvete"),
        ("cookie",          "Doces"),
        # Transporte
        ("car",             "Carro"),
        ("fuel",            "Combustível"),
        ("map-pin",         "Uber / Taxi"),
        ("plane",           "Viagem"),
        ("bus",             "Ônibus"),
        ("train",           "Trem / Metrô"),
        ("bike",            "Bicicleta"),
        ("ship",            "Navio"),
        ("navigation",      "GPS / Rota"),
        # Moradia
        ("home",            "Casa"),
        ("building-2",      "Apartamento"),
        ("wrench",          "Manutenção"),
        ("sofa",            "Móveis"),
        ("lamp",            "Decoração"),
        ("thermometer",     "Climatização"),
        ("zap",             "Energia"),
        ("droplets",        "Água"),
        ("flame",           "Gás"),
        ("trash-2",         "Limpeza"),
        # Saúde
        ("pill",            "Farmácia"),
        ("heart-pulse",     "Saúde"),
        ("heart",           "Bem-estar"),
        ("stethoscope",     "Médico"),
        ("dumbbell",        "Academia"),
        ("apple",           "Nutrição"),
        # Educação
        ("graduation-cap",  "Educação"),
        ("book-open",       "Livros"),
        ("pen",             "Papelaria"),
        ("monitor",         "Curso Online"),
        # Lazer
        ("tv",              "Streaming"),
        ("gamepad-2",       "Games"),
        ("music",           "Música"),
        ("headphones",      "Podcast"),
        ("camera",          "Fotografia"),
        ("film",            "Cinema"),
        ("ticket",          "Shows / Eventos"),
        ("star",            "Especial"),
        # Vestuário
        ("shirt",           "Vestuário"),
        ("shopping-bag",    "Calçados"),
        ("watch",           "Acessórios"),
        # Tecnologia
        ("smartphone",      "Celular"),
        ("laptop",          "Tecnologia"),
        ("tablet",          "Tablet"),
        ("credit-card",     "Assinaturas"),
        # Trabalho / Finanças
        ("briefcase",       "Trabalho"),
        ("receipt",         "Contas"),
        ("banknote",        "Finanças"),
        ("piggy-bank",      "Poupança"),
        ("coins",           "Investimento"),
        ("calculator",      "Impostos"),
        ("shield",          "Seguro"),
        # Família / Pessoal
        ("baby",            "Filhos"),
        ("paw-print",       "Pet"),
        ("sparkles",        "Beleza"),
        ("gift",            "Presentes"),
        ("heart-handshake", "Doação"),
        # Viagem / Hotel
        ("building",        "Hotel"),
        ("map",             "Turismo"),
        ("luggage",         "Bagagem"),
        # Outros
        ("package",         "Encomendas"),
        ("wallet",          "Outros"),
    ]

    CORES_CHOICES = [
        # Vermelhos / Laranjas
        ("#ef4444", "Vermelho"),
        ("#dc2626", "Vermelho Escuro"),
        ("#f97316", "Laranja"),
        ("#ea580c", "Laranja Escuro"),
        ("#fb923c", "Salmão"),
        # Amarelos / Âmbar
        ("#eab308", "Amarelo"),
        ("#f59e0b", "Âmbar"),
        ("#fbbf24", "Dourado"),
        ("#d97706", "Caramelo"),
        # Verdes
        ("#22c55e", "Verde"),
        ("#16a34a", "Verde Escuro"),
        ("#84cc16", "Lima"),
        ("#4ade80", "Verde Claro"),
        ("#14b8a6", "Teal"),
        ("#10b981", "Esmeralda"),
        # Azuis / Ciano
        ("#06b6d4", "Ciano"),
        ("#0891b2", "Azul Piscina"),
        ("#3b82f6", "Azul"),
        ("#2563eb", "Azul Escuro"),
        ("#60a5fa", "Azul Claro"),
        ("#0ea5e9", "Céu"),
        # Roxos / Índigo
        ("#6366f1", "Índigo"),
        ("#4f46e5", "Índigo Escuro"),
        ("#8b5cf6", "Roxo"),
        ("#7c3aed", "Roxo Escuro"),
        ("#a855f7", "Lavanda"),
        # Rosas
        ("#ec4899", "Rosa"),
        ("#db2777", "Rosa Escuro"),
        ("#f472b6", "Rosa Claro"),
        # Neutros
        ("#64748b", "Cinza Azul"),
        ("#475569", "Ardósia"),
        ("#78716c", "Marrom"),
        ("#57534e", "Marrom Escuro"),
        ("#888888", "Cinza"),
        ("#6b7280", "Cinza Médio"),
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
    data = models.DateField(db_index=True)
    conta = models.ForeignKey(
        "Conta", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="entradas", help_text="Conta bancária de recebimento.",
    )
    responsavel = models.ForeignKey(
        "Responsavel", on_delete=models.SET_NULL, null=True, blank=True, related_name="entradas"
    )
    auto_gerada = models.BooleanField(default=False)
    recorrente = models.BooleanField(default=False)
    grupo_recorrente = models.UUIDField(null=True, blank=True, db_index=True)
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
        ("credito_avista",    "Crédito à Vista"),
        ("credito_parcelado", "Crédito Parcelado"),
        ("recorrente",        "Compra Recorrente"),
        ("pix",               "Pix / Transferência"),
        ("debito",            "Débito"),
        ("ajuste_fatura",     "Ajuste de Fatura"),
    ]

    AJUSTE_TIPO_CHOICES = [
        ("desconto", "Desconto"),
        ("adicao",   "Adição"),
    ]

    TIPOS_CARTAO = {"credito_avista", "credito_parcelado"}
    TIPOS_CONTA  = {"debito"}

    descricao = models.CharField(max_length=255)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    tipo_pagamento = models.CharField(max_length=25, choices=TIPO_PAGAMENTO_CHOICES, db_index=True)
    cartao = models.ForeignKey(
        "Cartao", on_delete=models.PROTECT, related_name="gastos",
        null=True, blank=True,
    )
    responsavel = models.ForeignKey(
        "Responsavel", on_delete=models.PROTECT, related_name="gastos"
    )
    categoria = models.ForeignKey(
        "Categoria", on_delete=models.SET_NULL, null=True, blank=True, related_name="gastos"
    )
    data_compra = models.DateField(db_index=True, help_text="Data em que a compra foi realizada")
    observacao = models.TextField(blank=True)
    total_parcelas = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Número total de parcelas. Preencher apenas se parcelado."
    )
    grupo_divisao = models.UUIDField(
        null=True, blank=True, default=None, db_index=True,
        help_text="UUID compartilhado entre os dois lados de um gasto dividido.",
    )
    grupo_recorrente = models.UUIDField(
        null=True, blank=True, default=None, db_index=True,
        help_text="UUID compartilhado entre as ocorrências de um gasto recorrente.",
    )
    pct_divisao = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Percentual desta parte no gasto dividido (ex: 60 = 60%).",
    )
    ajuste_tipo = models.CharField(
        max_length=10, choices=AJUSTE_TIPO_CHOICES,
        null=True, blank=True,
        help_text="Apenas para tipo 'Ajuste de Fatura': desconto ou adição.",
    )
    conta_origem = models.ForeignKey(
        "Conta", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="gastos_debito",
        help_text="Conta debitada (obrigatória para tipo Débito).",
    )
    cartao_adicional = models.BooleanField(
        default=False,
        help_text="Indica se o gasto foi realizado em um cartão adicional.",
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

    @property
    def valor_compra_total(self):
        """Valor total da compra antes da divisão. Para gastos não-divididos, igual a valor_total."""
        from decimal import Decimal
        if self.grupo_divisao and self.pct_divisao:
            return (self.valor_total * Decimal("100") / Decimal(self.pct_divisao)).quantize(Decimal("0.01"))
        return self.valor_total

    def __str__(self):
        return f"{self.descricao} — R$ {self.valor_total} ({self.data_compra})"

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

    BANCO_CHOICES = [
        ("",            "— Selecione —"),
        ("nubank",      "Nubank"),
        ("inter",       "Banco Inter"),
        ("itau",        "Itaú"),
        ("bradesco",    "Bradesco"),
        ("mercadopago", "Mercado Pago"),
        ("bb",          "Banco do Brasil"),
        ("caixa",       "Caixa Econômica"),
        ("santander",   "Santander"),
        ("c6",          "C6 Bank"),
        ("picpay",      "PicPay"),
        ("xp",          "XP Investimentos"),
        ("outro",       "Outro"),
    ]

    BANCO_COR = {
        "nubank":      "#820AD1",
        "inter":       "#FF7A00",
        "itau":        "#EC7000",
        "bradesco":    "#CC092F",
        "mercadopago": "#009EE3",
        "bb":          "#F8D000",
        "caixa":       "#005CA9",
        "santander":   "#EC0000",
        "c6":          "#242424",
        "picpay":      "#21C25E",
        "xp":          "#000000",
        "outro":       "#64748b",
    }

    # SVG para nubank, picpay, inter e outro; PNG para caixa
    BANCO_LOGO_EXT = {
        "nubank":  "svg",
        "inter":   "svg",
        "picpay":  "svg",
        "caixa":   "png",
        "outro":   "svg",
    }

    nome = models.CharField(max_length=100)
    banco = models.CharField(max_length=20, choices=BANCO_CHOICES, blank=True)
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

    @property
    def banco_logo_path(self):
        if not self.banco:
            return None
        ext = self.BANCO_LOGO_EXT.get(self.banco, "png")
        return f"img/banks/{self.banco}.{ext}"

    @property
    def banco_cor(self):
        return self.BANCO_COR.get(self.banco, self.cor)


class Investimento(models.Model):
    TIPO_INV_CHOICES = [
        ("renda_fixa",        "Renda Fixa"),
        ("renda_variavel",    "Renda Variável"),
        ("fundo_imobiliario", "Fundo Imobiliário"),
    ]
    conta = models.ForeignKey(
        Conta, on_delete=models.CASCADE, related_name="investimentos"
    )
    descricao = models.CharField(max_length=200)
    tipo_investimento = models.CharField(
        max_length=20, choices=TIPO_INV_CHOICES, default="renda_fixa",
        verbose_name="Tipo de Investimento",
    )
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_atual = models.DecimalField(max_digits=14, decimal_places=2)
    liquidado = models.BooleanField(default=False)
    data_liquidacao = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="investimentos")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Investimento"
        verbose_name_plural = "Investimentos"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.descricao

    @property
    def rentabilidade(self):
        return self.saldo_atual - self.saldo_inicial

    @property
    def rentabilidade_pct(self):
        if not self.saldo_inicial:
            return Decimal("0")
        return (self.rentabilidade / self.saldo_inicial * 100).quantize(Decimal("0.01"))


class InvestimentoHistorico(models.Model):
    TIPO_CHOICES = [
        ("inicial",       "Aporte Inicial"),
        ("aporte",        "Aporte"),
        ("saque",         "Saque"),
        ("rendimento",    "Rendimento"),
        ("ajuste_saldo",  "Ajuste de Saldo"),
        ("liquidacao",    "Liquidação"),
    ]
    investimento = models.ForeignKey(
        Investimento, on_delete=models.CASCADE, related_name="historico"
    )
    valor_anterior = models.DecimalField(max_digits=14, decimal_places=2)
    valor_novo = models.DecimalField(max_digits=14, decimal_places=2)
    diferenca = models.DecimalField(max_digits=14, decimal_places=2)
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, default="rendimento")
    motivo = models.CharField(max_length=300, blank=True)
    data_movimentacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de Investimento"
        verbose_name_plural = "Histórico de Investimentos"
        ordering = ["-data_movimentacao"]

    def __str__(self):
        return f"{self.investimento} — {self.data_movimentacao:%d/%m/%Y %H:%M}"


class PagamentoFeito(models.Model):
    TIPO_CHOICES = [("pix", "Pix"), ("acerto", "Acerto")]
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
