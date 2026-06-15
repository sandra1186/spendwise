from decimal import Decimal
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Income, Transaction, UserProfile


class DashboardFinanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sandra', password='test-password')
        self.other_user = User.objects.create_user(username='other', password='test-password')
        self.profile = UserProfile.objects.create(user=self.user, total_income=Decimal('50000.00'))
        Income.objects.create(
            user=self.user,
            amount=Decimal('50000.00'),
            date='2026-06-15',
        )
        self.client.force_login(self.user)

    def expense_data(self, **overrides):
        data = {
            'type': 'expense',
            'amount': '15000.00',
            'date': '2026-06-15',
            'time': '12:30',
            'category': 'Food',
            'description': 'Monthly expenses',
        }
        data.update(overrides)
        return data

    def add_expense(self, **overrides):
        return self.client.post(
            reverse('add_transaction'),
            self.expense_data(**overrides),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_total_income_can_be_saved_and_persists_after_refresh(self):
        response = self.client.post(
            reverse('update_total_income'),
            {'total_income': '60000.00'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_income, Decimal('60000.00'))
        self.assertEqual(Income.objects.get(user=self.user).amount, Decimal('60000.00'))

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['summary']['total_income'], 60000.0)
        self.assertEqual(dashboard.context['summary']['net_income'], 60000.0)

        history = self.client.get(reverse('history'))
        self.assertEqual(history.context['weeks'][-1]['income'], 60000.0)
        self.assertEqual(history.context['months'][-1]['income'], 60000.0)
        self.assertEqual(history.context['years'][-1]['income'], 60000.0)
        self.assertContains(history, '60000.00')

    def test_dashboard_calculates_expenses_and_balance(self):
        response = self.add_expense()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['total_income'], 50000.0)
        self.assertEqual(response.json()['summary']['total_expense'], 15000.0)
        self.assertEqual(response.json()['summary']['net_income'], 35000.0)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, 'Monthly expenses')
        self.assertEqual(dashboard.context['summary']['total_expense'], 15000.0)
        self.assertEqual(dashboard.context['summary']['net_income'], 35000.0)

    def test_charts_and_summary_api_use_dashboard_records(self):
        Transaction.objects.create(
            user=self.user,
            type='income',
            amount=Decimal('25000.00'),
            date='2026-06-15',
            time='10:00',
            category='Salary',
            description='Legacy income transaction',
        )
        self.add_expense()

        dashboard = self.client.get(reverse('dashboard'))
        charts = self.client.get(reverse('charts'))
        api = self.client.get(reverse('api_summary'))

        expected = {
            'total_income': 50000.0,
            'total_expense': 15000.0,
            'net_income': 35000.0,
        }
        self.assertEqual(dashboard.context['summary'], expected)
        self.assertEqual(charts.context['summary'], expected)
        self.assertEqual(api.json(), expected)
        self.assertEqual(json.loads(charts.context['monthly_income'])[-1], 50000.0)
        self.assertContains(charts, '"Income": 50000.0')

    def test_charts_refresh_after_income_and_expense_changes(self):
        self.add_expense()
        expense = Transaction.objects.get(user=self.user, type='expense')

        self.client.post(
            reverse('update_total_income'),
            {'total_income': '60000.00'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.client.post(
            reverse('edit_transaction', args=[expense.pk]),
            self.expense_data(amount='10000.00'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        charts = self.client.get(reverse('charts'))
        history = self.client.get(reverse('history'))
        self.assertEqual(charts.context['summary']['total_income'], 60000.0)
        self.assertEqual(charts.context['summary']['total_expense'], 10000.0)
        self.assertEqual(charts.context['summary']['net_income'], 50000.0)
        self.assertEqual(history.context['months'][-1]['income'], 60000.0)
        self.assertEqual(history.context['months'][-1]['expense'], 10000.0)

        self.client.post(
            reverse('delete_transaction', args=[expense.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        charts = self.client.get(reverse('charts'))
        self.assertEqual(charts.context['summary']['total_expense'], 0.0)
        self.assertEqual(charts.context['summary']['net_income'], 60000.0)

    def test_forged_income_submission_is_saved_as_expense(self):
        response = self.add_expense(type='income')

        self.assertEqual(response.status_code, 200)
        transaction = Transaction.objects.get(user=self.user)
        self.assertEqual(transaction.type, 'expense')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_income, Decimal('50000.00'))

    def test_only_expenses_appear_in_dashboard_transaction_list(self):
        Transaction.objects.create(
            user=self.user,
            type='income',
            amount=Decimal('25000.00'),
            date='2026-06-15',
            time='10:00',
            category='Salary',
            description='Historical salary',
        )
        self.add_expense()

        dashboard = self.client.get(reverse('dashboard'))

        self.assertNotContains(dashboard, 'Historical salary')
        self.assertContains(dashboard, 'Monthly expenses')
        self.assertEqual(len(dashboard.context['transactions']), 1)
        self.assertEqual(dashboard.context['transactions'][0].type, 'expense')
        self.assertEqual(dashboard.context['summary']['total_income'], 50000.0)

    def test_history_lists_income_and_expense_records(self):
        self.add_expense()

        history = self.client.get(reverse('history'))
        records = history.context['records']

        self.assertEqual({record['type'] for record in records}, {'income', 'expense'})
        self.assertContains(history, 'Income')
        self.assertContains(history, 'Expense')
        self.assertContains(history, 'Monthly expenses')

    def test_expense_edit_and_delete_refresh_totals(self):
        self.add_expense()
        expense = Transaction.objects.get(user=self.user, type='expense')

        edit_response = self.client.post(
            reverse('edit_transaction', args=[expense.pk]),
            self.expense_data(amount='10000.00', description='Updated expense'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(edit_response.status_code, 200)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['summary']['total_expense'], 10000.0)
        self.assertEqual(dashboard.context['summary']['net_income'], 40000.0)

        delete_response = self.client.post(
            reverse('delete_transaction', args=[expense.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(delete_response.status_code, 200)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['summary']['total_expense'], 0.0)
        self.assertEqual(dashboard.context['summary']['net_income'], 50000.0)

    def test_invalid_income_and_expense_values_are_rejected(self):
        income_response = self.client.post(
            reverse('update_total_income'),
            {'total_income': '-1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        expense_response = self.add_expense(amount='0')

        self.assertEqual(income_response.status_code, 400)
        self.assertEqual(expense_response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_income, Decimal('50000.00'))
        self.assertEqual(Income.objects.get(user=self.user).amount, Decimal('50000.00'))
        self.assertFalse(Transaction.objects.exists())

    def test_users_only_see_their_own_expenses(self):
        UserProfile.objects.create(user=self.other_user, total_income=Decimal('99999.00'))
        Income.objects.create(
            user=self.other_user,
            amount=Decimal('99999.00'),
            date='2026-06-15',
        )
        Transaction.objects.create(
            user=self.other_user,
            type='expense',
            amount=Decimal('99.00'),
            date='2026-06-15',
            time='10:00',
            category='Bills',
            description='Private expense',
        )

        dashboard = self.client.get(reverse('dashboard'))

        self.assertNotContains(dashboard, 'Private expense')
        self.assertEqual(dashboard.context['summary']['total_income'], 50000.0)
        self.assertEqual(dashboard.context['summary']['total_expense'], 0.0)
