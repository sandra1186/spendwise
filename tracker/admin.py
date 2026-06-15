from django.contrib import admin
from .models import UserProfile, Income, Transaction


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'created_at']
    search_fields = ['user__username', 'full_name']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'category', 'amount', 'date', 'created_at']
    list_filter = ['type', 'category', 'date']
    search_fields = ['user__username', 'description', 'category']
    date_hierarchy = 'date'


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'date', 'updated_at']
    search_fields = ['user__username', 'description']
