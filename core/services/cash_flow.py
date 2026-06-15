"""
Serviço de projeção de fluxo de caixa.

Calcula o saldo projetado dia a dia e mês a mês para os próximos N meses,
combinando transações existentes com transações geradas por regras recorrentes.
"""

import calendar as _calendar
from collections import defaultdict
from datetime import date as _date
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from core.models import CreditCard, RecurringRule, Transaction, UserSettings


_BILL_MONTH_NAMES = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
}


def get_bill_period(card, year, month):
    """
    Retorna (start_date, end_date) do período de compras iniciado no mês de referência.
    Inicia no dia de fechamento de M/Y e termina no dia anterior ao fechamento de M+1.
    """
    closing_day = card.closing_day

    _, last_day_cur = _calendar.monthrange(year, month)
    start_date = _date(year, month, min(closing_day, last_day_cur))

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    _, last_day_next = _calendar.monthrange(next_year, next_month)
    closing_next = _date(next_year, next_month, min(closing_day, last_day_next))
    end_date = closing_next - timedelta(days=1)

    return start_date, end_date


def _bill_due_date(card, end_date):
    if card.due_day < card.closing_day:
        due_m = end_date.month + 1 if end_date.month < 12 else 1
        due_y = end_date.year if end_date.month < 12 else end_date.year + 1
    else:
        due_m, due_y = end_date.month, end_date.year
    _, last = _calendar.monthrange(due_y, due_m)
    return _date(due_y, due_m, min(card.due_day, last))


def materialize_card_bills(user, months_ahead=6):
    """
    Cria/atualiza transações de fatura (is_card_bill=True) para cada cartão,
    cobrindo os próximos N meses. Transações já pagas não são alteradas.
    """
    today = timezone.localdate()

    for card in CreditCard.objects.filter(user=user):
        for delta in range(months_ahead + 1):
            ref = today.month + delta
            ref_year = today.year + (ref - 1) // 12
            ref_month = ((ref - 1) % 12) + 1

            start, end = get_bill_period(card, ref_year, ref_month)

            period_txns = Transaction.objects.filter(
                user=user, credit_card=card,
                due_date__range=(start, end),
            ).exclude(funded_by_goal=True).exclude(is_card_bill=True)

            bill_total = (
                sum(t.amount for t in period_txns if t.is_expense)
                - sum(t.amount for t in period_txns if t.is_income)
            )

            due_date = _bill_due_date(card, end)

            bill_txn = Transaction.objects.filter(
                user=user, is_card_bill=True,
                bill_card=card, bill_year=ref_year, bill_month=ref_month,
            ).first()

            if bill_txn is None:
                if bill_total > 0:
                    Transaction.objects.create(
                        user=user,
                        description=f"Fatura {card.name} — {_BILL_MONTH_NAMES[due_date.month]}/{due_date.year}",
                        amount=bill_total,
                        due_date=due_date,
                        type=Transaction.TransactionType.EXPENSE,
                        status=Transaction.Status.PENDING,
                        is_card_bill=True,
                        bill_card=card,
                        bill_year=ref_year,
                        bill_month=ref_month,
                    )
            elif bill_txn.status == Transaction.Status.PENDING:
                if bill_total > 0:
                    Transaction.objects.filter(pk=bill_txn.pk).update(
                        amount=bill_total,
                        due_date=due_date,
                    )
                else:
                    bill_txn.delete()


def materialize_recurring_transactions(user, months_ahead=6):
    """
    Materializa transações mensais recorrentes para os próximos N meses.
    Chamado ao acessar o dashboard.
    """
    rules = RecurringRule.objects.filter(
        user=user,
        is_active=True,
        recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
    )
    for rule in rules:
        rule.materialize_monthly_transactions(months_ahead=months_ahead)


def project_cash_flow(user, months_ahead=6):
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
    materialize_recurring_transactions(user, months_ahead)
    materialize_card_bills(user, months_ahead)

    settings = UserSettings.load(user)
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
        user=user,
        due_date__gte=query_start_date,
        due_date__lte=end_date,
    ).exclude(
        funded_by_goal=True
    ).exclude(
        credit_card__isnull=False, is_card_bill=False,
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

    # Apenas transações PAGAS entram no saldo atual e na base da projeção.
    if start_balance == Decimal('0') and balance_date == today:
        past_transactions = Transaction.objects.filter(
            user=user,
            due_date__lt=today,
            status='PAID',
        ).exclude(funded_by_goal=True).exclude(credit_card__isnull=False, is_card_bill=False)
    else:
        past_transactions = Transaction.objects.filter(
            user=user,
            due_date__gt=balance_date,
            due_date__lt=today,
            status='PAID',
        ).exclude(funded_by_goal=True).exclude(credit_card__isnull=False, is_card_bill=False)

    for txn in past_transactions:
        running_balance += txn.signed_amount

    while current_date <= end_date:
        day_txns = txn_by_date.get(current_date, [])
        day_net = sum(txn.signed_amount for txn in day_txns)
        running_balance += day_net

        if current_date == today:
            # Saldo atual do card: apenas transações PAGAS até hoje (inclusive).
            # Transações PENDING de hoje ficam na projeção mas não no saldo atual.
            today_paid_net = sum(t.signed_amount for t in day_txns if t.status == 'PAID')
            current_balance = running_balance - day_net + today_paid_net

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
            user=user,
            due_date__gt=balance_date,
            due_date__lt=query_start_date,
        ).exclude(funded_by_goal=True).exclude(credit_card__isnull=False, is_card_bill=False)
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
                    user=user,
                    due_date__gte=ref_first_day,
                    due_date__lte=balance_date,
                ).exclude(funded_by_goal=True).exclude(credit_card__isnull=False, is_card_bill=False)
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


def get_upcoming_transactions(user, days=30):
    """Retorna as próximas transações dos próximos N dias."""
    today = timezone.localdate()
    end = today + timedelta(days=days)
    return Transaction.objects.filter(
        user=user,
        due_date__gte=today,
        due_date__lte=end,
    ).select_related('recurring_rule', 'credit_card').prefetch_related('tags').order_by('due_date')


def get_month_data(user, month, year, projection=None):
    """
    Retorna dados agregados de um mês específico para o dashboard mensal.

    Args:
        projection: resultado de project_cash_flow() já calculado (evita chamada dupla).
                    Se None, calcula internamente.
    """
    if projection is None:
        projection = project_cash_flow(user)

    # Todas as transações do mês para exibição (inclui compras individuais de cartão)
    all_transactions = list(
        Transaction.objects.filter(
            user=user,
            due_date__month=month,
            due_date__year=year,
            funded_by_goal=False,
        ).select_related('recurring_rule', 'credit_card').prefetch_related('tags').order_by('due_date')
    )

    # Apenas transações que afetam o fluxo de caixa (exclui compras individuais de cartão)
    flow_transactions = [
        t for t in all_transactions
        if not (t.credit_card_id is not None and not t.is_card_bill)
    ]

    income = sum(t.amount for t in flow_transactions if t.is_income)
    expense = sum(t.amount for t in flow_transactions if t.is_expense)
    net = income - expense

    paid_income = sum(t.amount for t in flow_transactions if t.is_income and t.status == 'PAID')
    paid_expense = sum(t.amount for t in flow_transactions if t.is_expense and t.status == 'PAID')
    pending_income = income - paid_income
    pending_expense = expense - paid_expense

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    prev_txns = list(
        Transaction.objects.filter(
            user=user,
            due_date__month=prev_m,
            due_date__year=prev_y,
            funded_by_goal=False,
        ).exclude(credit_card__isnull=False, is_card_bill=False)
    )
    prev_income = sum(t.amount for t in prev_txns if t.is_income)
    prev_expense = sum(t.amount for t in prev_txns if t.is_expense)

    def _delta_pct(current, prev):
        if not prev:
            return None
        return round(float((current - prev) / prev * 100), 1)

    month_key = f"{year}-{month:02d}"
    prev_month_key = f"{prev_y}-{prev_m:02d}"

    settings = UserSettings.load(user)
    balance_date = settings.balance_date
    balance_month_key = f"{balance_date.year}-{balance_date.month:02d}"

    if month_key == balance_month_key:
        # O mês selecionado é o mesmo do saldo de referência.
        # project_cash_flow reseta o saldo neste mês usando rollback a partir do
        # start_balance — replicamos a mesma lógica para obter o saldo do dia 1.
        ref_first_day = balance_date.replace(day=1)
        ref_rollback_txns = Transaction.objects.filter(
            user=user,
            due_date__gte=ref_first_day,
            due_date__lte=balance_date,
        ).exclude(funded_by_goal=True).exclude(credit_card__isnull=False, is_card_bill=False)
        month_start_balance = settings.current_balance
        for txn in ref_rollback_txns:
            month_start_balance -= txn.signed_amount
    else:
        # Saldo inicial do mês = end_balance do mês anterior no monthly_summary.
        # Percorre o summary em ordem para pegar o mês imediatamente anterior caso
        # o mês exato não esteja na janela calculada.
        month_start_balance = projection['start_balance']
        last_before = None
        for m_s in projection['monthly_summary']:
            if m_s['month'] == prev_month_key:
                month_start_balance = m_s['end_balance']
                last_before = None
                break
            if m_s['month'] < month_key:
                last_before = m_s['end_balance']
        if last_before is not None:
            month_start_balance = last_before

    # Reconstrói o saldo dia a dia usando apenas transações de fluxo de caixa.
    txns_by_date = defaultdict(list)
    for txn in flow_transactions:
        txns_by_date[txn.due_date].append(txn)

    _, days_in_month = _calendar.monthrange(year, month)
    running = month_start_balance
    daily_balances = []
    for day in range(1, days_in_month + 1):
        d = _date(year, month, day)
        day_txns = txns_by_date.get(d, [])
        day_net = sum(t.signed_amount for t in day_txns)
        running += day_net
        daily_balances.append({'date': d, 'balance': running, 'transactions': day_txns})

    end_balance = daily_balances[-1]['balance'] if daily_balances else month_start_balance
    # Confirma com o monthly_summary se disponível (fonte mais precisa)
    for m_s in projection['monthly_summary']:
        if m_s['month'] == month_key:
            end_balance = m_s['end_balance']
            break

    return {
        'income': income,
        'expense': expense,
        'net': net,
        'paid_income': paid_income,
        'paid_expense': paid_expense,
        'pending_income': pending_income,
        'pending_expense': pending_expense,
        'prev_income': prev_income,
        'prev_expense': prev_expense,
        'income_delta_pct': _delta_pct(income, prev_income),
        'expense_delta_pct': _delta_pct(expense, prev_expense),
        'transactions': all_transactions,
        'daily_balances': daily_balances,
        'end_balance': end_balance,
    }
