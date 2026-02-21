from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    
    # Main
    path('dashboard/', views.dashboard, name='dashboard'),
    path('groups/', views.groups, name='groups'),
    path('clients/', views.clients, name='clients'),
    path('loans/', views.loans, name='loans'),
    path('payments/', views.payments, name='payments'),
    path('monthly-overview/', views.monthly_overview, name='monthly_overview'),
    path('search/', views.search, name='search'),
    path('pdf-export/', views.pdf_export, name='pdf_export'),
    path('change-password/', views.change_password, name='change_password'),
    path('set-business-name/', views.set_business_name, name='set_business_name'),
]
