# views.py
import requests
import json
import base64
from datetime import datetime
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction as db_transaction
from django.db.models import Sum, Avg, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import random
import time
import threading
import logging
from .models import (
    SiteSetting, UserWallet, UserProfile, Transaction, 
    CryptoAnalysis, PurchasedAnalysis, Analyst, Consultation, 
    ConsultationPackage, MarketInsight, ChartAnnotation, 
    TechnicalIndicatorData, AnalysisInsight, AnalysisMetric, MpesaTransaction
)
from .forms import UserUpdateForm, UserProfileForm, PaymentMethodForm, DepositForm, WithdrawalForm

# Set up logging
logger = logging.getLogger(__name__)

# M-Pesa API credentials
MPESA_CONSUMER_KEY = 'LQost6BhC09UpLKaYjbRunq3IZN1ylfzHzI8tz47jxlaVHvI'
MPESA_CONSUMER_SECRET = "Kn2l7P0mCnFAJAi7KdOMsIRkpAsH698PBLbhG5EqVRc7CY27pv6d0U96hEhmByo6"
MPESA_SHORTCODE = '174379'
MPESA_SHORTCODE_TYPE = 'paybill'
MPESA_PASSKEY = 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
MPESA_CALLBACK_URL = 'http://darajambili.herokuapp.com/callback/'
MPESA_ENVIRONMENT = 'sandbox'
MPESA_INITIATOR_NAME = 'testapi'
MPESA_INITIATOR_PASSWORD = 'Safaricom2018'

# Exchange rate (you might want to fetch this from an API in production)
USD_TO_KES_RATE = Decimal('150.00')  # 1 USD = 150 KES

def get_mpesa_base_url():
    """Get M-Pesa API base URL based on environment"""
    if MPESA_ENVIRONMENT == 'production':
        return 'https://api.safaricom.co.ke'
    else:
        return 'https://sandbox.safaricom.co.ke'

def get_mpesa_access_token():
    """Get M-Pesa API access token with enhanced error handling"""
    try:
        auth_url = f'{get_mpesa_base_url()}/oauth/v1/generate?grant_type=client_credentials'
        logger.info(f"Getting M-Pesa access token from: {auth_url}")
        
        response = requests.get(auth_url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET), timeout=30)
        logger.info(f"Auth response status: {response.status_code}")
        
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if access_token:
            logger.info("Successfully obtained M-Pesa access token")
            return access_token
        else:
            logger.error(f"Failed to get access token. Response: {token_data}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("M-Pesa auth timeout - service not responding")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("M-Pesa auth connection error - cannot reach service")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"M-Pesa auth HTTP error: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"M-Pesa auth unexpected error: {str(e)}")
        return None

def format_phone_number(phone_number):
    """Format phone number to M-Pesa format (2547XXXXXXXX)"""
    try:
        cleaned = ''.join(filter(str.isdigit, phone_number))
        logger.info(f"Cleaned phone number: {cleaned}")
        
        if cleaned.startswith('0'):
            formatted = '254' + cleaned[1:]
        elif cleaned.startswith('7') and len(cleaned) == 9:
            formatted = '254' + cleaned
        elif cleaned.startswith('254') and len(cleaned) == 12:
            formatted = cleaned
        else:
            formatted = cleaned
            
        logger.info(f"Formatted phone number: {formatted}")
        return formatted
    except Exception as e:
        logger.error(f"Phone number formatting error: {e}")
        return phone_number

def usd_to_kes(amount_usd):
    """Convert USD to KES"""
    return Decimal(amount_usd) * USD_TO_KES_RATE

def kes_to_usd(amount_kes):
    """Convert KES to USD"""
    return Decimal(amount_kes) / USD_TO_KES_RATE

@login_required
def initiate_mpesa_deposit(request):
    """Initiate M-Pesa STK Push for deposit in KES"""
    if request.method == 'POST':
        amount_kes = request.POST.get('amount')  # Now in KES
        phone_number = request.POST.get('phone_number')
        
        if not amount_kes or not phone_number:
            messages.error(request, 'Amount and phone number are required.')
            return redirect('wallet')
        
        try:
            amount_kes = Decimal(amount_kes)
            if amount_kes <= Decimal('0'):
                messages.error(request, 'Amount must be greater than 0.')
                return redirect('wallet')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid amount format.')
            return redirect('wallet')
        
        # Convert KES to USD for wallet storage
        amount_usd = kes_to_usd(amount_kes)
        
        access_token = get_mpesa_access_token()
        if not access_token:
            messages.error(request, 'Unable to connect to M-Pesa service. Please try again.')
            return redirect('wallet')
        
        api_url = f'{get_mpesa_base_url()}/mpesa/stkpush/v1/processrequest'
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f'{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}'.encode()).decode()
        
        formatted_phone = format_phone_number(phone_number)
        
        payload = {
            'BusinessShortCode': MPESA_SHORTCODE,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount_kes),  # Send KES amount to M-Pesa
            'PartyA': formatted_phone,
            'PartyB': MPESA_SHORTCODE,
            'PhoneNumber': formatted_phone,
            'CallBackURL': MPESA_CALLBACK_URL,
            'AccountReference': f'CRYPTOCONSULT ,{request.user.username}',
            'TransactionDesc': f'Deposit to wallet - User {request.user.username}'
        }
        
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            response_data = response.json()
            
            if response_data.get('ResponseCode') == '0':
                # Create pending transaction - store USD amount in database
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount_usd,  # Store as USD in database
                    transaction_type='deposit',
                    payment_method='mpesa',
                    status='pending',
                    description=f'M-Pesa Deposit - {phone_number} (KES {amount_kes})',
                    reference=response_data.get('CheckoutRequestID'),
                    mpesa_code=response_data.get('CheckoutRequestID')
                )
                
                # Update user's M-Pesa number if different
                user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
                if user_wallet.mpesa_number != phone_number:
                    user_wallet.mpesa_number = phone_number
                    user_wallet.save()
                
                messages.success(request, f'M-Pesa payment of KES {amount_kes} initiated. Please check your phone to complete the transaction.')
            else:
                error_message = response_data.get('ResponseDescription', 'Failed to initiate M-Pesa payment.')
                messages.error(request, error_message)
                
        except Exception as e:
            logger.error(f"M-Pesa Deposit Error: {str(e)}")
            messages.error(request, f'An error occurred while initiating payment: {str(e)}')
    
    return redirect('wallet')

@csrf_exempt
def mpesa_callback(request):
    """Handle M-Pesa STK Push callback"""
    if request.method == 'POST':
        try:
            callback_data = json.loads(request.body)
            logger.info(f"M-Pesa Callback Received: {callback_data}")
            
            result_code = callback_data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
            result_desc = callback_data.get('Body', {}).get('stkCallback', {}).get('ResultDesc')
            checkout_request_id = callback_data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')
            
            if result_code == 0:
                # Payment successful
                try:
                    transaction = Transaction.objects.get(reference=checkout_request_id, status='pending')
                    transaction.status = 'completed'
                    transaction.save()
                    
                    # Update wallet balance (already in USD)
                    wallet = UserWallet.objects.get(user=transaction.user)
                    wallet.balance += transaction.amount  # USD amount
                    wallet.total_deposited += transaction.amount
                    wallet.save()
                    
                    logger.info(f"Deposit completed for user {transaction.user}: ${transaction.amount}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"Transaction not found for CheckoutRequestID: {checkout_request_id}")
                    
            else:
                # Payment failed
                try:
                    transaction = Transaction.objects.get(reference=checkout_request_id, status='pending')
                    transaction.status = 'failed'
                    transaction.description = f'{transaction.description} - Failed: {result_desc}'
                    transaction.save()
                    logger.error(f"Deposit failed for user {transaction.user}: {result_desc}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"Transaction not found for failed payment: {checkout_request_id}")
                    
        except Exception as e:
            logger.error(f"M-Pesa Callback Error: {str(e)}")
    
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})

@login_required
def initiate_mpesa_withdrawal(request):
    """Initiate M-Pesa B2C withdrawal in KES"""
    if request.method == 'POST':
        amount_kes = request.POST.get('amount')  # Now in KES
        phone_number = request.POST.get('phone_number')
        
        if not amount_kes or not phone_number:
            messages.error(request, 'Amount and phone number are required.')
            return redirect('wallet')
        
        try:
            amount_kes = Decimal(amount_kes)
            if amount_kes <= Decimal('0'):
                messages.error(request, 'Amount must be greater than 0.')
                return redirect('wallet')
                
            # Check minimum withdrawal amount (KES 10)
            if amount_kes < 10:
                messages.error(request, 'Minimum withdrawal amount is KES 10.')
                return redirect('wallet')
                
        except (ValueError, TypeError):
            messages.error(request, 'Invalid amount format.')
            return redirect('wallet')
        
        # Convert KES to USD for balance check
        amount_usd = kes_to_usd(amount_kes)
        
        # Check if user has sufficient balance
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        if user_wallet.balance < amount_usd:
            messages.error(request, 'Insufficient balance for withdrawal.')
            return redirect('wallet')
        
        access_token = get_mpesa_access_token()
        if not access_token:
            messages.error(request, 'Unable to connect to M-Pesa service. Please try again.')
            return redirect('wallet')
        
        api_url = f'{get_mpesa_base_url()}/mpesa/b2c/v1/paymentrequest'
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        formatted_phone = format_phone_number(phone_number)
        
        # Generate security credential for B2C
        security_credential = base64.b64encode(MPESA_INITIATOR_PASSWORD.encode()).decode()
        
        # Generate unique conversation ID
        conversation_id = f"WTH{random.randint(100000000, 999999999)}"
        
        payload = {
            'InitiatorName': MPESA_INITIATOR_NAME,
            'SecurityCredential': security_credential,
            'CommandID': 'BusinessPayment',
            'Amount': int(amount_kes),  # Send KES amount to M-Pesa
            'PartyA': MPESA_SHORTCODE,
            'PartyB': formatted_phone,
            'Remarks': f'Withdrawal from wallet - User {request.user.username}',
            'QueueTimeOutURL': f'{request.build_absolute_uri("/")}mpesa/withdrawal/callback/',
            'ResultURL': f'{request.build_absolute_uri("/")}mpesa/withdrawal/callback/',
            'Occasion': 'Wallet Withdrawal'
        }
        
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            response_data = response.json()
            
            logger.info(f"M-Pesa Withdrawal Response: {response_data}")
            
            if response_data.get('ResponseCode') == '0':
                # Create pending transaction and deduct from wallet
                with db_transaction.atomic():
                    transaction = Transaction.objects.create(
                        user=request.user,
                        amount=amount_usd,  # Store as USD in database
                        transaction_type='withdrawal',
                        payment_method='mpesa',
                        status='pending',
                        description=f'M-Pesa Withdrawal - {phone_number} (KES {amount_kes})',
                        reference=response_data.get('ConversationID', conversation_id),
                        mpesa_code=response_data.get('ConversationID', conversation_id)
                    )
                    
                    # Temporarily hold the amount (USD)
                    user_wallet.balance -= amount_usd
                    user_wallet.total_withdrawn += amount_usd
                    user_wallet.save()
                
                # Update user's M-Pesa number if different
                if user_wallet.mpesa_number != phone_number:
                    user_wallet.mpesa_number = phone_number
                    user_wallet.save()
                
                messages.success(request, f'Withdrawal of KES {amount_kes} initiated successfully. Funds will be sent to your M-Pesa account.')
            else:
                error_message = response_data.get('ResponseDescription', 'Failed to initiate withdrawal.')
                logger.error(f"M-Pesa Withdrawal Error: {error_message}")
                messages.error(request, f'Withdrawal failed: {error_message}')
                
        except Exception as e:
            logger.error(f"M-Pesa Withdrawal Error: {str(e)}")
            messages.error(request, f'An error occurred while initiating withdrawal: {str(e)}')
    
    return redirect('wallet')

@csrf_exempt
def mpesa_withdrawal_callback(request):
    """Handle M-Pesa B2C withdrawal callback"""
    if request.method == 'POST':
        try:
            callback_data = json.loads(request.body)
            logger.info(f"M-Pesa Withdrawal Callback Received: {callback_data}")
            
            result = callback_data.get('Result')
            if result:
                result_code = result.get('ResultCode')
                result_desc = result.get('ResultDesc')
                conversation_id = result.get('ConversationID')
                transaction_id = result.get('TransactionID')
                
                logger.info(f"Withdrawal Callback - ResultCode: {result_code}, ConversationID: {conversation_id}")
                
                if result_code == 0:
                    # Withdrawal successful
                    try:
                        transaction = Transaction.objects.get(
                            reference=conversation_id, 
                            transaction_type='withdrawal',
                            status='pending'
                        )
                        transaction.status = 'completed'
                        transaction.mpesa_code = transaction_id
                        transaction.save()
                        
                        logger.info(f"Withdrawal completed for user {transaction.user}: ${transaction.amount}")
                        
                    except Transaction.DoesNotExist:
                        logger.error(f"Withdrawal transaction not found for ConversationID: {conversation_id}")
                        
                else:
                    # Withdrawal failed - refund the amount
                    try:
                        transaction = Transaction.objects.get(
                            reference=conversation_id, 
                            transaction_type='withdrawal',
                            status='pending'
                        )
                        transaction.status = 'failed'
                        transaction.description = f'{transaction.description} - Failed: {result_desc}'
                        transaction.save()
                        
                        # Refund the amount to user's wallet
                        wallet = UserWallet.objects.get(user=transaction.user)
                        wallet.balance += transaction.amount  # USD amount
                        wallet.total_withdrawn -= transaction.amount
                        wallet.save()
                        
                        logger.info(f"Withdrawal failed for user {transaction.user}: {result_desc}. Amount refunded.")
                        
                    except Transaction.DoesNotExist:
                        logger.error(f"Withdrawal transaction not found for failed payment: {conversation_id}")
                    
        except Exception as e:
            logger.error(f"M-Pesa Withdrawal Callback Error: {str(e)}")
    
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})

@login_required
def debug_withdrawal(request):
    """Debug view to check withdrawal issues"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    
    debug_info = {
        'user': str(request.user),
        'wallet_balance': str(user_wallet.balance),
        'wallet_balance_kes': str(usd_to_kes(user_wallet.balance)),
        'mpesa_number': user_wallet.mpesa_number,
        'can_withdraw_1000_kes': user_wallet.can_withdraw(kes_to_usd(1000)),
        'daily_withdrawal_limit': str(user_wallet.daily_withdrawal_limit),
        'total_withdrawn': str(user_wallet.total_withdrawn),
        'pending_withdrawals': Transaction.objects.filter(
            user=request.user, 
            transaction_type='withdrawal',
            status='pending'
        ).count(),
        'exchange_rate': str(USD_TO_KES_RATE),
        'mpesa_environment': MPESA_ENVIRONMENT,
        'mpesa_shortcode': MPESA_SHORTCODE,
    }
    
    return JsonResponse(debug_info)

# In your base view or context processor
def base(request):
    # Get consultation packages from database
    consultation_packages = ConsultationPackage.objects.filter(is_active=True)
    
    # Convert to list of dicts for template compatibility
    packages_data = []
    for package in consultation_packages:
        package_kes = usd_to_kes(package.price)
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': str(package.price),  # String format for display
            'price_kes': package_kes,
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
            'duration_minutes': package.duration_minutes,
        })
    
    # Get site settings including hero video
    site_settings = SiteSetting.objects.filter(is_active=True).first()
    hero_video = site_settings.hero_video if site_settings else None
    
    context = {
        'consultation_packages': packages_data,
        'hero_video': hero_video,
        'site_settings': site_settings,
        'exchange_rate': USD_TO_KES_RATE,
    }
    
    # Add user_wallet if user is authenticated
    if request.user.is_authenticated:
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        context['user_wallet'] = user_wallet
        context['balance_kes'] = usd_to_kes(user_wallet.balance)
    
    return render(request, 'base.html', context)

@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/profile.html', context)

@login_required
def payment_methods(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user)[:10]
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/payment_methods.html', context)

@login_required
def deposit_funds(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
    if request.method == 'POST':
        form = DepositForm(request.POST)
        if form.is_valid():
            amount_usd = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            
            # Convert to KES for display
            amount_kes = usd_to_kes(amount_usd)
            
            # Check deposit limits
            if not user_wallet.can_deposit(amount_usd):
                messages.error(request, f'Deposit amount exceeds your daily limit of ${user_wallet.daily_deposit_limit}.')
                return redirect('deposit_funds')
            
            # For M-Pesa, redirect to M-Pesa initiation
            if payment_method == 'mpesa':
                if not user_wallet.mpesa_number:
                    messages.error(request, 'Please add your M-Pesa number first.')
                    return redirect('payment_methods')
                
                # Store deposit details in session for M-Pesa processing
                request.session['pending_deposit'] = {
                    'amount': str(amount_kes),  # Store KES amount
                    'payment_method': 'mpesa',
                    'phone_number': user_wallet.mpesa_number
                }
                return redirect('initiate_mpesa_deposit')
                
            elif payment_method == 'paypal':
                if not user_wallet.paypal_email:
                    messages.error(request, 'Please add your PayPal email first.')
                    return redirect('payment_methods')
                
                # Simulate PayPal payment
                paypal_id = f"PP{random.randint(100000000, 999999999)}"
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount_usd,
                    transaction_type='deposit',
                    payment_method='paypal',
                    status='pending',
                    description=f'PayPal deposit from {user_wallet.paypal_email}',
                    paypal_transaction_id=paypal_id
                )
                
                messages.info(request, f'Redirecting to PayPal for payment of ${amount_usd}...')
                
                def process_paypal_deposit():
                    time.sleep(2)
                    with db_transaction.atomic():
                        transaction.status = 'completed'
                        transaction.save()
                        user_wallet.balance += amount_usd
                        user_wallet.total_deposited += amount_usd
                        user_wallet.save()
                
                thread = threading.Thread(target=process_paypal_deposit)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'PayPal deposit of ${amount_usd} completed successfully!')
                return redirect('wallet')
                
    else:
        form = DepositForm()
    
    context = {
        'form': form,
        'user_wallet': user_wallet,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/deposit.html', context)

@login_required
def withdraw_funds(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            amount_usd = form.cleaned_data['amount']
            payment_method = form.cleaned_data['payment_method']
            
            # Convert to KES for display
            amount_kes = usd_to_kes(amount_usd)
            
            # Check withdrawal limits and balance
            if not user_wallet.can_withdraw(amount_usd):
                messages.error(request, 'Insufficient balance or amount exceeds withdrawal limit.')
                return redirect('withdraw_funds')
            
            # For M-Pesa, redirect to M-Pesa initiation
            if payment_method == 'mpesa':
                if not user_wallet.mpesa_number:
                    messages.error(request, 'Please add your M-Pesa number first.')
                    return redirect('payment_methods')
                
                # Store withdrawal details in session for M-Pesa processing
                request.session['pending_withdrawal'] = {
                    'amount': str(amount_kes),  # Store KES amount
                    'payment_method': 'mpesa',
                    'phone_number': user_wallet.mpesa_number
                }
                return redirect('initiate_mpesa_withdrawal')
                
            elif payment_method == 'paypal':
                if not user_wallet.paypal_email:
                    messages.error(request, 'Please add your PayPal email first.')
                    return redirect('payment_methods')
                
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount_usd,
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
                        user_wallet.balance -= amount_usd
                        user_wallet.total_withdrawn += amount_usd
                        user_wallet.save()
                
                thread = threading.Thread(target=process_paypal_withdrawal)
                thread.daemon = True
                thread.start()
                
                messages.success(request, f'Withdrawal of ${amount_usd} to PayPal initiated!')
                return redirect('wallet')
                
    else:
        form = WithdrawalForm()
    
    context = {
        'form': form,
        'user_wallet': user_wallet,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/withdraw.html', context)

@login_required
def wallet(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:20]
    
    # Convert wallet balance to KES for display
    balance_kes = usd_to_kes(user_wallet.balance)
    
    context = {
        'user_wallet': user_wallet,
        'transactions': transactions,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/wallet.html', context)

@login_required
def add_funds(request):
    """Alternative add funds view that works with the wallet template"""
    if request.method == 'POST':
        amount_usd = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        
        try:
            amount_usd = Decimal(amount_usd)
            if amount_usd <= Decimal('0'):
                messages.error(request, 'Amount must be greater than 0')
                return redirect('wallet')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid amount')
            return redirect('wallet')
        
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        
        # Add funds to wallet
        user_wallet.balance += amount_usd
        user_wallet.total_deposited += amount_usd
        user_wallet.save()
        
        # Create transaction record
        transaction = Transaction.objects.create(
            user=request.user,
            amount=amount_usd,
            transaction_type='deposit',
            payment_method=payment_method,
            status='completed',
            description=f'Added funds via {payment_method}'
        )
        
        logger.info(f"Created transaction: {transaction.id} for user {request.user}")
        
        messages.success(request, f'Successfully added ${amount_usd:.2f} to your wallet')
        return redirect('wallet')
    
    return redirect('wallet')

@login_required
def transaction_history(request):
    """View for full transaction history"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    balance_kes = usd_to_kes(user_wallet.balance)
    
    # Calculate counts for the summary
    completed_count = transactions.filter(status='completed').count()
    pending_count = transactions.filter(status='pending').count()
    
    context = {
        'user_wallet': user_wallet,
        'transactions': transactions,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/transaction_history.html', context)

@login_required
def debug_wallet(request):
    """Debug view to check wallet and transaction status"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    all_transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    balance_kes = usd_to_kes(user_wallet.balance)
    
    debug_info = {
        'user': str(request.user),
        'wallet_created': created,
        'wallet_balance': str(user_wallet.balance),
        'wallet_balance_kes': str(balance_kes),
        'total_deposited': str(user_wallet.total_deposited),
        'total_withdrawn': str(user_wallet.total_withdrawn),
        'total_transactions': all_transactions.count(),
        'transactions': list(all_transactions.values('id', 'transaction_type', 'amount', 'description', 'status', 'created_at')),
        'purchased_analyses': PurchasedAnalysis.objects.filter(user=request.user).count(),
        'exchange_rate': str(USD_TO_KES_RATE),
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
    
    # Convert to KES for display
    total_spent_kes = usd_to_kes(total_spent)
    balance_kes = usd_to_kes(user_wallet.balance)
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
        package_kes = usd_to_kes(package.price)
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': package.price,
            'price_kes': package_kes,
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
        })
    
    # GET MARKET INSIGHTS FROM DATABASE
    market_insights = MarketInsight.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by('-published_at', '-created_at')[:6]
    
    if not market_insights:
        market_insights = MarketInsight.objects.filter(
            is_active=True
        ).order_by('-published_at', '-created_at')[:6]
    
    purchased_analysis_ids = PurchasedAnalysis.objects.filter(
        user=request.user
    ).values_list('analysis_id', flat=True)
    
    context = {
        'user_wallet': user_wallet,
        'purchased_count': purchased_count,
        'total_spent': total_spent,
        'total_spent_kes': total_spent_kes,
        'balance_kes': balance_kes,
        'total_investment': total_investment,
        'consultation_count': consultation_count,
        'recent_transactions': recent_transactions,
        'purchased_analyses': purchased_analyses,
        'user_consultations': user_consultations,
        'consultation_packages': packages_data,
        'market_insights': market_insights,
        'purchased_analysis_ids': list(purchased_analysis_ids),
        'exchange_rate': USD_TO_KES_RATE,
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
    
    # Get purchased analyses for the current user
    purchased_analysis_ids = PurchasedAnalysis.objects.filter(
        user=request.user
    ).values_list('analysis_id', flat=True)
    
    # Get user's purchased analyses for display
    purchased_analyses = PurchasedAnalysis.objects.filter(
        user=request.user
    ).select_related('analysis').order_by('-purchased_at')[:6]
    
    # Calculate stats
    purchased_count = PurchasedAnalysis.objects.filter(user=request.user).count()
    total_spent_result = PurchasedAnalysis.objects.filter(user=request.user).aggregate(
        total=Sum('purchase_price')
    )
    total_spent = total_spent_result['total'] or Decimal('0.00')
    total_spent_kes = usd_to_kes(total_spent)
    balance_kes = usd_to_kes(user_wallet.balance)
    
    context = {
        'analyses': analyses,
        'user_wallet': user_wallet,
        'purchased_count': purchased_count,
        'total_spent': total_spent,
        'total_spent_kes': total_spent_kes,
        'balance_kes': balance_kes,
        'search_query': search_query,
        'selected_type': analysis_type,
        'selected_risk': risk_level,
        'selected_recommendation': recommendation,
        'purchased_analysis_ids': list(purchased_analysis_ids),
        'purchased_analyses': purchased_analyses,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/marketplace.html', context)

@login_required
def purchase_analysis(request):
    """Handle analysis purchases from wallet balance"""
    if request.method == 'POST':
        analysis_id = request.POST.get('analysis_id')
        payment_method = request.POST.get('payment_method', 'wallet')
        
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
        
        # Handle different payment methods
        if payment_method == 'wallet':
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
                    
                    # Update analysis sales count - handle missing total_revenue field
                    analysis.sales_count += 1
                    
                    # Safely update total_revenue if the field exists
                    try:
                        # Check if total_revenue field exists
                        if hasattr(analysis, 'total_revenue'):
                            analysis.total_revenue += analysis.price
                        else:
                            # If field doesn't exist, create it dynamically or skip
                            logger.warning(f"total_revenue field not found for analysis {analysis.id}")
                    except AttributeError:
                        logger.warning(f"total_revenue field not found for analysis {analysis.id}")
                    
                    analysis.save()
                    
                    logger.info(f"Purchase successful: {analysis.cryptocurrency} for ${analysis.price}")
                    logger.info(f"New balance: ${user_wallet.balance}")
                    logger.info(f"Transaction created: {transaction.id}")
                
                # Success response
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Successfully purchased {analysis.cryptocurrency} analysis!',
                        'analysis_id': analysis.id,
                        'analysis_name': analysis.cryptocurrency,
                        'price': str(analysis.price),
                        'price_kes': str(usd_to_kes(analysis.price)),
                        'new_balance': str(user_wallet.balance),
                        'redirect_url': f'/view-analysis/{analysis.id}/'
                    })
                
                messages.success(request, f'Successfully purchased {analysis.cryptocurrency} analysis!')
                return redirect('view_analysis', analysis_id=analysis.id)
                
            except Exception as e:
                logger.error(f"Purchase error: {str(e)}")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Purchase failed: {str(e)}'
                    })
                messages.error(request, f'Purchase failed: {str(e)}')
                return redirect('marketplace')
        
        elif payment_method == 'mpesa':
            # Handle M-Pesa payment - this will be processed via separate endpoint
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'pending',
                    'message': 'M-Pesa payment initiated. Please check your phone.',
                    'payment_method': 'mpesa',
                    'analysis_id': analysis.id,
                    'amount': str(analysis.price),
                    'amount_kes': str(usd_to_kes(analysis.price))
                })
            else:
                # For non-AJAX requests, redirect to M-Pesa payment page
                return redirect('purchase_analysis_mpesa_view', analysis_id=analysis.id)
        
        elif payment_method == 'paypal':
            # Handle PayPal payment
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'pending',
                    'message': 'Redirecting to PayPal...',
                    'payment_method': 'paypal',
                    'analysis_id': analysis.id,
                    'amount': str(analysis.price),
                    'redirect_url': f'/paypal/purchase/{analysis.id}/'
                })
            else:
                return redirect('paypal_purchase', analysis_id=analysis.id)
    
    # GET request - show purchased analyses
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    purchased_analyses = PurchasedAnalysis.objects.filter(
        user=request.user
    ).select_related('analysis', 'analysis__analyst', 'analysis__analyst__user').order_by('-purchased_at')
    balance_kes = usd_to_kes(user_wallet.balance)
    
    # Calculate stats
    total_investment = sum(p.purchase_price for p in purchased_analyses)
    total_investment_kes = usd_to_kes(total_investment)
    active_analyses = purchased_analyses.filter(access_expires__isnull=True).count()
    average_rating_result = purchased_analyses.aggregate(avg_rating=Avg('rating_given'))
    average_rating = average_rating_result['avg_rating'] or Decimal('4.5')
    
    context = {
        'purchased_analyses': purchased_analyses,
        'user_wallet': user_wallet,
        'total_investment': total_investment,
        'total_investment_kes': total_investment_kes,
        'active_analyses': active_analyses,
        'average_rating': average_rating,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
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
                
                # Update analysis sales count - handle missing total_revenue field
                analysis.sales_count += 1
                
                # Safely update total_revenue if the field exists
                try:
                    if hasattr(analysis, 'total_revenue'):
                        analysis.total_revenue += analysis.price
                except AttributeError:
                    logger.warning(f"total_revenue field not found for analysis {analysis.id}")
                
                analysis.save()
                
                logger.info(f"Instant purchase successful: {analysis.cryptocurrency}")
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully purchased {analysis.cryptocurrency} analysis!',
                'analysis_id': analysis.id,
                'analysis_name': analysis.cryptocurrency,
                'price': str(analysis.price),
                'price_kes': str(usd_to_kes(analysis.price)),
                'new_balance': str(user_wallet.balance),
                'redirect_url': f'/view-analysis/{analysis.id}/'
            })
            
        except Exception as e:
            logger.error(f"Instant purchase error: {str(e)}")
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
        balance_kes = usd_to_kes(user_wallet.balance)
        
        return JsonResponse({
            'status': 'success',
            'balance': str(user_wallet.balance),
            'balance_kes': str(balance_kes)
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
    balance_kes = usd_to_kes(user_wallet.balance)
    
    # Calculate portfolio stats
    total_investment = sum(p.purchase_price for p in purchased_analyses)
    total_investment_kes = usd_to_kes(total_investment)
    active_analyses = purchased_analyses.filter(access_expires__isnull=True).count()
    completed_analyses = purchased_analyses.filter(access_expires__isnull=False).count()
    
    context = {
        'user_wallet': user_wallet,
        'purchased_analyses': purchased_analyses,
        'total_investment': total_investment,
        'total_investment_kes': total_investment_kes,
        'active_analyses': active_analyses,
        'completed_analyses': completed_analyses,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/portfolio.html', context)

@login_required
def book_consultation(request):
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
    if request.method == 'POST':
        package_id = request.POST.get('package_id')
        scheduled_date = request.POST.get('scheduled_date')
        
        try:
            package = ConsultationPackage.objects.get(id=package_id, is_active=True)
        except ConsultationPackage.DoesNotExist:
            messages.error(request, 'Invalid consultation package selected.')
            return redirect('book_consultation')
        
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
        package_kes = usd_to_kes(package.price)
        packages_data.append({
            'id': package.id,
            'title': package.title,
            'level': package.level,
            'description': package.description,
            'price': package.price,
            'price_kes': package_kes,
            'features': package.get_features_list(),
            'icon_class': package.icon_class,
            'get_level_display': package.get_level_display,
        })
    
    context = {
        'consultation_packages': packages_data,
        'user_wallet': user_wallet,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/book_consultation.html', context)

@login_required
def my_consultations(request):
    """View for users to see their consultation bookings and status"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
    total_invested_kes = usd_to_kes(total_invested)
    
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
        'total_invested_kes': total_invested_kes,
        'next_consultation': next_consultation,
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    
    return render(request, 'dashboard/my_consultations.html', context)

@login_required
def view_analysis(request, analysis_id):
    """View for users to view a specific purchased analysis"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
    
    # Add KES prices to similar analyses
    for similar_analysis in similar_analyses:
        similar_analysis.price_kes = usd_to_kes(similar_analysis.price)
    
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
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/view_analysis.html', context)

@login_required
def market_insights(request):
    """View for all market insights"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
    }
    return render(request, 'dashboard/market_insights.html', context)

@login_required
def view_market_insight(request, insight_id):
    """View for a single market insight"""
    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
    balance_kes = usd_to_kes(user_wallet.balance)
    
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
        'balance_kes': balance_kes,
        'exchange_rate': USD_TO_KES_RATE,
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
        response.write(f"Price (KES): {usd_to_kes(analysis.price)}\n")
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

@login_required
def check_mpesa_transaction_status(request, transaction_id):
    """Check status of M-Pesa transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id, user=request.user)
        
        if transaction.status == 'completed':
            return JsonResponse({
                'status': 'completed',
                'message': 'Transaction completed successfully'
            })
        elif transaction.status == 'pending':
            return JsonResponse({
                'status': 'pending', 
                'message': 'Transaction is being processed'
            })
        else:
            return JsonResponse({
                'status': 'failed',
                'message': 'Transaction failed'
            })
            
    except Transaction.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Transaction not found'
        })


# views.py - Update the purchase_analysis_mpesa function

# views.py - Update the purchase_analysis_mpesa function

@login_required
@csrf_exempt
def purchase_analysis_mpesa(request):
    """Handle M-Pesa payment for analysis purchase with proper callback URL"""
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        analysis_id = request.POST.get('analysis_id')
        phone_number = request.POST.get('phone_number')
        amount = request.POST.get('amount')
        
        logger.info(f"M-Pesa Purchase Attempt: analysis_id={analysis_id}, phone={phone_number}, amount={amount}")
        
        if not analysis_id or not phone_number or not amount:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields.'
            })
        
        try:
            analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        except CryptoAnalysis.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Analysis not found.'
            })
        
        # Check if already purchased
        if PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
            return JsonResponse({
                'status': 'already_purchased',
                'message': 'You have already purchased this analysis.',
                'redirect_url': f'/view-analysis/{analysis.id}/'
            })
        
        # Convert USD amount to KES
        try:
            amount_kes = usd_to_kes(Decimal(amount))
            logger.info(f"Converted amount: ${amount} -> KES {amount_kes}")
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid amount format.'
            })
        
        # Validate amount
        if amount_kes < 1:
            return JsonResponse({
                'status': 'error',
                'message': 'Amount must be at least KES 1.00'
            })
        
        access_token = get_mpesa_access_token()
        if not access_token:
            return JsonResponse({
                'status': 'error',
                'message': 'Unable to connect to M-Pesa service. Please try again.'
            })
        
        api_url = f'{get_mpesa_base_url()}/mpesa/stkpush/v1/processrequest'
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f'{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}'.encode()).decode()
        
        formatted_phone = format_phone_number(phone_number)
        
        # Create proper callback URL
        if MPESA_ENVIRONMENT == 'sandbox':
            # For sandbox, you can use a test callback URL or your ngrok URL
            callback_url = "https://darajambili.herokuapp.com/mpesa/analysis-purchase/callback/"
        else:
            # For production, use your actual domain
            callback_url = f"{request.build_absolute_uri('/')}mpesa/analysis-purchase/callback/"
        
        # Alternative: Use a universal test callback for development
        callback_url = "https://webhook.site/your-unique-url"  # Get from https://webhook.site
        
        payload = {
            'BusinessShortCode': MPESA_SHORTCODE,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount_kes),
            'PartyA': formatted_phone,
            'PartyB': MPESA_SHORTCODE,
            'PhoneNumber': formatted_phone,
            'CallBackURL': callback_url,
            'AccountReference': f'ANALYSIS-{analysis.id}',
            'TransactionDesc': f'Purchase: {analysis.cryptocurrency} Analysis'
        }
        
        logger.info(f"M-Pesa Payload: {payload}")
        
        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            logger.info(f"M-Pesa Response Status: {response.status_code}")
            
            response_data = response.json()
            logger.info(f"M-Pesa Analysis Purchase Response: {response_data}")
            
            if response.status_code == 200:
                if response_data.get('ResponseCode') == '0':
                    # Create pending transaction
                    transaction = Transaction.objects.create(
                        user=request.user,
                        amount=Decimal(amount),
                        transaction_type='purchase',
                        payment_method='mpesa',
                        status='pending',
                        description=f'M-Pesa Purchase: {analysis.cryptocurrency} Analysis - {phone_number}',
                        reference=response_data.get('CheckoutRequestID'),
                        mpesa_code=response_data.get('CheckoutRequestID'),
                        analysis=analysis
                    )
                    
                    # Update user's M-Pesa number if different
                    user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
                    if user_wallet.mpesa_number != phone_number:
                        user_wallet.mpesa_number = phone_number
                        user_wallet.save()
                    
                    return JsonResponse({
                        'status': 'success',
                        'checkout_request_id': response_data.get('CheckoutRequestID'),
                        'merchant_request_id': response_data.get('MerchantRequestID'),
                        'message': 'M-Pesa payment initiated. Please check your phone to complete the transaction.'
                    })
                else:
                    error_message = response_data.get('ResponseDescription', 'Failed to initiate M-Pesa payment.')
                    error_code = response_data.get('ResponseCode', 'Unknown')
                    logger.error(f"M-Pesa Error {error_code}: {error_message}")
                    
                    return JsonResponse({
                        'status': 'error',
                        'message': f'M-Pesa Error: {error_message}',
                        'error_code': error_code
                    })
            else:
                logger.error(f"M-Pesa HTTP Error: {response.status_code} - {response.text}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'M-Pesa service error (HTTP {response.status_code}). Please try again.'
                })
                
        except Exception as e:
            logger.error(f"M-Pesa Analysis Purchase Error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected error occurred. Please try again.'
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    })



@csrf_exempt
def mpesa_analysis_purchase_callback(request):
    """Handle M-Pesa STK Push callback for analysis purchases"""
    if request.method == 'POST':
        try:
            callback_data = json.loads(request.body)
            logger.info(f"M-Pesa Analysis Purchase Callback Received: {callback_data}")
            
            result_code = callback_data.get('Body', {}).get('stkCallback', {}).get('ResultCode')
            result_desc = callback_data.get('Body', {}).get('stkCallback', {}).get('ResultDesc')
            checkout_request_id = callback_data.get('Body', {}).get('stkCallback', {}).get('CheckoutRequestID')
            
            logger.info(f"Analysis Purchase Callback - ResultCode: {result_code}, CheckoutRequestID: {checkout_request_id}")
            
            if result_code == 0:
                # Payment successful
                try:
                    # Find the transaction
                    transaction = Transaction.objects.get(
                        reference=checkout_request_id, 
                        transaction_type='purchase',
                        status='pending'
                    )
                    
                    # Update transaction status
                    transaction.status = 'completed'
                    
                    # Get M-Pesa receipt details
                    callback_metadata = callback_data.get('Body', {}).get('stkCallback', {}).get('CallbackMetadata', {}).get('Item', [])
                    mpesa_receipt = None
                    for item in callback_metadata:
                        if item.get('Name') == 'MpesaReceiptNumber':
                            mpesa_receipt = item.get('Value')
                            break
                    
                    if mpesa_receipt:
                        transaction.mpesa_code = mpesa_receipt
                    
                    transaction.save()
                    
                    # Create purchase record
                    purchase = PurchasedAnalysis.objects.create(
                        user=transaction.user,
                        analysis=transaction.analysis,
                        purchase_price=transaction.amount
                    )
                    
                    # Update analysis sales count
                    analysis = transaction.analysis
                    analysis.sales_count += 1
                    analysis.total_revenue += transaction.amount
                    analysis.save()
                    
                    # Update MpesaTransaction record
                    try:
                        mpesa_transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
                        mpesa_transaction.status = 'successful'
                        mpesa_transaction.mpesa_receipt_number = mpesa_receipt
                        mpesa_transaction.result_code = result_code
                        mpesa_transaction.result_desc = result_desc
                        mpesa_transaction.transaction_date = timezone.now()
                        mpesa_transaction.save()
                    except MpesaTransaction.DoesNotExist:
                        logger.warning(f"MpesaTransaction not found for checkout_request_id: {checkout_request_id}")
                    
                    logger.info(f"Analysis purchase completed for user {transaction.user}: {analysis.cryptocurrency}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"Transaction not found for CheckoutRequestID: {checkout_request_id}")
                    
            else:
                # Payment failed
                try:
                    transaction = Transaction.objects.get(
                        reference=checkout_request_id, 
                        transaction_type='purchase',
                        status='pending'
                    )
                    transaction.status = 'failed'
                    transaction.description = f'{transaction.description} - Failed: {result_desc}'
                    transaction.save()
                    
                    # Update MpesaTransaction record
                    try:
                        mpesa_transaction = MpesaTransaction.objects.get(checkout_request_id=checkout_request_id)
                        mpesa_transaction.status = 'failed'
                        mpesa_transaction.result_code = result_code
                        mpesa_transaction.result_desc = result_desc
                        mpesa_transaction.save()
                    except MpesaTransaction.DoesNotExist:
                        logger.warning(f"MpesaTransaction not found for failed payment: {checkout_request_id}")
                    
                    logger.error(f"Analysis purchase failed for user {transaction.user}: {result_desc}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"Transaction not found for failed payment: {checkout_request_id}")
                    
        except Exception as e:
            logger.error(f"M-Pesa Analysis Purchase Callback Error: {str(e)}")
    
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})

@login_required
def check_mpesa_payment_status(request, checkout_request_id):
    """Check status of M-Pesa payment for analysis purchase"""
    try:
        # Check transaction status
        transaction = Transaction.objects.get(
            reference=checkout_request_id,
            user=request.user,
            transaction_type='purchase'
        )
        
        if transaction.status == 'completed':
            # Payment successful
            analysis = transaction.analysis
            
            # Double-check if purchase record exists
            if not PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
                # Create purchase record if it doesn't exist
                PurchasedAnalysis.objects.create(
                    user=request.user,
                    analysis=analysis,
                    purchase_price=transaction.amount
                )
                
                # Update analysis sales count
                analysis.sales_count += 1
                analysis.total_revenue += transaction.amount
                analysis.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Payment completed successfully',
                'analysis_id': analysis.id,
                'analysis_name': analysis.cryptocurrency,
                'mpesa_receipt_number': transaction.mpesa_code,
                'amount': str(transaction.amount)
            })
            
        elif transaction.status == 'pending':
            return JsonResponse({
                'status': 'pending',
                'message': 'Payment is being processed'
            })
            
        else:
            return JsonResponse({
                'status': 'failed',
                'message': 'Payment failed or was cancelled'
            })
            
    except Transaction.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Transaction not found'
        })

@login_required
def purchase_analysis_mpesa_view(request, analysis_id):
    """View for M-Pesa payment page"""
    try:
        analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        user_wallet, created = UserWallet.objects.get_or_create(user=request.user)
        balance_kes = usd_to_kes(user_wallet.balance)
        
        # Check if already purchased
        if PurchasedAnalysis.objects.filter(user=request.user, analysis=analysis).exists():
            messages.warning(request, 'You have already purchased this analysis.')
            return redirect('view_analysis', analysis_id=analysis.id)
        
        context = {
            'analysis': analysis,
            'user_wallet': user_wallet,
            'balance_kes': balance_kes,
            'price_kes': usd_to_kes(analysis.price),
            'exchange_rate': USD_TO_KES_RATE,
        }
        return render(request, 'dashboard/purchase_mpesa.html', context)
        
    except CryptoAnalysis.DoesNotExist:
        messages.error(request, 'Analysis not found.')
        return redirect('marketplace')



@login_required
def analysis_detail_api(request, analysis_id):
    """API endpoint to get analysis details"""
    try:
        analysis = CryptoAnalysis.objects.get(id=analysis_id, is_active=True)
        
        data = {
            'id': analysis.id,
            'cryptocurrency': analysis.cryptocurrency,
            'symbol': analysis.symbol,
            'title': analysis.title,
            'description': analysis.description,
            'price': float(analysis.price),
            'analysis_type': analysis.analysis_type,
            'analysis_type_display': analysis.get_analysis_type_display(),
            'risk_level': analysis.risk_level,
            'risk_level_display': analysis.get_risk_level_display(),
            'recommendation': analysis.recommendation,
            'recommendation_display': analysis.get_recommendation_display(),
            'timeframe': analysis.timeframe,
            'timeframe_display': analysis.get_timeframe_display(),
            'overall_score': float(analysis.overall_score),
            'growth_potential': analysis.growth_potential,
            'features_list': analysis.features_list,
            'is_featured': analysis.is_featured,
            'sales_count': analysis.sales_count,
            'rating': float(analysis.rating),
        }
        
        return JsonResponse(data)
        
    except CryptoAnalysis.DoesNotExist:
        return JsonResponse({'error': 'Analysis not found'}, status=404)