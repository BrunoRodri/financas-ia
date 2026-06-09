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
        self.assertEqual(projection['total_income'], Decimal('600.00'))
        self.assertEqual(projection['total_expense'], Decimal('80.00'))

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

        self.assertEqual(by_month['2026-03']['end_balance'], Decimal('0.00'))
        self.assertEqual(by_month['2026-04']['end_balance'], Decimal('-700.00'))
        self.assertEqual(by_month['2026-05']['end_balance'], Decimal('500.00'))


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

    def test_transaction_update_adjusts_goal_current_amount(self):
        from core.models import Goal
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        # An EXPENSE (Aporte) is created linked to goal: increases goal amount
        txn = Transaction.objects.create(
            description="Aporte teste",
            amount=Decimal("200.00"),
            due_date=date(2026, 9, 27),
            type=Transaction.TransactionType.EXPENSE,
            goal=goal
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1200.00"))
        
        # Let's update the transaction amount: increase it to 350.00
        txn.amount = Decimal("350.00")
        txn.save()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1350.00"))
        
        # Let's change it to INCOME (Resgate) with value 100.00
        txn.amount = Decimal("100.00")
        txn.type = Transaction.TransactionType.INCOME
        txn.description = "Resgate teste"
        txn.save()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("900.00")) # 1000 original + 0 expense - 100 income = 900

    def test_transaction_delete_reverts_goal_current_amount(self):
        from core.models import Goal
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        txn = Transaction.objects.create(
            description="Aporte teste",
            amount=Decimal("300.00"),
            due_date=date(2026, 9, 27),
            type=Transaction.TransactionType.EXPENSE,
            goal=goal
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1300.00"))
        
        # Delete transaction
        txn.delete()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1000.00"))

    def test_manual_expense_transaction_subtracts_from_goal(self):
        from core.models import Goal
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        # A manual EXPENSE (Saída) linked to a goal (e.g. description "Compra de passagens")
        # should subtract from the goal amount
        txn = Transaction.objects.create(
            description="Compra de passagens",
            amount=Decimal("300.00"),
            due_date=date(2026, 9, 27),
            type=Transaction.TransactionType.EXPENSE,
            goal=goal
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("700.00"))
        
        # Update amount: change to 400.00
        txn.amount = Decimal("400.00")
        txn.save()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("600.00"))
        
        # Delete transaction
        txn.delete()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1000.00"))

    def test_manual_income_transaction_adds_to_goal(self):
        from core.models import Goal
        goal = Goal.objects.create(
            name="Viagem Rio",
            target_amount=Decimal("7000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 9, 27)
        )
        
        # A manual INCOME (Entrada) linked to a goal (e.g. description "Presente de aniversario")
        # should add to the goal amount
        txn = Transaction.objects.create(
            description="Presente de aniversario",
            amount=Decimal("200.00"),
            due_date=date(2026, 9, 27),
            type=Transaction.TransactionType.INCOME,
            goal=goal
        )
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1200.00"))
        
        # Update amount: change to 300.00
        txn.amount = Decimal("300.00")
        txn.save()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1300.00"))
        
        # Delete transaction
        txn.delete()
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("1000.00"))

    def test_recurring_rule_with_goal_propagates_goal_to_transactions(self):
        from core.models import Goal, RecurringRule
        goal = Goal.objects.create(
            name="Equipamentos",
            target_amount=Decimal("5000.00"),
            current_amount=Decimal("3000.00"),
            deadline=date(2026, 12, 31)
        )
        
        # Create an INSTALLMENT expense rule linked to the goal
        rule = RecurringRule.objects.create(
            description="Notebook",
            amount=Decimal("200.00"),
            type=Transaction.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.INSTALLMENT,
            total_installments=5,
            start_date=date(2026, 6, 8),
            goal=goal
        )
        
        # Generate the transactions
        txns = rule.generate_installment_transactions()
        self.assertEqual(len(txns), 5)
        
        # Check that all transactions are linked to the goal
        for txn in txns:
            self.assertEqual(txn.goal, goal)
            self.assertEqual(txn.recurring_rule, rule)
            
        # Check that the goal current_amount was correctly updated.
        # Since description is "Notebook (1/5)" etc, it does not start with "Aporte".
        # Therefore, these are treated as manual expenses and should SUBTRACT from the goal.
        # Original current_amount: 3000.00. 5 installments of 200.00 total 1000.00.
        # 3000.00 - 1000.00 = 2000.00.
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("2000.00"))

        # Test deletion via the view to make sure goal balance is reverted
        from django.urls import reverse
        response = self.client.post(reverse('recurring_delete', args=[rule.id]) + '?delete_all=true')
        self.assertEqual(response.status_code, 200)
        
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("3000.00"))

    def test_transaction_delete_confirm_view_returns_correct_template_and_context(self):
        from django.urls import reverse
        txn = Transaction.objects.create(
            description="Lanche",
            amount=Decimal("25.50"),
            due_date=date(2026, 9, 27),
            type=Transaction.TransactionType.EXPENSE
        )
        
        response = self.client.get(reverse('transaction_delete_confirm', args=[txn.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'partials/transaction_delete_modal.html')
        self.assertEqual(response.context['txn'], txn)

    def test_goal_form_supports_both_date_formats(self):
        from core.forms import GoalForm
        
        # Test YYYY-MM-DD
        form1 = GoalForm(data={
            'name': 'Viagem',
            'target_amount': '5000.00',
            'current_amount': '1000.00',
            'deadline': '2026-10-31',
            'color': '#ff0000'
        })
        self.assertTrue(form1.is_valid())
        
        # Test DD/MM/YYYY
        form2 = GoalForm(data={
            'name': 'Viagem',
            'target_amount': '5000.00',
            'current_amount': '1000.00',
            'deadline': '31/10/2026',
            'color': '#ff0000'
        })
        self.assertTrue(form2.is_valid())

    def test_user_settings_form_supports_both_date_formats(self):
        from core.forms import UserSettingsForm
        
        # Test YYYY-MM-DD
        form1 = UserSettingsForm(data={
            'current_balance': '12500.50',
            'balance_date': '2026-05-29'
        })
        self.assertTrue(form1.is_valid())
        
        # Test DD/MM/YYYY
        form2 = UserSettingsForm(data={
            'current_balance': '12500.50',
            'balance_date': '29/05/2026'
        })
        self.assertTrue(form2.is_valid())

    def test_goal_archive_and_restore(self):
        from django.urls import reverse
        from core.models import Goal
        
        goal = Goal.objects.create(
            name="Test Goal",
            target_amount=Decimal("1000.00"),
            deadline=date(2026, 12, 31)
        )
        self.assertFalse(goal.is_archived)
        
        # Toggle archive
        response = self.client.post(reverse('goal_toggle_archive', args=[goal.id]))
        self.assertEqual(response.status_code, 302) # Redirect to goal_list
        goal.refresh_from_db()
        self.assertTrue(goal.is_archived)
        
        # Toggle archive via HTMX
        response = self.client.post(
            reverse('goal_toggle_archive', args=[goal.id]),
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200) # Returns template partial
        goal.refresh_from_db()
        self.assertFalse(goal.is_archived)

    def test_recurring_rule_archive_and_restore(self):
        from django.urls import reverse
        from core.models import RecurringRule
        
        rule = RecurringRule.objects.create(
            description="Test Rule",
            amount=Decimal("50.00"),
            type=Transaction.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=date(2026, 6, 8)
        )
        self.assertFalse(rule.is_archived)
        
        # Toggle archive
        response = self.client.post(reverse('recurring_toggle_archive', args=[rule.id]))
        self.assertEqual(response.status_code, 302) # Redirect to recurring_list
        rule.refresh_from_db()
        self.assertTrue(rule.is_archived)
        
        # Verify that archived monthly rules do not materialize new transactions
        created_txns = rule.materialize_monthly_transactions(months_ahead=6)
        self.assertEqual(len(created_txns), 0)

    def test_auto_archive_expired_rules(self):
        from core.models import RecurringRule
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta
        
        today = timezone.localdate()
        
        # Expired installment rule: end_date is start_date + 4 months.
        # If start_date is 5 months ago, it is expired.
        expired_rule = RecurringRule.objects.create(
            description="Expired Installment",
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.INSTALLMENT,
            total_installments=5,
            start_date=today - relativedelta(months=6)
        )
        
        # Non-expired installment rule: start_date is today, so it ends 4 months in the future.
        active_rule = RecurringRule.objects.create(
            description="Active Installment",
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.INSTALLMENT,
            total_installments=5,
            start_date=today
        )
        
        # Non-installment rule (e.g. MONTHLY) should not be auto-archived even if start_date is in past
        monthly_rule = RecurringRule.objects.create(
            description="Monthly Rule",
            amount=Decimal("100.00"),
            type=Transaction.TransactionType.EXPENSE,
            recurrence_type=RecurringRule.RecurrenceType.MONTHLY,
            start_date=today - relativedelta(months=6)
        )
        
        self.assertFalse(expired_rule.is_archived)
        self.assertFalse(active_rule.is_archived)
        self.assertFalse(monthly_rule.is_archived)
        
        # Run auto-archiving
        RecurringRule.auto_archive_expired_rules()
        
        expired_rule.refresh_from_db()
        active_rule.refresh_from_db()
        monthly_rule.refresh_from_db()
        
        self.assertTrue(expired_rule.is_archived)
        self.assertFalse(active_rule.is_archived)
        self.assertFalse(monthly_rule.is_archived)


class TransactionUpdateTriggerTests(TestCase):
    def setUp(self):
        from core.models import Goal
        self.txn = Transaction.objects.create(
            description="Test Transaction",
            amount=Decimal("100.00"),
            due_date=date(2026, 6, 9),
            type=Transaction.TransactionType.EXPENSE
        )
        self.goal = Goal.objects.create(
            name="Test Goal",
            target_amount=Decimal("5000.00"),
            deadline=date(2026, 12, 31)
        )

    def test_transaction_create_triggers_event(self):
        from django.urls import reverse
        response = self.client.post(
            reverse('transaction_create'),
            {
                'description': 'New Transaction',
                'amount': '50.00',
                'type': 'EXPENSE',
                'due_date': '2026-06-09',
                'status': 'PENDING',
                'payment_type': 'other',
            },
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Trigger'), 'transactionUpdated')

    def test_transaction_toggle_triggers_event(self):
        from django.urls import reverse
        response = self.client.post(
            reverse('transaction_toggle', args=[self.txn.id]),
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Trigger'), 'transactionUpdated')

    def test_transaction_delete_triggers_event(self):
        from django.urls import reverse
        response = self.client.post(
            reverse('transaction_delete', args=[self.txn.id]),
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Trigger'), 'transactionUpdated')

    def test_transaction_edit_triggers_event(self):
        from django.urls import reverse
        response = self.client.post(
            reverse('transaction_edit', args=[self.txn.id]),
            {
                'description': 'Updated Transaction',
                'amount': '150.00',
                'type': 'EXPENSE',
                'due_date': '2026-06-09',
                'status': 'PAID',
                'payment_type': 'other',
            },
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Trigger'), 'transactionUpdated')

    def test_goal_update_triggers_event(self):
        from django.urls import reverse
        response = self.client.post(
            reverse('goal_update', args=[self.goal.id]),
            {
                'action_type': 'add',
                'adjust_amount': '500.00',
                'create_transaction': 'false',
            },
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Trigger'), 'transactionUpdated')






