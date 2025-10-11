from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction as db_transaction
from django.db.models import Sum, Avg, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
import random
import json
import time
import threading
from .models import (
    SiteSetting, UserWallet, UserProfile, Transaction, 
    CryptoAnalysis, PurchasedAnalysis, Analyst, Consultation, 
    ConsultationPackage, MarketInsight, ChartAnnotation, 
    TechnicalIndicatorData, AnalysisInsight, AnalysisMetric
)
from .forms import UserUpdateForm, UserProfileForm, PaymentMethodForm, DepositForm, WithdrawalForm


# In your base view or context processor
def base(request):
    # Get consultation packages from database
    consultation_packages = ConsultationPackage.objects.filter(is_active=True)
    
    # Convert to list of dicts for template compatibility
    packages_data = []
    for package in consultation_packages:
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': str(package.price),  # String format for display
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
            'duration_minutes': package.duration_minutes,
        })
    
    # Get site settings including hero video - FIXED THIS PART
    site_settings = SiteSetting.objects.filter(is_active=True).first()
    hero_video = site_settings.hero_video if site_settings else None
    
    context = {
        'consultation_packages': packages_data,
        'hero_video': hero_video,  # Now passing the actual video file, not the object
        'site_settings': site_settings,  # Optional: if you need the full object elsewhere
    }
    
    # Add user_wallet if user is authenticated
    if request.user.is_authenticated:
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        context['user_wallet'] = user_wallet
    
    return render(request, 'base.html', context)

@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=user_profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            
            # Update wallet payment details if provided
            mpesa_number = request.POST.get('mpesa_number')
            paypal_email = request.POST.get('paypal_email')
            
            if mpesa_number:
                user_wallet.mpesa_number = mpesa_number
            if paypal_email:
                user_wallet.paypal_email = paypal_email
            user_wallet.save()
            
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=user_profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'user_profile': user_profile,
        'user_wallet': user_wallet,
    }
    return render(request, 'dashboard/profile.html', context)

@login_required
def payment_methods(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user)[:10]
    
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST, instance=user_wallet)
        if form.is_valid():
            form.save()
            messages.success(request, 'Payment methods updated successfully!')
            return redirect('payment_methods')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PaymentMethodForm(instance=user_wallet)
    
    context = {
        'user_wallet': user_wallet,
        'form': form,
        'transactions': transactions,
    }
    return render(request, 'dashboard/payment_methods.html', context)

@login_required
def deposit_funds(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = DepositForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            
            # Check deposit limits
            if not user_wallet.can_deposit(amount):
                messages.error(request, f'Deposit amount exceeds your daily limit of ${user_wallet.daily_deposit_limit}.')
                return redirect('deposit_funds')
            
            # Simulate payment processing
            if payment_method == 'mpesa':
                if not user_wallet.mpesa_number:
                    messages.error(request, 'Please add your M-Pesa number first.')
                    return redirect('payment_methods')
                
                # Simulate M-Pesa STK push
                mpesa_code = f"MP{random.randint(100000, 999999)}"
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='deposit',
                    payment_method='mpesa',
                    status='pending',
                    description=f'M-Pesa deposit to {user_wallet.mpesa_number}',
                    mpesa_code=mpesa_code
                )
                
                messages.info(request, f'M-Pesa STK push sent to {user_wallet.mpesa_number}. Please complete the payment on your phone.')
                
                def process_deposit():
                    time.sleep(3)
                    with db_transaction.atomic():
                        transaction.status = 'completed'
                        transaction.save()
                        user_wallet.balance += amount
                        user_wallet.total_deposited += amount
                        user_wallet.save()
                
                thread = threading.Thread(target=process_deposit)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'Deposit of ${amount} initiated successfully!')
                return redirect('wallet')
                
            elif payment_method == 'paypal':
                if not user_wallet.paypal_email:
                    messages.error(request, 'Please add your PayPal email first.')
                    return redirect('payment_methods')
                
                # Simulate PayPal payment
                paypal_id = f"PP{random.randint(100000000, 999999999)}"
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='deposit',
                    payment_method='paypal',
                    status='pending',
                    description=f'PayPal deposit from {user_wallet.paypal_email}',
                    paypal_transaction_id=paypal_id
                )
                
                messages.info(request, f'Redirecting to PayPal for payment of ${amount}...')
                
                def process_paypal_deposit():
                    time.sleep(2)
                    with db_transaction.atomic():
                        transaction.status = 'completed'
                        transaction.save()
                        user_wallet.balance += amount
                        user_wallet.total_deposited += amount
                        user_wallet.save()
                
                thread = threading.Thread(target=process_paypal_deposit)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'PayPal deposit of ${amount} completed successfully!')
                return redirect('wallet')
                
    else:
        form = DepositForm()
    
    context = {
        'form': form,
        'user_wallet': user_wallet,
    }
    return render(request, 'dashboard/deposit.html', context)

@login_required
def withdraw_funds(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            
            # Check withdrawal limits and balance
            if not user_wallet.can_withdraw(amount):
                messages.error(request, 'Insufficient balance or amount exceeds withdrawal limit.')
                return redirect('withdraw_funds')
            
            # Process withdrawal
            if payment_method == 'mpesa':
                if not user_wallet.mpesa_number:
                    messages.error(request, 'Please add your M-Pesa number first.')
                    return redirect('payment_methods')
                
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='withdrawal',
                    payment_method='mpesa',
                    status='pending',
                    description=f'M-Pesa withdrawal to {user_wallet.mpesa_number}'
                )
                
                # Simulate M-Pesa processing
                def process_withdrawal():
                    time.sleep(3)
                    with db_transaction.atomic():
                        transaction.status = 'completed'
                        transaction.save()
                        user_wallet.balance -= amount
                        user_wallet.total_withdrawn += amount
                        user_wallet.save()
                
                thread = threading.Thread(target=process_withdrawal)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'Withdrawal of ${amount} to M-Pesa initiated!')
                return redirect('wallet')
                
            elif payment_method == 'paypal':
                if not user_wallet.paypal_email:
                    messages.error(request, 'Please add your PayPal email first.')
                    return redirect('payment_methods')
                
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    transaction_type='withdrawal',
                    payment_method='paypal',
                    status='pending',
                    description=f'PayPal withdrawal to {user_wallet.paypal_email}'
                )
                
                # Simulate PayPal processing
                def process_paypal_withdrawal():
                    time.sleep(2)
                    with db_transaction.atomic():
                        transaction.status = 'completed'
                        transaction.save()
                        user_wallet.balance -= amount
                        user_wallet.total_withdrawn += amount
                        user_wallet.save()
                
                thread = threading.Thread(target=process_paypal_withdrawal)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'Withdrawal of ${amount} to PayPal initiated!')
                return redirect('wallet')
                
    else:
        form = WithdrawalForm()
    
    context = {
        'form': form,
        'user_wallet': user_wallet,
    }
    return render(request, 'dashboard/withdraw.html', context)

@login_required
def wallet(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:20]
    
    # Debug information
    print(f"Wallet Debug - User: {request.user}")
    print(f"Wallet balance: {user_wallet.balance}")
    print(f"Transaction count: {transactions.count()}")
    for t in transactions:
        print(f"Transaction: {t.id}, {t.transaction_type}, ${t.amount}, {t.description}")
    
    context = {
        'user_wallet': user_wallet,
        'transactions': transactions,
    }
    return render(request, 'dashboard/wallet.html', context)

@login_required
def add_funds(request):
    """Alternative add funds view that works with the wallet template"""
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        
        try:
            amount = Decimal(amount)
            if amount <= Decimal('0'):
                messages.error(request, 'Amount must be greater than 0')
                return redirect('wallet')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid amount')
            return redirect('wallet')
        
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        # Add funds to wallet
        user_wallet.balance += amount
        user_wallet.total_deposited += amount
        user_wallet.save()
        
        # Create transaction record
        transaction = Transaction.objects.create(
            user=request.user,
            amount=amount,
            transaction_type='deposit',
            payment_method=payment_method,
            status='completed',
            description=f'Added funds via {payment_method}'
        )
        
        print(f"Created transaction: {transaction.id} for user {request.user}")
        
        messages.success(request, f'Successfully added ${amount:.2f} to your wallet')
        return redirect('wallet')
    
    return redirect('wallet')

@login_required
def transaction_history(request):
    """View for full transaction history"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate counts for the summary
    completed_count = transactions.filter(status='completed').count()
    pending_count = transactions.filter(status='pending').count()
    
    context = {
        'user_wallet': user_wallet,
        'transactions': transactions,
        'completed_count': completed_count,
        'pending_count': pending_count,
    }
    return render(request, 'dashboard/transaction_history.html', context)

@login_required
def debug_wallet(request):
    """Debug view to check wallet and transaction status"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    all_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    
    debug_info = {
        'user': str(request.user),
        'wallet_created': created,
        'wallet_balance': str(user_wallet.balance),
        'total_deposited': str(user_wallet.total_deposited),
        'total_withdrawn': str(user_wallet.total_withdrawn),
        'total_transactions': all_transactions.count(),
        'transactions': list(all_transactions.values('id', 'transaction_type', 'amount', 'description', 'status', 'created_at')),
        'purchased_analyses': PurchasedAnalysis.objects.filter(user=request.user).count(),
    }
    
    return JsonResponse(debug_info)

@login_required
def dashboard(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Get user stats
    purchased_count = PurchasedAnalysis.objects.filter(user=request.user).count()
    
    # Calculate total spent on analyses
    total_spent_result = PurchasedAnalysis.objects.filter(user=request.user).aggregate(
        total=Sum('purchase_price')
    )
    total_spent = total_spent_result['total'] or Decimal('0.00')
    
    # Calculate total investment
    total_investment = total_spent
    
    # Get recent transactions
    recent_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    
    # Consultation count
    consultation_count = Consultation.objects.filter(user=request.user, status='scheduled').count()
    
    # Get purchased analyses for the user
    purchased_analyses = PurchasedAnalysis.objects.filter(
        user=request.user
    ).select_related('analysis').order_by('-purchased_at')[:3]
    
    # Get user consultations
    user_consultations = Consultation.objects.filter(
        user=request.user, 
        status='scheduled'
    ).order_by('scheduled_date')[:3]
    
    # Get consultation packages from database
    consultation_packages = ConsultationPackage.objects.filter(is_active=True)
    
    # Convert to list of dicts for template compatibility
    packages_data = []
    for package in consultation_packages:
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': package.price,
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
        })
    
    # GET MARKET INSIGHTS FROM DATABASE
    # Get featured market insights
    market_insights = MarketInsight.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by('-published_at', '-created_at')[:6]
    
    # If no featured insights, get recent ones
    if not market_insights:
        market_insights = MarketInsight.objects.filter(
            is_active=True
        ).order_by('-published_at', '-created_at')[:6]
    
    # Get user's purchased analysis IDs for button logic
    purchased_analysis_ids = PurchasedAnalysis.objects.filter(
        user=request.user
    ).values_list('analysis_id', flat=True)
    
    context = {
        'user_wallet': user_wallet,
        'purchased_count': purchased_count,
        'total_spent': total_spent,
        'total_investment': total_investment,
        'consultation_count': consultation_count,
        'recent_transactions': recent_transactions,
        'purchased_analyses': purchased_analyses,
        'user_consultations': user_consultations,
        'consultation_packages': packages_data,
        'market_insights': market_insights,  # Add market insights to context
        'purchased_analysis_ids': list(purchased_analysis_ids),  # Add purchased IDs
    }
    return render(request, 'dashboard/dashboard.html', context)

@login_required
def marketplace(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Get search and filter parameters
    search_query = request.GET.get('search', '')
    analysis_type = request.GET.get('type', '')
    risk_level = request.GET.get('risk', '')
    recommendation = request.GET.get('recommendation', '')
    
    # Build query
    analyses = CryptoAnalysis.objects.filter(is_active=True).select_related('analyst', 'analyst__user')
    
    if search_query:
        analyses = analyses.filter(
            Q(cryptocurrency__icontains=search_query) |
            Q(symbol__icontains=search_query) |
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if analysis_type:
        analyses = analyses.filter(analysis_type=analysis_type)
    
    if risk_level:
        analyses = analyses.filter(risk_level=risk_level)
        
    if recommendation:
        analyses = analyses.filter(recommendation=recommendation)
    
    # Get user's purchased analyses
    purchased_analysis_ids = PurchasedAnalysis.objects.filter(
        user=request.user
    ).values_list('analysis_id', flat=True)
    
    # Add purchase status to each analysis
    for analysis in analyses:
        analysis.is_purchased = analysis.id in purchased_analysis_ids
    
    # Calculate stats
    purchased_count = PurchasedAnalysis.objects.filter(user=request.user).count()
    total_spent_result = PurchasedAnalysis.objects.filter(user=request.user).aggregate(
        total=Sum('purchase_price')
    )
    total_spent = total_spent_result['total'] or Decimal('0.00')
    
    context = {
        'analyses': analyses,
        'user_wallet': user_wallet,
        'purchased_count': purchased_count,
        'total_spent': total_spent,
        'search_query': search_query,
        'selected_type': analysis_type,
        'selected_risk': risk_level,
        'selected_recommendation': recommendation,
    }
    return render(request, 'dashboard/marketplace.html', context)

@login_required
def purchase_analysis(request):
    """Handle analysis purchases from wallet balance"""
    if request.method == 'POST':
        analysis_id = request.POST.get('analysis_id')
        
        if not analysis_id:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': 'No analysis selected.'
                })
            messages.error(request, 'No analysis selected.')
            return redirect('marketplace')
        
        try:
            analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        except CryptoAnalysis.DoesNotExist:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': 'Analysis not found.'
                })
            messages.error(request, 'Analysis not found.')
            return redirect('marketplace')
        
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        # Check if already purchased
        if PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'already_purchased',
                    'message': 'You have already purchased this analysis.',
                    'redirect_url': f'/view-analysis/{analysis.id}/'
                })
            messages.warning(request, 'You have already purchased this analysis.')
            return redirect('view_analysis', analysis_id=analysis.id)
        
        # Check balance
        if user_wallet.balance < analysis.price:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': 'Insufficient balance to purchase this analysis.'
                })
            messages.error(request, 'Insufficient balance to purchase this analysis.')
            return redirect('marketplace')
        
        # Process purchase with wallet balance
        try:
            with db_transaction.atomic():
                # Deduct from wallet
                user_wallet.balance -= analysis.price
                user_wallet.save()
                
                # Create purchase record
                purchase = PurchasedAnalysis.objects.create(
                    user=request.user,
                    analysis=analysis,
                    purchase_price=analysis.price
                )
                
                # Create transaction record
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=analysis.price,
                    transaction_type='purchase',
                    payment_method='wallet',
                    status='completed',
                    description=f'Purchase: {analysis.cryptocurrency} Analysis',
                    analysis=analysis
                )
                
                # Update analysis sales count
                analysis.sales_count += 1
                analysis.total_revenue += analysis.price
                analysis.save()
                
                print(f"Purchase successful: {analysis.cryptocurrency} for ${analysis.price}")
                print(f"New balance: ${user_wallet.balance}")
                print(f"Transaction created: {transaction.id}")
            
            # Success response
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'message': f'Successfully purchased {analysis.cryptocurrency} analysis!',
                    'analysis_id': analysis.id,
                    'analysis_name': analysis.cryptocurrency,
                    'price': str(analysis.price),
                    'new_balance': str(user_wallet.balance),
                    'redirect_url': f'/view-analysis/{analysis.id}/'
                })
            
            messages.success(request, f'Successfully purchased {analysis.cryptocurrency} analysis!')
            return redirect('view_analysis', analysis_id=analysis.id)
            
        except Exception as e:
            print(f"Purchase error: {str(e)}")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': f'Purchase failed: {str(e)}'
                })
            messages.error(request, f'Purchase failed: {str(e)}')
            return redirect('marketplace')
    
    # GET request - show purchased analyses
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    purchased_analyses = PurchasedAnalysis.objects.filter(
        user=request.user
    ).select_related('analysis', 'analysis__analyst', 'analysis__analyst__user').order_by('-purchased_at')
    
    # Calculate stats
    total_investment = sum(p.purchase_price for p in purchased_analyses)
    active_analyses = purchased_analyses.filter(access_expires__isnull=True).count()
    average_rating_result = purchased_analyses.aggregate(avg_rating=Avg('rating_given'))
    average_rating = average_rating_result['avg_rating'] or Decimal('4.5')
    
    context = {
        'purchased_analyses': purchased_analyses,
        'user_wallet': user_wallet,
        'total_investment': total_investment,
        'active_analyses': active_analyses,
        'average_rating': average_rating,
    }
    return render(request, 'dashboard/purchase_analysis.html', context)

@login_required
@csrf_exempt
def instant_purchase(request):
    """AJAX endpoint for instant purchases from wallet"""
    if request.method == 'POST':
        analysis_id = request.POST.get('analysis_id')
        
        if not analysis_id:
            return JsonResponse({
                'status': 'error',
                'message': 'No analysis selected.'
            })
        
        try:
            analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        except CryptoAnalysis.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Analysis not found.'
            })
        
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        # Check if already purchased
        if PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
            return JsonResponse({
                'status': 'already_purchased',
                'message': 'You already own this analysis.',
                'redirect_url': f'/view-analysis/{analysis.id}/'
            })
        
        # Check balance
        if user_wallet.balance < analysis.price:
            return JsonResponse({
                'status': 'error',
                'message': f'Insufficient balance. You need ${analysis.price} but only have ${user_wallet.balance}.'
            })
        
        # Process instant purchase
        try:
            with db_transaction.atomic():
                # Deduct from wallet
                user_wallet.balance -= analysis.price
                user_wallet.save()
                
                # Create purchase record
                purchase = PurchasedAnalysis.objects.create(
                    user=request.user,
                    analysis=analysis,
                    purchase_price=analysis.price
                )
                
                # Create transaction record
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=analysis.price,
                    transaction_type='purchase',
                    payment_method='wallet',
                    status='completed',
                    description=f'Instant Purchase: {analysis.cryptocurrency} Analysis',
                    analysis=analysis
                )
                
                # Update analysis sales count
                analysis.sales_count += 1
                analysis.total_revenue += analysis.price
                analysis.save()
                
                print(f"Instant purchase successful: {analysis.cryptocurrency}")
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully purchased {analysis.cryptocurrency} analysis!',
                'analysis_id': analysis.id,
                'analysis_name': analysis.cryptocurrency,
                'price': str(analysis.price),
                'new_balance': str(user_wallet.balance),
                'redirect_url': f'/view-analysis/{analysis.id}/'
            })
            
        except Exception as e:
            print(f"Instant purchase error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Purchase failed: {str(e)}'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    })

@login_required
def check_wallet_balance(request):
    """AJAX endpoint to check wallet balance"""
    if request.method == 'GET' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        return JsonResponse({
            'status': 'success',
            'balance': str(user_wallet.balance)
        })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request.'
    })

@login_required
def portfolio(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    purchased_analyses = PurchasedAnalysis.objects.filter(
        user=request.user
    ).select_related('analysis').order_by('-purchased_at')
    
    # Calculate portfolio stats
    total_investment = sum(p.purchase_price for p in purchased_analyses)
    active_analyses = purchased_analyses.filter(access_expires__isnull=True).count()
    completed_analyses = purchased_analyses.filter(access_expires__isnull=False).count()
    
    context = {
        'user_wallet': user_wallet,
        'purchased_analyses': purchased_analyses,
        'total_investment': total_investment,
        'active_analyses': active_analyses,
        'completed_analyses': completed_analyses,
    }
    return render(request, 'dashboard/portfolio.html', context)

@login_required
def book_consultation(request):
    if request.method == 'POST':
        package_id = request.POST.get('package_id')
        scheduled_date = request.POST.get('scheduled_date')
        
        try:
            package = ConsultationPackage.objects.get(id=package_id, is_active=True)
        except ConsultationPackage.DoesNotExist:
            messages.error(request, 'Invalid consultation package selected.')
            return redirect('book_consultation')
        
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        # Check if scheduled_date is provided
        if not scheduled_date:
            messages.error(request, 'Please select a date and time for your consultation.')
            return redirect('book_consultation')
        
        # Check balance
        if user_wallet.balance < package.price:
            messages.error(request, 'Insufficient balance to book this consultation.')
            return redirect('book_consultation')
        
        try:
            # Parse the scheduled_date
            scheduled_datetime = timezone.make_aware(
                datetime.strptime(scheduled_date, '%Y-%m-%dT%H:%M')
            )
            
            # Check if the scheduled date is in the future
            if scheduled_datetime <= timezone.now():
                messages.error(request, 'Please select a future date and time for your consultation.')
                return redirect('book_consultation')
            
            # Create consultation
            consultation = Consultation.objects.create(
                user=request.user,
                title=package.title,
                level=package.level,
                description=f"{package.title} - Scheduled session",
                price=package.price,
                scheduled_date=scheduled_datetime,
                status='scheduled'
            )
            
            # Deduct from wallet
            user_wallet.balance -= package.price
            user_wallet.save()
            
            # Create transaction
            Transaction.objects.create(
                user=request.user,
                amount=package.price,
                transaction_type='payment',
                payment_method='wallet',
                status='completed',
                description=f"Consultation: {package.title}",
                consultation=consultation
            )
            
            messages.success(request, f"Successfully booked {package.title} for {scheduled_datetime.strftime('%B %d, %Y at %I:%M %p')}!")
            return redirect('dashboard')
            
        except ValueError:
            messages.error(request, 'Invalid date format. Please try again.')
            return redirect('book_consultation')
    
    # GET request - show consultation booking page
    consultation_packages = ConsultationPackage.objects.filter(is_active=True)
    
    # Convert to list of dicts for template compatibility
    packages_data = []
    for package in consultation_packages:
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': package.price,
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
        })
    
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    context = {
        'consultation_packages': packages_data,
        'user_wallet': user_wallet,
    }
    return render(request, 'dashboard/book_consultation.html', context)

@login_required
def my_consultations(request):
    """View for users to see their consultation bookings and status"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Get all user consultations
    all_consultations = Consultation.objects.filter(user=request.user).order_by('-scheduled_date')
    
    # Categorize consultations
    upcoming_consultations = all_consultations.filter(
        status='scheduled',
        scheduled_date__gte=timezone.now()
    ).order_by('scheduled_date')
    
    completed_consultations = all_consultations.filter(status='completed')
    cancelled_consultations = all_consultations.filter(status='cancelled')
    
    # Calculate stats
    scheduled_count = upcoming_consultations.count()
    completed_count = completed_consultations.count()
    cancelled_count = cancelled_consultations.count()
    
    # Calculate total invested
    total_invested_result = all_consultations.aggregate(total=Sum('price'))
    total_invested = total_invested_result['total'] or Decimal('0.00')
    
    # Get next consultation
    next_consultation = upcoming_consultations.first()
    
    context = {
        'user_wallet': user_wallet,
        'upcoming_consultations': upcoming_consultations,
        'completed_consultations': completed_consultations,
        'cancelled_consultations': cancelled_consultations,
        'scheduled_count': scheduled_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
        'total_invested': total_invested,
        'next_consultation': next_consultation,
    }
    
    return render(request, 'dashboard/my_consultations.html', context)

@login_required
def view_analysis(request, analysis_id):
    """View for users to view a specific purchased analysis"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Check if analysis_id is valid
    if analysis_id <= 0:
        messages.error(request, 'Invalid analysis ID.')
        return redirect('marketplace')
    
    try:
        # Get the analysis      
        analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
    except CryptoAnalysis.DoesNotExist:
        messages.error(request, 'Analysis not found or no longer available.')
        return redirect('marketplace')
    
    # Check if user has purchased this analysis
    try:
        purchase = PurchasedAnalysis.objects.get(user=request.user, analysis=analysis)
    except PurchasedAnalysis.DoesNotExist:
        messages.error(request, 'You have not purchased this analysis.')
        return redirect('marketplace')
    
    # Get similar analyses for recommendation
    similar_analyses = CryptoAnalysis.objects.filter(
        is_active=True,
        cryptocurrency=analysis.cryptocurrency
    ).exclude(id=analysis_id).select_related('analyst')[:3]
    
    # Get chart annotations
    chart_annotations = analysis.chart_annotations.all()
    
    # Get technical indicators
    technical_indicators = analysis.indicator_data.all()
    
    # Get insights
    insights = analysis.insights.all()
    
    # Get metrics
    metrics = analysis.metrics.all()
    
    context = {
        'analysis': analysis,
        'purchase': purchase,
        'user_wallet': user_wallet,
        'similar_analyses': similar_analyses,
        'chart_annotations': chart_annotations,
        'technical_indicators': technical_indicators,
        'insights': insights,
        'metrics': metrics,
    }
    return render(request, 'dashboard/view_analysis.html', context)

@login_required
def market_insights(request):
    """View for all market insights"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Get filter parameters
    insight_type = request.GET.get('type', '')
    urgency = request.GET.get('urgency', '')
    cryptocurrency = request.GET.get('crypto', '')
    
    # Build query
    market_insights = MarketInsight.objects.filter(is_active=True)
    
    if insight_type:
        market_insights = market_insights.filter(insight_type=insight_type)
    
    if urgency:
        market_insights = market_insights.filter(urgency=urgency)
    
    if cryptocurrency:
        market_insights = market_insights.filter(cryptocurrency__icontains=cryptocurrency)
    
    # Order by published date
    market_insights = market_insights.order_by('-published_at', '-created_at')
    
    # Get featured insights for sidebar
    featured_insights = MarketInsight.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by('-published_at')[:5]
    
    # Get recent insights for sidebar
    recent_insights = MarketInsight.objects.filter(
        is_active=True
    ).order_by('-published_at')[:5]
    
    context = {
        'user_wallet': user_wallet,
        'market_insights': market_insights,
        'featured_insights': featured_insights,
        'recent_insights': recent_insights,
        'selected_type': insight_type,
        'selected_urgency': urgency,
        'selected_crypto': cryptocurrency,
    }
    return render(request, 'dashboard/market_insights.html', context)

@login_required
def view_market_insight(request, insight_id):
    """View for a single market insight"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    # Get the insight - MarketInsight doesn't have author field, it has verified_by
    insight = get_object_or_404(
        MarketInsight.objects.select_related('verified_by', 'verified_by__user'), 
        id=insight_id, 
        is_active=True
    )
    
    # Increment view count
    insight.views_count += 1
    insight.save()
    
    # Get related insights
    related_insights = MarketInsight.objects.filter(
        is_active=True,
        cryptocurrency=insight.cryptocurrency
    ).exclude(id=insight_id).order_by('-published_at')[:3]
    
    # If no related insights by cryptocurrency, get by type
    if not related_insights:
        related_insights = MarketInsight.objects.filter(
            is_active=True,
            insight_type=insight.insight_type
        ).exclude(id=insight_id).order_by('-published_at')[:3]
    
    # Prepare author/verifier information for template
    author_info = {
        'name': 'CryptoConsult Team',  # Default name
        'has_analyst_profile': False,
        'is_verified': insight.is_verified,
        'specialization': None,
    }
    
    # If there's a verified_by analyst, use their information
    if insight.verified_by:
        author_info.update({
            'name': insight.verified_by.user.get_full_name() or insight.verified_by.user.username,
            'has_analyst_profile': True,
            'is_verified': insight.verified_by.is_verified,
            'specialization': insight.verified_by.specialization,
        })
    
    context = {
        'user_wallet': user_wallet,
        'insight': insight,
        'related_insights': related_insights,
        'author_info': author_info,
    }
    return render(request, 'dashboard/view_market_insight.html', context)
@login_required
def download_analysis(request, analysis_id):
    """Handle analysis PDF download"""
    try:
        analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        
        # Check if user has purchased this analysis
        if not PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
            messages.error(request, "You don't have access to this analysis.")
            return redirect('marketplace')
        
        # For now, return a simple response - you can implement PDF generation later
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="analysis_{analysis_id}.pdf"'
        
        # Simple PDF content - you can replace this with actual PDF generation
        response.write(f"Analysis Report #{analysis_id}\n")
        response.write(f"Cryptocurrency: {analysis.cryptocurrency}\n")
        response.write(f"Description: {analysis.description}\n")
        response.write(f"Price: ${analysis.price}\n")
        response.write(f"Risk Level: {analysis.get_risk_level_display()}\n")
        
        return response
        
    except CryptoAnalysis.DoesNotExist:
        messages.error(request, "Analysis not found.")
        return redirect('marketplace')

@login_required
def refresh_analysis(request, analysis_id):
    """AJAX endpoint to refresh analysis data"""
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        try:
            analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
            
            # Check if user has purchased this analysis
            if not PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
                return JsonResponse({
                    'status': 'error',
                    'message': 'You do not have access to this analysis.'
                })
            
            # Simulate data refresh
            # In a real application, this would fetch updated market data
            time.sleep(1)  # Simulate processing time
            
            return JsonResponse({
                'status': 'success',
                'message': 'Analysis data refreshed successfully!',
                'updated_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except CryptoAnalysis.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Analysis not found.'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    })