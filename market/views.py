from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Product, Order
from django.db.models import Count, Sum
from django.contrib import messages
import json

from django.utils import timezone
from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce # <--- Important Import
from .models import SellerProfile, Product, Order, SellerCertification
from accounts.models import User
from .forms import CertificationForm 

from django.contrib.auth import get_user_model
from .forms import CertificationForm

User = get_user_model()

def product_list(request):
    # 1. Start with base query
    products = Product.objects.filter(is_active=True, seller__is_verified=True)

    # 2. Get Filter Parameters
    q = request.GET.get('q')
    category = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    sort_by = request.GET.get('sort')

    # 3. Apply Filters
    if q:
        products = products.filter(
            Q(name__icontains=q) | 
            Q(description__icontains=q)
        )
    
    if category:
        products = products.filter(category=category)

    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass # Ignore invalid numbers

    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass

    # 4. Sorting
    if sort_by == 'price_asc':
        products = products.order_by('price')
    elif sort_by == 'price_desc':
        products = products.order_by('-price')
    else:
        # Default: Newest first
        products = products.order_by('-created_at')

    # 5. Get Categories for the Dropdown (from Model choices)
    # We retrieve the actual choices list from the model class
    categories = Product.CATEGORY_CHOICES 

    context = {
        'products': products,
        'categories': categories,
    }
    return render(request, 'market/list.html', context)

# --- 2. NEW: PRODUCT DETAIL VIEW ---
def product_detail(request, product_id):
    """Shows full details and allows ordering"""
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'market/detail.html', {'product': product})

# --- 3. UPDATED: CREATE ORDER (Handles Quantity) ---
@login_required
def create_order(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    # Validation
    if not product.seller.is_verified:
        messages.error(request, "Seller not verified.")
        return redirect('product_list')

    if request.user == product.seller:
        messages.warning(request, "You cannot buy your own product.")
        return redirect('product_detail', product_id=product.id)

    if request.method == 'POST':
        # Get quantity from the form (Default to 1 kg if missing)
        qty = int(request.POST.get('quantity', 1))
        
        if qty < 1:
            messages.error(request, "Quantity must be at least 1kg.")
            return redirect('product_detail', product_id=product.id)

        # Create Order
        order = Order.objects.create(
            buyer=request.user, 
            product=product,
            quantity=qty,               # Save quantity
            total_price=product.price * qty, # Calculate Total
            status='Pending'
        )
        return redirect('payment_page', order_id=order.id)
    
    # If someone tries to GET this URL directly, send them to detail page
    return redirect('product_detail', product_id=product.id)

@login_required
def payment_page(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    if request.method == 'POST':
        order.status = 'Paid'
        order.save()
        messages.success(request, "Payment successful! Order sent to seller.")
        return redirect('chat_room', user_id=order.product.seller.id)
    return render(request, 'market/payment.html', {'order': order})

@login_required
def add_product(request):
    if request.user.role == 'seller':
        return redirect('seller_products')
    return redirect('home')

# ==========================================
# 2. SELLER DASHBOARD VIEWS
# ==========================================

@login_required
def seller_dashboard(request):
    if request.user.role != 'seller': return redirect('home')

    # Alert if not verified
    if not request.user.is_verified:
        messages.warning(request, "Your account is NOT verified. You cannot list products until Admin approval.")

    my_products = Product.objects.filter(seller=request.user, is_active=True)
    my_orders = Order.objects.filter(product__seller=request.user)
    
    # --- FIX IS HERE ---
    # We now calculate revenue for Paid, Shipped, AND Delivered orders
    valid_statuses = ['Paid', 'Shipped', 'Delivered']
    
    revenue = my_orders.filter(status__in=valid_statuses).aggregate(Sum('total_price'))['total_price__sum'] or 0
    # -------------------
    
    status_data = list(my_orders.values('status').annotate(count=Count('status')))
    labels = [x['status'] for x in status_data]
    values = [x['count'] for x in status_data]

    context = {
        'products_count': my_products.count(),
        'orders_count': my_orders.count(),
        'revenue': revenue,
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values)
    }
    return render(request, 'seller_panel/dashboard.html', context)

@login_required
def seller_products(request):
    if request.user.role != 'seller': return redirect('home')

    # --- SECURITY CHECK ---
    # If seller is not verified, they cannot add products
    if request.method == 'POST':
        if not request.user.is_verified:
            messages.error(request, "Action Failed: Your account is pending verification.")
            return redirect('seller_products')

        action = request.POST.get('action')
        
        if action == 'add':
            Product.objects.create(
                seller=request.user,
                name=request.POST.get('name'),
                category=request.POST.get('category'),
                price=request.POST.get('price'),
                description=request.POST.get('description'),
                image=request.FILES.get('image')
            )
            messages.success(request, "Product listed successfully.")
            
        elif action == 'remove':
            p_id = request.POST.get('product_id')
            p = get_object_or_404(Product, id=p_id, seller=request.user)
            p.is_active = False 
            p.save()
            messages.warning(request, "Product removed from market.")
        
        return redirect('seller_products')

    products = Product.objects.filter(seller=request.user, is_active=True)
    return render(request, 'seller_panel/products.html', {'products': products})


@login_required
def seller_orders(request):
    if request.user.role != 'seller': return redirect('home')

    if request.method == 'POST':
        if not request.user.is_verified:
            messages.error(request, "Verification Required to manage orders.")
            return redirect('seller_orders')

        o_id = request.POST.get('order_id')
        action = request.POST.get('action')
        order = get_object_or_404(Order, id=o_id, product__seller=request.user)
        
        # --- Handle Status Actions ---
        if action == 'accept':
            order.status = 'Accepted' # Or 'Paid' if you want to skip payment logic
            messages.success(request, "Order Accepted.")
            
        elif action == 'shipped':
            order.status = 'Shipped'
            messages.info(request, "Order marked as On Shipping.")
            
        elif action == 'delivered':
            order.status = 'Delivered'
            messages.success(request, "Order marked as Delivered.")
            
        elif action == 'decline':
            order.status = 'Declined'
            messages.warning(request, "Order Declined.")

        elif action == 'pending':
            order.status = 'Pending' # Reset status
            messages.info(request, "Order status reset to Pending.")
        
        order.save()
        return redirect('seller_orders')

    orders = Order.objects.filter(product__seller=request.user).order_by('-created_at')
    return render(request, 'seller_panel/orders.html', {'orders': orders})

# --- BUYER ORDERS ---
@login_required
def buyer_orders(request):
    """View for buyers to see their purchase history"""
    orders = Order.objects.filter(buyer=request.user).order_by('-created_at')
    return render(request, 'market/buyer_orders.html', {'orders': orders})

@login_required
def business_profile(request):
    if request.user.role != 'seller': 
        return redirect('home')

    # 1. Get or Create Profile
    profile, created = SellerProfile.objects.get_or_create(user=request.user)

    # 2. Handle Form Post (Updating Profile)
    if request.method == 'POST':
        # Text Fields
        profile.company_name = request.POST.get('company_name', '')
        profile.country = request.POST.get('country', '')
        profile.city = request.POST.get('city', '')
        profile.description = request.POST.get('description', '')
        profile.core_products = request.POST.get('core_products', '')
        profile.certifications = request.POST.get('certifications', '')

        # Roles (Booleans)
        profile.is_farmer = 'is_farmer' in request.POST
        profile.is_roaster = 'is_roaster' in request.POST
        profile.is_exporter = 'is_exporter' in request.POST
        profile.is_supplier = 'is_supplier' in request.POST

        # File Upload (Logo)
        if 'logo' in request.FILES:
            profile.logo = request.FILES['logo']

        profile.save()
        messages.success(request, "Business Profile Updated Successfully!")
        return redirect('business_profile')

    # 3. Revenue Calculations (Existing Logic)
    now = timezone.now()
    valid_status = ['Paid', 'Shipped', 'Delivered']
    
    all_sales = Order.objects.filter(product__seller=request.user, status__in=valid_status)

    rev_today = all_sales.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
    rev_month = all_sales.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
    rev_year = all_sales.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0

    # 4. Inventory Stats
    total_products = Product.objects.filter(seller=request.user, is_active=True).count()
    total_orders = all_sales.count()

    # 5. Market Ranking (Existing Logic)
    # Note: Ensure User model is imported
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    sellers_ranked = User.objects.filter(role='seller').annotate(
        total_revenue=Coalesce(
            Sum('product__order__total_price', 
                filter=Q(product__order__status__in=valid_status)
            ), 
            Value(0), 
            output_field=DecimalField()
        )
    ).order_by('-total_revenue')

    my_rank = 0
    total_sellers = sellers_ranked.count()
    for rank, seller in enumerate(sellers_ranked, start=1):
        if seller.id == request.user.id:
            my_rank = rank
            break

    context = {
        'profile': profile,
        'rev_today': rev_today,
        'rev_month': rev_month,
        'rev_year': rev_year,
        'total_products': total_products,
        'total_orders': total_orders,
        'my_rank': my_rank,
        'total_sellers': total_sellers,
        'chart_labels': json.dumps(['Today', 'This Month', 'This Year']),
        'chart_data': json.dumps([float(rev_today), float(rev_month), float(rev_year)])
    }
    return render(request, 'seller_panel/business_profile.html', context)

# ================================
# 2. PUBLIC SELLER PROFILE (UPDATE)
# ================================
def public_seller_profile(request, seller_id):
    seller_user = get_object_or_404(User, id=seller_id)
    profile = get_object_or_404(SellerProfile, user=seller_user)
    
    # 1. Fetch Products for this seller
    products = Product.objects.filter(seller=seller_user, is_active=True)
    
    # 2. Fetch Certifications
    certs = SellerCertification.objects.filter(seller=profile)
    
    # 3. Calculate Stats
    valid_status = ['Paid', 'Shipped', 'Delivered']
    successful_orders = Order.objects.filter(product__seller=seller_user, status__in=valid_status).count()

    context = {
        'seller': seller_user,
        'profile': profile,
        'products': products,       # <--- Pass products to the template
        'certs': certs,
        'successful_orders': successful_orders,
        'product_count': products.count(),
    }
    # Ensure you have this template created (code below if you need it)
    return render(request, 'market/public_profile.html', context)

@login_required
def business_profile(request):
    if request.user.role != 'seller': 
        return redirect('home')

    # 1. Get Profile
    profile, created = SellerProfile.objects.get_or_create(user=request.user)
    
    # 2. Handle Forms (POST)
    if request.method == 'POST':
        # --- A. Update Profile Info ---
        if 'update_profile' in request.POST:
            profile.company_name = request.POST.get('company_name', '')
            profile.country = request.POST.get('country', '')
            profile.city = request.POST.get('city', '')
            profile.description = request.POST.get('description', '')
            profile.core_products = request.POST.get('core_products', '')
            
            # Roles (Checkbox logic)
            profile.is_farmer = 'is_farmer' in request.POST
            profile.is_roaster = 'is_roaster' in request.POST
            profile.is_exporter = 'is_exporter' in request.POST
            profile.is_supplier = 'is_supplier' in request.POST

            if 'logo' in request.FILES:
                profile.logo = request.FILES['logo']
            
            profile.save()
            messages.success(request, "Profile details updated successfully.")
            return redirect('business_profile')

        # --- B. Upload Certificate ---
        elif 'upload_cert' in request.POST:
            cert_form = CertificationForm(request.POST, request.FILES)
            if cert_form.is_valid():
                cert = cert_form.save(commit=False)
                cert.seller = profile
                cert.save()
                messages.success(request, "Certificate uploaded! Pending Verification.")
                return redirect('business_profile')
            else:
                messages.error(request, "Error uploading certificate. Please check input.")
    
    else:
        cert_form = CertificationForm()

    # 3. Revenue Logic
    now = timezone.now()
    valid_status = ['Paid', 'Shipped', 'Delivered']
    
    # Filter orders belonging to this seller
    all_sales = Order.objects.filter(product__seller=request.user, status__in=valid_status)

    # Calculate Totals
    rev_today = all_sales.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
    rev_month = all_sales.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
    rev_year = all_sales.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0

    # 4. Inventory Stats
    total_products = Product.objects.filter(seller=request.user, is_active=True).count()
    total_orders = all_sales.count()

    # 5. Market Ranking Logic
    # Rank sellers based on total revenue of valid orders
    sellers_ranked = User.objects.filter(role='seller').annotate(
        total_revenue=Coalesce(
            Sum('product__order__total_price', 
                filter=Q(product__order__status__in=valid_status)
            ), 
            Value(0), 
            output_field=DecimalField()
        )
    ).order_by('-total_revenue')

    my_rank = "N/A"
    total_sellers = sellers_ranked.count()
    
    # Find loop index
    for rank, seller in enumerate(sellers_ranked, start=1):
        if seller.id == request.user.id:
            my_rank = rank
            break

    # 6. Chart Data Preparation
    # Convert Decimals to Float for JSON
    chart_data = [float(rev_today), float(rev_month), float(rev_year)]
    chart_labels = ["Today", "This Month", "This Year"]

    context = {
        'profile': profile,
        'cert_form': cert_form,
        
        # Financials
        'rev_today': rev_today,
        'rev_month': rev_month,
        'rev_year': rev_year,
        
        # Stats
        'total_products': total_products,
        'total_orders': total_orders,
        'my_rank': my_rank,
        'total_sellers': total_sellers,
        
        # Chart (JSON strings)
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data)
    }
    
    return render(request, 'seller_panel/business_profile.html', context)

@login_required
def delete_certificate(request, cert_id):
    # Ensure user owns the profile linked to the cert
    cert = get_object_or_404(SellerCertification, id=cert_id, seller__user=request.user)
    cert.delete()
    messages.warning(request, "Certificate removed.")
    return redirect('business_profile')


def business_directory(request):
    """
    Advanced Business Directory with Filtering and Sorting
    """
    # 1. Base Query: All Sellers
    profiles = SellerProfile.objects.filter(user__role='seller')

    # 2. Annotation: Count Successful Orders (for sorting by success)
    # We follow the path: Profile -> User -> Product -> Order
    valid_statuses = ['Paid', 'Shipped', 'Delivered']
    profiles = profiles.annotate(
        successful_orders=Count(
            'user__product__order', 
            filter=Q(user__product__order__status__in=valid_statuses)
        )
    )

    # 3. Get Filter Parameters
    query = request.GET.get('q')
    country = request.GET.get('country')
    verified_seller = request.GET.get('verified_seller')
    verified_cert = request.GET.get('verified_cert')
    sort_by = request.GET.get('sort')

    # 4. Apply Filters
    
    # Search Text
    if query:
        profiles = profiles.filter(
            Q(company_name__icontains=query) | 
            Q(core_products__icontains=query) |
            Q(user__username__icontains=query)
        )

    # Filter by Country
    if country:
        profiles = profiles.filter(country=country)

    # Filter by Verified Seller Badge
    if verified_seller == 'on':
        profiles = profiles.filter(user__is_verified=True)

    # Filter by Verified Certificates (Has at least one verified cert)
    if verified_cert == 'on':
        profiles = profiles.filter(certificates__is_verified=True).distinct()

    # 5. Apply Sorting
    if sort_by == 'orders_high':
        profiles = profiles.order_by('-successful_orders')
    else:
        # Default sort: Verified sellers first, then by company name
        profiles = profiles.order_by('-user__is_verified', 'company_name')

    # 6. Get List of Countries for the Dropdown (Unique values only)
    # Exclude empty strings
    countries = SellerProfile.objects.exclude(country='').values_list('country', flat=True).distinct().order_by('country')

    context = {
        'profiles': profiles,
        'countries': countries,
    }
    return render(request, 'market/business_directory.html', context)
