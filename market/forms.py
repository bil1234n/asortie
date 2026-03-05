from django import forms
from .models import SellerCertification

class CertificationForm(forms.ModelForm):
    class Meta:
        model = SellerCertification
        fields = ['name', 'authority_name', 'expiry_date', 'document_image']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'name': forms.Select(attrs={'class': 'form-control'}),
            'authority_name': forms.TextInput(attrs={'class': 'form-control'}),
            # document_image usually handled by Cloudinary widget or standard file input
        }