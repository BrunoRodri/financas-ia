from django import forms
from django.utils import timezone

from core.models import CreditCard, Goal, RecurringRule, Tag, Transaction, UserSettings


class TransactionForm(forms.ModelForm):
    """Form para lançamento rápido de transações."""

    class Meta:
        model = Transaction
        fields = ['description', 'amount', 'due_date', 'type', 'status', 'credit_card', 'tags']
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
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-input',
            }, format='%Y-%m-%d'),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'credit_card': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].initial = timezone.localdate()
        self.fields['credit_card'].required = False
        self.fields['credit_card'].empty_label = 'Sem cartão'
        self.fields['tags'].required = False


class RecurringRuleForm(forms.ModelForm):
    """Form para criar regras recorrentes (mensais ou parceladas)."""

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
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-input',
            }, format='%Y-%m-%d'),
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
        recurrence_type = cleaned_data.get('recurrence_type')
        total_installments = cleaned_data.get('total_installments')

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
