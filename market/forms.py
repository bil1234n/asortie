from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import BusinessCertification

# Get the correct User model safely
User = get_user_model()

class BuyerRegisterForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'package_tier']
        widgets = {
            'package_tier': forms.RadioSelect(attrs={'class': 'btn-check'}),
        }

class SellerRegisterForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'package_tier']
        widgets = {
            'package_tier': forms.RadioSelect(attrs={'class': 'btn-check'}),
        }

class CertificationForm(forms.ModelForm):
    class Meta:
        model = BusinessCertification
        fields = ['name', 'authority_name', 'expiry_date', 'document_image']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'name': forms.Select(attrs={'class': 'form-select'}),
            'authority_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fairtrade International'}),
            'document_image': forms.FileInput(attrs={'class': 'form-control'}),
        }
