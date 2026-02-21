from django.contrib import admin
from .models import Group, Client, Loan, LoanInterestHistory, Payment, Setting

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'user', 'created_at']
    list_filter = ['user']
    search_fields = ['name']

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'user', 'created_at']
    list_filter = ['group', 'user']
    search_fields = ['name']

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'loan_date', 'current_principal', 'status', 'user']
    list_filter = ['status', 'user']
    search_fields = ['client__name']

@admin.register(LoanInterestHistory)
class LoanInterestHistoryAdmin(admin.ModelAdmin):
    list_display = ['loan', 'due_date', 'interest_amount', 'is_paid']
    list_filter = ['is_paid', 'user']

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['loan', 'amount', 'payment_date', 'user']
    list_filter = ['user']
    date_hierarchy = 'payment_date'

@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'user']
    list_filter = ['user']
