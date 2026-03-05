from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum
import json
from .models import Notification
from accounts.models import User
from market.models import Product, Order
from django.shortcuts import render
from market.models import Product 
import random  
from django.contrib.auth import get_user_model
from django.db.models import Q
from chat.models import ChatRoom, Message # Ensure these are imported
from market.models import Product, Order, SellerCertification # <--- Added SellerCertification

User = get_user_model()

def marketing_contact(request):
    if request.method == 'POST':
        # 1. Get Data from Form
        name = request.POST.get('name')
        email = request.POST.get('Email')
        phone = request.POST.get('Phone-Number')
        country = request.POST.get('Category-2')
        body = request.POST.get('field')

        # 2. Find a RANDOM Admin to receive the message
        # Filter for users with role 'admin' OR superusers
        admins = list(User.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True))

        if not admins:
            messages.error(request, "System Error: No support agents available.")
            return redirect('contact')

        # Pick one random admin
        target_admin = random.choice(admins)

        # 3. Create/Get the "Website_Guest" user (The Sender)
        # This user acts as the proxy for all public visitors
        guest_user, created = User.objects.get_or_create(username="Website_Guest")
        if created:
            guest_user.set_unusable_password()
            guest_user.save()

        # 4. Get or Create Chat Room between Guest and the Random Admin
        room = ChatRoom.objects.filter(
            (Q(participant_1=guest_user) & Q(participant_2=target_admin)) |
            (Q(participant_1=target_admin) & Q(participant_2=guest_user))
        ).first()

        if not room:
            room = ChatRoom.objects.create(participant_1=guest_user, participant_2=target_admin)

        # 5. Create the Message Content
        full_message = (
            f"📢 **NEW CONTACT INQUIRY** <br>"
            f"👤 Name: {name} <br>"
            f"📧 Email: {email} <br>"
            f"📞 Phone: {phone} <br>"
            f"🌍 Country: {country} <br>"
            f"---------------------- <br>"
            f"{body}"
        )

        # 6. Save the Message to Database
        Message.objects.create(room=room, sender=guest_user, content=full_message)
        
        # Update room timestamp so it floats to top
        room.save()

        # 7. Success Message
        messages.success(request, f"Thank you, {name}! Your message has been sent to our support team.")
        return redirect('contact')

    return render(request, 'marketing/contact.html')

def marketing_home(request):
    products = Product.objects.filter(
        is_active=True, 
        seller__is_verified=True
    ).order_by('-created_at')[:6] 
    
    return render(request, 'marketing/index.html', {'products': products})

def marketing_about(request):
    return render(request, 'marketing/about.html')

def marketing_shop(request):
    products = Product.objects.filter(
        is_active=True, 
        seller__is_verified=True
    ).order_by('-created_at')[:6] 
    
    return render(request, 'marketing/shop.html', {'products': products})

# --- PUBLIC VIEWS ---
def home(request):
    total_products = Product.objects.filter(is_active=True).count()
    return render(request, 'core/home.html', {'total_products': total_products})

def coming_soon(request):
    return render(request, 'core/coming_soon.html')

@login_required
def login_redirect_view(request):
    if request.user.role == 'admin' or request.user.is_superuser:
        return redirect('admin_dashboard')
    elif request.user.role == 'seller':
        return redirect('seller_dashboard')
    else:
        return redirect('home')

# ==========================================
# ADMIN DASHBOARD & ANALYTICS
# ==========================================

@login_required
def admin_dashboard(request):
    if not request.user.is_staff: return redirect('home')
    
    total_users = User.objects.count()
    total_products = Product.objects.count()
    total_revenue = sum(o.total_price for o in Order.objects.filter(status='Paid'))

    # Analytics: Users by Role
    role_data = list(User.objects.values('role').annotate(count=Count('role')))
    labels = [item['role'].capitalize() for item in role_data]
    values = [item['count'] for item in role_data]

    context = {
        'total_users': total_users,
        'total_products': total_products,
        'total_revenue': total_revenue,
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values),
    }
    return render(request, 'admin_panel/dashboard.html', context)

@login_required
def admin_users(request):
    """Manage Users: Approve/Suspend, Identity Verification & Certificate Review"""
    
    # 1. Security Check
    if not request.user.is_staff: 
        return redirect('home')

    # 2. Handle POST Actions
    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        
        # Get the user object safely
        target_user = get_object_or_404(User, id=user_id)
        
        # --- A. User Account Status ---
        if action == 'suspend':
            target_user.is_active = False
            target_user.save()
            messages.warning(request, f"User {target_user.username} suspended.")
            
        elif action == 'unsuspend':
            target_user.is_active = True
            target_user.save()
            messages.success(request, f"User {target_user.username} restored.")

        # --- B. Identity Verification (License) ---
        elif action == 'approve_identity':
            target_user.is_verified = True
            target_user.save()
            messages.success(request, f"Identity verified for {target_user.username}.")
            
        elif action == 'revoke_identity':
            target_user.is_verified = False
            target_user.save()
            messages.warning(request, f"Identity verification revoked for {target_user.username}.")

        # --- C. Certificate Verification (Market App) ---
        elif action == 'verify_cert':
            cert_id = request.POST.get('cert_id')
            cert = get_object_or_404(SellerCertification, id=cert_id)
            cert.is_verified = True
            cert.save()
            messages.success(request, f"Certificate '{cert.name}' approved.")

        elif action == 'reject_cert':
            cert_id = request.POST.get('cert_id')
            cert = get_object_or_404(SellerCertification, id=cert_id)
            cert.is_verified = False
            cert.save()
            messages.warning(request, f"Certificate '{cert.name}' rejected.")

        return redirect('admin_users')

    # 3. GET Request: Render List
    # Using select_related/prefetch_related to optimize the database queries for the modal
    users = User.objects.select_related('seller_profile', 'verification_doc').prefetch_related('seller_profile__certificates').all().order_by('-date_joined')
    
    return render(request, 'admin_panel/users.html', {'users': users})

@login_required
def admin_product_analytics(request):
    if not request.user.is_staff: return redirect('home')
    
    products = Product.objects.all()
    # Analytics: Products by Category
    cat_data = list(Product.objects.values('category').annotate(count=Count('category')))
    labels = [x['category'] for x in cat_data]
    values = [x['count'] for x in cat_data]
    
    return render(request, 'admin_panel/products.html', {
        'products': products,
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values)
    })

@login_required
def admin_order_analytics(request):
    if not request.user.is_staff: return redirect('home')
    
    orders = Order.objects.all().order_by('-created_at')
    # Analytics: Orders by Status
    status_data = list(Order.objects.values('status').annotate(count=Count('status')))
    labels = [x['status'] for x in status_data]
    values = [x['count'] for x in status_data]
    
    return render(request, 'admin_panel/orders.html', {
        'orders': orders,
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values)
    })
    

@login_required
def mark_notification_read(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.is_read = True
    notif.save()
    # Redirect to the link (e.g., the order or chat)
    return redirect(notif.link if notif.link else 'home')

@login_required
def all_notifications(request):
    # Show all history
    all_notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    # Mark all as read when visiting this page (optional strategy)
    return render(request, 'core/notifications.html', {'all_notifs': all_notifs})

@login_required
def mark_all_read(request):
    """Updates all unread notifications to read"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('all_notifications')

@login_required
def delete_all_notifications(request):
    """Permanently deletes all notifications"""
    Notification.objects.filter(recipient=request.user).delete()
    messages.warning(request, "All notifications have been cleared.")
    return redirect('all_notifications')