import json
import datetime
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import (
    CreditCardForm,
    GoalForm,
    RecurringRuleEditForm,
    RecurringRuleForm,
    TransactionForm,
    UserSettingsForm,
)
from core.models import CreditCard, Goal, RecurringRule, Tag, Transaction, UserSettings
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
    RecurringRule.auto_archive_expired_rules()
    projection = project_cash_flow(request.user, months_ahead=6)
    upcoming = get_upcoming_transactions(request.user, days=30)
    goals = Goal.objects.filter(user=request.user, is_archived=False)
    settings = UserSettings.load(request.user)
    today = timezone.localdate()

    # Widget de faturas dos cartões
    cards_with_bills = []
    for c in CreditCard.objects.filter(user=request.user):
        # A fatura em aberto "agora" é a que contém a data de hoje. Se ainda não
        # chegou no dia de fechamento deste mês, o período em aberto começou no
        # mês anterior.
        actual_closing_day = min(c.closing_day, calendar.monthrange(today.year, today.month)[1])
        if today.day >= actual_closing_day:
            ref_month, ref_year = today.month, today.year
        else:
            ref_month = today.month - 1 if today.month > 1 else 12
            ref_year = today.year if today.month > 1 else today.year - 1
        start, end = get_bill_period(c, ref_year, ref_month)
        txns = Transaction.objects.filter(
            user=request.user, credit_card=c,
            due_date__range=(start, end),
        ).exclude(funded_by_goal=True)
        bill_total = sum(t.amount for t in txns if t.is_expense) - sum(t.amount for t in txns if t.is_income)
        if c.due_day < c.closing_day:
            due_month = end.month + 1 if end.month < 12 else 1
            due_year = end.year if end.month < 12 else end.year + 1
        else:
            due_month, due_year = end.month, end.year
        due_date = datetime.date(due_year, due_month, min(c.due_day, calendar.monthrange(due_year, due_month)[1]))
        cards_with_bills.append({'card': c, 'total': bill_total, 'due_date': due_date})

    # Dados para o gráfico (Chart.js)
    chart_labels = [m['month_label'] for m in projection['monthly_summary']]
    chart_balances = [float(m['end_balance']) for m in projection['monthly_summary']]
    chart_income = [float(m['income']) for m in projection['monthly_summary']]
    chart_expense = [float(m['expense']) for m in projection['monthly_summary']]

    # Form de lançamento rápido
    form = TransactionForm(user=request.user)

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
        'today': today,
        'cards_with_bills': cards_with_bills,
    }
    return render(request, 'dashboard.html', context)


# ─── Transactions ────────────────────────────────────────────────────────────

import calendar

def get_bill_period(card, year, month):
    """
    Retorna o período de compras (start_date, end_date) iniciado no mês de referência (M/Y).
    O período inicia no dia do fechamento do mês de referência (M/Y) e vai até o dia
    anterior ao fechamento do mês seguinte (M+1).
    Isso alinha as compras feitas a partir do dia de fechamento com o mês selecionado.
    """
    closing_day = card.closing_day

    # Data de início: fechamento no mês selecionado (M/Y)
    _, last_day_current = calendar.monthrange(year, month)
    actual_closing_day_current = min(closing_day, last_day_current)
    start_date = datetime.date(year, month, actual_closing_day_current)

    # Data de término: um dia antes do fechamento do mês seguinte (M+1)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    _, last_day_next = calendar.monthrange(next_year, next_month)
    actual_closing_day_next = min(closing_day, last_day_next)
    closing_date_next = datetime.date(next_year, next_month, actual_closing_day_next)
    end_date = closing_date_next - datetime.timedelta(days=1)

    return start_date, end_date

def transaction_list(request):
    """Lista completa de transações com filtros."""
    from core.services.cash_flow import materialize_recurring_transactions
    materialize_recurring_transactions(request.user, months_ahead=6)

    transactions = Transaction.objects.filter(
        user=request.user,
    ).select_related(
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
    view_by_bill = request.GET.get('view_by_bill') == 'true'

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

    applied_bill_filter = False
    if view_by_bill and card_id:
        try:
            card = CreditCard.objects.get(id=card_id, user=request.user)
            target_year = int(year_filter) if year_filter else timezone.localdate().year
            target_month = int(month_filter) if month_filter else timezone.localdate().month
            start_date, end_date = get_bill_period(card, target_year, target_month)
            transactions = transactions.filter(due_date__range=(start_date, end_date))
            applied_bill_filter = True
        except (ValueError, CreditCard.DoesNotExist):
            pass

    if not applied_bill_filter:
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

    user_settings = UserSettings.load(request.user)

    # Calcular somatórios pós-saldo (apenas transações com due_date >= balance_date e não financiadas por meta)
    total_income = sum(t.amount for t in transactions if t.is_income and t.due_date >= user_settings.balance_date and not t.funded_by_goal)
    total_expense = sum(t.amount for t in transactions if t.is_expense and t.due_date >= user_settings.balance_date and not t.funded_by_goal)

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

    # Saldo líquido inclui o saldo de partida (se estiver ativo/exibido nos filtros atuais)
    net_balance = total_income - total_expense
    if show_initial_balance:
        net_balance += user_settings.current_balance

    transactions_list = list(transactions)
    for t in transactions_list:
        t.is_before_initial_balance = t.due_date < user_settings.balance_date

    if show_initial_balance:
        virtual_bal = VirtualInitialBalance(user_settings.current_balance, user_settings.balance_date)
        transactions_list.append(virtual_bal)
        # Ordenação estável: no mesmo dia, o saldo inicial aparece primeiro
        transactions_list.sort(key=lambda t: (t.due_date, 0 if getattr(t, 'is_initial_balance', False) else 1))

    cards = CreditCard.objects.filter(user=request.user)

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
    years_query = Transaction.objects.filter(user=request.user).annotate(
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
        'tags': Tag.objects.filter(user=request.user),
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
        'view_by_bill': view_by_bill,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_balance': net_balance,
        'has_advanced': has_advanced,
        'user_settings': user_settings,
    }

    # Retorna o fragmento HTML se for uma requisição HTMX
    if request.headers.get('HX-Request'):
        return render(request, 'partials/transactions_full_content.html', context)

    return render(request, 'transactions/list.html', context)


@require_POST
def transaction_create(request):
    """Lançamento rápido via HTMX — retorna o partial da nova transação."""
    form = TransactionForm(request.POST, user=request.user)
    if form.is_valid():
        transaction = form.save(commit=False)
        transaction.user = request.user
        transaction.save()
        form.save_m2m()
        user_settings = UserSettings.load(request.user)
        transaction.is_before_initial_balance = transaction.due_date < user_settings.balance_date
        # Retorna o partial para HTMX inserir na lista
        response = render(request, 'partials/transaction_row.html', {
            'txn': transaction,
            'is_new': True,
            'user_settings': user_settings,
        })
        response['HX-Trigger'] = 'transactionUpdated'
        return response
    # Se inválido, retorna o form com erros
    return render(request, 'partials/transaction_form.html', {
        'form': form,
    }, status=400)


@require_POST
def transaction_toggle(request, pk):
    """Alterna status pago/pendente via HTMX."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    if txn.status == Transaction.Status.PENDING:
        txn.status = Transaction.Status.PAID
    else:
        txn.status = Transaction.Status.PENDING
    txn.save()
    user_settings = UserSettings.load(request.user)
    txn.is_before_initial_balance = txn.due_date < user_settings.balance_date
    response = render(request, 'partials/transaction_row.html', {
        'txn': txn,
        'user_settings': user_settings,
    })
    response['HX-Trigger'] = 'transactionUpdated'
    return response


@require_POST
def transaction_delete(request, pk):
    """Remove transação via HTMX."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    txn.delete()
    response = HttpResponse('')
    response['HX-Trigger'] = 'transactionUpdated'
    return response


def transaction_delete_confirm(request, pk):
    """Renderiza o modal de confirmação de exclusão para uma transação."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    return render(request, 'partials/transaction_delete_modal.html', {'txn': txn})


def transaction_edit(request, pk):
    """Edita uma transação via HTMX inline."""
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    goals = Goal.objects.filter(user=request.user).filter(Q(is_archived=False) | Q(pk=txn.goal_id))

    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=txn, user=request.user)
        if form.is_valid():
            txn = form.save()
            user_settings = UserSettings.load(request.user)
            txn.is_before_initial_balance = txn.due_date < user_settings.balance_date
            response = render(request, 'partials/transaction_row.html', {
                'txn': txn,
                'user_settings': user_settings,
            })
            response['HX-Trigger'] = 'transactionUpdated'
            return response
        # Form inválido: retorna o form com erros
        return render(request, 'partials/transaction_edit_form.html', {
            'form': form, 'txn': txn, 'goals': goals,
        }, status=400)

    # GET com ?cancel=1 → cancela e retorna a row original sem salvar
    if request.GET.get('cancel'):
        return render(request, 'partials/transaction_row.html', {'txn': txn})

    # GET sem cancel → retorna o form inline de edição
    if request.headers.get('HX-Request'):
        return render(request, 'partials/transaction_edit_form.html', {
            'form': TransactionForm(instance=txn, user=request.user), 'txn': txn, 'goals': goals,
        })

    # Fallback página completa (não HTMX)
    form = TransactionForm(instance=txn, user=request.user)
    return render(request, 'transactions/edit.html', {'form': form, 'txn': txn, 'goals': goals})


# ─── Recurring Rules ────────────────────────────────────────────────────────

def recurring_list(request):
    """Lista de regras recorrentes."""
    RecurringRule.auto_archive_expired_rules()
    rules = RecurringRule.objects.filter(user=request.user).select_related('credit_card').prefetch_related('tags')
    form = RecurringRuleForm(user=request.user)
    context = {
        'rules': rules,
        'active_rules_count': rules.filter(is_archived=False).count(),
        'archived_rules_count': rules.filter(is_archived=True).count(),
        'form': form,
    }
    return render(request, 'recurring/list.html', context)


@require_POST
def recurring_create(request):
    """Cria nova regra recorrente via HTMX."""
    form = RecurringRuleForm(request.POST, user=request.user)
    if form.is_valid():
        rule = form.save(commit=False)
        rule.user = request.user
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
    rule = get_object_or_404(RecurringRule, pk=pk, user=request.user)
    rule.is_active = not rule.is_active
    rule.save()

    if rule.recurrence_type == RecurringRule.RecurrenceType.MONTHLY:
        today = timezone.localdate()
        if not rule.is_active:
            for txn in list(rule.transactions.filter(
                status=Transaction.Status.PENDING,
                due_date__gte=today,
            )):
                txn.delete()
        else:
            rule.materialize_monthly_transactions(months_ahead=6)

    return render(request, 'partials/recurring_row.html', {'rule': rule})


@require_POST
def recurring_delete(request, pk):
    """Remove regra recorrente baseando-se nas preferências do usuário."""
    rule = get_object_or_404(RecurringRule, pk=pk, user=request.user)
    delete_all = request.GET.get('delete_all') == 'true'

    if delete_all:
        # Exclui absolutamente tudo (inclusive transações pagas)
        for txn in list(rule.transactions.all()):
            txn.delete()
    else:
        # Desvincula transações pagas para que não sejam apagadas pelo CASCADE
        rule.transactions.filter(status=Transaction.Status.PAID).update(recurring_rule=None)
        # Exclui as transações pendentes
        for txn in list(rule.transactions.filter(status=Transaction.Status.PENDING)):
            txn.delete()

    rule.delete()
    return HttpResponse('')


def recurring_delete_confirm(request, pk):
    """Renderiza o modal de confirmação de exclusão para a regra recorrente."""
    rule = get_object_or_404(RecurringRule, pk=pk, user=request.user)
    paid_count = rule.transactions.filter(status=Transaction.Status.PAID).count()
    total_count = rule.transactions.count()

    context = {
        'rule': rule,
        'paid_count': paid_count,
        'total_count': total_count,
    }
    return render(request, 'partials/recurring_delete_modal.html', context)


def recurring_edit(request, pk):
    """Edita campos de uma regra recorrente e propaga alterações para as transações."""
    rule = get_object_or_404(RecurringRule, pk=pk, user=request.user)

    if request.method == 'GET':
        form = RecurringRuleEditForm(instance=rule, user=request.user)
        return render(request, 'partials/recurring_edit_modal.html', {'form': form, 'rule': rule})

    scope = request.POST.get('scope')
    form = RecurringRuleEditForm(request.POST, instance=rule, user=request.user)

    if not form.is_valid():
        return render(request, 'partials/recurring_edit_modal.html',
                      {'form': form, 'rule': rule}, status=422)

    paid_count = rule.transactions.filter(status=Transaction.Status.PAID).count()

    if paid_count > 0 and not scope:
        form_pairs = [(k, v) for k in request.POST for v in request.POST.getlist(k)]
        return render(request, 'partials/recurring_edit_confirm_modal.html', {
            'rule': rule,
            'paid_count': paid_count,
            'form_pairs': form_pairs,
        })

    form.save()

    transactions_qs = (
        rule.transactions.all() if scope == 'all'
        else rule.transactions.filter(status=Transaction.Status.PENDING)
    )
    _apply_recurring_rule_changes(rule, transactions_qs)

    response = render(request, 'partials/recurring_row.html', {'rule': rule})
    response['HX-Retarget'] = f'#rule-{rule.pk}'
    response['HX-Reswap'] = 'outerHTML'
    return response


def _apply_recurring_rule_changes(rule, transactions_qs):
    per_amount = (
        rule.amount if rule.recurrence_type == RecurringRule.RecurrenceType.MONTHLY
        else rule.amount / Decimal(rule.total_installments)
    )
    for tx in transactions_qs:
        tx.description = rule.description
        tx.amount = per_amount
        tx.type = rule.type
        tx.credit_card = rule.credit_card
        tx.goal = rule.goal
        tx.save()
        tx.tags.set(rule.tags.all())


# ─── Goals ───────────────────────────────────────────────────────────────────

def goal_list(request):
    """Lista de metas financeiras."""
    goals = Goal.objects.filter(user=request.user)
    form = GoalForm()
    context = {
        'goals': goals,
        'active_goals_count': goals.filter(is_archived=False).count(),
        'archived_goals_count': goals.filter(is_archived=True).count(),
        'form': form,
    }
    return render(request, 'goals/list.html', context)


@require_POST
def goal_create(request):
    """Cria meta via HTMX."""
    form = GoalForm(request.POST)
    if form.is_valid():
        goal = form.save(commit=False)
        goal.user = request.user
        goal.save()
        form.save_m2m()
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
    goal = get_object_or_404(Goal, pk=pk, user=request.user)

    # Suporte a ajuste rápido inline (aporte/resgate/utilizar)
    action_type = request.POST.get('action_type')
    adjust_amount = request.POST.get('adjust_amount')
    create_transaction = request.POST.get('create_transaction') == 'true'
    description = request.POST.get('description', '').strip()

    if action_type and adjust_amount:
        try:
            amount = Decimal(adjust_amount)
            if action_type == 'add':
                if create_transaction:
                    tag, _ = Tag.objects.get_or_create(
                        name="Metas",
                        user=request.user,
                        defaults={"color": "#8b5cf6"}
                    )
                    txn = Transaction.objects.create(
                        user=request.user,
                        description=f"Aporte: {goal.name}",
                        amount=amount,
                        due_date=timezone.localdate(),
                        type=Transaction.TransactionType.EXPENSE,
                        status=Transaction.Status.PAID,
                        goal=goal
                    )
                    txn.tags.add(tag)
                    goal.refresh_from_db()
                else:
                    goal.current_amount += amount
                    goal.save()
            elif action_type == 'subtract':
                # Só gera transação sobre o valor real resgatado (limitado ao atual acumulado da meta)
                actual_subtracted = min(amount, goal.current_amount)
                if create_transaction:
                    if actual_subtracted > 0:
                        tag, _ = Tag.objects.get_or_create(
                            name="Metas",
                            user=request.user,
                            defaults={"color": "#8b5cf6"}
                        )
                        txn = Transaction.objects.create(
                            user=request.user,
                            description=f"Resgate: {goal.name}",
                            amount=actual_subtracted,
                            due_date=timezone.localdate(),
                            type=Transaction.TransactionType.INCOME,
                            status=Transaction.Status.PAID,
                            goal=goal
                        )
                        txn.tags.add(tag)
                        goal.refresh_from_db()
                else:
                    goal.current_amount = max(goal.current_amount - amount, Decimal('0.00'))
                    goal.save()
            elif action_type == 'use':
                # Utilizar: gasto financiado pelo dinheiro já guardado na meta
                available = goal.available_amount
                actual_used = min(amount, available)
                if actual_used > 0:
                    tag, _ = Tag.objects.get_or_create(
                        name="Metas",
                        user=request.user,
                        defaults={"color": "#8b5cf6"}
                    )
                    txn_desc = description or f"Gasto: {goal.name}"
                    txn = Transaction.objects.create(
                        user=request.user,
                        description=txn_desc,
                        amount=actual_used,
                        due_date=timezone.localdate(),
                        type=Transaction.TransactionType.EXPENSE,
                        status=Transaction.Status.PAID,
                        goal=goal,
                        funded_by_goal=True,
                    )
                    txn.tags.add(tag)
                    goal.refresh_from_db()

            if request.headers.get('HX-Request'):
                response = render(request, 'partials/goal_card.html', {'goal': goal})
                response['HX-Trigger'] = 'transactionUpdated'
                return response
            return redirect('goal_list')
        except (ValueError, ArithmeticError):
            pass

    # Caso contrário, fluxo padrão de form de edição
    form = GoalForm(request.POST, instance=goal)
    if form.is_valid():
        form.save()
        if request.headers.get('HX-Request'):
            response = render(request, 'partials/goal_card.html', {'goal': goal})
            response['HX-Trigger'] = 'transactionUpdated'
            return response
        return redirect('goal_list')
    return render(request, 'partials/goal_form.html', {'form': form}, status=400)


def goal_edit(request, pk):
    """Renderiza o formulário inline de aporte/resgate de uma meta via HTMX."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    action_type = request.GET.get('type', 'add')
    context = {
        'goal': goal,
        'action_type': action_type,
    }
    return render(request, 'partials/goal_card_adjust_form.html', context)


def goal_detail(request, pk):
    """Renderiza o card de meta em estado normal via HTMX (cancelamento/fallback)."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    return render(request, 'partials/goal_card.html', {'goal': goal})


def goal_delete_confirm(request, pk):
    """Renderiza o modal de confirmação para exclusão de metas."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    return render(request, 'partials/goal_delete_modal.html', {'goal': goal})


@require_POST
def goal_delete(request, pk):
    """Remove meta."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.delete()
    return HttpResponse('')


# ─── Credit Cards ────────────────────────────────────────────────────────────

def card_list(request):
    """Lista de cartões cadastrados."""
    cards = CreditCard.objects.filter(user=request.user)
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
        card = form.save(commit=False)
        card.user = request.user
        card.save()
        if request.headers.get('HX-Request'):
            return render(request, 'partials/card_row.html', {
                'card': card, 'is_new': True,
            })
        return redirect('card_list')
    return render(request, 'partials/card_form.html', {'form': form}, status=400)


@require_POST
def card_delete(request, pk):
    """Remove cartão."""
    card = get_object_or_404(CreditCard, pk=pk, user=request.user)
    card.delete()
    return HttpResponse('')


def card_edit(request, pk):
    """Edita um cartão de crédito via HTMX inline."""
    card = get_object_or_404(CreditCard, pk=pk, user=request.user)

    if request.method == 'POST':
        form = CreditCardForm(request.POST, instance=card)
        if form.is_valid():
            card = form.save()
            return render(request, 'partials/card_row.html', {'card': card})
        # Retorna o formulário com erros de validação
        return render(request, 'partials/card_edit_form.html', {
            'form': form, 'card': card,
        }, status=400)

    # GET com ?cancel=1 → cancela e retorna o item original
    if request.GET.get('cancel'):
        return render(request, 'partials/card_row.html', {'card': card})

    # GET comum via HTMX → renderiza o formulário de edição
    if request.headers.get('HX-Request'):
        return render(request, 'partials/card_edit_form.html', {
            'form': CreditCardForm(instance=card), 'card': card,
        })

    # Redirecionamento fallback caso acessado diretamente via URL convencional
    return redirect('card_list')


_MONTH_NAMES = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
}


def _build_bill(user, card, year, month):
    """Computa um único dict de fatura para o mês/ano de referência."""
    today = timezone.localdate()
    start, end = get_bill_period(card, year, month)
    txns = list(
        Transaction.objects.filter(
            user=user, credit_card=card,
            due_date__range=(start, end),
        ).exclude(funded_by_goal=True).order_by('due_date')
    )
    bill_total = sum(t.amount for t in txns if t.is_expense) - sum(t.amount for t in txns if t.is_income)
    if card.due_day < card.closing_day:
        due_month = end.month + 1 if end.month < 12 else 1
        due_year = end.year if end.month < 12 else end.year + 1
    else:
        due_month, due_year = end.month, end.year
    due_date = datetime.date(due_year, due_month,
                             min(card.due_day, calendar.monthrange(due_year, due_month)[1]))
    return {
        'month_label': f"{_MONTH_NAMES[due_month]}/{due_year}",
        'ref_month': month,
        'ref_year': year,
        'start_date': start,
        'end_date': end,
        'due_date': due_date,
        'transactions': txns,
        'total': bill_total,
        'is_current': start <= today <= end,
        'is_past': end < today,
        'all_paid': all(t.status == 'PAID' for t in txns) if txns else False,
    }


def card_bill_list(request, pk):
    """Visão geral das faturas de um cartão (mês anterior + atual + 4 futuros)."""
    card = get_object_or_404(CreditCard, pk=pk, user=request.user)
    today = timezone.localdate()
    bills = []
    for delta in range(-1, 5):
        ref = today.month + delta
        ref_year = today.year + (ref - 1) // 12
        ref_month = ((ref - 1) % 12) + 1
        bills.append(_build_bill(request.user, card, ref_year, ref_month))
    all_cards = CreditCard.objects.filter(user=request.user)
    return render(request, 'cards/bills.html', {'card': card, 'bills': bills, 'all_cards': all_cards})


def analytics_view(request):
    """Análise de despesas agrupadas por tag para o mês selecionado."""
    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    transactions = list(
        Transaction.objects.filter(
            user=request.user, type='EXPENSE',
            due_date__month=month, due_date__year=year,
            funded_by_goal=False,
        ).prefetch_related('tags')
    )

    tag_map = {}
    untagged = Decimal('0')
    for txn in transactions:
        txn_tags = list(txn.tags.all())
        if txn_tags:
            for tag in txn_tags:
                if tag.id not in tag_map:
                    tag_map[tag.id] = {'name': tag.name, 'color': tag.color, 'total': Decimal('0')}
                tag_map[tag.id]['total'] += txn.amount
        else:
            untagged += txn.amount

    tag_items = sorted(tag_map.values(), key=lambda x: x['total'], reverse=True)
    if untagged > 0:
        tag_items.append({'name': 'Sem categoria', 'color': '#6b7280', 'total': untagged})

    grand_total = sum(i['total'] for i in tag_items)
    for item in tag_items:
        item['pct'] = round(float(item['total'] / grand_total * 100), 1) if grand_total else 0

    years_available = sorted(
        {d.year for d in Transaction.objects.filter(user=request.user).dates('due_date', 'year')} | {today.year},
        reverse=True,
    )
    months_available = [{'value': i, 'label': _MONTH_NAMES[i]} for i in range(1, 13)]

    return render(request, 'analytics/by_tag.html', {
        'tag_items': tag_items,
        'grand_total': grand_total,
        'chart_labels': [i['name'] for i in tag_items],
        'chart_values': [float(i['total']) for i in tag_items],
        'chart_colors': [i['color'] for i in tag_items],
        'current_month': month,
        'current_year': year,
        'months_available': months_available,
        'years_available': years_available,
    })


@require_POST
def card_bill_pay(request, pk, year, month):
    """Marca todas as transações pendentes da fatura como pagas."""
    card = get_object_or_404(CreditCard, pk=pk, user=request.user)
    start, end = get_bill_period(card, year, month)
    Transaction.objects.filter(
        user=request.user, credit_card=card,
        due_date__range=(start, end), status='PENDING',
    ).exclude(funded_by_goal=True).update(status='PAID')
    bill = _build_bill(request.user, card, year, month)
    return render(request, 'partials/bill_card.html', {'card': card, 'bill': bill})


@require_POST
def card_bill_unpay(request, pk, year, month):
    """Desfaz o pagamento da fatura, revertendo transações para pendente."""
    card = get_object_or_404(CreditCard, pk=pk, user=request.user)
    start, end = get_bill_period(card, year, month)
    Transaction.objects.filter(
        user=request.user, credit_card=card,
        due_date__range=(start, end), status='PAID',
    ).exclude(funded_by_goal=True).update(status='PENDING')
    bill = _build_bill(request.user, card, year, month)
    return render(request, 'partials/bill_card.html', {'card': card, 'bill': bill})


# ─── Settings ────────────────────────────────────────────────────────────────

def settings_view(request):
    """Atualiza saldo atual, data de referência e exibe painel de tags."""
    settings = UserSettings.load(request.user)
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
        'tags': Tag.objects.filter(user=request.user),
    }
    return render(request, 'settings/edit.html', context)


@require_POST
def tag_create(request):
    """Cria uma nova tag via HTMX e retorna a listagem atualizada."""
    name = request.POST.get('name', '').strip()
    color = request.POST.get('color', '#6366f1').strip()

    if name:
        Tag.objects.get_or_create(name=name, user=request.user, defaults={'color': color})

    tags = Tag.objects.filter(user=request.user)
    return render(request, 'partials/tag_list.html', {'tags': tags})


@require_POST
def tag_delete(request, pk):
    """Exclui uma tag via HTMX."""
    tag = get_object_or_404(Tag, pk=pk, user=request.user)
    tag.delete()
    return HttpResponse('')


@require_POST
def goal_toggle_archive(request, pk):
    """Alterna o status arquivado de uma meta."""
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    goal.is_archived = not goal.is_archived
    goal.save()

    if request.headers.get('HX-Request'):
        return render(request, 'partials/goal_card.html', {'goal': goal})
    return redirect('goal_list')


@require_POST
def recurring_toggle_archive(request, pk):
    """Alterna o status arquivado de uma regra recorrente."""
    rule = get_object_or_404(RecurringRule, pk=pk, user=request.user)
    rule.is_archived = not rule.is_archived
    if rule.is_archived:
        rule.is_active = False
    else:
        rule.is_active = True
    rule.save()

    if rule.recurrence_type == RecurringRule.RecurrenceType.MONTHLY:
        today = timezone.localdate()
        if rule.is_archived:
            for txn in list(rule.transactions.filter(
                status=Transaction.Status.PENDING,
                due_date__gte=today,
            )):
                txn.delete()
        else:
            rule.materialize_monthly_transactions(months_ahead=6)

    if request.headers.get('HX-Request'):
        return render(request, 'partials/recurring_row.html', {'rule': rule})
    return redirect('recurring_list')
