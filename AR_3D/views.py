from django.shortcuts import render
from market.models import Product
from django import forms

# Custom widget to handle multiple file selection professionally
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

def index(request):
    """The premium 3D showroom page"""
    products = Product.objects.filter(is_active=True, variants__isnull=False).distinct().prefetch_related('gallery', 'variants')
    
    return render(request, 'AR_3D/index.html', {'products': products})

