from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum, Q, F, OuterRef, Subquery
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
from decimal import Decimal
import io
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from .models import Group, Client, Loan, LoanInterestHistory, Payment, Setting

# Constants
INTEREST_RATE = Decimal('0.40')

# ---------- HELPER FUNCTIONS ----------

def calculate_interest(principal):
    """Calculate 40% interest on principal"""
    return round(principal * INTEREST_RATE, 2)

def get_next_due_date(current_due_date):
    """Get the next due date (one month later)"""
    if not current_due_date:
        return None
    return current_due_date + relativedelta(months=1)

def calculate_total_owed(loan):
    """Calculate total amount owed for a loan (principal + unpaid interest)"""
    unpaid_interest = LoanInterestHistory.objects.filter(
        loan=loan, is_paid=False
    ).aggregate(total=Sum('interest_amount'))['total'] or Decimal('0')
    
    total_owed = loan.current_principal + unpaid_interest
    return total_owed, loan.current_principal, unpaid_interest

def get_setting(request, key, default=None):
    """Get a setting for the current user"""
    try:
        setting = Setting.objects.get(key=key, user=request.user)
        return setting.value
    except Setting.DoesNotExist:
        return default

def set_setting(request, key, value):
    """Set a setting for the current user"""
    setting, created = Setting.objects.update_or_create(
        key=key, user=request.user,
        defaults={'value': value}
    )
    return setting

def status_color_html(status):
    """Returns colored status HTML"""
    colors = {
        'Paid': 'green',
        'Partial': 'orange',
        'Overdue': 'red',
        'Active': 'blue'
    }
    emoji = {
        'Paid': '🟢',
        'Partial': '🟡',
        'Overdue': '🔴',
        'Active': '🔵'
    }
    color = colors.get(status, 'black')
    return f'<span style="color: {color}; font-weight: bold;">{emoji.get(status, "")} {status}</span>'

def format_money(amount):
    """Format money values"""
    if amount is None:
        return "R 0.00"
    return f"R {amount:.2f}"

def colored_money_html(label, value):
    """Apply color rules to money"""
    value = float(value)
    if label == "paid" and value > 0:
        return f'<span style="color: green; font-weight: bold;">R {value:.2f}</span>'
    elif label == "balance" and value > 0:
        return f'<span style="color: red; font-weight: bold;">R {value:.2f}</span>'
    else:
        return f'R {value:.2f}'

def update_loan_statuses(user):
    """Update status for all loans"""
    today = date.today()
    
    # First, add overdue interest
    check_and_add_overdue_interest(user)
    
    # Update status for all loans
    loans = Loan.objects.filter(user=user)
    for loan in loans:
        total_owed, _, _ = calculate_total_owed(loan)
        
        if total_owed <= 0:
            status = "Paid"
        else:
            if loan.current_due_date and today > loan.current_due_date:
                status = "Overdue"
            else:
                status = "Partial"
        
        loan.status = status
        loan.save()

def check_and_add_overdue_interest(user):
    """Check all loans and add interest for ALL missed due dates"""
    today = date.today()
    
    active_loans = Loan.objects.filter(user=user).exclude(status="Paid")
    
    for loan in active_loans:
        current_due_date = loan.current_due_date
        
        if not current_due_date:
            continue
        
        # Loop through ALL missed months
        while today > current_due_date:
            # Check if interest already exists for this due date
            existing_interest = LoanInterestHistory.objects.filter(
                loan=loan,
                due_date=current_due_date
            ).exists()
            
            if not existing_interest:
                interest_amount = calculate_interest(loan.current_principal)
                
                LoanInterestHistory.objects.create(
                    loan=loan,
                    due_date=current_due_date,
                    interest_amount=interest_amount,
                    principal_at_time=loan.current_principal,
                    added_date=today,
                    is_paid=False,
                    user=user
                )
            
            # Move to next due date
            current_due_date = current_due_date + relativedelta(months=1)
        
        # Update the loan's current due date
        loan.current_due_date = current_due_date
        loan.status = "Overdue"
        loan.save()

@transaction.atomic
def process_payment(loan_id, payment_amount, payment_date, user):
    """Process a payment according to the rules"""
    try:
        loan = Loan.objects.get(id=loan_id, user=user)
        payment_amount = Decimal(str(payment_amount))
        
        # Get unpaid interest sorted by due date
        unpaid_interest = LoanInterestHistory.objects.filter(
            loan=loan,
            is_paid=False,
            interest_amount__gt=0
        ).order_by('due_date')
        
        remaining_payment = payment_amount
        applied_to_interest = Decimal('0')
        applied_to_principal = Decimal('0')
        
        # Pay interest first
        for interest_entry in unpaid_interest:
            if remaining_payment <= 0:
                break
            
            if remaining_payment >= interest_entry.interest_amount:
                # Fully pay interest
                applied_to_interest += interest_entry.interest_amount
                remaining_payment -= interest_entry.interest_amount
                interest_entry.is_paid = True
                interest_entry.save()
            else:
                # Partial interest payment
                new_interest_amount = interest_entry.interest_amount - remaining_payment
                applied_to_interest += remaining_payment
                interest_entry.interest_amount = new_interest_amount
                interest_entry.save()
                remaining_payment = Decimal('0')
        
        # Apply to principal
        if remaining_payment > 0:
            applied_to_principal = remaining_payment
            new_principal = loan.current_principal - applied_to_principal
            loan.current_principal = max(new_principal, Decimal('0'))
            loan.save()
        
        # Record payment
        Payment.objects.create(
            loan=loan,
            amount=payment_amount,
            payment_date=payment_date,
            applied_to_interest=applied_to_interest,
            applied_to_principal=applied_to_principal,
            remaining_amount=remaining_payment,
            user=user
        )
        
        # Update loan status
        total_owed, _, _ = calculate_total_owed(loan)
        loan.status = "Paid" if total_owed <= 0 else "Active"
        loan.save()
        
        return True, "Payment processed successfully"
    except Exception as e:
        return False, f"Error processing payment: {str(e)}"

def get_loans_simple_view(user):
    """Get loans data in the simple view format"""
    loans = Loan.objects.filter(user=user).select_related('client__group')
    
    results = []
    for loan in loans:
        # Calculate unpaid interest
        interest_sum = LoanInterestHistory.objects.filter(
            loan=loan, is_paid=False
        ).aggregate(total=Sum('interest_amount'))['total'] or Decimal('0')
        
        # Calculate paid amount
        paid_sum = Payment.objects.filter(loan=loan).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        total = loan.current_principal + interest_sum
        
        results.append({
            'id': loan.id,
            'client': loan.client.name,
            'group_name': loan.client.group.name if loan.client.group else '',
            'loan_date': loan.loan_date,
            'due_date': loan.current_due_date,
            'principal': loan.current_principal,
            'interest': interest_sum,
            'paid': paid_sum,
            'total': total,
            'status': loan.status
        })
    
    return results

def get_payments_simple_view(user, limit=20):
    """Get payments data in the simple view format"""
    payments = Payment.objects.filter(user=user).select_related(
        'loan__client__group'
    ).order_by('-payment_date')[:limit]
    
    results = []
    for payment in payments:
        loan = payment.loan
        # Calculate unpaid interest
        interest_sum = LoanInterestHistory.objects.filter(
            loan=loan, is_paid=False
        ).aggregate(total=Sum('interest_amount'))['total'] or Decimal('0')
        
        total = loan.current_principal + interest_sum
        
        results.append({
            'client': loan.client.name,
            'group_name': loan.client.group.name if loan.client.group else '',
            'loan_date': loan.loan_date,
            'due_date': loan.current_due_date,
            'principal': loan.current_principal,
            'interest': interest_sum,
            'paid': payment.amount,
            'total': total,
            'payment_date': payment.payment_date,
            'status': loan.status
        })
    
    return results

def can_delete_client(client_id, user):
    """Check if client can be deleted (no related loans)"""
    return not Loan.objects.filter(client_id=client_id, user=user).exists()

def can_delete_group(group_id, user):
    """Check if group can be deleted (no related clients)"""
    return not Client.objects.filter(group_id=group_id, user=user).exists()

@transaction.atomic
def delete_client_with_related_data(client_id, user):
    """Delete client and all related data"""
    try:
        client = Client.objects.get(id=client_id, user=user)
        
        # Get all loans for this client
        loans = Loan.objects.filter(client=client, user=user)
        
        for loan in loans:
            # Delete related payments and interest history
            Payment.objects.filter(loan=loan, user=user).delete()
            LoanInterestHistory.objects.filter(loan=loan, user=user).delete()
        
        # Delete loans
        loans.delete()
        
        # Delete client
        client.delete()
        
        return True, "Client and all related data deleted successfully"
    except Exception as e:
        return False, f"Error deleting client: {str(e)}"

@transaction.atomic
def delete_group_with_related_data(group_id, user):
    """Delete group and all related data"""
    try:
        group = Group.objects.get(id=group_id, user=user)
        
        # Get all clients in this group
        clients = Client.objects.filter(group=group, user=user)
        
        for client in clients:
            success, message = delete_client_with_related_data(client.id, user)
            if not success:
                return False, message
        
        # Delete group
        group.delete()
        
        return True, "Group and all related data deleted successfully"
    except Exception as e:
        return False, f"Error deleting group: {str(e)}"

# ---------- AUTH VIEWS ----------

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Login successful!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'core/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
    return redirect('login')

def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
        elif len(username) < 3:
            messages.error(request, 'Username must be at least 3 characters')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
    
    return render(request, 'core/signup.html')

# ---------- MAIN VIEWS ----------

@login_required
def dashboard(request):
    # Update loan statuses
    update_loan_statuses(request.user)
    
    business_name = get_setting(request, 'business_name', '')
    
    # Get summary statistics
    total_clients = Client.objects.filter(user=request.user).count()
    total_loans = Loan.objects.filter(user=request.user).count()
    
    # Calculate total money issued (sum of original principals)
    total_issued = Loan.objects.filter(user=request.user).aggregate(
        total=Sum('original_principal')
    )['total'] or 0
    
    # Calculate total outstanding
    loans = Loan.objects.filter(user=request.user)
    total_outstanding = 0
    for loan in loans:
        total_owed, _, _ = calculate_total_owed(loan)
        total_outstanding += total_owed
    
    # Calculate total interest earned (sum of all interest - paid or unpaid)
    total_interest = LoanInterestHistory.objects.filter(
        user=request.user
    ).aggregate(total=Sum('interest_amount'))['total'] or 0
    
    # Get recent loans
    recent_loans = get_loans_simple_view(request.user)[:5]
    
    context = {
        'business_name': business_name,
        'total_clients': total_clients,
        'total_loans': total_loans,
        'total_issued': total_issued,
        'total_outstanding': total_outstanding,
        'total_interest': total_interest,
        'recent_loans': recent_loans,
        'format_money': format_money,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def groups(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            name = request.POST.get('name')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            if name and start_date and end_date:
                Group.objects.create(
                    name=name.strip(),
                    start_date=start_date,
                    end_date=end_date,
                    user=request.user
                )
                messages.success(request, 'Group added successfully')
        
        elif action == 'update':
            group_id = request.POST.get('group_id')
            name = request.POST.get('name')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            group = get_object_or_404(Group, id=group_id, user=request.user)
            group.name = name.strip()
            group.start_date = start_date
            group.end_date = end_date
            group.save()
            messages.success(request, 'Group updated successfully')
        
        elif action == 'delete':
            group_id = request.POST.get('group_id')
            if can_delete_group(group_id, request.user):
                success, message = delete_group_with_related_data(group_id, request.user)
                if success:
                    messages.success(request, message)
                else:
                    messages.error(request, message)
            else:
                messages.error(request, 'Cannot delete group: There are clients in this group')
        
        return redirect('groups')
    
    groups_data = Group.objects.filter(user=request.user).order_by('name')
    
    context = {
        'groups': groups_data,
    }
    return render(request, 'core/groups.html', context)

@login_required
def clients(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            name = request.POST.get('name')
            group_id = request.POST.get('group_id')
            
            if name and group_id:
                Client.objects.create(
                    name=name.strip(),
                    group_id=group_id,
                    user=request.user
                )
                messages.success(request, 'Client added successfully')
        
        elif action == 'update':
            client_id = request.POST.get('client_id')
            name = request.POST.get('name')
            group_id = request.POST.get('group_id')
            
            client = get_object_or_404(Client, id=client_id, user=request.user)
            client.name = name.strip()
            client.group_id = group_id
            client.save()
            messages.success(request, 'Client updated successfully')
        
        elif action == 'delete':
            client_id = request.POST.get('client_id')
            if can_delete_client(client_id, request.user):
                success, message = delete_client_with_related_data(client_id, request.user)
                if success:
                    messages.success(request, message)
                else:
                    messages.error(request, message)
            else:
                messages.error(request, 'Cannot delete client: There are loans associated')
        
        return redirect('clients')
    
    clients_data = Client.objects.filter(user=request.user).select_related('group').order_by('name')
    groups_data = Group.objects.filter(user=request.user).order_by('name')
    
    context = {
        'clients': clients_data,
        'groups': groups_data,
    }
    return render(request, 'core/clients.html', context)

@login_required
def loans(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            client_id = request.POST.get('client_id')
            loan_date = request.POST.get('loan_date')
            due_date = request.POST.get('due_date')
            principal = Decimal(request.POST.get('principal', '0'))
            
            if client_id and loan_date and due_date and principal > 0:
                client = get_object_or_404(Client, id=client_id, user=request.user)
                
                # Create loan
                loan = Loan.objects.create(
                    client=client,
                    loan_date=loan_date,
                    original_due_date=due_date,
                    current_due_date=due_date,
                    original_principal=principal,
                    current_principal=principal,
                    status='Partial',
                    user=request.user
                )
                
                # Record initial interest
                interest = calculate_interest(principal)
                LoanInterestHistory.objects.create(
                    loan=loan,
                    due_date=due_date,
                    interest_amount=interest,
                    principal_at_time=principal,
                    added_date=date.today(),
                    is_paid=False,
                    user=request.user
                )
                
                messages.success(request, 'Loan created successfully')
        
        elif action == 'update':
            loan_id = request.POST.get('loan_id')
            principal = Decimal(request.POST.get('principal', '0'))
            due_date = request.POST.get('due_date')
            
            loan = get_object_or_404(Loan, id=loan_id, user=request.user)
            
            # Update loan
            loan.current_principal = principal
            loan.original_principal = principal
            loan.current_due_date = due_date
            loan.original_due_date = due_date
            loan.save()
            
            # Update interest record
            interest = calculate_interest(principal)
            interest_record, created = LoanInterestHistory.objects.get_or_create(
                loan=loan,
                due_date=due_date,
                defaults={
                    'interest_amount': interest,
                    'principal_at_time': principal,
                    'added_date': date.today(),
                    'is_paid': False,
                    'user': request.user
                }
            )
            if not created:
                interest_record.interest_amount = interest
                interest_record.principal_at_time = principal
                interest_record.save()
            
            messages.success(request, 'Loan updated successfully')
        
        elif action == 'delete':
            loan_id = request.POST.get('loan_id')
            try:
                loan = Loan.objects.get(id=loan_id, user=request.user)
                Payment.objects.filter(loan=loan, user=request.user).delete()
                LoanInterestHistory.objects.filter(loan=loan, user=request.user).delete()
                loan.delete()
                messages.success(request, 'Loan deleted successfully')
            except Exception as e:
                messages.error(request, f'Error deleting loan: {str(e)}')
        
        return redirect('loans')
    
    # Update statuses
    update_loan_statuses(request.user)
    
    clients_data = Client.objects.filter(user=request.user).order_by('name')
    loans_list = get_loans_simple_view(request.user)
    
    context = {
        'clients': clients_data,
        'loans': loans_list,
        'status_color_html': status_color_html,
        'format_money': format_money,
    }
    return render(request, 'core/loans.html', context)

@login_required
def payments(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            loan_id = request.POST.get('loan_id')
            amount = Decimal(request.POST.get('amount', '0'))
            payment_date = request.POST.get('payment_date')
            
            if loan_id and amount > 0 and payment_date:
                # Check minimum payment rule
                loan = get_object_or_404(Loan, id=loan_id, user=request.user)
                _, _, unpaid_interest = calculate_total_owed(loan)
                
                payment_date_obj = date.fromisoformat(payment_date)
                if payment_date_obj >= loan.current_due_date and unpaid_interest > 0 and amount < unpaid_interest:
                    messages.error(request, f'Minimum payment required: R {unpaid_interest:.2f}')
                else:
                    success, message = process_payment(loan_id, amount, payment_date_obj, request.user)
                    if success:
                        messages.success(request, 'Payment recorded successfully')
                    else:
                        messages.error(request, message)
        
        return redirect('payments')
    
    # Update statuses
    update_loan_statuses(request.user)
    
    # Get active loans
    active_loans = Loan.objects.filter(user=request.user).exclude(
        status='Paid'
    ).select_related('client')
    
    active_loans_list = []
    for loan in active_loans:
        _, _, unpaid_interest = calculate_total_owed(loan)
        active_loans_list.append({
            'id': loan.id,
            'client_name': loan.client.name,
            'loan_date': loan.loan_date,
            'current_due_date': loan.current_due_date,
            'current_principal': loan.current_principal,
            'unpaid_interest': unpaid_interest,
            'status': loan.status,
            'total_owed': loan.current_principal + unpaid_interest
        })
    
    payments_list = get_payments_simple_view(request.user, limit=20)
    
    context = {
        'active_loans': active_loans_list,
        'payments': payments_list,
        'today': date.today().isoformat(),
        'status_color_html': status_color_html,
        'format_money': format_money,
    }
    return render(request, 'core/payments.html', context)

@login_required
def monthly_overview(request):
    # Update statuses
    update_loan_statuses(request.user)
    
    loans_list = get_loans_simple_view(request.user)
    
    # Group by month and group
    monthly_data = {}
    for loan in loans_list:
        loan_date = loan['loan_date']
        month_key = loan_date.strftime('%B %Y') if hasattr(loan_date, 'strftime') else str(loan_date)
        
        if month_key not in monthly_data:
            monthly_data[month_key] = {}
        
        group_name = loan['group_name'] or 'No Group'
        if group_name not in monthly_data[month_key]:
            monthly_data[month_key][group_name] = []
        
        monthly_data[month_key][group_name].append(loan)
    
    context = {
        'monthly_data': monthly_data,
        'status_color_html': status_color_html,
        'format_money': format_money,
    }
    return render(request, 'core/monthly_overview.html', context)

@login_required
def search(request):
    search_type = request.GET.get('type', 'client')
    query = request.GET.get('q', '')
    
    results = []
    if query:
        loans_list = get_loans_simple_view(request.user)
        df = pd.DataFrame(loans_list)
        
        if search_type == 'client' and not df.empty:
            df = df[df['client'].str.contains(query, case=False, na=False)]
        elif search_type == 'group' and not df.empty:
            df = df[df['group_name'].str.contains(query, case=False, na=False)]
        elif search_type == 'date' and not df.empty:
            df = df[df['due_date'].astype(str).str.contains(query, case=False, na=False)]
        
        results = df.to_dict('records') if not df.empty else []
    
    context = {
        'search_type': search_type,
        'query': query,
        'results': results,
        'status_color_html': status_color_html,
        'format_money': format_money,
    }
    return render(request, 'core/search.html', context)

@login_required
def pdf_export(request):
    if request.method == 'POST':
        export_type = request.POST.get('export_type')
        client_id = request.POST.get('client_id')
        group_id = request.POST.get('group_id')
        
        business_name = get_setting(request, 'business_name', 'Nethengwe Finance Services (NFS)')
        
        # Get loans data
        loans_list = get_loans_simple_view(request.user)
        df = pd.DataFrame(loans_list)
        
        if export_type == 'client' and client_id:
            client = get_object_or_404(Client, id=client_id, user=request.user)
            df = df[df['client'] == client.name]
            title = f"Client Statement - {client.name}"
            filename = f"{client.name.replace(' ', '_')}_statement_{date.today().isoformat()}.pdf"
        elif export_type == 'group' and group_id:
            group = get_object_or_404(Group, id=group_id, user=request.user)
            df = df[df['group_name'] == group.name]
            title = f"Group Report - {group.name}"
            filename = f"{group.name.replace(' ', '_')}_report_{date.today().isoformat()}.pdf"
        else:
            messages.error(request, 'Invalid export parameters')
            return redirect('pdf_export')
        
        if df.empty:
            messages.error(request, 'No loans found')
            return redirect('pdf_export')
        
        # Sort by loan date
        df['loan_date'] = pd.to_datetime(df['loan_date'])
        df = df.sort_values(by='loan_date', ascending=True)
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer)
        styles = getSampleStyleSheet()
        story = []
        
        # Header
        story.append(Paragraph(business_name, styles['Title']))
        story.append(Paragraph(title, styles['Heading1']))
        story.append(Paragraph(f"Generated: {date.today().isoformat()}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        # Loans table
        story.append(Paragraph("Loans Overview", styles['Heading2']))
        
        table_data = [["Client", "Group", "Loan Date", "Due Date", "Principal", "Interest", "Paid", "Total", "Status"]]
        
        for _, row in df.iterrows():
            status_display = row['status']
            table_data.append([
                row['client'] if export_type == 'group' else '',
                row['group_name'] if export_type == 'client' else '',
                row['loan_date'].strftime('%Y-%m-%d'),
                row['due_date'].strftime('%Y-%m-%d') if hasattr(row['due_date'], 'strftime') else str(row['due_date']),
                f"R {row['principal']:.2f}",
                f"R {row['interest']:.2f}",
                f"R {row['paid']:.2f}",
                f"R {row['total']:.2f}",
                status_display
            ])
        
        t = Table(table_data, repeatRows=1)
        style = TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])
        
        # Color coding
        for i in range(1, len(table_data)):
            total_val = float(table_data[i][7].replace('R', '').strip())
            if total_val > 0:
                style.add('TEXTCOLOR', (7, i), (7, i), colors.red)
            
            paid_val = float(table_data[i][6].replace('R', '').strip())
            if paid_val > 0:
                style.add('TEXTCOLOR', (6, i), (6, i), colors.green)
            
            status = table_data[i][8]
            if 'Paid' in status:
                style.add('TEXTCOLOR', (8, i), (8, i), colors.green)
            elif 'Partial' in status:
                style.add('TEXTCOLOR', (8, i), (8, i), colors.orange)
            elif 'Overdue' in status:
                style.add('TEXTCOLOR', (8, i), (8, i), colors.red)
        
        t.setStyle(style)
        story.append(t)
        story.append(Spacer(1, 12))
        
        # Summary
        total_principal = df['principal'].sum()
        total_interest = df['interest'].sum()
        total_paid = df['paid'].sum()
        total_total = df['total'].sum()
        
        story.append(Paragraph("Summary", styles['Heading2']))
        summary_data = [
            ["Total Principal", f"R {total_principal:.2f}"],
            ["Total Interest", f"R {total_interest:.2f}"],
            ["Total Paid", f"R {total_paid:.2f}"],
            ["Total Balance Owing", f"R {total_total:.2f}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[200, 100])
        summary_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
            ('TEXTCOLOR', (1,3), (1,3), colors.red if total_total > 0 else colors.black),
            ('TEXTCOLOR', (1,2), (1,2), colors.green if total_paid > 0 else colors.black),
        ]))
        story.append(summary_table)
        
        # Build PDF
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Return PDF as response
        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    # GET request - show form
    clients_data = Client.objects.filter(user=request.user).order_by('name')
    groups_data = Group.objects.filter(user=request.user).order_by('name')
    
    context = {
        'clients': clients_data,
        'groups': groups_data,
    }
    return render(request, 'core/pdf_export.html', context)

@login_required
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Verify current password
        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect')
        elif new_password != confirm_password:
            messages.error(request, 'New passwords do not match')
        elif len(new_password) < 6:
            messages.error(request, 'New password must be at least 6 characters')
        else:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully')
            return redirect('dashboard')
    
    return render(request, 'core/change_password.html')

@login_required
def set_business_name(request):
    if request.method == 'POST':
        business_name = request.POST.get('business_name', '').strip()
        if business_name:
            set_setting(request, 'business_name', business_name)
            messages.success(request, 'Business name saved')
        return redirect('dashboard')
