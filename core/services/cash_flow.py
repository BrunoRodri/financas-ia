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
    materialize_recurring_transactions(months_ahead)

    settings = UserSettings.load()
    start_balance = settings.current_balance
    balance_date = settings.balance_date

    today = timezone.localdate()
    end_date = today + relativedelta(months=months_ahead)
    first_day_of_current_month = today.replace(day=1)
    cards_end_month = first_day_of_current_month + relativedelta(months=5)

    # Exibe histórico de 2 meses no resumo/gráfico
    start_display_month = first_day_of_current_month - relativedelta(months=2)
    query_start_date = start_display_month

    transactions_in_horizon = Transaction.objects.filter(
        due_date__gte=query_start_date,
        due_date__lte=end_date,
    ).select_related('recurring_rule', 'credit_card').prefetch_related('tags').order_by('due_date')

    # Projeção diária para hoje em diante
    txn_by_date = defaultdict(list)
    for txn in transactions_in_horizon:
        if txn.due_date >= today:
            txn_by_date[txn.due_date].append(txn)

    daily = []
    running_balance = start_balance
    current_date = today
    current_balance = start_balance

    # Se o usuário ainda não configurou saldo inicial (0 em hoje), considera todo o histórico.
    if start_balance == Decimal('0') and balance_date == today:
        past_transactions = Transaction.objects.filter(
            due_date__lt=today,
        )
    else:
        # Caso contrário, respeita a data de referência definida nas configurações.
        past_transactions = Transaction.objects.filter(
            due_date__gt=balance_date,
            due_date__lt=today,
        )

    for txn in past_transactions:
        running_balance += txn.signed_amount

    while current_date <= end_date:
        day_txns = txn_by_date.get(current_date, [])
        day_net = sum(txn.signed_amount for txn in day_txns)
        running_balance += day_net

        if current_date == today:
            # Saldo atual do card: saldo de referência + movimentos após a referência até hoje.
            current_balance = running_balance

        if day_txns or current_date == today:
            daily.append({
                'date': current_date,
                'balance': running_balance,
                'transactions': day_txns,
                'net': day_net,
            })

        current_date += timedelta(days=1)

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

    # Reconstrói o saldo no início da janela exibida com base na data de referência,
    # para não ancorar o saldo de referência diretamente em meses anteriores.
    # Inicializa o saldo acumulado dependendo se a data de referência está antes ou dentro da janela de exibição
    if balance_date < query_start_date:
        # Se a data de referência é anterior à janela de exibição, retroagimos o saldo inicial até o começo da janela
        month_balance = start_balance
        forward_txns = Transaction.objects.filter(
            due_date__gt=balance_date,
            due_date__lt=query_start_date,
        )
        for txn in forward_txns:
            month_balance += txn.signed_amount
    else:
        # Se a data de referência está dentro da janela, o histórico anterior começa zerado
        month_balance = Decimal('0')

    current_month = start_display_month

    while current_month <= end_date:
        month_key = current_month.strftime('%Y-%m')

        # Se chegamos ao mês da data de referência, redefinimos o saldo acumulado usando o saldo de partida configurado
        if balance_date >= query_start_date:
            if current_month.year == balance_date.year and current_month.month == balance_date.month:
                ref_first_day = balance_date.replace(day=1)
                ref_rollback_txns = Transaction.objects.filter(
                    due_date__gte=ref_first_day,
                    due_date__lte=balance_date,
                )
                ref_start_balance = start_balance
                for txn in ref_rollback_txns:
                    ref_start_balance -= txn.signed_amount
                month_balance = ref_start_balance

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

    cards_start_key = first_day_of_current_month.strftime('%Y-%m')
    cards_end_key = cards_end_month.strftime('%Y-%m')

    total_income = sum(
        m['income']
        for m in monthly_summary
        if cards_start_key <= m['month'] <= cards_end_key
    )
    total_expense = sum(
        m['expense']
        for m in monthly_summary
        if cards_start_key <= m['month'] <= cards_end_key
    )

    return {
        'start_balance': start_balance,
        'current_balance': current_balance,
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
