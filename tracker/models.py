from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=150, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    dark_mode = models.BooleanField(default=True)
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def get_initials(self):
        name = self.full_name or self.user.username
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()


class Income(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='income_record')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    description = models.CharField(max_length=150, default='Total Income')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-updated_at']

    def __str__(self):
        return f"{self.user.username} - income - {self.amount}"


INCOME_CATEGORIES = [
    ('Salary', 'Salary'),
    ('Business', 'Business'),
    ('Freelancing', 'Freelancing'),
    ('Investments', 'Investments'),
    ('Bonus', 'Bonus'),
    ('Other Income', 'Other Income'),
]

EXPENSE_CATEGORIES = [
    ('Food', 'Food'),
    ('Bills', 'Bills'),
    ('Transport', 'Transport'),
    ('Medical', 'Medical'),
    ('Shopping', 'Shopping'),
    ('Education', 'Education'),
    ('Housing', 'Housing'),
    ('Entertainment', 'Entertainment'),
    ('Travel', 'Travel'),
    ('Miscellaneous', 'Miscellaneous'),
]

ALL_CATEGORIES = INCOME_CATEGORIES + EXPENSE_CATEGORIES

TRANSACTION_TYPES = [
    ('income', 'Income'),
    ('expense', 'Expense'),
]


class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    category = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    date = models.DateField()
    time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-time']

    def __str__(self):
        return f"{self.user.username} - {self.type} - {self.amount}"
