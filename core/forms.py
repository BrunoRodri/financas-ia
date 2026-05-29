from django import forms
from django.utils import timezone

from core.models import CreditCard, Goal, RecurringRule, Tag, Transaction, UserSettings


class TransactionForm(forms.ModelForm):
    """Form para lançamento rápido de transações."""

    due_date = forms.DateField(
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'dd/mm/aaaa',
            'autocomplete': 'off',
            'inputmode': 'numeric',
        }),
        label='Data'
    )

    payment_type = forms.ChoiceField(
        choices=[
            ('other', 'Dinheiro / Pix / Débito'),
            ('card', 'Cartão de Crédito'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tipo de Pagamento'
    )

    class Meta:
        model = Transaction
        fields = ['description', 'amount', 'due_date', 'type', 'status', 'credit_card', 'tags', 'goal']
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'Ex: Mercado, Salário, Netflix...',
                'class': 'form-input',
                'autofocus': True,
            }),
            'amount': forms.NumberInput(attrs={
                'placeholder': '0,00',
                'class': 'form-input',
                'step': '0.01',
                'min': '0.01',
            }),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'credit_card': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.CheckboxSelectMultiple(),
            'goal': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].initial = timezone.localdate()
        self.fields['credit_card'].required = False
        self.fields['credit_card'].empty_label = 'Sem cartão'
        self.fields['tags'].required = False
        self.fields['goal'].required = False
        self.fields['goal'].empty_label = 'Sem meta'

        if self.instance and self.instance.pk:
            if self.instance.credit_card:
                self.fields['payment_type'].initial = 'card'
            else:
                self.fields['payment_type'].initial = 'other'

    def clean(self):
        cleaned_data = super().clean()
        txn_type = cleaned_data.get('type')
        payment_type = cleaned_data.get('payment_type')
        credit_card = cleaned_data.get('credit_card')

        if txn_type == Transaction.TransactionType.INCOME:
            # Entrada não tem cartão nem tipo de pagamento
            cleaned_data['credit_card'] = None
        elif txn_type == Transaction.TransactionType.EXPENSE:
            if payment_type == 'other':
                cleaned_data['credit_card'] = None
            elif payment_type == 'card' and not credit_card:
                self.add_error('credit_card', 'Selecione um cartão de crédito.')
        return cleaned_data


class RecurringRuleForm(forms.ModelForm):
    """Form para criar regras recorrentes (mensais ou parceladas)."""

    start_date = forms.DateField(
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'dd/mm/aaaa',
            'autocomplete': 'off',
            'inputmode': 'numeric',
        }),
        label='Data início'
    )

    class Meta:
        model = RecurringRule
        fields = [
            'description', 'amount', 'type', 'recurrence_type',
            'total_installments', 'start_date', 'credit_card', 'tags',
        ]
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'Ex: Netflix, Celular 12x...',
                'class': 'form-input',
            }),
            'amount': forms.NumberInput(attrs={
                'placeholder': '0,00',
                'class': 'form-input',
                'step': '0.01',
                'min': '0.01',
            }),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'recurrence_type': forms.Select(attrs={'class': 'form-select'}),
            'total_installments': forms.NumberInput(attrs={
                'placeholder': 'Ex: 12',
                'class': 'form-input',
                'min': '2',
            }),
            'credit_card': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_date'].initial = timezone.localdate()
        self.fields['credit_card'].required = False
        self.fields['credit_card'].empty_label = 'Sem cartão'
        self.fields['total_installments'].required = False
        self.fields['tags'].required = False

    def clean(self):
        cleaned_data = super().clean()
        txn_type = cleaned_data.get('type')
        recurrence_type = cleaned_data.get('recurrence_type')
        total_installments = cleaned_data.get('total_installments')
        credit_card = cleaned_data.get('credit_card')

        if txn_type == RecurringRule.TransactionType.INCOME and credit_card:
            cleaned_data['credit_card'] = None

        if recurrence_type == RecurringRule.RecurrenceType.INSTALLMENT:
            if not total_installments or total_installments < 2:
                self.add_error(
                    'total_installments',
                    'Para parcelado, informe o número de parcelas (mínimo 2).'
                )
        return cleaned_data


class GoalForm(forms.ModelForm):
    """Form para criar/editar metas financeiras."""

    class Meta:
        model = Goal
        fields = ['name', 'target_amount', 'current_amount', 'deadline', 'color']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Ex: Viagem pro Rio',
                'class': 'form-input',
            }),
            'target_amount': forms.NumberInput(attrs={
                'placeholder': '0,00',
                'class': 'form-input',
                'step': '0.01',
            }),
            'current_amount': forms.NumberInput(attrs={
                'placeholder': '0,00',
                'class': 'form-input',
                'step': '0.01',
            }),
            'deadline': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-input',
            }, format='%Y-%m-%d'),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-input-color',
            }),
        }


class CreditCardForm(forms.ModelForm):
    """Form para cadastrar cartões de crédito."""

    class Meta:
        model = CreditCard
        fields = ['name', 'last_digits', 'brand', 'color', 'due_day', 'closing_day']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Ex: Nubank',
                'class': 'form-input',
            }),
            'last_digits': forms.TextInput(attrs={
                'placeholder': '1234',
                'class': 'form-input',
                'maxlength': '4',
            }),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'form-input-color',
            }),
            'due_day': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'max': '31',
            }),
            'closing_day': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '1',
                'max': '31',
            }),
        }


class UserSettingsForm(forms.ModelForm):
    """Form para atualizar o saldo atual."""

    class Meta:
        model = UserSettings
        fields = ['current_balance', 'balance_date']
        widgets = {
            'current_balance': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
            }),
            'balance_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-input',
            }, format='%Y-%m-%d'),
        }
