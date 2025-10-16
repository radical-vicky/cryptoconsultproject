from django.urls import path
from . import views

urlpatterns = [
    path('', views.base, name='base'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('marketplace/', views.marketplace, name='marketplace'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('payment-methods/', views.payment_methods, name='payment_methods'),
    path('deposit/', views.deposit_funds, name='deposit'),
    path('withdraw/', views.withdraw_funds, name='withdraw'),
    path('wallet/', views.wallet, name='wallet'),
    path('profile/', views.profile, name='profile'),
    path('wallet/add-funds/', views.add_funds, name='add_funds'),
    path('wallet/transaction-history/', views.transaction_history, name='transaction_history'),
    path('purchase_analysis/', views.purchase_analysis, name='purchase_analysis'),
    path('book_consultation/', views.book_consultation, name='book_consultation'),
    path('my-consultations/', views.my_consultations, name='my_consultations'),
    
    # Analysis viewing URLs - multiple patterns for compatibility
    path('analysis/<int:analysis_id>/', views.view_analysis, name='view_analysis_old'),
    path('view-analysis/<int:analysis_id>/', views.view_analysis, name='view_analysis'),
    
    path('market-insights/', views.market_insights, name='market_insights'),
    path('market-insights/<int:insight_id>/', views.view_market_insight, name='view_market_insight'),
    path('instant-purchase/', views.instant_purchase, name='instant_purchase'),
    path('check-balance/', views.check_wallet_balance, name='check_balance'),
    path('download-analysis/<int:analysis_id>/', views.download_analysis, name='download_analysis'),
    path('refresh-analysis/<int:analysis_id>/', views.refresh_analysis, name='refresh_analysis'),
    
    # M-Pesa URLs - Updated with correct patterns
    path('mpesa/deposit/initiate/', views.initiate_mpesa_deposit, name='initiate_mpesa_deposit'),
    path('mpesa/withdrawal/initiate/', views.initiate_mpesa_withdrawal, name='initiate_mpesa_withdrawal'),
    path('mpesa/callback/', views.mpesa_callback, name='mpesa_callback'),
    path('mpesa/withdrawal/callback/', views.mpesa_withdrawal_callback, name='mpesa_withdrawal_callback'),
    
    # New M-Pesa Analysis Purchase URLs
    path('mpesa/purchase-analysis/', views.purchase_analysis_mpesa, name='purchase_analysis_mpesa'),
    path('mpesa/analysis-purchase/callback/', views.mpesa_analysis_purchase_callback, name='mpesa_analysis_purchase_callback'),
    path('mpesa/check-payment-status/<str:checkout_request_id>/', views.check_mpesa_payment_status, name='check_mpesa_payment_status'),
    # urls.py - Add these patterns


    # M-Pesa URLs
    path('purchase-analysis-mpesa/', views.purchase_analysis_mpesa, name='purchase_analysis_mpesa'),
    path('mpesa/analysis-purchase/callback/', views.mpesa_analysis_purchase_callback, name='mpesa_analysis_purchase_callback'),
    path('check-mpesa-status/<str:checkout_request_id>/', views.check_mpesa_payment_status, name='check_mpesa_payment_status'),

    # Transaction and debug URLs
    path('transaction-status/<int:transaction_id>/', views.check_mpesa_transaction_status, name='check_mpesa_status'),
    path('debug-wallet/', views.debug_wallet, name='debug_wallet'),
    path('debug/withdrawal/', views.debug_withdrawal, name='debug_withdrawal'),
    path('api/analysis/<int:analysis_id>/', views.analysis_detail_api, name='analysis_detail_api'),

]