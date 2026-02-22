from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal

class Group(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'name']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name

class Client(models.Model):
    name = models.CharField(max_length=200)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, related_name='clients')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'name']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name

class Loan(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Partial', 'Partial'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='loans')
    loan_date = models.DateField()
    original_due_date = models.DateField()
    current_due_date = models.DateField()
    original_principal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    current_principal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='loans')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'current_due_date']),
        ]
        ordering = ['-loan_date']

    def __str__(self):
        return f"{self.client.name} - {self.loan_date}"

class LoanInterestHistory(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='interest_history')
    due_date = models.DateField()
    interest_amount = models.DecimalField(max_digits=10, decimal_places=2)
    principal_at_time = models.DecimalField(max_digits=10, decimal_places=2)
    added_date = models.DateField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interest_records')

    class Meta:
        indexes = [
            models.Index(fields=['loan', 'is_paid']),
            models.Index(fields=['loan', 'due_date']),
        ]
        ordering = ['due_date']

    def __str__(self):
        return f"Interest for {self.loan} - {self.due_date}"

class Payment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    applied_to_interest = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    applied_to_principal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['loan', 'payment_date']),
        ]
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment {self.amount} for {self.loan}"

class Setting(models.Model):
    key = models.CharField(max_length=100)
    value = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='settings')

    class Meta:
        unique_together = ['key', 'user']
        indexes = [
            models.Index(fields=['user', 'key']),
        ]

    def __str__(self):
        return f"{self.key}: {self.value}"
