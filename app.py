# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import shutil
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors as rlcolors
from reportlab.lib.styles import getSampleStyleSheet
from dateutil.relativedelta import relativedelta

# ---------- SUPABASE CONFIG ----------
import supabase
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))
# DO NOT use service role key in frontend - use anon/public key only

# Initialize Supabase client
@st.cache_resource
def init_supabase():
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return client
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

supabase_client = init_supabase()

# ---------- CONFIG ----------
BACKUP_DIR = "backups"
INTEREST_RATE = 0.40  # 40% interest rate

st.set_page_config(page_title="💼 Loan Management System", layout="wide")


# ---------- UTILITIES ----------
def format_money(v):
    try:
        v = round(float(v), 2)
    except Exception:
        return v
    s = f"{v:.2f}"
    # remove trailing zeros and decimal if not needed
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

def hash_pw(pw: str) -> str:
    """Legacy function kept for compatibility - Supabase now handles auth"""
    import hashlib
    return hashlib.sha256(pw.encode()).hexdigest()

def round_money(amount):
    """Round and format numbers - from STRUCTURE PLAN"""
    return round(float(amount), 2)

def colored_money(label, value):
    """Apply color rules - from STRUCTURE PLAN"""
    value = float(value)
    if label == "paid" and value > 0:
        return f"🟢 R {value:.2f}"
    elif label == "balance" and value > 0:
        return f"🔴 R {value:.2f}"
    else:
        return f"R {value:.2f}"

def status_color(status):
    """Returns colored status string - from STRUCTURE PLAN"""
    if status == "Paid":
        return f"🟢 {status}"
    elif status == "Partial":
        return f"🟡 {status}"
    elif status == "Overdue":
        return f"🔴 {status}"
    elif status == "Active":
        return f"🔵 {status}"
    return status

def ensure_dirs():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def daily_backup():
    """Backup function - keeping for compatibility but will be Supabase-based"""
    ensure_dirs()
    # Supabase handles backups automatically
    pass

# Helper function to get current user ID
def get_current_user_id():
    """Get current user ID from Supabase auth session"""
    if "auth_session" in st.session_state:
        return st.session_state.auth_session.user.id
    return None

# ---------- SUPABASE DB OPERATIONS ----------
def execute_query(sql, params=None):
    """Execute raw SQL query on Supabase (for views and complex queries)"""
    try:
        # Use Supabase's REST API for data operations
        # For complex queries, we'll use the REST API methods
        return None
    except Exception as e:
        st.error(f"Query error: {e}")
        return None

# ---------- SUPABASE DB OPERATIONS WITH USER ISOLATION ----------

def get_table_data(table_name, filters=None, order_by=None, limit=None):
    """Get data from Supabase table with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return []
        
        query = supabase_client.table(table_name).select("*").eq("user_id", user_id)
        
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        
        if order_by:
            query = query.order(order_by)
        
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching from {table_name}: {e}")
        return []

def insert_table_data(table_name, data):
    """Insert data into Supabase table with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return None
        
        # Add user_id to all data
        data_with_user = {**data, "user_id": user_id}
        response = supabase_client.table(table_name).insert(data_with_user).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Error inserting into {table_name}: {e}")
        return None

def update_table_data(table_name, id_value, data):
    """Update data in Supabase table with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return None
        
        response = supabase_client.table(table_name).update(data).eq("id", id_value).eq("user_id", user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Error updating {table_name}: {e}")
        return None

def delete_table_data(table_name, id_value):
    """Delete data from Supabase table with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return False
        
        response = supabase_client.table(table_name).delete().eq("id", id_value).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting from {table_name}: {e}")
        return False

def get_setting(key):
    """Get setting from Supabase with user isolation"""
    try:
        user_id = get_current_user_id()
        # If no user is logged in (login page), don't query settings
        if not user_id:
            return None
        
        response = supabase_client.table("settings").select("value").eq("key", key).eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]["value"]
        return None
    except Exception as e:
        # Don't show error on login page
        if "auth_session" in st.session_state and st.session_state.auth_session:
            st.error(f"Error getting setting {key}: {e}")
        return None

def set_setting(key, value):
    """Set setting in Supabase with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return False
        
        # Check if setting exists
        existing = get_setting(key)
        if existing:
            supabase_client.table("settings").update({"value": value}).eq("key", key).eq("user_id", user_id).execute()
        else:
            supabase_client.table("settings").insert({"key": key, "value": value, "user_id": user_id}).execute()
        return True
    except Exception as e:
        st.error(f"Error setting {key}: {e}")
        return False

# ---------- CORE LOGIC FUNCTIONS WITH USER ISOLATION ----------

def calculate_interest(principal):
    """Calculate 40% interest on principal"""
    return round(principal * INTEREST_RATE, 2)

def get_next_due_date(current_due_date_str):
    """Get the next due date (one month later)"""
    if not current_due_date_str:
        return None
    current_due_date = date.fromisoformat(current_due_date_str)
    next_due_date = current_due_date + relativedelta(months=1)
    return next_due_date.isoformat()

def calculate_total_owed(loan_id):
    """Calculate total amount owed for a loan (principal + unpaid interest) with user isolation"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return 0, 0, 0
        
        # Get loan info with user isolation
        loans = supabase_client.table("loans_new").select("*").eq("id", loan_id).eq("user_id", user_id).execute()
        if not loans.data:
            return 0, 0, 0
        
        loan = loans.data[0]
        current_principal = loan["current_principal"]
        
        # Get unpaid interest for this loan (user isolation handled by RLS)
        interest_data = supabase_client.table("loan_interest_history").select("interest_amount").eq("loan_id", loan_id).eq("is_paid", 0).execute()
        
        unpaid_interest = sum(item["interest_amount"] for item in interest_data.data if item["interest_amount"] > 0)
        total_owed = round(current_principal + unpaid_interest, 2)
        
        return total_owed, current_principal, unpaid_interest
    except Exception as e:
        st.error(f"Error calculating total owed: {e}")
        return 0, 0, 0


# ---------- CORE LOGIC ----------
def calculate_interest(principal):
    """Calculate 40% interest on principal"""
    return round(principal * INTEREST_RATE, 2)

def get_next_due_date(current_due_date_str):
    """Get the next due date (one month later)"""
    if not current_due_date_str:
        return None
    current_due_date = date.fromisoformat(current_due_date_str)
    next_due_date = current_due_date + relativedelta(months=1)
    return next_due_date.isoformat()

def calculate_total_owed(loan_id):
    """Calculate total amount owed for a loan (principal + unpaid interest)"""
    try:
        # Get loan info
        loans = get_table_data("loans_new", {"id": loan_id})
        if not loans:
            return 0, 0, 0
        
        loan = loans[0]
        current_principal = loan["current_principal"]
        
        # Get unpaid interest
        interest_data = supabase_client.table("loan_interest_history").select("interest_amount").eq("loan_id", loan_id).eq("is_paid", 0).execute()
        
        unpaid_interest = sum(item["interest_amount"] for item in interest_data.data if item["interest_amount"] > 0)
        total_owed = round(current_principal + unpaid_interest, 2)
        
        return total_owed, current_principal, unpaid_interest
    except Exception as e:
        st.error(f"Error calculating total owed: {e}")
        return 0, 0, 0

def process_payment(loan_id, payment_amount, payment_date):
    """Process a payment according to the new rules"""
    try:
        # ---------------- AUTH ----------------
        user_id = get_current_user_id()
        if not user_id:
            return False, "User not authenticated"

        # ---------------- GET LOAN (USER-SCOPED) ----------------
        loans = (
            supabase_client
            .table("loans_new")
            .select("*")
            .eq("id", loan_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not loans.data:
            return False, "Loan not found or access denied"

        loan = loans.data[0]
        current_principal = float(loan["current_principal"])

        # ---------------- GET UNPAID INTEREST ----------------
        interest_data = (
            supabase_client
            .table("loan_interest_history")
            .select("*")
            .eq("loan_id", loan_id)
            .eq("user_id", user_id)
            .eq("is_paid", 0)
            .gt("interest_amount", 0)
            .order("due_date")
            .execute()
        )

        remaining_payment = round(float(payment_amount), 2)
        applied_to_interest = 0.0
        applied_to_principal = 0.0

        # ---------------- PAY INTEREST FIRST ----------------
        for entry in interest_data.data:
            if remaining_payment <= 0:
                break

            entry_id = entry["id"]
            interest_amount = float(entry["interest_amount"])

            if remaining_payment >= interest_amount:
                # Fully pay interest
                supabase_client.table("loan_interest_history").update({
                    "is_paid": 1
                }).eq("id", entry_id).eq("user_id", user_id).execute()

                applied_to_interest += interest_amount
                remaining_payment = round(remaining_payment - interest_amount, 2)
            else:
                # Partial interest payment
                new_interest_amount = round(interest_amount - remaining_payment, 2)

                supabase_client.table("loan_interest_history").update({
                    "interest_amount": new_interest_amount
                }).eq("id", entry_id).eq("user_id", user_id).execute()

                applied_to_interest += remaining_payment
                remaining_payment = 0

        # ---------------- APPLY TO PRINCIPAL ----------------
        if remaining_payment > 0:
            applied_to_principal = remaining_payment
            new_principal = round(current_principal - applied_to_principal, 2)
            new_principal = max(new_principal, 0)

            supabase_client.table("loans_new").update({
                "current_principal": new_principal
            }).eq("id", loan_id).eq("user_id", user_id).execute()

        # ---------------- RECORD PAYMENT (CRITICAL FIX) ----------------
        supabase_client.table("payments_new").insert({
            "loan_id": loan_id,
            "amount": payment_amount,
            "payment_date": payment_date.isoformat(),
            "applied_to_interest": applied_to_interest,
            "applied_to_principal": applied_to_principal,
            "remaining_amount": remaining_payment,
            "user_id": user_id  # ✅ REQUIRED
        }).execute()

        # ---------------- UPDATE LOAN STATUS ----------------
        total_owed, _, _ = calculate_total_owed(loan_id)

        new_status = "Paid" if total_owed <= 0 else "Active"

        supabase_client.table("loans_new").update({
            "status": new_status
        }).eq("id", loan_id).eq("user_id", user_id).execute()

        return True, "Payment processed successfully"

    except Exception as e:
        return False, f"Error processing payment: {str(e)}"


def check_and_add_overdue_interest():
    """Check all loans and add interest for ALL missed due dates"""
    try:
        today = date.today()
        
        # Get active loans
        loans_data = supabase_client.table("loans_new").select("*").neq("status", "Paid").execute()
        
        for loan in loans_data.data:
            loan_id = loan["id"]
            current_principal = loan["current_principal"]
            current_due_date_str = loan["current_due_date"]
            
            if not current_due_date_str:
                continue
            
            current_due_date = date.fromisoformat(current_due_date_str)
            
            # Loop through ALL missed months
            while today > current_due_date:
                # Check if interest already exists for this due date
                existing_interest = supabase_client.table("loan_interest_history").select("*").eq("loan_id", loan_id).eq("due_date", current_due_date.isoformat()).execute()
                
                if not existing_interest.data:
                    interest_amount = calculate_interest(current_principal)
                    
                    supabase_client.table("loan_interest_history").insert({
                        "loan_id": loan_id,
                        "due_date": current_due_date.isoformat(),
                        "interest_amount": interest_amount,
                        "principal_at_time": current_principal,
                        "added_date": today.isoformat(),
                        "is_paid": 0
                    }).execute()
                
                # Move to next due date
                current_due_date = current_due_date + relativedelta(months=1)
            
            # Update the loan's current due date
            supabase_client.table("loans_new").update({
                "current_due_date": current_due_date.isoformat(),
                "status": "Overdue"
            }).eq("id", loan_id).execute()
        
        return True
    except Exception as e:
        st.error(f"Error checking overdue interest: {e}")
        return False

def update_loan_statuses():
    """Update status for all loans"""
    try:
        today = date.today()
        check_and_add_overdue_interest()
        
        # Get all loans
        loans_data = supabase_client.table("loans_new").select("*").execute()
        
        for loan in loans_data.data:
            loan_id = loan["id"]
            total_owed, current_principal, unpaid_interest = calculate_total_owed(loan_id)
            
            if total_owed <= 0:
                status = "Paid"
            else:
                current_due_date_str = loan["current_due_date"]
                if current_due_date_str:
                    due_date = date.fromisoformat(current_due_date_str)
                    if today > due_date:
                        status = "Overdue"
                    else:
                        status = "Partial"
                else:
                    status = "Partial"
            
            supabase_client.table("loans_new").update({"status": status}).eq("id", loan_id).execute()
        
        return True
    except Exception as e:
        st.error(f"Error updating loan statuses: {e}")
        return False

# Run status updates on start
update_loan_statuses()

# ---------- VIEW FUNCTIONS ----------
def get_loans_simple_view():
    """Get loans data in the simple view format"""
    try:
        # This is a complex query that we need to handle manually
        # Get all loans with client and group info
        loans_data = supabase_client.table("loans_new").select("*, clients(name, groups(name))").execute()
        
        results = []
        for loan in loans_data.data:
            loan_id = loan["id"]
            client_name = loan["clients"]["name"] if loan.get("clients") else ""
            group_name = loan["clients"]["groups"]["name"] if loan.get("clients") and loan["clients"].get("groups") else ""
            
            # Calculate interest
            interest_data = supabase_client.table("loan_interest_history").select("interest_amount").eq("loan_id", loan_id).eq("is_paid", 0).execute()
            interest = sum(item["interest_amount"] for item in interest_data.data)
            
            # Calculate paid amount
            payments_data = supabase_client.table("payments_new").select("amount").eq("loan_id", loan_id).execute()
            paid = sum(item["amount"] for item in payments_data.data)
            
            total = loan["current_principal"] + interest
            
            results.append({
                "id": loan_id,
                "client": client_name,
                "group_name": group_name,
                "loan_date": loan["loan_date"],
                "due_date": loan["current_due_date"],
                "principal": loan["current_principal"],
                "interest": interest,
                "paid": paid,
                "total": total,
                "status": loan["status"]
            })
        
        return results
    except Exception as e:
        st.error(f"Error getting loans view: {e}")
        return []

def get_payments_simple_view(limit=20):
    """Get payments data in the simple view format"""
    try:
        # Get payments with loan and client info
        payments_data = supabase_client.table("payments_new").select("*, loans_new(*, clients(*, groups(*)))").order("payment_date", desc=True).limit(limit).execute()
        
        results = []
        for payment in payments_data.data:
            loan = payment.get("loans_new", {})
            client = loan.get("clients", {})
            group = client.get("groups", {})
            
            # Calculate interest for this loan
            interest_data = supabase_client.table("loan_interest_history").select("interest_amount").eq("loan_id", loan.get("id")).eq("is_paid", 0).execute()
            interest = sum(item["interest_amount"] for item in interest_data.data)
            
            total = loan.get("current_principal", 0) + interest
            
            results.append({
                "client": client.get("name", ""),
                "group_name": group.get("name", ""),
                "loan_date": loan.get("loan_date", ""),
                "due_date": loan.get("current_due_date", ""),
                "principal": loan.get("current_principal", 0),
                "interest": interest,
                "paid": payment["amount"],
                "total": total,
                "payment_date": payment["payment_date"],
                "status": loan.get("status", "")
            })
        
        return results
    except Exception as e:
        st.error(f"Error getting payments view: {e}")
        return []

# ---------- HELPER FUNCTIONS ----------
def can_delete_client(client_id):
    """Check if client can be deleted (no related loans)"""
    try:
        loans_data = supabase_client.table("loans_new").select("id").eq("client_id", client_id).execute()
        return len(loans_data.data) == 0
    except Exception as e:
        st.error(f"Error checking client deletion: {e}")
        return False

def can_delete_group(group_id):
    """Check if group can be deleted (no related clients)"""
    try:
        clients_data = supabase_client.table("clients").select("id").eq("group_id", group_id).execute()
        return len(clients_data.data) == 0
    except Exception as e:
        st.error(f"Error checking group deletion: {e}")
        return False

def delete_client_with_related_data(client_id):
    """Delete client and all related data"""
    try:
        # Get all loan IDs for this client
        loans_data = supabase_client.table("loans_new").select("id").eq("client_id", client_id).execute()
        
        # Delete related payments and interest history for each loan
        for loan in loans_data.data:
            loan_id = loan["id"]
            supabase_client.table("payments_new").delete().eq("loan_id", loan_id).execute()
            supabase_client.table("loan_interest_history").delete().eq("loan_id", loan_id).execute()
        
        # Delete loans
        supabase_client.table("loans_new").delete().eq("client_id", client_id).execute()
        
        # Delete client
        supabase_client.table("clients").delete().eq("id", client_id).execute()
        
        return True, "Client and all related data deleted successfully"
    except Exception as e:
        return False, f"Error deleting client: {str(e)}"

def delete_group_with_related_data(group_id):
    """Delete group and all related data"""
    try:
        # Get all client IDs in this group
        clients_data = supabase_client.table("clients").select("id").eq("group_id", group_id).execute()
        
        # Delete each client and their related data
        for client in clients_data.data:
            success, message = delete_client_with_related_data(client["id"])
            if not success:
                return False, message
        
        # Delete group
        supabase_client.table("groups").delete().eq("id", group_id).execute()
        
        return True, "Group and all related data deleted successfully"
    except Exception as e:
        return False, f"Error deleting group: {str(e)}"

def update_client(client_id, new_name, new_group_id):
    """Update client information"""
    try:
        supabase_client.table("clients").update({
            "name": new_name.strip(),
            "group_id": new_group_id
        }).eq("id", client_id).execute()
        return True, "Client updated successfully"
    except Exception as e:
        return False, f"Error updating client: {str(e)}"

def update_group(group_id, new_name, new_start_date, new_end_date):
    """Update group information"""
    try:
        supabase_client.table("groups").update({
            "name": new_name.strip(),
            "start_date": new_start_date.isoformat(),
            "end_date": new_end_date.isoformat()
        }).eq("id", group_id).execute()
        return True, "Group updated successfully"
    except Exception as e:
        return False, f"Error updating group: {str(e)}"

def update_loan(loan_id, new_principal, new_due_date):
    """Update loan information"""
    try:
        # Get current loan details
        loans_data = supabase_client.table("loans_new").select("*").eq("id", loan_id).execute()
        if not loans_data.data:
            return False, "Loan not found"
        
        current_principal = loans_data.data[0]["current_principal"]
        new_principal_rounded = round(float(new_principal), 2)
        
        # Update loan principal
        supabase_client.table("loans_new").update({
            "current_principal": new_principal_rounded,
            "original_principal": new_principal_rounded,
            "current_due_date": new_due_date.isoformat(),
            "original_due_date": new_due_date.isoformat()
        }).eq("id", loan_id).execute()
        
        # Update or create interest record
        interest = calculate_interest(new_principal_rounded)
        
        # Check if interest record exists
        existing_interest = supabase_client.table("loan_interest_history").select("*").eq("loan_id", loan_id).eq("due_date", new_due_date.isoformat()).execute()
        
        if existing_interest.data:
            # Update existing interest
            supabase_client.table("loan_interest_history").update({
                "interest_amount": interest,
                "principal_at_time": new_principal_rounded
            }).eq("id", existing_interest.data[0]["id"]).execute()
        else:
            # Create new interest record
            supabase_client.table("loan_interest_history").insert({
                "loan_id": loan_id,
                "due_date": new_due_date.isoformat(),
                "interest_amount": interest,
                "principal_at_time": new_principal_rounded,
                "added_date": date.today().isoformat(),
                "is_paid": 0
            }).execute()
        
        update_loan_statuses()
        return True, "Loan updated successfully"
    except Exception as e:
        return False, f"Error updating loan: {str(e)}"

def delete_loan_with_related_data(loan_id):
    """Delete loan and all related data"""
    try:
        # Delete related payments
        supabase_client.table("payments_new").delete().eq("loan_id", loan_id).execute()
        
        # Delete related interest history
        supabase_client.table("loan_interest_history").delete().eq("loan_id", loan_id).execute()
        
        # Delete loan
        supabase_client.table("loans_new").delete().eq("id", loan_id).execute()
        
        return True, "Loan and all related data deleted successfully"
    except Exception as e:
        return False, f"Error deleting loan: {str(e)}"

# ---------- STYLES ----------
def style_money_cell(x, column_name):
    try:
        val = float(x)
    except Exception:
        return ""
    if column_name == "paid":
        if val > 0:
            return "color: green"
        else:
            return ""
    if column_name == "total":
        if val > 0:
            return "color: red"
        else:
            return ""
    return ""

def style_status_cell(x):
    if pd.isna(x):
        return ""
    if x == "Paid":
        return "color: green; font-weight: bold"
    if x == "Partial":
        return "color: orange; font-weight: bold"
    if x == "Overdue":
        return "color: red; font-weight: bold"
    return ""

def style_dataframe(df):
    """Apply styling with colors and formatting"""
    numeric_cols = df.select_dtypes(include=['float64', 'float32', 'int64', 'int32']).columns
    sty = df.style
    
    if len(numeric_cols) > 0:
        sty = sty.format("{:.2f}", subset=numeric_cols)
    
    # Apply styling to all numeric columns if they match the conditions
    for col in df.columns:
        if col.lower() in ['total', 'balance']:
            sty = sty.applymap(lambda x: 'color: red; font-weight: bold' 
                              if pd.notnull(x) and isinstance(x, (int, float)) and float(x) > 0 else '', 
                              subset=[col])
        elif col.lower() == 'paid':
            sty = sty.applymap(lambda x: 'color: green; font-weight: bold' 
                              if pd.notnull(x) and isinstance(x, (int, float)) and float(x) > 0 else '', 
                              subset=[col])
    
    if "status" in df.columns:
        sty = sty.applymap(lambda v: style_status_cell(v), subset=["status"])
    
    return sty

# ---------- AUTH ----------
if "auth_session" not in st.session_state:
    st.session_state.auth_session = None
if "user" not in st.session_state:
    st.session_state.user = None


def login_page():
    st.title("🔐 Login")
    
    # Initialize Supabase client check
    if not supabase_client:
        st.error("⚠️ Supabase connection failed. Check your API keys in settings.")
        return
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        
        if st.button("Login"):
            try:
                if not email or not password:
                    st.error("Please enter both email and password")
                else:
                    # Use Supabase Auth
                    auth_response = supabase_client.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })
                    
                    if auth_response.user:
                        st.session_state.auth_session = auth_response
                        st.session_state.user = auth_response.user.email
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Login failed. Please check your credentials.")
            except Exception as e:
                error_msg = str(e)
                if "Invalid login credentials" in error_msg:
                    st.error("Invalid email or password")
                elif "Email not confirmed" in error_msg:
                    st.error("Please confirm your email first")
                elif "401" in error_msg:
                    st.error("Authentication error. Check Supabase API key configuration.")
                else:
                    st.error(f"Login error: {error_msg}")
        
        # Sign up option
        with st.expander("Don't have an account? Sign up"):
            new_email = st.text_input("Email for signup", key="signup_email")
            new_password = st.text_input("Password for signup", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm password", type="password", key="confirm_password")
            
            if st.button("Sign up", key="signup_button"):
                if not new_email or not new_password:
                    st.error("Please enter email and password")
                elif new_password != confirm_password:
                    st.error("Passwords don't match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    try:
                        signup_response = supabase_client.auth.sign_up({
                            "email": new_email,
                            "password": new_password
                        })
                        if signup_response.user:
                            st.success("✅ Account created successfully! You can now login.")
                        else:
                            st.error("Signup failed. Please try again.")
                    except Exception as e:
                        st.error(f"Signup error: {str(e)}")
    
    with col2:
        # Only show business name setup if logged in
        if st.session_state.auth_session:
            business = get_setting("business_name")
            st.markdown("### Optional: Set Business Name (one-time)")
            if not business:
                bn = st.text_input("Business name (optional)", key="business_name_input")
                if st.button("Save business name", key="save_business"):
                    if bn.strip():
                        set_setting("business_name", bn.strip())
                        st.success("Business name saved. It will show on every page.")
                        st.rerun()
                    else:
                        st.error("Please enter a non-empty name or cancel.")
        else:
            st.info("Set your business name after logging in")

def logout():
    try:
        supabase_client.auth.sign_out()
    except:
        pass
    st.session_state.auth_session = None
    st.session_state.user = None
    st.rerun()

# Check authentication
if not st.session_state.auth_session:
    login_page()
    st.stop()

# Verify session is still valid
try:
    # This will refresh the session if needed
    current_user = supabase_client.auth.get_user()
    if not current_user.user:
        st.session_state.auth_session = None
        st.session_state.user = None
        st.rerun()
except:
    st.session_state.auth_session = None
    st.session_state.user = None
    st.rerun()

business_name = get_setting("business_name") or ""

# ---------- HEADER HELPER ----------
def page_header(page_name: str):
    """Display header with business name and emojis"""
    if business_name:
        headers = {
            "Tutorial Dashboard": f"## 🏢 **{business_name}** ",
            "Groups": f"## 📁 Manage Groups | **{business_name}**",
            "Clients": f"## 👤 Manage Clients | **{business_name}**",
            "Loans": f"## 💰 Loans Overview | **{business_name}**",
            "Payments": f"## 💳 Payments | **{business_name}**",
            "Monthly Overview": f"## 📆 Monthly Overview | **{business_name}**",
            "Search": f"## 🔍 Search Loans | **{business_name}**",
            "PDF Report": f"## 🧾 PDF Report | **{business_name}**",
            "Change Password": f"## 🔐 Change Password | **{business_name}**",
            "Logout": f"## 🚪 Logout | **{business_name}**"
        }
    else:
        headers = {
            "Tutorial Dashboard": f"## 👋 Welcome {st.session_state.user}",
            "Groups": f"## 📁 Manage Groups",
            "Clients": f"## 👤 Manage Clients",
            "Loans": f"## 💰 Loans Overview",
            "Payments": f"## 💳 Payments",
            "Monthly Overview": f"## 📆 Monthly Overview",
            "Search": f"## 🔍 Search Loans",
            "PDF Report": f"## 🧾 PDF Report",
            "Change Password": f"## 🔐 Change Password",
            "Logout": f"## 🚪 Logout"
        }
    
    st.markdown(headers.get(page_name, f"## 👋 Welcome {st.session_state.user}"))

# ---------- SIDEBAR NAV ----------
st.sidebar.title(f"🏢 {business_name}" if business_name else "🏢 Menu")
menu = st.sidebar.radio("Navigate", [
    "📘 Tutorial Dashboard",
    "📁 Groups",
    "👤 Clients",
    "💰 Loans",
    "💳 Payments",
    "📆 Monthly Overview",
    "🔍 Search",
    "🧾 PDF Export",
    "🔐 Change Password",
    "🚪 Logout"
])

# ---------- PAGE: Tutorial Dashboard ----------
if menu == "📘 Tutorial Dashboard":
    page_header("Tutorial Dashboard")
    st.subheader("How this Loan System Works")
    st.markdown(f"""
    This page explains how to use the system.  
       
    **Pages:**

    1. 📁 **Groups** — Create a group (for example 'January 2026'). Groups help you organise clients by month or batch.
       - Go to **📁 Groups** → Add group name, start and end dates (optional).

    2. 👤 **Clients** — Add clients and assign them to a group.
       - Go to **👤 Clients** → Add client and select the group.

    3. 💰 **Loans** — Create loans for clients.
       - Choose a client, enter principal and due date. Interest is calculated automatically (40% rate shown).
       - The system saves: principal, interest, total, due date, and initial status.

    4. 💳 **Payments** — Record cash received.
       - Choose the loan and record the amount + payment date.
       - Amounts are rounded to **2 decimals**.
       - The loan balance and status update automatically:
         - 🟢 **Paid** — balance is zero
         - 🟡 **Partial** — some paid, balance > 0, not overdue
         - 🔴 **Overdue** — due date passed and balance > 0

    5. 🔍 **Search** — Find all loan info by Client, Group, or Due Date. Every search result shows:
       - Loan date, Due date, Principal, Interest, Total, Paid, Balance, Status
       - Paid > 0 highlights green; Balance > 0 highlights red; Status uses icons & colors.

    6. 📆 **Monthly Overview** — See groups and clients organized by month:
       - Example: **2026-01**
         - Group A
           - Client X → loan details & status

    7. 🧾 **PDF Export** — Export a full client statement with colored statuses and balances.

    8. 🔐 **Change Password** — Securely change your password (old password required).

    💡 **Loan Rules (40% Interest):**
    - Principal only reduces when payment exceeds interest
    - Interest calculated monthly on current principal
    - Minimum payment = interest amount on due dates
    - Payments apply to interest first, then principal

   ### LOAN SYSTEM RULES 
    
    1. **Loan Basics:**
       - Principal stays separate and only reduces when payment exceeds interest
       - Interest rate: {INTEREST_RATE*100}%
       - Interest is calculated on current remaining principal
       - Interest is charged monthly on the due date
    
    2. **Due Dates & Overdue Logic:**
       - First due date is set when creating loan
       - If unpaid, every following month on the same day becomes another overdue date
       - Each overdue date adds new interest based on current principal
    
    3. **Payment Rules:**
       - Minimum payment = interest amount (enforced on due dates)
       - Payments apply to interest first, then principal
       - If interest is not fully paid by due date, it's added to total owed
    
    **Example:**
    - Loan: R500 principal
    - Initial interest (40%): R200
    - Total shown: R700
    - If no payment by due date: R200 interest added, principal remains R500
    - Next month: New interest calculated on R500 principal = R200
    - Total after 2 months overdue: R500 + R200 + R200 = R900
    
    """)

# ---------- PAGE: Groups ----------
elif menu == "📁 Groups":
    page_header("Groups")
    
    # Get groups data
    groups_data = get_table_data("groups", order_by="name")
    groups_df = pd.DataFrame(groups_data) if groups_data else pd.DataFrame()
    
    if not groups_df.empty:
        st.subheader("Edit or Delete Groups")
        
        for _, group in groups_df.iterrows():
            with st.expander(f"📁 {group['name']} ({group['start_date']} to {group['end_date']})"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    with st.form(f"edit_group_{group['id']}"):
                        new_name = st.text_input("Group Name", value=group['name'], key=f"name_{group['id']}")
                        new_start = st.date_input("Start Date", value=date.fromisoformat(group['start_date']), key=f"start_{group['id']}")
                        new_end = st.date_input("End Date", value=date.fromisoformat(group['end_date']), key=f"end_{group['id']}")
                        
                        if st.form_submit_button("Update Group"):
                            success, message = update_group(group['id'], new_name, new_start, new_end)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_{group['id']}"):
                        if can_delete_group(group['id']):
                            success, message = delete_group_with_related_data(group['id'])
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                        else:
                            st.error("Cannot delete group: There are clients in this group. Delete the clients first.")

    st.subheader("Create a new group")
    with st.form("add_group", clear_on_submit=True):
        gname = st.text_input("Group name (e.g. January 2026)")
        start = st.date_input("Start date", value=date.today())
        end = st.date_input("End date", value=date.today())
        if st.form_submit_button("Add group"):
            try:
                insert_table_data("groups", {
                    "name": gname.strip(),
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat()
                })
                st.success("✅ Group added")
                st.rerun()
            except Exception as e:
                st.error(f"Could not add group: {e}")

    st.subheader("Existing groups")
    if not groups_df.empty:
        # Hide the ID column for display
        display_df = groups_df[['name', 'start_date', 'end_date']].copy()
        display_df.columns = ['Group Name', 'Start Date', 'End Date']
        st.dataframe(display_df)
    else:
        st.info("No groups yet. Add one above.")

# ---------- PAGE: Clients ----------
elif menu == "👤 Clients":
    page_header("Clients")
    
    # Get groups data
    groups_data = get_table_data("groups", order_by="name")
    groups_df = pd.DataFrame(groups_data) if groups_data else pd.DataFrame()
    group_names = groups_df["name"].tolist() if not groups_df.empty else []
    
    # Get clients data with group info
    clients_data = supabase_client.table("clients").select("*, groups(name)").order("name").execute()
    clients_list = []
    for client in clients_data.data:
        clients_list.append({
            "id": client["id"],
            "name": client["name"],
            "group_id": client["group_id"],
            "group_name": client["groups"]["name"] if client.get("groups") else "No Group"
        })
    clients_df = pd.DataFrame(clients_list)
    
    if not clients_df.empty:
        st.subheader("Edit or Delete Clients")
        
        for _, client in clients_df.iterrows():
            with st.expander(f"👤 {client['name']} (Group: {client['group_name'] or 'No Group'})"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    with st.form(f"edit_client_{client['id']}"):
                        new_name = st.text_input("Client Name", value=client['name'], key=f"name_{client['id']}")
                        
                        # Find current group index
                        current_group_name = client['group_name'] or "-- choose group --"
                        group_options = ["-- choose group --"] + group_names
                        current_index = group_options.index(current_group_name) if current_group_name in group_options else 0
                        
                        new_group = st.selectbox("Group", group_options, index=current_index, key=f"group_{client['id']}")
                        
                        if st.form_submit_button("Update Client"):
                            if new_group == "-- choose group --":
                                st.error("Please select a group")
                            else:
                                # Get the new group ID
                                new_group_id_result = supabase_client.table("groups").select("id").eq("name", new_group).execute()
                                if new_group_id_result.data:
                                    new_group_id = new_group_id_result.data[0]["id"]
                                    success, message = update_client(client['id'], new_name, new_group_id)
                                    if success:
                                        st.success(message)
                                        st.rerun()
                                    else:
                                        st.error(message)
                                else:
                                    st.error("Selected group not found in database")
                
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_{client['id']}"):
                        if can_delete_client(client['id']):
                            success, message = delete_client_with_related_data(client['id'])
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                        else:
                            st.error("Cannot delete client: There are loans associated with this client. Delete the loans first.")

    st.subheader("Add a client")
    with st.form("add_client", clear_on_submit=True):
        cname = st.text_input("Client full name")
        gsel = st.selectbox("Group", ["-- choose group --"] + group_names, key="add_client_group")
        
        if st.form_submit_button("Add client"):
            if not cname.strip():
                st.error("Client name cannot be empty")
            elif gsel == "-- choose group --":
                st.error("Choose a group first")
            else:
                group_result = supabase_client.table("groups").select("id").eq("name", gsel).execute()
                if group_result.data:
                    group_id = group_result.data[0]["id"]
                    try:
                        insert_table_data("clients", {
                            "name": cname.strip(),
                            "group_id": group_id
                        })
                        st.success("✅ Client added")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not add client: {e}")
                else:
                    st.error("Selected group not found in database")

    st.subheader("Clients list")
    if not clients_df.empty:
        display_df = clients_df[['name', 'group_name']].copy()
        display_df.columns = ['Client Name', 'Group']
        st.dataframe(display_df)
    else:
        st.info("No clients yet. Add one above.")

# ---------- PAGE: Loans ----------
elif menu == "💰 Loans":
    page_header("Loans")
    
    # Get clients for dropdown
    clients_data = get_table_data("clients", order_by="name")
    clients_df = pd.DataFrame(clients_data) if clients_data else pd.DataFrame()
    client_options = clients_df["name"].tolist() if not clients_df.empty else []
    
    # Get loans data
    loans_list = get_loans_simple_view()
    loans_df = pd.DataFrame(loans_list) if loans_list else pd.DataFrame()
    
    if not loans_df.empty:
        st.subheader("Edit or Delete Loans")
        
        for _, loan in loans_df.iterrows():
            with st.expander(f"💰 {loan['client']} - {loan['loan_date']} (Total: R{loan['total']:.2f})"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    with st.form(f"edit_loan_{loan['id']}"):
                        new_principal = st.number_input("Principal (R)", min_value=0.0, format="%.2f", 
                                                       value=float(loan['principal']), key=f"principal_{loan['id']}")
                        new_due_date = st.date_input("Due Date", 
                                                    value=date.fromisoformat(loan['due_date']), 
                                                    key=f"due_{loan['id']}")
                        
                        if st.form_submit_button("Update Loan"):
                            success, message = update_loan(loan['id'], new_principal, new_due_date)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_loan_{loan['id']}"):
                        success, message = delete_loan_with_related_data(loan['id'])
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

    st.subheader("Create a new loan")
    with st.form("add_loan", clear_on_submit=True):
        client_sel = st.selectbox("Client", ["-- choose client --"] + client_options)
        loan_date = st.date_input("Loan Date", value=date.today())
        due_date = st.date_input("Due Date", value=date.today() + timedelta(days=30))
        principal = st.number_input("Principal (R)", min_value=0.0, format="%.2f", value=0.0)
        
        if st.form_submit_button("Create loan"):
            if client_sel == "-- choose client --":
                st.error("Select a client")
            elif principal <= 0:
                st.error("Principal must be > 0")
            else:
                client_result = supabase_client.table("clients").select("id").eq("name", client_sel).execute()
                if client_result.data:
                    client_id = client_result.data[0]["id"]
                    principal_rounded = round(float(principal), 2)
                    interest = calculate_interest(principal_rounded)
                    total = principal_rounded + interest
                    
                    try:
                        # Create loan
                        loan_data = insert_table_data("loans_new", {
                            "client_id": client_id,
                            "loan_date": loan_date.isoformat(),
                            "original_due_date": due_date.isoformat(),
                            "current_due_date": due_date.isoformat(),
                            "original_principal": principal_rounded,
                            "current_principal": principal_rounded,
                            "status": "Partial"
                        })
                        
                        if loan_data:
                            loan_id = loan_data["id"]
                            
                            # Record initial interest
                            insert_table_data("loan_interest_history", {
                                "loan_id": loan_id,
                                "due_date": due_date.isoformat(),
                                "interest_amount": interest,
                                "principal_at_time": principal_rounded,
                                "added_date": date.today().isoformat(),
                                "is_paid": 0
                            })
                            
                            update_loan_statuses()
                            st.success(f"✅ Loan recorded (Total: R {total:.2f})")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Could not create loan: {e}")
                else:
                    st.error("Selected client not found in database")

    st.subheader("All loans (full details)")
    
    # Update statuses before showing
    update_loan_statuses()
    
    # Refresh loans data
    loans_list = get_loans_simple_view()
    loans_df = pd.DataFrame(loans_list) if loans_list else pd.DataFrame()
    
    if not loans_df.empty:
        display_df = loans_df[['client', 'group_name', 'loan_date', 'due_date', 
                              'principal', 'interest', 'paid', 'total', 'status']].copy()
        display_df.columns = ['Client', 'Group Name', 'Loan Date', 'Due Date', 'Principal', 'Interest', 'Paid', 'Total', 'Status']
        # Apply styling
        styled_df = style_dataframe(display_df)
        st.dataframe(styled_df)
    else:
        st.info("No loans yet. Create one above.")

# ---------- PAGE: Payments ----------
elif menu == "💳 Payments":
    page_header("Payments")
    
    # Update statuses first
    update_loan_statuses()
    
    # Get active loans for dropdown
    try:
        # Get loans that are not paid
        loans_data = supabase_client.table("loans_new").select("*, clients(name)").neq("status", "Paid").order("current_due_date").execute()
        
        active_loans = []
        for loan in loans_data.data:
            # Calculate unpaid interest
            interest_data = supabase_client.table("loan_interest_history").select("interest_amount").eq("loan_id", loan["id"]).eq("is_paid", 0).gt("interest_amount", 0).execute()
            unpaid_interest = sum(item["interest_amount"] for item in interest_data.data)
            
            active_loans.append({
                "id": loan["id"],
                "client_name": loan["clients"]["name"] if loan.get("clients") else "",
                "loan_date": loan["loan_date"],
                "current_due_date": loan["current_due_date"],
                "current_principal": loan["current_principal"],
                "unpaid_interest": unpaid_interest,
                "status": loan["status"]
            })
        
        active_loans_df = pd.DataFrame(active_loans)
    except Exception as e:
        st.error(f"Error fetching active loans: {e}")
        active_loans_df = pd.DataFrame()
    
    st.subheader("Record a payment")
    
    if active_loans_df.empty:
        st.info("No active loans found. All loans may be fully paid.")
    else:
        # Create loan selection options
        loan_options = []
        for _, loan in active_loans_df.iterrows():
            total_owed = loan['current_principal'] + loan['unpaid_interest']
            option_text = f"{loan['client_name']} (Loan: {loan['loan_date']}) - Total: R{total_owed:.2f}, Due: {loan['current_due_date']}"
            loan_options.append((loan['id'], option_text, loan['unpaid_interest'], loan['current_due_date']))
        
        with st.form("add_payment", clear_on_submit=True):
            loan_choices = ["-- choose loan --"] + [opt[1] for opt in loan_options]
            selected_option = st.selectbox("Select loan", loan_choices)
            
            amount = st.number_input("Amount (R)", min_value=0.0, format="%.2f", value=0.0)
            pay_date = st.date_input("Payment date", value=date.today())
            
            if selected_option != "-- choose loan --":
                selected_index = loan_choices.index(selected_option) - 1
                selected_loan_id, _, unpaid_interest, due_date_str = loan_options[selected_index]
                
                col1, col2 = st.columns(2)
                with col1:
                    loan_details = active_loans_df[active_loans_df['id'] == selected_loan_id].iloc[0]
                    st.info(f"**Client:** {loan_details['client_name']}")
                    st.info(f"**Principal:** R {loan_details['current_principal']:.2f}")
                with col2:
                    st.info(f"**Unpaid Interest:** R {unpaid_interest:.2f}")
                    st.info(f"**Due Date:** {due_date_str}")
                
                # Check minimum payment rule
                due_date = date.fromisoformat(due_date_str) if due_date_str else date.today()
                if pay_date >= due_date and unpaid_interest > 0:
                    st.warning(f"⚠️ **Minimum Payment:** Payment is on or after due date. You must pay at least R {unpaid_interest:.2f} (unpaid interest).")
            
            if st.form_submit_button("Record payment"):
                if selected_option == "-- choose loan --":
                    st.error("Select a loan")
                elif amount <= 0:
                    st.error("Amount must be > 0")
                else:
                    selected_index = loan_choices.index(selected_option) - 1
                    selected_loan_id, _, unpaid_interest, due_date_str = loan_options[selected_index]
                    
                    # Enforce minimum payment rule
                    due_date = date.fromisoformat(due_date_str) if due_date_str else date.today()
                    if pay_date >= due_date and amount < unpaid_interest:
                        st.error(f"❌ Minimum payment required: R {unpaid_interest:.2f} (unpaid interest)")
                        st.stop()
                    
                    success, message = process_payment(selected_loan_id, amount, pay_date)
                    
                    if success:
                        st.success(f"✅ Payment recorded")
                        
                        # Show payment breakdown
                        payment_details = supabase_client.table("payments_new").select("*").eq("loan_id", selected_loan_id).order("id", desc=True).limit(1).execute()
                        
                        if payment_details.data:
                            payment = payment_details.data[0]
                            st.info(f"""
                            **Payment Breakdown:**
                            - Applied to Interest: R {payment['applied_to_interest']:.2f}
                            - Applied to Principal: R {payment['applied_to_principal']:.2f}
                            """)
                        
                        st.rerun()
                    else:
                        st.error(f"Payment failed: {message}")

    st.subheader("Recent Payments")
    payments_list = get_payments_simple_view(limit=20)
    payments_df = pd.DataFrame(payments_list) if payments_list else pd.DataFrame()
    
    if not payments_df.empty:
        display_df = payments_df[['client', 'group_name', 'loan_date', 'due_date', 'principal', 'interest', 'paid', 'total', 'payment_date', 'status']].copy()
        display_df.columns = ['Client', 'Group Name', 'Loan Date', 'Due Date', 'Principal', 'Interest', 'Paid', 'Total', 'Payment Date', 'Status']
        # Apply styling
        styled_df = style_dataframe(display_df)
        st.dataframe(styled_df)
    else:
        st.info("No payments recorded yet.")

# ---------- PAGE: Monthly Overview ----------
elif menu == "📆 Monthly Overview":
    page_header("Monthly Overview")
    st.caption("Grouped by month & group. Shows each client, all loan info & statuses")
    
    update_loan_statuses()

    # Get loans data
    loans_list = get_loans_simple_view()
    if loans_list:
        monthly_df = pd.DataFrame(loans_list)
        monthly_df['month'] = monthly_df['due_date'].str[:7]  # Extract YYYY-MM
        
        if not monthly_df.empty:
            months = monthly_df["month"].unique().tolist()
            for m in months:
                st.subheader(f"📅 {m}")
                dfm = monthly_df[monthly_df["month"] == m]
                
                for group_name in dfm["group_name"].unique():
                    st.markdown(f"**📁 {group_name or 'No Group'}**")
                    sub = dfm[dfm["group_name"] == group_name][[
                        "client", "loan_date", "due_date", "principal", 
                        "interest", "paid", "total", "status"
                    ]]
                    
                    # Style the dataframe
                    styled_sub = sub.copy()
                    styled_sub['status'] = styled_sub['status'].apply(status_color)
                    
                    # Create a styled dataframe
                    display_df = styled_sub.style.applymap(
                        lambda x: 'color: red' if isinstance(x, (int, float)) and x > 0 and x == styled_sub['total'].iloc[0] else '',
                        subset=['total']
                    ).applymap(
                        lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 and x == styled_sub['paid'].iloc[0] else '',
                        subset=['paid']
                    )
                    
                    st.dataframe(display_df.format({
                        'principal': '{:.2f}',
                        'interest': '{:.2f}',
                        'paid': '{:.2f}',
                        'total': '{:.2f}'
                    }))
    else:
        st.info("No loans to show in monthly overview.")

# ---------- PAGE: Search ----------
elif menu == "🔍 Search":
    page_header("Search")
    st.markdown("Search by Client, Group, or Due Date")
    
    update_loan_statuses()
    
    search_type = st.radio("Search by", ["Client", "Group", "Due Date"], horizontal=True)
    
    if search_type == "Client":
        q = st.text_input("Client name contains")
        if q:
            loans_list = get_loans_simple_view()
            if loans_list:
                df = pd.DataFrame(loans_list)
                df = df[df['client'].str.contains(q, case=False, na=False)]
                if not df.empty:
                    display_df = df[['client', 'group_name', 'loan_date', 'due_date', 'principal', 'interest', 'paid', 'total', 'status']].copy()
                    styled_df = style_dataframe(display_df)
                    st.dataframe(styled_df)
                else:
                    st.info("No results found")
    
    elif search_type == "Group":
        groups_data = get_table_data("groups", order_by="name")
        groups_df = pd.DataFrame(groups_data) if groups_data else pd.DataFrame()
        gsel = st.selectbox("Select group", ["-- choose --"] + groups_df["name"].tolist() if not groups_df.empty else ["-- choose --"])
        if gsel and gsel != "-- choose --":
            loans_list = get_loans_simple_view()
            if loans_list:
                df = pd.DataFrame(loans_list)
                df = df[df['group_name'] == gsel]
                if not df.empty:
                    display_df = df[['client', 'group_name', 'loan_date', 'due_date', 'principal', 'interest', 'paid', 'total', 'status']].copy()
                    styled_df = style_dataframe(display_df)
                    st.dataframe(styled_df)
                else:
                    st.info("No loans for that group.")
    
    else:  # Due Date
        d = st.date_input("Due Date")
        if d:
            loans_list = get_loans_simple_view()
            if loans_list:
                df = pd.DataFrame(loans_list)
                df = df[df['due_date'] == d.isoformat()]
                if not df.empty:
                    display_df = df[['client', 'group_name', 'loan_date', 'due_date', 'principal', 'interest', 'paid', 'total', 'status']].copy()
                    styled_df = style_dataframe(display_df)
                    st.dataframe(styled_df)
                else:
                    st.info("No loans due on that date")
# ---------- PAGE: PDF Export ----------
elif menu == "🧾 PDF Export":
    page_header("PDF Report")
    
    # Get clients for selection
    clients_data = get_table_data("clients", order_by="name")
    clients_df = pd.DataFrame(clients_data) if clients_data else pd.DataFrame()
    client_names = clients_df["name"].tolist() if not clients_df.empty else []
    
    # Get groups for selection
    groups_data = get_table_data("groups", order_by="name")
    groups_df = pd.DataFrame(groups_data) if groups_data else pd.DataFrame()
    group_names = groups_df["name"].tolist() if not groups_df.empty else []
    
    col1, col2 = st.columns(2)
    with col1:
        export_type = st.radio("Export type", ["Client Statement", "Group Report"])
    
    with col2:
        if export_type == "Client Statement":
            client_sel = st.selectbox("Select client", ["-- choose client --"] + client_names)
        else:
            group_sel = st.selectbox("Select group", ["-- choose group --"] + group_names)
    
    if st.button("Generate PDF"):
        if export_type == "Client Statement" and client_sel == "-- choose client --":
            st.error("Select a client")
        elif export_type == "Group Report" and group_sel == "-- choose group --":
            st.error("Select a group")
        else:
            # Update statuses before generating report
            update_loan_statuses()
            
            if export_type == "Client Statement":
                loans_list = get_loans_simple_view()
                if loans_list:
                    df = pd.DataFrame(loans_list)
                    loans_df = df[df['client'] == client_sel]
                    
                    if loans_df.empty:
                        st.error("No loans found for this client")
                        st.stop()
                    
                    filename = f"{client_sel.replace(' ','_')}_statement_{date.today().isoformat()}.pdf"
                    title = f"Client Statement - {client_sel}"
                    data_type = "client"
                else:
                    st.error("No loans found")
                    st.stop()
                
            else:  # Group Report
                loans_list = get_loans_simple_view()
                if loans_list:
                    df = pd.DataFrame(loans_list)
                    loans_df = df[df['group_name'] == group_sel]
                    
                    if loans_df.empty:
                        st.error("No loans found for this group")
                        st.stop()
                    
                    filename = f"{group_sel.replace(' ','_')}_report_{date.today().isoformat()}.pdf"
                    title = f"Group Report - {group_sel}"
                    data_type = "group"
                else:
                    st.error("No loans found")
                    st.stop()
            
            # ---------- CREATE PDF IN MEMORY ----------
            import io
            buffer = io.BytesIO()
            
            doc = SimpleDocTemplate(buffer)
            styles = getSampleStyleSheet()
            story = []
            
            # Header
            story.append(Paragraph(f"{business_name or 'Loan Management System'}", styles["Title"]))
            story.append(Paragraph(title, styles["Heading1"]))
            story.append(Paragraph(f"Generated: {date.today().isoformat()}", styles["Normal"]))
            story.append(Spacer(1, 12))
            
            # Loans table
            story.append(Paragraph("Loans Overview", styles["Heading2"]))
            
            table_data = [["Client", "Group", "Loan Date", "Due Date", "Principal", "Interest", "Paid", "Total", "Status"]]
            
            for _, row in loans_df.iterrows():
                status_display = status_color(row['status'])
                
                table_data.append([
                    row['client'] if data_type == 'group' else '',
                    row['group_name'] if data_type == 'client' else '',
                    row['loan_date'],
                    row['due_date'],
                    f"R {row['principal']:.2f}",
                    f"R {row['interest']:.2f}",
                    f"R {row['paid']:.2f}",
                    f"R {row['total']:.2f}",
                    status_display.replace("🟢", "").replace("🟡", "").replace("🔴", "").strip()
                ])
            
            t = Table(table_data, repeatRows=1)
            style = TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, rlcolors.black),
                ("BACKGROUND", (0,0), (-1,0), rlcolors.lightgrey),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ])
            
            for i in range(1, len(table_data)):
                total_value = float(table_data[i][7].replace('R', '').strip())
                if total_value > 0:
                    style.add("TEXTCOLOR", (7, i), (7, i), rlcolors.red)
                
                paid_value = float(table_data[i][6].replace('R', '').strip())
                if paid_value > 0:
                    style.add("TEXTCOLOR", (6, i), (6, i), rlcolors.green)
                
                status_text = table_data[i][8]
                if "Paid" in status_text:
                    style.add("TEXTCOLOR", (8, i), (8, i), rlcolors.green)
                elif "Partial" in status_text:
                    style.add("TEXTCOLOR", (8, i), (8, i), rlcolors.orange)
                elif "Overdue" in status_text:
                    style.add("TEXTCOLOR", (8, i), (8, i), rlcolors.red)
            
            t.setStyle(style)
            story.append(t)
            story.append(Spacer(1, 12))
            
            # Summary
            total_principal = loans_df['principal'].sum()
            total_interest = loans_df['interest'].sum()
            total_paid = loans_df['paid'].sum()
            total_total = loans_df['total'].sum()
            
            story.append(Paragraph("Summary", styles["Heading2"]))
            summary_data = [
                ["Total Principal", f"R {total_principal:.2f}"],
                ["Total Interest", f"R {total_interest:.2f}"],
                ["Total Paid", f"R {total_paid:.2f}"],
                ["Total Balance Owing", f"R {total_total:.2f}"]
            ]
            
            summary_table = Table(summary_data, colWidths=[200, 100])
            summary_table.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, rlcolors.black),
                ("BACKGROUND", (0,0), (0,-1), rlcolors.lightgrey),
                ("TEXTCOLOR", (1,3), (1,3), rlcolors.red if total_total > 0 else rlcolors.black),
                ("TEXTCOLOR", (1,2), (1,2), rlcolors.green if total_paid > 0 else rlcolors.black),
            ]))
            story.append(summary_table)
            
            # Build PDF
            doc.build(story)
            pdf_data = buffer.getvalue()
            buffer.close()
            
            st.success("✅ PDF generated successfully!")
            
            st.download_button(
                label="📥 Download PDF",
                data=pdf_data,
                file_name=filename,
                mime="application/pdf",
                help="Click to download the PDF to your computer"
            )
            
            st.info(f"**File will download as:** `{filename}`")

# ---------- PAGE: Change Password ----------
elif menu == "🔐 Change Password":
    page_header("Change Password")
    
    st.subheader("Change your password or email")
    
    # Get current user info
    current_email = st.session_state.user  # This should be the email from Supabase Auth
    
    with st.form("change_password"):
        st.info(f"**Current email:** {current_email}")
        
        current_pw = st.text_input("Current password", type="password")
        new_email = st.text_input("New email (optional)", value=current_email)
        new_pw = st.text_input("New password", type="password")
        confirm_pw = st.text_input("Confirm new password", type="password")
        
        if st.form_submit_button("Update credentials"):
            if not current_pw:
                st.error("Current password is required")
            elif new_pw and new_pw != confirm_pw:
                st.error("New passwords do not match")
            elif new_pw and len(new_pw) < 6:
                st.error("New password must be at least 6 characters")
            else:
                try:
                    # First, verify current password by trying to re-authenticate
                    try:
                        # This verifies the current password is correct
                        supabase_client.auth.sign_in_with_password({
                            "email": current_email,
                            "password": current_pw
                        })
                    except Exception as auth_error:
                        st.error("Current password is incorrect")
                        st.stop()
                    
                    # Update email if changed
                    if new_email != current_email:
                        try:
                            supabase_client.auth.update_user({
                                "email": new_email
                            })
                            st.session_state.user = new_email
                            st.success("✅ Email updated successfully")
                        except Exception as email_error:
                            if "already registered" in str(email_error):
                                st.error("This email is already registered to another account")
                            else:
                                st.error(f"Error updating email: {str(email_error)}")
                            st.stop()
                    
                    # Update password if provided
                    if new_pw:
                        try:
                            supabase_client.auth.update_user({
                                "password": new_pw
                            })
                            st.success("✅ Password updated successfully")
                        except Exception as pw_error:
                            st.error(f"Error updating password: {str(pw_error)}")
                            st.stop()
                    
                    # Show success message
                    if new_email != current_email and new_pw:
                        st.success("✅ Email and password updated successfully! Please login again.")
                    elif new_email != current_email:
                        st.success("✅ Email updated successfully!")
                    elif new_pw:
                        st.success("✅ Password updated successfully!")
                    else:
                        st.info("No changes were made")
                    
                    # If email was changed, suggest re-login
                    if new_email != current_email:
                        st.warning("Since you changed your email, you might need to login again on your next visit.")
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error updating credentials: {str(e)}")
    
    # Additional security options
    with st.expander("🔒 Advanced Security Options"):
        st.markdown("""
        **Password Requirements:**
        - At least 6 characters
        - Case sensitive
        
        **Security Notes:**
        - Passwords are encrypted by Supabase
        - Never share your password
        - Use a strong, unique password
        """)
        
        # Option to reset password via email
        if st.button("Send password reset email"):
            try:
                supabase_client.auth.reset_password_for_email(current_email, {
                    "redirect_to": f"{st.secrets.SUPABASE_URL}/auth/confirm"
                })
                st.success("📧 Password reset email sent! Check your inbox.")
            except Exception as e:
                st.error(f"Error sending reset email: {str(e)}")

# ---------- PAGE: Logout ----------
elif menu == "🚪 Logout":
    page_header("Logout")
    st.write("Are you sure you want to logout?")
    if st.button("Yes, logout"):
        logout()


# ---------- END ----------
update_loan_statuses()
daily_backup()
