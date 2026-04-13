from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.contrib.auth import get_user_model
import json
import random  
from django.http import JsonResponse
from django.template.loader import render_to_string

# --- IMPORTS ---
from .models import Notification
from chat.models import ChatRoom, Message
# We use BusinessProfile and BusinessCertification now (per your previous fix)
from market.models import Product, Order, BusinessProfile, BusinessCertification

User = get_user_model()

# ==========================================
# 1. MARKETING & PUBLIC VIEWS
# ==========================================

def marketing_contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('Email')
        phone = request.POST.get('Phone-Number')
        country = request.POST.get('Category-2')
        body = request.POST.get('field')

        admins = list(User.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True))

        if not admins:
            messages.error(request, "System Error: No support agents available.")
            return redirect('contact')

        target_admin = random.choice(admins)
        guest_user, created = User.objects.get_or_create(username="Website_Guest")
        if created:
            guest_user.set_unusable_password()
            guest_user.save()

        room = ChatRoom.objects.filter(
            (Q(participant_1=guest_user) & Q(participant_2=target_admin)) |
            (Q(participant_1=target_admin) & Q(participant_2=guest_user))
        ).first()

        if not room:
            room = ChatRoom.objects.create(participant_1=guest_user, participant_2=target_admin)

        full_message = (
            f"📢 **NEW CONTACT INQUIRY** <br>"
            f"👤 Name: {name} <br>"
            f"📧 Email: {email} <br>"
            f"📞 Phone: {phone} <br>"
            f"🌍 Country: {country} <br>"
            f"---------------------- <br>"
            f"{body}"
        )

        Message.objects.create(room=room, sender=guest_user, content=full_message)
        room.save()

        messages.success(request, f"Thank you, {name}! Your message has been sent to our support team.")
        return redirect('contact')

    return render(request, 'marketing/contact.html')

# old
# def marketing_home(request):
#     products = Product.objects.filter(
#         is_active=True, 
#         seller__is_verified=True
#     ).order_by('-created_at')[:6] 
#     return render(request, 'marketing/index.html', {'products': products})

def marketing_home(request):
    products = Product.objects.filter(
        is_active=True, 
        seller__is_verified=True
    ).order_by('-created_at')[:6] 
    return render(request, 'core/home.html', {'products': products})

def marketing_about(request):
    return render(request, 'marketing/about.html')

def marketing_producers(request):
    return render(request, 'marketing/producers.html')

def marketing_roasters(request):
    return render(request, 'marketing/roasters.html')

def marketing_shop(request):
    products = Product.objects.filter(
        is_active=True, 
        seller__is_verified=True
    ).order_by('-created_at')[:6] 
    return render(request, 'marketing/shop.html', {'products': products})

def home(request):
    total_products = Product.objects.filter(is_active=True).count()
    return render(request, 'core/home.html', {'total_products': total_products})

def coming_soon(request):
    return render(request, 'core/coming_soon.html')

def coming_soon_2(request):
    return render(request, 'core/coming_soon_2.html')

@login_required
def login_redirect_view(request):
    if request.user.role == 'admin' or request.user.is_superuser:
        return redirect('admin_dashboard')
    elif request.user.role == 'seller':
        return redirect('seller_dashboard')
    else:
        return redirect('home')

# ==========================================
# 2. ADMIN DASHBOARD & USER MANAGEMENT
# ==========================================

@login_required
def admin_dashboard(request):
    if not request.user.is_staff: return redirect('home')
    
    total_users = User.objects.count()
    total_products = Product.objects.count()
    # Fixed Revenue Logic: Count only Paid/Shipped/Delivered
    valid_statuses = ['Paid', 'Shipped', 'Delivered']
    total_revenue = Order.objects.filter(status__in=valid_statuses).aggregate(Sum('total_price'))['total_price__sum'] or 0

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
    """
    Manage Users: Approve/Suspend, Identity Verification & Certificate Review.
    Includes Notification logic.
    """
    if not request.user.is_staff: 
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        
        # --- A. Account Actions ---
        if user_id and action in ['suspend', 'unsuspend', 'approve_identity', 'revoke_identity']:
            target_user = get_object_or_404(User, id=user_id)

            if action == 'suspend':
                target_user.is_active = False
                target_user.save()
                messages.warning(request, f"User {target_user.username} suspended.")
                # Notify
                Notification.objects.create(
                    recipient=target_user,
                    message="Your account has been suspended by the administrator.",
                    link="#"
                )
                
            elif action == 'unsuspend':
                target_user.is_active = True
                target_user.save()
                messages.success(request, f"User {target_user.username} restored.")
                # Notify
                Notification.objects.create(
                    recipient=target_user,
                    message="Your account has been reactivated.",
                    link="/account/business-profile/"
                )

            elif action == 'approve_identity':
                target_user.is_verified = True
                target_user.save()
                messages.success(request, f"Identity verified for {target_user.username}.")
                # Notify
                Notification.objects.create(
                    recipient=target_user,
                    message="Your identity verification has been Approved! You are now a Verified user.",
                    link="/account/business-profile/"
                )
                
            elif action == 'revoke_identity':
                target_user.is_verified = False
                target_user.save()
                messages.warning(request, f"Identity verification revoked for {target_user.username}.")
                # Notify
                Notification.objects.create(
                    recipient=target_user,
                    message="Your identity verification status has been revoked. Please check your documents.",
                    link="/account/business-profile/"
                )

        # --- B. Certificate Actions ---
        elif action in ['verify_cert', 'reject_cert']:
            cert_id = request.POST.get('cert_id')
            # Use BusinessCertification (New Model Name)
            cert = get_object_or_404(BusinessCertification, id=cert_id)
            cert_owner = cert.profile.user # Get the user to notify

            if action == 'verify_cert':
                cert.is_verified = True
                cert.save()
                messages.success(request, f"Certificate '{cert.name}' approved.")
                # Notify
                Notification.objects.create(
                    recipient=cert_owner,
                    message=f"Your document '{cert.name}' has been Verified by Admin.",
                    link="/account/business-profile/"
                )

            elif action == 'reject_cert':
                cert.is_verified = False
                cert.save()
                messages.warning(request, f"Certificate '{cert.name}' rejected.")
                # Notify
                Notification.objects.create(
                    recipient=cert_owner,
                    message=f"Your document '{cert.name}' was rejected. Please upload a valid copy.",
                    link="/account/business-profile/"
                )

        return redirect('admin_users')

    # GET Request: Optimized Query
    users = User.objects.select_related('business_profile', 'verification_doc').prefetch_related('business_profile__certificates').all().order_by('-date_joined')
    
    return render(request, 'admin_panel/users.html', {'users': users})

@login_required
def admin_product_analytics(request):
    if not request.user.is_staff: return redirect('home')
    
    products = Product.objects.all()
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
    status_data = list(Order.objects.values('status').annotate(count=Count('status')))
    labels = [x['status'] for x in status_data]
    values = [x['count'] for x in status_data]
    
    return render(request, 'admin_panel/orders.html', {
        'orders': orders,
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values)
    })

# ==========================================
# 3. NOTIFICATIONS SYSTEM
# ==========================================

@login_required
def mark_notification_read(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, recipient=request.user)
    notif.is_read = True
    notif.save()
    return redirect(notif.link if notif.link else 'home')

@login_required
def all_notifications(request):
    all_notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    return render(request, 'core/notifications.html', {'all_notifs': all_notifs})

@login_required
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('all_notifications')

@login_required
def delete_all_notifications(request):
    Notification.objects.filter(recipient=request.user).delete()
    messages.warning(request, "All notifications cleared.")
    return redirect('all_notifications')

def get_notifications_ajax(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'unauthorized'}, status=401)
    
    # 1. Get the base queryset of ALL unread notifications
    unread_notifications = request.user.notifications.filter(is_read=False)
    
    # 2. Get the ACTUAL total count before applying any limits
    count = unread_notifications.count()
    
    # 3. Slice the queryset to get only the latest 5 for the dropdown UI
    latest_notifications = unread_notifications.order_by('-created_at')[:5]
    
    # Render the dropdown items to a string to inject via JS
    html = render_to_string('partials/notification_items.html', {'notifications': latest_notifications})
    
    return JsonResponse({
        'count': count,
        'html': html
    })
