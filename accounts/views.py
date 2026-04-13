import json
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.conf import settings

# Google Auth Libraries
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .models import User, VerificationDoc
from .forms import (
    BuyerRegisterForm, 
    SellerRegisterForm, 
    AdminRegisterForm, 
    RoleBasedLoginForm, 
    UserUpdateForm,
    VerificationDocForm
)

import logging 
# 2. Initialize a logger for this file
logger = logging.getLogger(__name__)

# --- GOOGLE LOGIN API ---
def google_login_api(request):
    """
    Endpoint to verify Google JWT and log the user in.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:
        data = json.loads(request.body)
        token = data.get('credential')
        client_id = settings.GOOGLE_CLIENT_ID 
        
        # 3. Use logger.debug instead of print
        logger.debug(f"Verifying token for Client ID: {client_id}")

        # 4. FIX: Add clock_skew_in_seconds to handle time drift
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            client_id,
            clock_skew_in_seconds=60  # Allows up to 60 seconds of clock difference
        )

        email = idinfo['email']
        first_name = idinfo.get('given_name', '')
        last_name = idinfo.get('family_name', '')
        
        user = User.objects.filter(email=email).first()
        
        if not user:
            # Handle Unique Username Generation
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            # Create New User (Default to Buyer)
            user = User.objects.create(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=User.BUYER,
                is_verified=True 
            )
        
        login(request, user)
        return JsonResponse({'status': 'success', 'redirect_url': '/'})
        
    except ValueError as e:
        # 5. Use logger.warning for token issues, and don't expose raw errors to the frontend
        logger.warning(f"Google Token Verification Failed: {str(e)}")
        return JsonResponse({'status': 'error', 'message': "Authentication failed. Please try again."}, status=400)
        
    except Exception as e:
        # 6. Use logger.error for critical crashes
        logger.error(f"Google Login General Error: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)
    
# --- UNIFIED VIEWS (WITH GOOGLE CONTEXT) ---

def unified_login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RoleBasedLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.role == User.SELLER:
                return redirect('seller_dashboard')
            return redirect('home')
    else:
        form = RoleBasedLoginForm()
    
    context = {
        'form': form,
        'google_client_id': settings.GOOGLE_CLIENT_ID,
    }
    return render(request, 'accounts/login.html', context)


def unified_register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    # Get role from POST or GET (defaults to buyer)
    role_type = request.POST.get('role_type') or request.GET.get('role_type', 'buyer')

    if request.method == 'POST':
        # Select the correct form based on the role submitted
        if role_type == 'seller':
            form = SellerRegisterForm(request.POST, request.FILES)
        else:
            form = BuyerRegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('seller_dashboard' if user.role == User.SELLER else 'home')
    else:
        # Initial empty form based on role_type
        form = SellerRegisterForm() if role_type == 'seller' else BuyerRegisterForm()

    context = {
        'form': form,
        'role_type': role_type, # Pass current role to template
        'google_client_id': settings.GOOGLE_CLIENT_ID,
    }
    return render(request, 'accounts/register.html', context)


# --- EXISTING ROLE LOGIC ---

def role_login(request, role, template_name, success_url):
    if request.method == 'POST':
        form = RoleBasedLoginForm(request, data=request.POST, role=role)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(success_url)
    else:
        form = RoleBasedLoginForm(role=role)
    return render(request, template_name, {'form': form, 'role': role})


# --- ADMIN VIEWS ---
def admin_register(request):
    if request.method == 'POST':
        form = AdminRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('admin_dashboard')
    else:
        form = AdminRegisterForm()
    return render(request, 'accounts/admin/register.html', {'form': form})

def admin_login(request):
    return role_login(request, User.ADMIN, 'accounts/admin/login.html', 'admin_dashboard')

def seller_login(request):
    return role_login(request, User.SELLER, 'accounts/seller/login.html', 'seller_dashboard')

def buyer_login(request):
    return role_login(request, User.BUYER, 'accounts/buyer/login.html', 'home')


# --- PROFILE & PASSWORD ---
@login_required
def profile_view(request):
    # Get or create the doc instance for sellers
    doc_instance = None
    if request.user.role == User.SELLER:
        doc_instance, created = VerificationDoc.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        # Process doc_form if the user is a seller
        doc_form = VerificationDocForm(request.POST, request.FILES, instance=doc_instance) if doc_instance else None
        
        if user_form.is_valid() and (doc_form is None or doc_form.is_valid()):
            
            # 1. Save user info, but don't commit to the database yet (commit=False)
            user = user_form.save(commit=False)
            
            if doc_form:
                # 2. Check if the business_license or id_card was actually changed
                if 'business_license' in doc_form.changed_data or 'id_card' in doc_form.changed_data:
                    
                    # 3. Strip their verification status
                    user.is_verified = False
                    messages.warning(request, "Documents updated. Your account is pending re-verification.")
                
                # 4. Save the documents
                doc_form.save()
            
            # 5. Finally, save the user to the database
            user.save()
            
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
    else:
        user_form = UserUpdateForm(instance=request.user)
        doc_form = VerificationDocForm(instance=doc_instance) if doc_instance else None

    context = {
        'form': user_form,       # Basic info
        'doc_form': doc_form,   # License & ID
        'date_joined': request.user.date_joined
    }
    return render(request, 'accounts/profile.html', context)

class ChangePasswordView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'accounts/change_password.html'
    success_message = "Your password has been changed successfully."
    success_url = reverse_lazy('profile')
