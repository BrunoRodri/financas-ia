from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from core.models import Transaction, UserSettings
from core.services.cash_flow import project_cash_flow


class CashFlowProjectionTests(TestCase):
    @patch('core.services.cash_flow.materialize_recurring_transactions')
    @patch('core.services.cash_flow.timezone.localdate')
    def test_cards_totals_use_only_next_six_months(self, mocked_localdate, _mocked_materialize):
        # Base date fixed for deterministic month windows.
        mocked_localdate.return_value = date(2026, 5, 21)
        today = mocked_localdate.return_value

        settings = UserSettings.load()
        settings.current_balance = Decimal('1000.00')
        settings.balance_date = today
        settings.save()

        def create_txn(description, amount, txn_type, due_date):
            Transaction.objects.create(
                description=description,
                amount=Decimal(amount),
                type=txn_type,
                status=Transaction.Status.PENDING,
                due_date=due_date,
            )

        from dateutil.relativedelta import relativedelta

        # Historical months (must be ignored by cards).
        create_txn('Hist income', '900.00', Transaction.TransactionType.INCOME, today.replace(day=1) - relativedelta(months=1))
        create_txn('Hist expense', '400.00', Transaction.TransactionType.EXPENSE, today.replace(day=1) - relativedelta(months=2))

        # Inside cards window: current month + next 5 months (6 months total).
        create_txn('M0 income', '100.00', Transaction.TransactionType.INCOME, today.replace(day=5))
        create_txn('M0 expense', '20.00', Transaction.TransactionType.EXPENSE, today.replace(day=7))
        create_txn('M1 income', '200.00', Transaction.TransactionType.INCOME, today.replace(day=1) + relativedelta(months=1))
        create_txn('M4 expense', '60.00', Transaction.TransactionType.EXPENSE, today.replace(day=1) + relativedelta(months=4))
        create_txn('M5 income', '300.00', Transaction.TransactionType.INCOME, today.replace(day=1) + relativedelta(months=5))

        # Month +6 (must be excluded from cards).
        create_txn('M6 income', '700.00', Transaction.TransactionType.INCOME, today.replace(day=1) + relativedelta(months=6))
        create_txn('M6 expense', '500.00', Transaction.TransactionType.EXPENSE, today.replace(day=1) + relativedelta(months=6))

        projection = project_cash_flow(months_ahead=6)

        self.assertEqual(projection['start_balance'], Decimal('1000.00'))
        self.assertEqual(projection['total_income'], Decimal('500.00'))
        self.assertEqual(projection['total_expense'], Decimal('60.00'))

    @patch('core.services.cash_flow.materialize_recurring_transactions')
    @patch('core.services.cash_flow.timezone.localdate')
    def test_current_balance_uses_history_when_settings_are_default(self, mocked_localdate, _mocked_materialize):
        mocked_localdate.return_value = date(2026, 5, 21)
        today = mocked_localdate.return_value

        settings = UserSettings.load()
        settings.current_balance = Decimal('0.00')
        settings.balance_date = today
        settings.save()

        Transaction.objects.create(
            description='Saida abril',
            amount=Decimal('200.00'),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING,
            due_date=date(2026, 4, 1),
        )
        Transaction.objects.create(
            description='Entrada maio',
            amount=Decimal('100.00'),
            type=Transaction.TransactionType.INCOME,
            status=Transaction.Status.PENDING,
            due_date=date(2026, 5, 19),
        )

        projection = project_cash_flow(months_ahead=6)

        self.assertEqual(projection['current_balance'], Decimal('-100.00'))

    @patch('core.services.cash_flow.materialize_recurring_transactions')
    @patch('core.services.cash_flow.timezone.localdate')
    def test_current_balance_excludes_reference_day_transactions(self, mocked_localdate, _mocked_materialize):
        mocked_localdate.return_value = date(2026, 5, 21)

        settings = UserSettings.load()
        settings.current_balance = Decimal('500.00')
        settings.balance_date = date(2026, 5, 19)
        settings.save()

        # Já refletida no saldo de referência, não deve entrar novamente.
        Transaction.objects.create(
            description='Entrada no dia da referencia',
            amount=Decimal('100.00'),
            type=Transaction.TransactionType.INCOME,
            status=Transaction.Status.PENDING,
            due_date=date(2026, 5, 19),
        )

        projection = project_cash_flow(months_ahead=6)

        self.assertEqual(projection['current_balance'], Decimal('500.00'))

    @patch('core.services.cash_flow.materialize_recurring_transactions')
    @patch('core.services.cash_flow.timezone.localdate')
    def test_monthly_summary_rebuilds_previous_months_from_reference_balance(self, mocked_localdate, _mocked_materialize):
        mocked_localdate.return_value = date(2026, 5, 21)

        settings = UserSettings.load()
        settings.current_balance = Decimal('500.00')
        settings.balance_date = date(2026, 5, 21)
        settings.save()

        Transaction.objects.create(
            description='Saida abril',
            amount=Decimal('700.00'),
            type=Transaction.TransactionType.EXPENSE,
            status=Transaction.Status.PENDING,
            due_date=date(2026, 4, 1),
        )
        Transaction.objects.create(
            description='Entrada maio',
            amount=Decimal('300.00'),
            type=Transaction.TransactionType.INCOME,
            status=Transaction.Status.PENDING,
            due_date=date(2026, 5, 19),
        )

        projection = project_cash_flow(months_ahead=6)
        by_month = {m['month']: m for m in projection['monthly_summary']}

        self.assertEqual(by_month['2026-03']['end_balance'], Decimal('900.00'))
        self.assertEqual(by_month['2026-04']['end_balance'], Decimal('200.00'))
        self.assertEqual(by_month['2026-05']['end_balance'], Decimal('200.00'))


class GoalTransactionTests(TestCase):
    def test_goal_deposit_creates_expense_transaction_when_flag_is_true(self):
        from django.urls import reverse
        from core.models import Goal
        
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        response = self.client.post(
            reverse('goal_update', args=[goal.id]),
            {
                'action_type': 'add',
                'adjust_amount': '500.00',
                'create_transaction': 'true'
            }
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1500.00"))
        
        # Verify transaction was created
        txn = Transaction.objects.latest('created_at')
        self.assertEqual(txn.description, "Aporte: Viagem Rio")
        self.assertEqual(txn.amount, Decimal("500.00"))
        self.assertEqual(txn.type, Transaction.TransactionType.EXPENSE)
        self.assertEqual(txn.status, Transaction.Status.PAID)
        self.assertTrue(txn.tags.filter(name="Metas").exists())

    def test_goal_withdraw_creates_income_transaction_when_flag_is_true(self):
        from django.urls import reverse
        from core.models import Goal
        
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        response = self.client.post(
            reverse('goal_update', args=[goal.id]),
            {
                'action_type': 'subtract',
                'adjust_amount': '300.00',
                'create_transaction': 'true'
            }
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("700.00"))
        
        # Verify transaction was created
        txn = Transaction.objects.latest('created_at')
        self.assertEqual(txn.description, "Resgate: Viagem Rio")
        self.assertEqual(txn.amount, Decimal("300.00"))
        self.assertEqual(txn.type, Transaction.TransactionType.INCOME)
        self.assertEqual(txn.status, Transaction.Status.PAID)
        self.assertTrue(txn.tags.filter(name="Metas").exists())

    def test_goal_deposit_no_transaction_when_flag_is_false(self):
        from django.urls import reverse
        from core.models import Goal
        
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        initial_txn_count = Transaction.objects.count()
        
        response = self.client.post(
            reverse('goal_update', args=[goal.id]),
            {
                'action_type': 'add',
                'adjust_amount': '500.00',
                'create_transaction': 'false'
            }
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1500.00"))
        self.assertEqual(Transaction.objects.count(), initial_txn_count)

