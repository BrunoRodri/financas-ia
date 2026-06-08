from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Tag(models.Model):
    """Classificação flexível para transações (ex: Alimentação, Lazer)."""
    name = models.CharField('Nome', max_length=50, unique=True)
    color = models.CharField('Cor', max_length=7, default='#6366f1',
                             help_text='Cor hexadecimal (ex: #6366f1)')

    class Meta:
        ordering = ['name']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

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
        if self.recurrence_type != self.RecurrenceType.MONTHLY or not self.is_active:
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

    def save(self, *args, **kwargs):
        # Controle de consistência de Metas vinculadas
        original_goal = None
        original_amount = Decimal('0.00')
        original_type = None
        original_description = ""

        if self.pk is not None:
            # Transação existente: vamos ver o estado anterior
            try:
                from core.models import Transaction
                original = Transaction.objects.get(pk=self.pk)
                original_goal = original.goal
                original_amount = original.amount
                original_type = original.type
                original_description = original.description
            except Transaction.DoesNotExist:
                pass

        # Executa o save original
        super().save(*args, **kwargs)

        # Se houver meta anterior ou atual, ajustamos o progresso
        if original_goal or self.goal:
            # 1. Reverter o impacto original se havia uma meta
            if original_goal:
                goal_obj = original_goal
                is_original_aporte = (original_type == self.TransactionType.EXPENSE and original_description.strip().lower().startswith('aporte'))
                is_original_resgate = (original_type == self.TransactionType.INCOME and original_description.strip().lower().startswith('resgate'))

                if is_original_aporte or (original_type == self.TransactionType.INCOME and not is_original_resgate):
                    # Adicionou à meta originalmente (Aporte ou Entrada manual). Revertemos subtraindo.
                    goal_obj.current_amount = max(goal_obj.current_amount - original_amount, Decimal('0.00'))
                else:
                    # Subtraiu da meta originalmente (Resgate ou Saída manual). Revertemos somando.
                    goal_obj.current_amount += original_amount
                goal_obj.save()

            # 2. Aplicar o novo impacto se houver uma meta atualmente vinculada
            if self.goal:
                # Se for a mesma meta do passo anterior, recarregamos para ter o saldo já revertido
                goal_obj = self.goal
                if original_goal and original_goal.pk == self.goal.pk:
                    goal_obj.refresh_from_db()
                
                is_aporte = (self.type == self.TransactionType.EXPENSE and self.description.strip().lower().startswith('aporte'))
                is_resgate = (self.type == self.TransactionType.INCOME and self.description.strip().lower().startswith('resgate'))

                if is_aporte or (self.type == self.TransactionType.INCOME and not is_resgate):
                    # Aporte ou Entrada manual comum: adiciona à meta
                    goal_obj.current_amount += self.amount
                else:
                    # Resgate ou Saída manual comum: subtrai da meta (limitado a zero)
                    goal_obj.current_amount = max(goal_obj.current_amount - self.amount, Decimal('0.00'))
                goal_obj.save()

    def delete(self, *args, **kwargs):
        # Ao excluir, reverte o impacto na meta vinculada
        if self.goal:
            goal_obj = self.goal
            is_aporte = (self.type == self.TransactionType.EXPENSE and self.description.strip().lower().startswith('aporte'))
            is_resgate = (self.type == self.TransactionType.INCOME and self.description.strip().lower().startswith('resgate'))

            if is_aporte or (self.type == self.TransactionType.INCOME and not is_resgate):
                # Se adicionou, subtraímos para reverter
                goal_obj.current_amount = max(goal_obj.current_amount - self.amount, Decimal('0.00'))
            else:
                # Se subtraiu, somamos para reverter
                goal_obj.current_amount += self.amount
            goal_obj.save()

        super().delete(*args, **kwargs)


class Goal(models.Model):
    """Meta financeira (ex: Viagem pro Rio, Reserva de emergência)."""
    name = models.CharField('Nome', max_length=100)
    target_amount = models.DecimalField('Valor alvo', max_digits=12, decimal_places=2)
    current_amount = models.DecimalField('Valor acumulado', max_digits=12, decimal_places=2,
                                         default=0)
    deadline = models.DateField('Data limite')
    color = models.CharField('Cor', max_length=7, default='#22c55e')
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


class UserSettings(models.Model):
    """Configurações do usuário (singleton). Armazena o saldo atual de referência."""
    current_balance = models.DecimalField('Saldo atual', max_digits=12, decimal_places=2,
                                          default=0)
    balance_date = models.DateField('Data de referência', default=timezone.localdate)

    class Meta:
        verbose_name = 'Configurações'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return f'Saldo: R${self.current_balance} em {self.balance_date}'

    def save(self, *args, **kwargs):
        # Singleton pattern: force pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Retorna a instância singleton, criando se não existir."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
