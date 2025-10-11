from django import forms
from django.contrib.auth.models import User
from .models import UserProfile, UserWallet

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'address', 'profile_picture', 'date_of_birth']

class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = UserWallet
        fields = ['mpesa_number', 'paypal_email', 'preferred_payment_method']

class DepositForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    payment_method = forms.ChoiceField(choices=UserWallet.PAYMENT_METHODS)

class WithdrawalForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=1)
    payment_method = forms.ChoiceField(choices=UserWallet.PAYMENT_METHODS)