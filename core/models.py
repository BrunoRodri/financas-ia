from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Tag(models.Model):
    """Classificação flexível para transações (ex: Alimentação, Lazer)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='Usuário', related_name='tags')
    name = models.CharField('Nome', max_length=50)
    color = models.CharField('Cor', max_length=7, default='#6366f1',
                             help_text='Cor hexadecimal (ex: #6366f1)')

    class Meta:
        ordering = ['name']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        unique_together = ('user', 'name')

    def __str__(self):
        return self.name


class CreditCard(models.Model):
    """Cartão de crédito cadastrado pelo usuário para vincular a compras."""

    class Brand(models.TextChoices):
        VISA = 'VISA', 'Visa'
        MASTERCARD = 'MASTERCARD', 'Mastercard'
        ELO = 'ELO', 'Elo'
        AMEX = 'AMEX', 'American Express'
        HIPERCARD = 'HIPERCARD', 'Hipercard'
        OTHER = 'OTHER', 'Outra'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='Usuário', related_name='credit_cards')
    name = models.CharField('Nome do cartão', max_length=100,
                            help_text='Ex: Nubank, MercadoPago, Inter')
    last_digits = models.CharField('Últimos 4 dígitos', max_length=4, blank=True, default='')
    brand = models.CharField('Bandeira', max_length=20, choices=Brand.choices, default=Brand.VISA)
    color = models.CharField('Cor', max_length=7, default='#8b5cf6',
                             help_text='Cor hexadecimal para identificação visual')
    due_day = models.PositiveSmallIntegerField(
        'Dia de vencimento',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        default=10,
        help_text='Dia do mês em que a fatura vence',
    )
    closing_day = models.PositiveSmallIntegerField(
        'Dia de fechamento',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        default=3,
        help_text='Dia do mês em que a fatura fecha',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Cartão de Crédito'
        verbose_name_plural = 'Cartões de Crédito'

    def __str__(self):
        label = self.name
        if self.last_digits:
            label += f' •••• {self.last_digits}'
        return label


class RecurringRule(models.Model):
    """
    Regra recorrente: pode ser assinatura mensal (MONTHLY) ou compra parcelada (INSTALLMENT).
    - MONTHLY: gera transações indefinidamente enquanto is_active=True.
    - INSTALLMENT: gera todas as N transações imediatamente ao ser criada.
    """

    class RecurrenceType(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Mensal (recorrente)'
        INSTALLMENT = 'INSTALLMENT', 'Parcelado'

    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', 'Entrada'
        EXPENSE = 'EXPENSE', 'Saída'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='Usuário', related_name='recurring_rules')
    description = models.CharField('Descrição', max_length=200)
    amount = models.DecimalField('Valor', max_digits=12, decimal_places=2)
    type = models.CharField('Tipo', max_length=10, choices=TransactionType.choices,
                            default=TransactionType.EXPENSE)
    recurrence_type = models.CharField('Recorrência', max_length=15,
                                       choices=RecurrenceType.choices)
    total_installments = models.PositiveIntegerField(
        'Total de parcelas', null=True, blank=True,
        help_text='Apenas para parcelado. Ex: 12',
    )
    start_date = models.DateField('Data de início')
    end_date = models.DateField('Data de término', null=True, blank=True,
                                help_text='Calculado automaticamente para parcelados')
    is_active = models.BooleanField('Ativo', default=True)
    is_archived = models.BooleanField('Arquivado', default=False)
    credit_card = models.ForeignKey(
        CreditCard, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Cartão', related_name='recurring_rules',
    )
    goal = models.ForeignKey(
        'Goal', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Meta vinculada', related_name='recurring_rules',
    )
    tags = models.ManyToManyField(Tag, blank=True, verbose_name='Tags',
                                  related_name='recurring_rules')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Regra Recorrente'
        verbose_name_plural = 'Regras Recorrentes'

    def __str__(self):
        if self.recurrence_type == self.RecurrenceType.INSTALLMENT and self.total_installments:
            return f'{self.description} ({self.total_installments}x)'
        return f'{self.description} (mensal)'

    def save(self, *args, **kwargs):
        # Auto-calculate end_date for installments
        if (self.recurrence_type == self.RecurrenceType.INSTALLMENT
                and self.total_installments and not self.end_date):
            self.end_date = self.start_date + relativedelta(
                months=self.total_installments - 1
            )
        super().save(*args, **kwargs)

    def generate_installment_transactions(self):
        """
        Gera todas as transações de parcelas de uma vez (chamado ao criar regra INSTALLMENT).
        Não duplica se já existirem transações para esta regra.
        """
        if self.recurrence_type != self.RecurrenceType.INSTALLMENT:
            return []

        existing_numbers = set(
            self.transactions.values_list('installment_number', flat=True)
        )

        transactions = []
        for i in range(1, (self.total_installments or 0) + 1):
            if i in existing_numbers:
                continue
            due_date = self.start_date + relativedelta(months=i - 1)
            txn = Transaction(
                user=self.user,
                description=f'{self.description} ({i}/{self.total_installments})',
                amount=self.amount,
                type=self.type,
                due_date=due_date,
                status=Transaction.Status.PENDING,
                recurring_rule=self,
                credit_card=self.credit_card,
                installment_number=i,
                goal=self.goal,
            )
            transactions.append(txn)

        created = []
        for txn in transactions:
            txn.save()
            txn.tags.set(self.tags.all())
            created.append(txn)
        return created

    def materialize_monthly_transactions(self, months_ahead=6):
        """
        Gera transações mensais para os próximos N meses que ainda não existam.
        Chamado quando o dashboard é acessado.
        """
        if self.recurrence_type != self.RecurrenceType.MONTHLY or not self.is_active or self.is_archived:
            return []

        today = timezone.localdate()
        end_horizon = today + relativedelta(months=months_ahead)

        start_materialize = self.start_date

        existing_dates = set(
            self.transactions.values_list('due_date', flat=True)
        )

        transactions = []
        current = self.start_date
        while current <= end_horizon:
            if current >= start_materialize and current not in existing_dates:
                txn = Transaction(
                    user=self.user,
                    description=self.description,
                    amount=self.amount,
                    type=self.type,
                    due_date=current,
                    status=Transaction.Status.PENDING,
                    recurring_rule=self,
                    credit_card=self.credit_card,
                    goal=self.goal,
                )
                transactions.append(txn)
            current += relativedelta(months=1)

        created = []
        for txn in transactions:
            txn.save()
            txn.tags.set(self.tags.all())
            created.append(txn)
        return created

    @classmethod
    def auto_archive_expired_rules(cls):
        """
        Arquiva automaticamente regras parceladas vencidas (cujo end_date < hoje).
        """
        today = timezone.localdate()
        expired_rules = cls.objects.filter(
            recurrence_type=cls.RecurrenceType.INSTALLMENT,
            is_archived=False
        )
        to_update = []
        for rule in expired_rules:
            if rule.end_date and rule.end_date < today:
                rule.is_archived = True
                to_update.append(rule)
        if to_update:
            cls.objects.bulk_update(to_update, ['is_archived'])



class Transaction(models.Model):
    """
    Transação financeira (receita ou despesa).
    Pode ser avulsa ou gerada por uma RecurringRule.
    """

    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', 'Entrada'
        EXPENSE = 'EXPENSE', 'Saída'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        PAID = 'PAID', 'Pago'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='Usuário', related_name='transactions')
    description = models.CharField('Descrição', max_length=200)
    amount = models.DecimalField('Valor', max_digits=12, decimal_places=2)
    due_date = models.DateField('Data de vencimento')
    type = models.CharField('Tipo', max_length=10, choices=TransactionType.choices)
    status = models.CharField('Status', max_length=10, choices=Status.choices,
                              default=Status.PENDING)
    recurring_rule = models.ForeignKey(
        RecurringRule, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name='Regra recorrente', related_name='transactions',
    )
    credit_card = models.ForeignKey(
        CreditCard, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Cartão', related_name='transactions',
    )
    goal = models.ForeignKey(
        'Goal', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Meta vinculada', related_name='transactions',
    )
    funded_by_goal = models.BooleanField(
        'Financiado pela meta', default=False,
        help_text='Se True, esta despesa foi paga com dinheiro já guardado na meta e não afeta o fluxo de caixa.',
    )
    is_card_bill = models.BooleanField(
        'É fatura de cartão', default=False,
        help_text='Se True, esta transação representa o pagamento da fatura e entra no fluxo de caixa.',
    )
    bill_card = models.ForeignKey(
        CreditCard, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Cartão da fatura', related_name='bill_transactions',
    )
    bill_year = models.SmallIntegerField('Ano da fatura', null=True, blank=True)
    bill_month = models.SmallIntegerField('Mês da fatura', null=True, blank=True)
    installment_number = models.PositiveIntegerField(
        'Parcela nº', null=True, blank=True,
        help_text='Número da parcela (ex: 3 de 12)',
    )
    tags = models.ManyToManyField(Tag, blank=True, verbose_name='Tags',
                                  related_name='transactions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', '-amount']
        verbose_name = 'Transação'
        verbose_name_plural = 'Transações'

    def __str__(self):
        signal = '+' if self.type == self.TransactionType.INCOME else '-'
        return f'{self.description} {signal}R${self.amount}'

    @property
    def is_income(self):
        return self.type == self.TransactionType.INCOME

    @property
    def is_expense(self):
        return self.type == self.TransactionType.EXPENSE

    @property
    def signed_amount(self):
        """Retorna o valor com sinal: positivo para entrada, negativo para saída."""
        if self.is_income:
            return self.amount
        return -self.amount

    def _is_aporte(self, txn_type=None, desc=None):
        """Verifica se é um Aporte oficial (despesa com descrição 'Aporte...')."""
        t = txn_type or self.type
        d = desc or self.description
        return t == self.TransactionType.EXPENSE and d.strip().lower().startswith('aporte')

    def _is_resgate(self, txn_type=None, desc=None):
        """Verifica se é um Resgate oficial (entrada com descrição 'Resgate...')."""
        t = txn_type or self.type
        d = desc or self.description
        return t == self.TransactionType.INCOME and d.strip().lower().startswith('resgate')

    def _goal_impact(self, txn_type=None, desc=None, funded=None):
        """
        Retorna o tipo de impacto na meta:
        - 'add': soma ao current_amount (Aporte)
        - 'subtract': subtrai do current_amount (Resgate)
        - 'spend': soma ao spent_amount (gasto financiado pela meta)
        - None: sem impacto na meta
        """
        t = txn_type or self.type
        d = desc or self.description
        f = funded if funded is not None else self.funded_by_goal

        if self._is_aporte(t, d):
            return 'add'
        if self._is_resgate(t, d):
            return 'subtract'
        if f:
            return 'spend'
        return None

    def save(self, *args, **kwargs):
        # Controle de consistência de Metas vinculadas
        original_goal = None
        original_amount = Decimal('0.00')
        original_type = None
        original_description = ""
        original_funded = False

        if self.pk is not None:
            try:
                original = Transaction.objects.get(pk=self.pk)
                original_goal = original.goal
                original_amount = original.amount
                original_type = original.type
                original_description = original.description
                original_funded = original.funded_by_goal
            except Transaction.DoesNotExist:
                pass

        # Definição automática de funded_by_goal:
        # Se for uma despesa vinculada a uma meta e não for um Aporte, é considerada financiada pela meta.
        if self.type == self.TransactionType.EXPENSE and self.goal is not None:
            if not self._is_aporte():
                self.funded_by_goal = True
            else:
                self.funded_by_goal = False
        else:
            self.funded_by_goal = False

        super().save(*args, **kwargs)

        # Ajustar metas se houver meta anterior ou atual
        if original_goal or self.goal:
            # 1. Reverter impacto original
            if original_goal:
                impact = self._goal_impact(original_type, original_description, original_funded)
                goal_obj = original_goal
                if impact == 'add':
                    goal_obj.current_amount = max(goal_obj.current_amount - original_amount, Decimal('0.00'))
                elif impact == 'subtract':
                    goal_obj.current_amount += original_amount
                elif impact == 'spend':
                    goal_obj.spent_amount = max(goal_obj.spent_amount - original_amount, Decimal('0.00'))
                if impact:
                    goal_obj.save()

            # 2. Aplicar novo impacto
            if self.goal:
                goal_obj = self.goal
                if original_goal and original_goal.pk == self.goal.pk:
                    goal_obj.refresh_from_db()

                impact = self._goal_impact()
                if impact == 'add':
                    goal_obj.current_amount += self.amount
                elif impact == 'subtract':
                    goal_obj.current_amount = max(goal_obj.current_amount - self.amount, Decimal('0.00'))
                elif impact == 'spend':
                    goal_obj.spent_amount += self.amount
                if impact:
                    goal_obj.save()

    def delete(self, *args, **kwargs):
        # Ao excluir, reverte o impacto na meta vinculada
        if self.goal:
            goal_obj = self.goal
            impact = self._goal_impact()
            if impact == 'add':
                goal_obj.current_amount = max(goal_obj.current_amount - self.amount, Decimal('0.00'))
            elif impact == 'subtract':
                goal_obj.current_amount += self.amount
            elif impact == 'spend':
                goal_obj.spent_amount = max(goal_obj.spent_amount - self.amount, Decimal('0.00'))
            if impact:
                goal_obj.save()

        super().delete(*args, **kwargs)


class Goal(models.Model):
    """Meta financeira (ex: Viagem pro Rio, Reserva de emergência)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             verbose_name='Usuário', related_name='goals')
    name = models.CharField('Nome', max_length=100)
    target_amount = models.DecimalField('Valor alvo', max_digits=12, decimal_places=2)
    current_amount = models.DecimalField('Valor acumulado', max_digits=12, decimal_places=2,
                                         default=0)
    spent_amount = models.DecimalField('Valor utilizado', max_digits=12, decimal_places=2,
                                       default=0,
                                       help_text='Quanto do dinheiro guardado já foi gasto no propósito da meta.')
    deadline = models.DateField('Data limite')
    color = models.CharField('Cor', max_length=7, default='#22c55e')
    is_archived = models.BooleanField('Arquivado', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['deadline']
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'

    def __str__(self):
        return f'{self.name} ({self.progress_percent:.0f}%)'

    @property
    def progress_percent(self):
        if self.target_amount <= 0:
            return 100
        return min((self.current_amount / self.target_amount) * 100, 100)

    @property
    def remaining(self):
        return max(self.target_amount - self.current_amount, 0)

    @property
    def available_amount(self):
        """Quanto do dinheiro guardado ainda está disponível para uso."""
        return max(self.current_amount - self.spent_amount, Decimal('0.00'))


class UserSettings(models.Model):
    """Configurações por usuário. Armazena o saldo atual de referência."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                verbose_name='Usuário', related_name='settings')
    current_balance = models.DecimalField('Saldo atual', max_digits=12, decimal_places=2,
                                          default=0)
    balance_date = models.DateField('Data de referência', default=timezone.localdate)

    class Meta:
        verbose_name = 'Configurações'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return f'Saldo: R${self.current_balance} em {self.balance_date}'

    @classmethod
    def load(cls, user):
        """Retorna as configurações do usuário, criando se não existirem."""
        obj, _ = cls.objects.get_or_create(
            user=user,
            defaults={'current_balance': Decimal('0'), 'balance_date': timezone.localdate()},
        )
        return obj
