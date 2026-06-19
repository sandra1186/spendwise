from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.http import JsonResponse, HttpResponse
from django.db import DatabaseError, transaction
from django.db.models import Sum, Q
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from decimal import Decimal
import json
import csv
import datetime
import logging

from .models import UserProfile, Income, Transaction, EXPENSE_CATEGORIES
from .forms import RegisterForm, TransactionForm, TotalIncomeForm, ProfileForm, ChangePasswordForm

logger = logging.getLogger(__name__)


def google_login_status(request):
    try:
        from allauth.socialaccount.models import SocialApp

        site = get_current_site(request)
        app = SocialApp.objects.filter(provider='google', sites=site).first()
    except Exception:
        logger.exception('Failed to inspect Google social login configuration')
        return {
            'ready': False,
            'message': 'Google sign-in is not configured for this site.',
        }

    if not app:
        return {
            'ready': False,
            'message': 'Google sign-in is not configured for this site.',
        }
    if not app.client_id or not app.secret or len(app.secret.strip()) < 20:
        return {
            'ready': False,
            'message': 'Google sign-in needs a valid OAuth client ID and client secret.',
        }
    return {'ready': True, 'message': ''}


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to SpendWise, {user.username}!')
            return redirect('dashboard')
    return render(request, 'auth/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            remember = request.POST.get('remember_me')
            if not remember:
                request.session.set_expiry(0)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            error = 'Invalid username or password.'
    return render(
        request,
        'auth/login.html',
        {
            'error': error,
            'google_login': google_login_status(request),
            'debug': settings.DEBUG,
        },
    )


def logout_view(request):
    logout(request)
    return redirect('login')


def get_finance_summary(user, incomes=None, expenses=None):
    if incomes is None:
        incomes = Income.objects.filter(user=user)
    if expenses is None:
        expenses = Transaction.objects.filter(user=user, type='expense')
    total_income = incomes.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_expense = expenses.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    net = total_income - total_expense
    return {
        'total_income': float(total_income),
        'total_expense': float(total_expense),
        'net_income': float(net),
    }


def month_start_offset(date, months):
    month_index = date.year * 12 + date.month - 1 + months
    year, month_index = divmod(month_index, 12)
    return datetime.date(year, month_index + 1, 1)


@login_required
def dashboard(request):
    all_expenses = Transaction.objects.filter(user=request.user, type='expense')
    transactions = all_expenses

    # Filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    categories = request.GET.getlist('categories')
    search = request.GET.get('search', '')

    if date_from:
        transactions = transactions.filter(date__gte=date_from)
    if date_to:
        transactions = transactions.filter(date__lte=date_to)
    if categories:
        transactions = transactions.filter(category__in=categories)
    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) | Q(category__icontains=search)
        )

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    summary = get_finance_summary(request.user, expenses=all_expenses)
    all_categories = [c[0] for c in EXPENSE_CATEGORIES]

    context = {
        'transactions': transactions[:50],
        'summary': summary,
        'profile': profile,
        'expense_categories': [c[0] for c in EXPENSE_CATEGORIES],
        'all_categories': all_categories,
        'filters': {
            'date_from': date_from,
            'date_to': date_to,
            'categories': categories,
            'search': search,
        }
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
@require_POST
def add_transaction(request):
    form = TransactionForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                tx = form.save(commit=False)
                tx.user = request.user
                tx.type = 'expense'
                tx.save()
        except DatabaseError:
            logger.exception('Failed to save transaction for user %s', request.user.pk)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse(
                    {'success': False, 'message': 'The transaction could not be saved. Please try again.'},
                    status=500,
                )
            messages.error(request, 'The transaction could not be saved. Please try again.')
            return redirect('dashboard')

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            expenses = Transaction.objects.filter(user=request.user, type='expense')
            return JsonResponse({
                'success': True,
                'message': 'Expense added!',
                'transaction_id': tx.pk,
                'redirect_url': reverse('dashboard'),
                'summary': get_finance_summary(request.user, expenses=expenses),
            })
        messages.success(request, 'Expense added successfully!')
        return redirect('dashboard')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'success': False,
                'message': 'Please correct the highlighted transaction details.',
                'errors': form.errors.get_json_data(),
            },
            status=400,
        )

    for field_errors in form.errors.values():
        for error in field_errors:
            messages.error(request, error)
    return redirect('dashboard')


@login_required
@require_POST
def update_total_income(request):
    form = TotalIncomeForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {
                'success': False,
                'message': 'Enter a valid income amount.',
                'errors': form.errors.get_json_data(),
            },
            status=400,
        )

    try:
        with transaction.atomic():
            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
            profile.total_income = form.cleaned_data['total_income']
            profile.save(update_fields=['total_income'])
            income, _ = Income.objects.select_for_update().get_or_create(
                user=request.user,
                defaults={
                    'amount': form.cleaned_data['total_income'],
                    'date': timezone.localdate(),
                },
            )
            income.amount = form.cleaned_data['total_income']
            income.date = timezone.localdate()
            income.save(update_fields=['amount', 'date', 'updated_at'])
    except DatabaseError:
        logger.exception('Failed to update total income for user %s', request.user.pk)
        return JsonResponse(
            {'success': False, 'message': 'Total income could not be saved. Please try again.'},
            status=500,
        )

    expenses = Transaction.objects.filter(user=request.user, type='expense')
    return JsonResponse({
        'success': True,
        'message': 'Total income updated!',
        'summary': get_finance_summary(request.user, expenses=expenses),
    })


@login_required
def edit_transaction(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, user=request.user, type='expense')
    if request.method == 'POST':
        form = TransactionForm(request.POST, instance=tx)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.type = 'expense'
            expense.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, 'Transaction updated!')
            return redirect('dashboard')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors})
    else:
        data = {
            'id': tx.pk,
            'type': tx.type,
            'category': tx.category,
            'amount': str(tx.amount),
            'date': str(tx.date),
            'time': str(tx.time),
            'description': tx.description,
        }
        return JsonResponse(data)


@login_required
def delete_transaction(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, user=request.user, type='expense')
    if request.method == 'POST':
        tx.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        messages.success(request, 'Transaction deleted.')
        return redirect('dashboard')
    return JsonResponse({'error': 'POST required'}, status=400)


@login_required
def charts_view(request):
    all_incomes = Income.objects.filter(user=request.user)
    all_expenses = Transaction.objects.filter(user=request.user, type='expense')
    incomes = all_incomes
    expenses = all_expenses

    # Same filters as dashboard
    tx_type = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if date_from:
        incomes = incomes.filter(date__gte=date_from)
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        incomes = incomes.filter(date__lte=date_to)
        expenses = expenses.filter(date__lte=date_to)
    if tx_type == 'income':
        expenses = expenses.none()
    elif tx_type == 'expense':
        incomes = incomes.none()

    # Income is stored as the user's canonical total rather than categorized transactions.
    filtered_income = incomes.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    income_by_cat = {'Income': float(filtered_income)} if filtered_income else {}

    # Expense by category
    expense_by_cat = {}
    for cat, _ in EXPENSE_CATEGORIES:
        val = expenses.filter(category=cat).aggregate(s=Sum('amount'))['s']
        if val:
            expense_by_cat[cat] = float(val)

    # Monthly trends (last 12 months)
    today = datetime.date.today()
    months = []
    monthly_income = []
    monthly_expense = []
    for i in range(11, -1, -1):
        month = month_start_offset(today, -i)
        label = month.strftime('%b %Y')
        months.append(label)
        inc = incomes.filter(date__year=month.year, date__month=month.month).aggregate(s=Sum('amount'))['s'] or 0
        exp = expenses.filter(date__year=month.year, date__month=month.month).aggregate(s=Sum('amount'))['s'] or 0
        monthly_income.append(float(inc))
        monthly_expense.append(float(exp))

    summary = get_finance_summary(request.user, all_incomes, all_expenses)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    context = {
        'profile': profile,
        'summary': summary,
        'income_by_cat': json.dumps(income_by_cat),
        'expense_by_cat': json.dumps(expense_by_cat),
        'months': json.dumps(months),
        'monthly_income': json.dumps(monthly_income),
        'monthly_expense': json.dumps(monthly_expense),
        'filters': {'type': tx_type, 'date_from': date_from, 'date_to': date_to},
    }
    return render(request, 'tracker/charts.html', context)


@login_required
def history_view(request):
    expenses = Transaction.objects.filter(user=request.user, type='expense')
    incomes = Income.objects.filter(user=request.user)
    today = datetime.date.today()
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    # Weekly: last 8 weeks
    weeks = []
    for i in range(7, -1, -1):
        week_end = today - datetime.timedelta(weeks=i)
        week_start = week_end - datetime.timedelta(days=6)
        label = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
        inc = float(incomes.filter(date__gte=week_start, date__lte=week_end).aggregate(s=Sum('amount'))['s'] or 0)
        exp = float(expenses.filter(date__gte=week_start, date__lte=week_end).aggregate(s=Sum('amount'))['s'] or 0)
        weeks.append({'label': label, 'income': inc, 'expense': exp, 'savings': inc - exp})

    # Monthly: last 12 months
    months = []
    for i in range(11, -1, -1):
        month = month_start_offset(today, -i)
        label = month.strftime('%B %Y')
        inc = float(incomes.filter(date__year=month.year, date__month=month.month).aggregate(s=Sum('amount'))['s'] or 0)
        exp = float(expenses.filter(date__year=month.year, date__month=month.month).aggregate(s=Sum('amount'))['s'] or 0)
        months.append({'label': label, 'income': inc, 'expense': exp, 'savings': inc - exp})

    # Yearly: last 5 years
    years = []
    for i in range(4, -1, -1):
        year = today.year - i
        inc = float(incomes.filter(date__year=year).aggregate(s=Sum('amount'))['s'] or 0)
        exp = float(expenses.filter(date__year=year).aggregate(s=Sum('amount'))['s'] or 0)
        years.append({'label': str(year), 'income': inc, 'expense': exp, 'savings': inc - exp})

    records = [
        {
            'date': income.date,
            'time': income.updated_at.time(),
            'type': 'income',
            'type_label': 'Income',
            'category': 'Income',
            'amount': income.amount,
            'description': income.description,
        }
        for income in incomes
    ]
    records.extend({
        'date': expense.date,
        'time': expense.time,
        'type': 'expense',
        'type_label': 'Expense',
        'category': expense.category,
        'amount': expense.amount,
        'description': expense.description,
    } for expense in expenses)
    records.sort(key=lambda record: (record['date'], record['time']), reverse=True)

    context = {
        'profile': profile,
        'weeks': weeks,
        'months': months,
        'years': years,
        'records': records,
    }
    return render(request, 'tracker/history.html', context)


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    password_form = ChangePasswordForm()
    profile_form = ProfileForm(instance=profile)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            profile_form = ProfileForm(request.POST, request.FILES, instance=profile)
            if profile_form.is_valid():
                profile_form.save()
                request.user.email = request.POST.get('email', request.user.email)
                request.user.save()
                messages.success(request, 'Profile updated successfully!')
                return redirect('profile')
        elif action == 'change_password':
            password_form = ChangePasswordForm(request.POST)
            if password_form.is_valid():
                data = password_form.cleaned_data
                if not request.user.check_password(data['old_password']):
                    messages.error(request, 'Current password is incorrect.')
                elif data['new_password'] != data['confirm_password']:
                    messages.error(request, 'New passwords do not match.')
                else:
                    request.user.set_password(data['new_password'])
                    request.user.save()
                    messages.success(request, 'Password changed successfully! Please log in again.')
                    return redirect('login')

    context = {'profile': profile, 'profile_form': profile_form, 'password_form': password_form}
    return render(request, 'tracker/profile.html', context)


@login_required
def export_csv(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date', '-time')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="spendwise_transactions.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Time', 'Type', 'Category', 'Amount', 'Description'])
    for tx in transactions:
        writer.writerow([tx.date, tx.time, tx.type, tx.category, tx.amount, tx.description])
    return response


@login_required
def api_summary(request):
    incomes = Income.objects.filter(user=request.user)
    expenses = Transaction.objects.filter(user=request.user, type='expense')
    tx_type = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        incomes = incomes.filter(date__gte=date_from)
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        incomes = incomes.filter(date__lte=date_to)
        expenses = expenses.filter(date__lte=date_to)
    if tx_type == 'income':
        expenses = expenses.none()
    elif tx_type == 'expense':
        incomes = incomes.none()
    return JsonResponse(get_finance_summary(request.user, incomes, expenses))
