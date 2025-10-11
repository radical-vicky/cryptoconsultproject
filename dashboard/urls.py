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
    
    # ADD THIS LINE - Support the /analysis/4/ pattern
    path('analysis/<int:analysis_id>/', views.view_analysis, name='view_analysis_old'),
    
    path('view-analysis/<int:analysis_id>/', views.view_analysis, name='view_analysis'),
    path('market-insights/', views.market_insights, name='market_insights'),
    path('market-insights/<int:insight_id>/', views.view_market_insight, name='view_market_insight'),
    path('instant-purchase/', views.instant_purchase, name='instant_purchase'),
    path('check-balance/', views.check_wallet_balance, name='check_balance'),
    path('download-analysis/<int:analysis_id>/', views.download_analysis, name='download_analysis'),
    path('refresh-analysis/<int:analysis_id>/', views.refresh_analysis, name='refresh_analysis'),
]