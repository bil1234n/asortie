from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.conf import settings
from .models import User, VerificationDoc

# --- 1. BUYER FORM ---
class BuyerRegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'package_tier')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.BUYER
        user.is_verified = True
        if commit:
            user.save()
        return user

# --- 2. SELLER FORM (Updated fields) ---
class SellerRegisterForm(UserCreationForm):
    business_license = forms.FileField(required=True, help_text="Upload valid Import/Export License")
    id_card = forms.FileField(required=True, help_text="Upload National ID Card")

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'package_tier')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.SELLER
        user.is_verified = False
        if commit:
            user.save()
            # Create the document record using NEW fields
            VerificationDoc.objects.create(
                user=user,
                business_license=self.cleaned_data['business_license'],
                id_card=self.cleaned_data['id_card']
            )
        return user

# --- 3. ADMIN FORM ---
class AdminRegisterForm(UserCreationForm):
    security_code = forms.CharField(widget=forms.PasswordInput, help_text="Enter Master Passcode")

    class Meta:
        model = User
        fields = ('username', 'email')

    def clean_security_code(self):
        code = self.cleaned_data.get('security_code')
        # Ensure you added ADMIN_SIGNUP_PASSCODE in settings.py
        if code != getattr(settings, 'ADMIN_SIGNUP_PASSCODE', 'COFFEE_MASTER_2025'):
            raise forms.ValidationError("Invalid Security Passcode.")
        return code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_verified = True
        if commit:
            user.save()
        return user

# --- LOGIN FORM ---
class RoleBasedLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        self.required_role = kwargs.pop('role', None)
        super().__init__(*args, **kwargs)

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if self.required_role and user.role != self.required_role:
            raise forms.ValidationError(f"This login area is for {self.required_role}s only.")

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class VerificationDocForm(forms.ModelForm):
    class Meta:
        model = VerificationDoc
        fields = ['business_license', 'id_card']
        widgets = {
            'business_license': forms.FileInput(attrs={'class': 'form-control'}),
            'id_card': forms.FileInput(attrs={'class': 'form-control'}),
        }
