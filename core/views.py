import json
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import (
    CreditCardForm,
    GoalForm,
    RecurringRuleForm,
    TransactionForm,
    UserSettingsForm,
)
from core.models import CreditCard, Goal, RecurringRule, Transaction, UserSettings
from core.services.cash_flow import get_upcoming_transactions, project_cash_flow


class VirtualInitialBalance:
    def __init__(self, amount, date):
        self.is_initial_balance = True
        self.amount = abs(amount)
        self.due_date = date
        self.type = 'INCOME' if amount >= 0 else 'EXPENSE'
        self.description = "Saldo de Referência (Configurações)"
        self.status = 'PAID'
        self.id = 0
        self.tags = type('MockTags', (object,), {'all': lambda: []})()
        self.credit_card = None
        self.installment_number = None
        self.recurring_rule = None

    @property
    def is_income(self):
        return self.type == 'INCOME'

    @property
    def is_expense(self):
        return self.type == 'EXPENSE'


# ─── Dashboard ───────────────────────────────────────────────────────────────

def dashboard(request):
    """Página principal com projeção de saldo e lançamento rápido."""
    projection = project_cash_flow(months_ahead=6)
    upcoming = get_upcoming_transactions(days=30)
    goals = Goal.objects.all()
    settings = UserSettings.load()

    # Dados para o gráfico (Chart.js)
    chart_labels = [m['month_label'] for m in projection['monthly_summary']]
    chart_balances = [float(m['end_balance']) for m in projection['monthly_summary']]
    chart_income = [float(m['income']) for m in projection['monthly_summary']]
    chart_expense = [float(m['expense']) for m in projection['monthly_summary']]

    # Form de lançamento rápido
    form = TransactionForm()

    context = {
        'projection': projection,
        'upcoming': upcoming,
        'goals': goals,
        'settings': settings,
        'form': form,
        'chart_labels': chart_labels,
        'chart_balances': chart_balances,
        'chart_income': chart_income,
        'chart_expense': chart_expense,
        'today': timezone.localdate(),
    }
    return render(request, 'dashboard.html', context)


# ─── Transactions ────────────────────────────────────────────────────────────

def transaction_list(request):
    """Lista completa de transações com filtros."""
    # Materializa recorrências mensais pendentes antes de listar para garantir dados atualizados
    from core.services.cash_flow import materialize_recurring_transactions
    materialize_recurring_transactions(months_ahead=6)

    transactions = Transaction.objects.select_related(
        'recurring_rule', 'credit_card'
    ).prefetch_related('tags').order_by('due_date')

    # Filtros
    status = request.GET.get('status')
    txn_type = request.GET.get('type')
    tag = request.GET.get('tag')
    month_filter = request.GET.get('month')  # Pode ser "05" ou "2026-05" (redirecionamento do dashboard)
    year_filter = request.GET.get('year')
    payment_method = request.GET.get('payment_method')
    card_id = request.GET.get('card')

    # Suporte a redirecionamentos do dashboard no formato YYYY-MM
    if month_filter and '-' in month_filter:
        try:
            year_filter, month_filter = month_filter.split('-')
        except ValueError:
            pass

    # Aplicar filtros
    if status:
        transactions = transactions.filter(status=status)
    if txn_type:
        transactions = transactions.filter(type=txn_type)
    if tag:
        transactions = transactions.filter(tags__id=tag)
    if year_filter:
        try:
            transactions = transactions.filter(due_date__year=int(year_filter))
        except ValueError:
            pass
    if month_filter:
        try:
            transactions = transactions.filter(due_date__month=int(month_filter))
        except ValueError:
            pass
    if payment_method:
        if payment_method == 'other':
            transactions = transactions.filter(credit_card__isnull=True)
        elif payment_method == 'card':
            transactions = transactions.filter(credit_card__isnull=False)
    if card_id:
        transactions = transactions.filter(credit_card_id=card_id)

    # Calcular somatórios
    total_income = sum(t.amount for t in transactions if t.is_income)
    total_expense = sum(t.amount for t in transactions if t.is_expense)
    net_balance = total_income - total_expense

    # Carregar saldo inicial das configurações
    user_settings = UserSettings.load()
    show_initial_balance = True

    if txn_type:
        is_positive = user_settings.current_balance >= 0
        if (txn_type == 'INCOME' and not is_positive) or (txn_type == 'EXPENSE' and is_positive):
            show_initial_balance = False
    if tag or card_id or payment_method:
        show_initial_balance = False
    if year_filter:
        try:
            if user_settings.balance_date.year != int(year_filter):
                show_initial_balance = False
        except ValueError:
            pass
    if month_filter:
        try:
            if user_settings.balance_date.month != int(month_filter):
                show_initial_balance = False
        except ValueError:
            pass

    transactions_list = list(transactions)
    if show_initial_balance:
        virtual_bal = VirtualInitialBalance(user_settings.current_balance, user_settings.balance_date)
        transactions_list.append(virtual_bal)
        # Ordenação estável: no mesmo dia, o saldo inicial aparece primeiro
        transactions_list.sort(key=lambda t: (t.due_date, 0 if getattr(t, 'is_initial_balance', False) else 1))

    # Opções para popular os dropdowns de filtro na página inteira e HTMX partial
    from core.models import CreditCard, Tag
    cards = CreditCard.objects.all()

    # Todos os 12 meses em ordem cronológica
    months_available = [
        {'value': '01', 'label': 'Janeiro'},
        {'value': '02', 'label': 'Fevereiro'},
        {'value': '03', 'label': 'Março'},
        {'value': '04', 'label': 'Abril'},
        {'value': '05', 'label': 'Maio'},
        {'value': '06', 'label': 'Junho'},
        {'value': '07', 'label': 'Julho'},
        {'value': '08', 'label': 'Agosto'},
        {'value': '09', 'label': 'Setembro'},
        {'value': '10', 'label': 'Outubro'},
        {'value': '11', 'label': 'Novembro'},
        {'value': '12', 'label': 'Dezembro'},
    ]

    # Mapear os anos existentes nas transações
    from django.db.models.functions import ExtractYear
    years_query = Transaction.objects.annotate(
        year=ExtractYear('due_date')
    ).values_list('year', flat=True).distinct().order_by('-year')

    current_year = timezone.localdate().year
    years_available = list(years_query)
    if current_year not in years_available:
        years_available.append(current_year)
    
    # Remover valores nulos e ordenar decrescente
    years_available = sorted([y for y in years_available if y is not None], reverse=True)

    has_advanced = bool(status or month_filter or year_filter or payment_method or card_id or tag)

    context = {
        'transactions': transactions_list,
        'tags': Tag.objects.all(),
        'cards': cards,
        'months_available': months_available,
        'years_available': years_available,
        'current_status': status,
        'current_type': txn_type,
        'current_tag': tag,
        'current_month': month_filter,
        'current_year': year_filter,
        'current_payment_method': payment_method,
        'current_card': card_id,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_balance': net_balance,
        'has_advanced': has_advanced,
    }

    # Retorna o fragmento HTML se for uma requisição HTMX
    if request.headers.get('HX-Request'):
        return render(request, 'partials/transactions_full_content.html', context)

    return render(request, 'transactions/list.html', context)


@require_POST
def transaction_create(request):
    """Lançamento rápido via HTMX — retorna o partial da nova transação."""
    form = TransactionForm(request.POST)
    if form.is_valid():
        transaction = form.save()
        # Retorna o partial para HTMX inserir na lista
        return render(request, 'partials/transaction_row.html', {
            'txn': transaction,
            'is_new': True,
        })
    # Se inválido, retorna o form com erros
    return render(request, 'partials/transaction_form.html', {
        'form': form,
    }, status=400)


@require_POST
def transaction_toggle(request, pk):
    """Alterna status pago/pendente via HTMX."""
    txn = get_object_or_404(Transaction, pk=pk)
    if txn.status == Transaction.Status.PENDING:
        txn.status = Transaction.Status.PAID
    else:
        txn.status = Transaction.Status.PENDING
    txn.save()
    return render(request, 'partials/transaction_row.html', {'txn': txn})


@require_POST
def transaction_delete(request, pk):
    """Remove transação via HTMX."""
    txn = get_object_or_404(Transaction, pk=pk)
    txn.delete()
    return HttpResponse('')


def transaction_edit(request, pk):
    """Edita uma transação via HTMX inline."""
    txn = get_object_or_404(Transaction, pk=pk)

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=txn)
        if form.is_valid():
            txn = form.save()
            return render(request, 'partials/transaction_row.html', {'txn': txn})
        # Form inválido: retorna o form com erros
        return render(request, 'partials/transaction_edit_form.html', {
            'form': form, 'txn': txn,
        }, status=400)

    # GET com ?cancel=1 → cancela e retorna a row original sem salvar
    if request.GET.get('cancel'):
        return render(request, 'partials/transaction_row.html', {'txn': txn})

    # GET sem cancel → retorna o form inline de edição
    if request.headers.get('HX-Request'):
        return render(request, 'partials/transaction_edit_form.html', {
            'form': TransactionForm(instance=txn), 'txn': txn,
        })

    # Fallback página completa (não HTMX)
    form = TransactionForm(instance=txn)
    return render(request, 'transactions/edit.html', {'form': form, 'txn': txn})


# ─── Recurring Rules ────────────────────────────────────────────────────────

def recurring_list(request):
    """Lista de regras recorrentes."""
    rules = RecurringRule.objects.select_related('credit_card').prefetch_related('tags').all()
    form = RecurringRuleForm()
    context = {
        'rules': rules,
        'form': form,
    }
    return render(request, 'recurring/list.html', context)


@require_POST
def recurring_create(request):
    """Cria nova regra recorrente via HTMX."""
    form = RecurringRuleForm(request.POST)
    if form.is_valid():
        rule = form.save(commit=False)
        # Se for parcelado, divide o valor total pelo número de parcelas
        if (rule.recurrence_type == RecurringRule.RecurrenceType.INSTALLMENT
                and rule.total_installments and rule.total_installments > 0):
            rule.amount = (rule.amount / Decimal(rule.total_installments)).quantize(Decimal('0.01'))
        rule.save()
        form.save_m2m()  # Salva tags (ManyToMany)
        # Se for parcelado, gera todas as transações imediatamente
        if rule.recurrence_type == RecurringRule.RecurrenceType.INSTALLMENT:
            rule.generate_installment_transactions()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/recurring_row.html', {
                'rule': rule, 'is_new': True,
            })
        return redirect('recurring_list')
    if request.headers.get('HX-Request'):
        installments_error = form.errors.get('total_installments')
        if installments_error:
            message = f'{installments_error[0]} Solução: informe 2 ou mais parcelas para regras parceladas.'
        else:
            message = 'Não foi possível criar a regra recorrente. Revise os campos e tente novamente.'

        response = HttpResponse('', status=200)
        response['HX-Reswap'] = 'none'
        response['HX-Trigger'] = json.dumps({
            'showToast': {
                'level': 'error',
                'message': message,
            }
        })
        return response

    return redirect('recurring_list')


@require_POST
def recurring_toggle(request, pk):
    """Ativa/desativa regra recorrente."""
    rule = get_object_or_404(RecurringRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save()
    return render(request, 'partials/recurring_row.html', {'rule': rule})


@require_POST
def recurring_delete(request, pk):
    """Remove regra recorrente e suas transações pendentes."""
    rule = get_object_or_404(RecurringRule, pk=pk)
    # Remove apenas transações pendentes (pagas ficam como histórico)
    rule.transactions.filter(status=Transaction.Status.PENDING).delete()
    rule.delete()
    return HttpResponse('')


# ─── Goals ───────────────────────────────────────────────────────────────────

def goal_list(request):
    """Lista de metas financeiras."""
    goals = Goal.objects.all()
    form = GoalForm()
    context = {
        'goals': goals,
        'form': form,
    }
    return render(request, 'goals/list.html', context)


@require_POST
def goal_create(request):
    """Cria meta via HTMX."""
    form = GoalForm(request.POST)
    if form.is_valid():
        goal = form.save()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/goal_card.html', {
                'goal': goal, 'is_new': True,
            })
        return redirect('goal_list')
    return render(request, 'partials/goal_form.html', {
        'form': form,
    }, status=400)


@require_POST
def goal_update(request, pk):
    """Atualiza meta (valor acumulado)."""
    goal = get_object_or_404(Goal, pk=pk)
    form = GoalForm(request.POST, instance=goal)
    if form.is_valid():
        form.save()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/goal_card.html', {'goal': goal})
        return redirect('goal_list')
    return render(request, 'partials/goal_form.html', {'form': form}, status=400)


@require_POST
def goal_delete(request, pk):
    """Remove meta."""
    goal = get_object_or_404(Goal, pk=pk)
    goal.delete()
    return HttpResponse('')


# ─── Credit Cards ────────────────────────────────────────────────────────────

def card_list(request):
    """Lista de cartões cadastrados."""
    cards = CreditCard.objects.all()
    form = CreditCardForm()
    context = {
        'cards': cards,
        'form': form,
    }
    return render(request, 'cards/list.html', context)


@require_POST
def card_create(request):
    """Cadastra cartão via HTMX."""
    form = CreditCardForm(request.POST)
    if form.is_valid():
        card = form.save()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/card_row.html', {
                'card': card, 'is_new': True,
            })
        return redirect('card_list')
    return render(request, 'partials/card_form.html', {'form': form}, status=400)


@require_POST
def card_delete(request, pk):
    """Remove cartão."""
    card = get_object_or_404(CreditCard, pk=pk)
    card.delete()
    return HttpResponse('')


# ─── Settings ────────────────────────────────────────────────────────────────

def settings_view(request):
    """Atualiza saldo atual e data de referência."""
    settings = UserSettings.load()
    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return render(request, 'partials/balance_card.html', {
                    'settings': settings,
                })
            return redirect('dashboard')
    else:
        form = UserSettingsForm(instance=settings)

    context = {
        'form': form,
        'settings': settings,
    }
    return render(request, 'settings/edit.html', context)
