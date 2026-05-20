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
    transactions = Transaction.objects.select_related(
        'recurring_rule', 'credit_card'
    ).prefetch_related('tags').order_by('due_date')

    # Filtros
    status = request.GET.get('status')
    txn_type = request.GET.get('type')
    tag = request.GET.get('tag')
    month_filter = request.GET.get('month')  # Formato: YYYY-MM
    payment_method = request.GET.get('payment_method')
    card_id = request.GET.get('card')

    # Aplicar filtros
    if status:
        transactions = transactions.filter(status=status)
    if txn_type:
        transactions = transactions.filter(type=txn_type)
    if tag:
        transactions = transactions.filter(tags__id=tag)
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            transactions = transactions.filter(due_date__year=year, due_date__month=month)
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

    # Opções para popular os dropdowns de filtro na página inteira e HTMX partial
    from core.models import CreditCard, Tag
    cards = CreditCard.objects.all()

    # Mapear os meses/anos existentes nas transações
    from django.db.models.functions import ExtractMonth, ExtractYear
    months_query = Transaction.objects.annotate(
        year=ExtractYear('due_date'),
        month=ExtractMonth('due_date')
    ).values('year', 'month').distinct().order_by('-year', '-month')

    months_available = []
    MONTH_NAMES = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    for item in months_query:
        y = item['year']
        m = item['month']
        if y and m:
            months_available.append({
                'value': f"{y}-{m:02d}",
                'label': f"{MONTH_NAMES[m]} {y}"
            })

    context = {
        'transactions': transactions,
        'tags': Tag.objects.all(),
        'cards': cards,
        'months_available': months_available,
        'current_status': status,
        'current_type': txn_type,
        'current_tag': tag,
        'current_month': month_filter,
        'current_payment_method': payment_method,
        'current_card': card_id,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_balance': net_balance,
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
    """Edita uma transação."""
    txn = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=txn)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return render(request, 'partials/transaction_row.html', {'txn': txn})
            return redirect('transaction_list')
    else:
        form = TransactionForm(instance=txn)

    if request.headers.get('HX-Request'):
        return render(request, 'partials/transaction_edit_form.html', {
            'form': form, 'txn': txn,
        })
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
        rule = form.save()
        # Se for parcelado, gera todas as transações imediatamente
        if rule.recurrence_type == RecurringRule.RecurrenceType.INSTALLMENT:
            rule.generate_installment_transactions()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/recurring_row.html', {
                'rule': rule, 'is_new': True,
            })
        return redirect('recurring_list')
    return render(request, 'partials/recurring_form.html', {
        'form': form,
    }, status=400)


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
