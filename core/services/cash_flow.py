"""
Serviço de projeção de fluxo de caixa.

Calcula o saldo projetado dia a dia e mês a mês para os próximos N meses,
combinando transações existentes com transações geradas por regras recorrentes.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from core.models import RecurringRule, Transaction, UserSettings


def materialize_recurring_transactions(months_ahead=6):
    """
    Materializa transações mensais recorrentes para os próximos N meses.
    Chamado ao acessar o dashboard.
    """
    rules = RecurringRule.objects.filter(
        is_active=True,
        recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
    )
    for rule in rules:
        rule.materialize_monthly_transactions(months_ahead=months_ahead)


def project_cash_flow(months_ahead=6):
    """
    Calcula a projeção de saldo para os próximos N meses.

    Returns:
        dict: {
            'start_balance': Decimal,
            'balance_date': date,
            'daily': [
                {'date': date, 'balance': Decimal, 'transactions': [Transaction, ...]},
                ...
            ],
            'monthly_summary': [
                {
                    'month': 'YYYY-MM',
                    'month_label': 'Jun/2026',
                    'income': Decimal,
                    'expense': Decimal,
                    'net': Decimal,
                    'end_balance': Decimal,
                },
                ...
            ],
            'total_income': Decimal,
            'total_expense': Decimal,
        }
    """
    # 1. Materializa recorrências mensais pendentes
    materialize_recurring_transactions(months_ahead)

    # 2. Carrega configurações
    settings = UserSettings.load()
    start_balance = settings.current_balance
    balance_date = settings.balance_date

    # 3. Define o horizonte de projeção
    today = timezone.localdate()
    end_date = today + relativedelta(months=months_ahead)

    # 4. Define data de início para exibição (2 meses anteriores ao atual) e busca todas as transações no horizonte exibido
    first_day_of_current_month = today.replace(day=1)
    start_display_month = first_day_of_current_month - relativedelta(months=2)
    query_start_date = start_display_month

    transactions_in_horizon = Transaction.objects.filter(
        due_date__gte=query_start_date,
        due_date__lte=end_date,
    ).select_related('recurring_rule', 'credit_card').prefetch_related('tags').order_by('due_date')

    # 5. Agrupa transações por data para a projeção diária (apenas de hoje em diante)
    txn_by_date = defaultdict(list)
    for txn in transactions_in_horizon:
        if txn.due_date >= today:
            txn_by_date[txn.due_date].append(txn)

    # 6. Calcula projeção dia a dia
    daily = []
    running_balance = start_balance
    current_date = today

    # Inclui transações entre balance_date e hoje para o saldo inicial diário
    past_transactions = Transaction.objects.filter(
        due_date__gte=balance_date,
        due_date__lt=today,
    )
    for txn in past_transactions:
        running_balance += txn.signed_amount

    while current_date <= end_date:
        day_txns = txn_by_date.get(current_date, [])
        day_net = sum(txn.signed_amount for txn in day_txns)
        running_balance += day_net

        if day_txns or current_date == today:
            daily.append({
                'date': current_date,
                'balance': running_balance,
                'transactions': day_txns,
                'net': day_net,
            })

        current_date += timedelta(days=1)

    # 7. Agrupa por mês (a partir do início do mês de exibição inicial)
    MONTH_NAMES = {
        1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
    }

    monthly_data = defaultdict(lambda: {
        'income': Decimal('0'),
        'expense': Decimal('0'),
    })

    for txn in transactions_in_horizon:
        month_key = txn.due_date.strftime('%Y-%m')
        if txn.is_income:
            monthly_data[month_key]['income'] += txn.amount
        else:
            monthly_data[month_key]['expense'] += txn.amount

    monthly_summary = []
    month_balance = start_balance

    # Ajusta o saldo inicial mensal com transações anteriores ao primeiro mês exibido
    past_non_displayed_transactions = Transaction.objects.filter(
        due_date__gte=balance_date,
        due_date__lt=query_start_date,
    )
    for txn in past_non_displayed_transactions:
        month_balance += txn.signed_amount

    current_month = start_display_month

    while current_month <= end_date:
        month_key = current_month.strftime('%Y-%m')
        data = monthly_data.get(month_key, {'income': Decimal('0'), 'expense': Decimal('0')})
        net = data['income'] - data['expense']
        month_balance += net

        month_label = f"{MONTH_NAMES[current_month.month]}/{current_month.year}"

        monthly_summary.append({
            'month': month_key,
            'month_label': month_label,
            'income': data['income'],
            'expense': data['expense'],
            'net': net,
            'end_balance': month_balance,
        })

        current_month += relativedelta(months=1)


    total_income = sum(m['income'] for m in monthly_summary if m['month'] >= first_day_of_current_month.strftime('%Y-%m'))
    total_expense = sum(m['expense'] for m in monthly_summary if m['month'] >= first_day_of_current_month.strftime('%Y-%m'))


    return {
        'start_balance': start_balance,
        'balance_date': balance_date,
        'daily': daily,
        'monthly_summary': monthly_summary,
        'total_income': total_income,
        'total_expense': total_expense,
    }


def get_upcoming_transactions(days=30):
    """Retorna as próximas transações dos próximos N dias."""
    today = timezone.localdate()
    end = today + timedelta(days=days)
    return Transaction.objects.filter(
        due_date__gte=today,
        due_date__lte=end,
    ).select_related('recurring_rule', 'credit_card').prefetch_related('tags').order_by('due_date')
