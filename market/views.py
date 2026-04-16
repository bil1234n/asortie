from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, Value, DecimalField, Count, F, ExpressionWrapper
from django.db.models.functions import Coalesce 
from django.contrib.auth import get_user_model
import json
import stripe
import requests
from django.conf import settings
from django.urls import reverse

# Import Models
from .models import Product, Order, BusinessProfile, BusinessCertification, ProductVariant, ProductImage, SellerPaymentConfig
from core.models import Notification 
from .forms import CertificationForm 
from datetime import datetime
from django.utils import timezone
from datetime import timedelta
import math
import iyzipay


User = get_user_model()

# ==========================
# 1. MARKETPLACE VIEWS (PUBLIC)
# ==========================

def product_list(request):
    products = Product.objects.filter(is_active=True, seller__is_verified=True)
    
    q = request.GET.get('q')
    category = request.GET.get('category')
    sub_category = request.GET.get('sub_category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    if q:
        products = products.filter(
            Q(name__icontains=q) | 
            Q(description__icontains=q) | 
            Q(sub_category__icontains=q)
        )
    if category:
        products = products.filter(category=category)
    if sub_category:
        products = products.filter(sub_category=sub_category)
    if min_price:
        try: products = products.filter(price__gte=float(min_price))
        except: pass
    if max_price:
        try: products = products.filter(price__lte=float(max_price))
        except: pass

    products = products.order_by('-created_at')

    context = {
        'products': products, 
        'categories': Product.CATEGORY_CHOICES,
    }

    # PROFESSIONAL FIX: Check if the request is an AJAX call from our JavaScript
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax:
        # If AJAX, only return the raw HTML for the product cards
        return render(request, 'market/_product_grid.html', context)

    # Otherwise, return the full page
    return render(request, 'market/list.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    # Prefetch related variants and gallery for performance
    variants = product.variants.all() 
    gallery = product.gallery.all()
    
    return render(request, 'market/detail.html', {
        'product': product,
        'variants': variants,
        'gallery': gallery
    })

# ==========================
# 2. SELLER PANEL VIEWS
# ==========================

@login_required
def seller_dashboard(request):
    if request.user.role != 'seller': return redirect('home')
    my_products = Product.objects.filter(seller=request.user, is_active=True)
    my_orders = Order.objects.filter(product__seller=request.user)
    
    valid_statuses = ['Paid', 'Shipped', 'Delivered']
    revenue = my_orders.filter(status__in=valid_statuses).aggregate(Sum('total_price'))['total_price__sum'] or 0
    
    status_data = list(my_orders.values('status').annotate(count=Count('status')))
    
    # Handle charts safely
    import json
    chart_labels = json.dumps([x['status'] for x in status_data])
    chart_values = json.dumps([x['count'] for x in status_data])

    context = {
        'products_count': my_products.count(),
        'orders_count': my_orders.count(),
        'revenue': revenue,
        'chart_labels': chart_labels,
        'chart_values': chart_values
    }
    return render(request, 'seller_panel/dashboard.html', context)

@login_required
def seller_products(request):
    """List view for Seller's products"""
    if request.user.role != 'seller':
        return redirect('home')

    products = Product.objects.filter(seller=request.user, is_active=True).order_by('-created_at')
    return render(request, 'seller_panel/products.html', {'products': products})


# Helper functions assuming they exist based on your provided code
def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except ValueError:
        return default

def safe_int(val, default=0):
    try:
        return int(val) if val else default
    except ValueError:
        return default

@login_required
def seller_product_add(request):
    if request.user.role != 'seller': 
        return redirect('home')
    
    if not request.user.is_verified:
        messages.error(request, "You must be a verified seller to list products.")
        return redirect('seller_products')
    
    if request.method == 'POST':
        # 1. Create Core Product Data
        product = Product.objects.create(
            seller=request.user,
            name=request.POST.get('name'),
            category=request.POST.get('category', 'Classic'),
            sub_category=request.POST.get('sub_category'),
            description=request.POST.get('description'),
            price=safe_float(request.POST.get('price')),
            stock=safe_int(request.POST.get('stock')),
            
            # --- Delivery & Logistics Fields ---
            pickup_country=request.POST.get('pickup_country', 'Ethiopia'),
            pickup_lat=safe_float(request.POST.get('pickup_lat')) or None,
            pickup_lng=safe_float(request.POST.get('pickup_lng')) or None,
            address=request.POST.get('address', ''),
            free_delivery_km=safe_float(request.POST.get('free_delivery_km')),
            price_per_country=safe_float(request.POST.get('price_per_country')),
            price_per_0_1_km=safe_float(request.POST.get('price_per_0_1_km')),
            maximum_delivery_km=safe_float(request.POST.get('maximum_delivery_km'), 100.0),
            container_price=safe_float(request.POST.get('container_price')),
            container_number=safe_int(request.POST.get('container_number')),
            transport_fee=safe_float(request.POST.get('transport_fee')),
            transport_type=request.POST.get('transport_type', 'Land'),
        )
        
        # 2. Add Main Image
        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
            product.save()

        # 3. Handle Gallery Images Addition (Multiple)
        gallery_files = request.FILES.getlist('gallery_images')
        for f in gallery_files:
            ProductImage.objects.create(product=product, image=f)

        # 4. Handle 3D Variants Addition (Dynamic List)
        v_names = request.POST.getlist('variant_name[]')
        v_files = request.FILES.getlist('variant_file[]')
        v_links = request.POST.getlist('variant_link[]')

        for i in range(len(v_names)):
            if v_names[i]:  # Proceed only if variant name is provided
                file_to_upload = v_files[i] if i < len(v_files) else None
                link_to_save = v_links[i] if i < len(v_links) else ""

                ProductVariant.objects.create(
                    product=product,
                    variant_name=v_names[i],
                    model_3d=file_to_upload,
                    model_3d_link=link_to_save
                )
            
        messages.success(request, "Product added successfully with gallery and variants.")
        return redirect('seller_products')
        
    return render(request, 'seller_panel/products_form.html', {'edit_mode': False})


@login_required
def seller_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    
    if request.method == 'POST':
        # 1. Update Core Data
        product.name = request.POST.get('name')
        product.category = request.POST.get('category', 'Classic')
        product.sub_category = request.POST.get('sub_category')
        product.description = request.POST.get('description')
        product.price = safe_float(request.POST.get('price'))
        product.stock = safe_int(request.POST.get('stock'))
        
        # --- Delivery & Logistics Fields Update ---
        product.pickup_country = request.POST.get('pickup_country', 'Ethiopia')
        product.pickup_lat = safe_float(request.POST.get('pickup_lat')) or None
        product.pickup_lng = safe_float(request.POST.get('pickup_lng')) or None
        product.address = request.POST.get('address', '')
        product.free_delivery_km = safe_float(request.POST.get('free_delivery_km'))
        product.price_per_country = safe_float(request.POST.get('price_per_country'))
        product.price_per_0_1_km = safe_float(request.POST.get('price_per_0_1_km'))
        product.maximum_delivery_km = safe_float(request.POST.get('maximum_delivery_km'), 100.0)
        product.container_price = safe_float(request.POST.get('container_price'))
        product.container_number = safe_int(request.POST.get('container_number'))
        product.transport_fee = safe_float(request.POST.get('transport_fee'))
        product.transport_type = request.POST.get('transport_type', 'Land')
        
        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
            
        product.save()

        # 2. Deletion Logic (Professional String Parsing Handling)
        del_gallery_ids = request.POST.get('delete_gallery_ids', '').split(',')
        del_variant_ids = request.POST.get('delete_variant_ids', '').split(',')

        # Clean empty strings and Delete from DB
        del_gallery_ids = [id for id in del_gallery_ids if id.isdigit()]
        if del_gallery_ids:
            ProductImage.objects.filter(id__in=del_gallery_ids, product=product).delete()

        del_variant_ids = [id for id in del_variant_ids if id.isdigit()]
        if del_variant_ids:
            ProductVariant.objects.filter(id__in=del_variant_ids, product=product).delete()

        # 3. Add New Gallery Images Uploaded during edit
        gallery_files = request.FILES.getlist('gallery_images')
        for f in gallery_files:
            ProductImage.objects.create(product=product, image=f)

        # 4. Add New Variants Added during edit
        v_names = request.POST.getlist('variant_name[]')
        v_files = request.FILES.getlist('variant_file[]')
        v_links = request.POST.getlist('variant_link[]')

        for i in range(len(v_names)):
            if v_names[i]:
                file_to_upload = v_files[i] if i < len(v_files) else None
                link_to_save = v_links[i] if i < len(v_links) else ""
                
                ProductVariant.objects.create(
                    product=product,
                    variant_name=v_names[i],
                    model_3d=file_to_upload,
                    model_3d_link=link_to_save
                )

        messages.success(request, "Product updated successfully.")
        return redirect('seller_products')
        
    return render(request, 'seller_panel/products_form.html', {'product': product, 'edit_mode': True})

@login_required
def seller_product_delete(request, pk):
    """Permanently removes a product from the database"""
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    
    if request.method == "POST":
        # Delete the product and all associated variants/images (Cascade)
        product.delete() 
        messages.success(request, "Product permanently deleted.")
        
    return redirect('seller_products')



# ==========================
# 3. ORDER & PAYMENT (THE FIX)
# ==========================
@login_required
def seller_orders(request):
    if request.user.role != 'seller': 
        return redirect('home')

    now = timezone.now()
    # Change to timedelta(days=3) when you are done testing!
    expiration_time = now - timedelta(days=3) 
    
    # --- 1. AUTO-EXPIRE ENGINE (For Seller) ---
    expired_orders = Order.objects.filter(
        product__seller=request.user, 
        status='Quoted', 
        quoted_at__lt=expiration_time
    )
    for eo in expired_orders:
        eo.status = 'Expired'
        eo.save()

    # --- PART 1: POST LOGIC (Status Management & Negotiation) ---
    if request.method == 'POST':
        o_id = request.POST.get('order_id')
        action = request.POST.get('action')
        order = get_object_or_404(Order, id=o_id, product__seller=request.user)
        
        if action == 'set_quote':
            new_quote = request.POST.get('total_price')
            order.product_price = new_quote 
            order.total_price = new_quote
            order.delivery_fee = 0 
            
            order.seller_note = request.POST.get('seller_note')
            order.status = 'Quoted'
            order.quoted_at = timezone.now() # Record the time the quote was sent
            messages.success(request, f"Quote sent for Order #{order.id}")
        
        elif action == 'accept': order.status = 'Accepted'
        elif action == 'shipped': order.status = 'Shipped'
        elif action == 'delivered': order.status = 'Delivered'
        elif action == 'decline': order.status = 'Declined'
        elif action == 'pending': 
            order.status = 'Pending'
            order.quoted_at = None # Reset the quote timer when reopening
        elif action == 'quoted_reverse': order.status = 'Quoted'
        elif action == 'accepted_reverse': order.status = 'Accepted'
        elif action == 'shipped_reverse': order.status = 'Shipped'
        
        order.save()
        
        # Professional Notification
        Notification.objects.create(
            recipient=order.buyer,
            sender=request.user,
            notification_type='order',
            message=f"Order Update: Your inquiry for {order.product.name} is now '{order.get_status_display()}'.",
            link=reverse('buyer_orders')
        )
        
        messages.info(request, f"Order #{order.id} moved to {order.get_status_display()}.")
        return redirect('seller_orders')

    # --- PART 2: GET LOGIC (Advanced Filtering) ---
    orders = Order.objects.filter(product__seller=request.user).order_by('-created_at')

    # Capture Filter Parameters
    q_user = request.GET.get('username')
    q_product = request.GET.get('product_name')
    q_date = request.GET.get('date')
    q_month = request.GET.get('month')
    q_year = request.GET.get('year')
    q_min = request.GET.get('min_price')
    q_max = request.GET.get('max_price')

    # Apply Filters if they exist
    if q_user:
        orders = orders.filter(buyer__username__icontains=q_user)
    if q_product:
        orders = orders.filter(product__name__icontains=q_product)
    if q_date:
        orders = orders.filter(created_at__date=q_date)
    if q_month:
        orders = orders.filter(created_at__month=q_month)
    if q_year:
        orders = orders.filter(created_at__year=q_year)
    if q_min:
        orders = orders.filter(total_price__gte=q_min)
    if q_max:
        orders = orders.filter(total_price__lte=q_max)

    # Prepare Context Data for UI Select Boxes
    current_year = datetime.now().year
    years = range(current_year, current_year - 5, -1)
    months = [
        (1, "January"), (2, "February"), (3, "March"), (4, "April"),
        (5, "May"), (6, "June"), (7, "July"), (8, "August"),
        (9, "September"), (10, "October"), (11, "November"), (12, "December")
    ]

    context = {
        'orders': orders,
        'years': years,
        'months': months,
    }
    
    return render(request, 'seller_panel/orders.html', context)

@login_required
def seller_order_detail(request, order_id):
    """
    Dedicated Professional Details Page for a specific Order.
    Shows map routing, financial breakdown, and buyer details.
    """
    if request.user.role != 'seller':
        return redirect('home')
        
    order = get_object_or_404(Order, id=order_id, product__seller=request.user)
    
    context = {
        'order': order,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY  # Ensure this is set in settings.py
    }
    return render(request, 'seller_panel/order_details.html', context)

@login_required
def create_order(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if not product.seller.is_verified:
        messages.error(request, "Seller not verified.")
        return redirect('product_list')

    if request.user == product.seller:
        messages.warning(request, "You cannot buy your own product.")
        return redirect('product_detail', product_id=product.id)

    if request.method == 'POST':
        qty = int(request.POST.get('quantity', 1))
        
        # New Inquiry Logic: Initial price is 0
        order = Order.objects.create(
            buyer=request.user, 
            product=product,
            quantity=qty,
            total_price=0, 
            status='Pending'
        )
        
        # Notify Seller of new inquiry
        Notification.objects.create(
            recipient=product.seller,
            sender=request.user,
            notification_type='order',
            message=f"New Inquiry: {request.user.username} is interested in {product.name}.",
            link=reverse('seller_orders')
        )

        messages.success(request, "Inquiry sent! Please wait for the seller to provide a final quote.")
        return redirect('buyer_orders')
    
    return redirect('product_detail', product_id=product.id)

@login_required
def buyer_orders(request):
    now = timezone.now()
    three_days_ago = now - timedelta(days=3)
    
    # 1. AUTO-EXPIRE ENGINE: Find quotes older than 3 days and mark them Expired
    expired_orders = Order.objects.filter(
        buyer=request.user, 
        status='Quoted', 
        quoted_at__lt=three_days_ago
    )
    for eo in expired_orders:
        eo.status = 'Expired'
        eo.save()

    # 2. Base queryset for this buyer
    orders = Order.objects.filter(buyer=request.user).select_related('product', 'product__seller').order_by('-created_at')
    
    # --- ADVANCED FILTERING ---
    q_product = request.GET.get('product_name')
    q_date = request.GET.get('date')
    q_month = request.GET.get('month')
    q_year = request.GET.get('year')
    q_min = request.GET.get('min_price')
    q_max = request.GET.get('max_price')

    if q_product:
        orders = orders.filter(product__name__icontains=q_product)
    if q_date:
        orders = orders.filter(created_at__date=q_date)
    if q_month:
        orders = orders.filter(created_at__month=q_month)
    if q_year:
        orders = orders.filter(created_at__year=q_year)
    if q_min:
        orders = orders.filter(total_price__gte=q_min)
    if q_max:
        orders = orders.filter(total_price__lte=q_max)

    # Calculate total spent (on successful orders)
    total_spend = orders.filter(status__in=['Paid', 'Shipped', 'Delivered']).aggregate(Sum('total_price'))['total_price__sum'] or 0
    
    # 3. ATTACH EXPIRATION DEADLINE FOR THE TEMPLATE COUNTDOWN
    for order in orders:
        if order.status == 'Quoted' and order.quoted_at:
            order.expires_at = order.quoted_at + timedelta(days=3)

    # Data for filter dropdowns
    current_year = datetime.now().year
    years = range(current_year, current_year - 5, -1)
    months = [
        (1, "January"), (2, "February"), (3, "March"), (4, "April"),
        (5, "May"), (6, "June"), (7, "July"), (8, "August"),
        (9, "September"), (10, "October"), (11, "November"), (12, "December")
    ]

    context = {
        'orders': orders, 
        'total_spend': total_spend,
        'years': years,
        'months': months
    }
    return render(request, 'market/buyer_orders.html', context)

@login_required
def payment(request, order_id):
    """Buyer Checkout View - Dynamically shows only seller-allowed payment methods"""
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    if order.status == 'Pending':
        messages.warning(request, "Awaiting seller quote. You will be able to pay once the price is set.")
        return redirect('buyer_orders')

    # --- Fetch Seller Payment Configurations ---
    seller_config = getattr(order.product.seller, 'payment_config', None)
    
    seller_has_stripe = bool(seller_config and seller_config.stripe_account_id)
    seller_has_chapa = bool(seller_config and seller_config.chapa_account_id)
    seller_has_iyzico = bool(seller_config and seller_config.iyzico_api_key and seller_config.iyzico_secret_key)
    seller_has_cod = bool(seller_config and seller_config.is_cod_enabled)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        
        # --- SECURITY CHECK: Ensure buyer didn't force a disabled method ---
        if payment_method == 'stripe' and not seller_has_stripe:
            messages.error(request, "Stripe is not accepted by this seller.")
            return redirect('payment', order_id=order.id)
            
        if payment_method == 'chapa' and not seller_has_chapa:
            messages.error(request, "Chapa is not accepted by this seller.")
            return redirect('payment', order_id=order.id)
            
        if payment_method == 'iyzico' and not seller_has_iyzico:
            messages.error(request, "Iyzico is not accepted by this seller.")
            return redirect('payment', order_id=order.id)
        
        if payment_method == 'cod' and not seller_has_cod:
            messages.error(request, "Cash on Delivery is not allowed by this seller.")
            return redirect('payment', order_id=order.id)

        # Standard Processing...
        delivery_option = request.POST.get('delivery_option', 'Pickup')
        delivery_fee = float(request.POST.get('calculated_delivery_fee', 0.0))
        
        order.delivery_option = delivery_option
        order.delivery_fee = delivery_fee
        order.delivery_lat = request.POST.get('delivery_lat') or None
        order.delivery_lng = request.POST.get('delivery_lng') or None
        order.buyer_country = request.POST.get('buyer_country') or None
        order.payment_gateway = payment_method 
        
        selected_transport = request.POST.get('transport_type')
        if selected_transport:
            order.seller_note = (order.seller_note or "") + f" [Buyer Requested Transport: {selected_transport}]"

        base_price = float(order.product_price) if order.product_price > 0 else float(order.total_price)
        order.product_price = base_price 
        order.total_price = base_price + delivery_fee 
        order.save()

        # Gateways
        if payment_method == 'stripe': return redirect('stripe_checkout', order_id=order.id)
        elif payment_method == 'chapa': return redirect('chapa_checkout', order_id=order.id)
        elif payment_method == 'iyzico': return redirect('iyzico_checkout', order_id=order.id)
        elif payment_method == 'cod':
            order.status = 'Accepted'
            order.save()
            Notification.objects.create(recipient=request.user, notification_type='order', message=f"Order Confirmed: You selected Cash on Delivery for {order.product.name}.", link=reverse('buyer_orders'))
            Notification.objects.create(recipient=order.product.seller, notification_type='order', message=f"New COD Order: {request.user.username} chose Cash on Delivery for {order.product.name}.", link=reverse('seller_orders'))
            messages.success(request, "Order confirmed! You will pay when the item arrives.")
            return redirect('buyer_orders')

    context = {
        'order': order,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
        # Pass flags to template
        'seller_has_stripe': seller_has_stripe,
        'seller_has_chapa': seller_has_chapa,
        'seller_has_iyzico': seller_has_iyzico,
        'seller_has_cod': seller_has_cod,
    }
    return render(request, 'market/payment.html', context)

@login_required
def stripe_checkout(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # Safety Check
    if order.total_price <= 0:
        messages.error(request, "Price not yet quoted.")
        return redirect('buyer_orders')

    # Ensure the seller has a Stripe Account linked
    seller_config = getattr(order.product.seller, 'payment_config', None)
    if not seller_config or not seller_config.stripe_account_id:
        messages.error(request, "The seller has not configured their payment method yet. Please contact support.")
        return redirect('buyer_orders')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    success_url = request.build_absolute_uri(f'/payment-success/{order.id}/')
    
    # Calculate totals in cents
    total_cents = int(math.ceil(order.total_price * 100))
    
    # Calculate the 5% Asortie platform fee
    application_fee_cents = int(math.ceil(total_cents * 0.05))

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': order.product.name},
                    'unit_amount': total_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            payment_intent_data={
                # The 5% cut for the platform
                'application_fee_amount': application_fee_cents,
                # The remaining 95% goes to the seller
                'transfer_data': {
                    'destination': seller_config.stripe_account_id,
                },
            },
            success_url=success_url,
            cancel_url=request.build_absolute_uri(f'/payment-page/{order.id}'),
        )
        return redirect(session.url)
    except stripe.error.StripeError as e:
        messages.error(request, f"Stripe Error: {str(e)}")
        return redirect('payment', order_id=order.id)
    
@login_required
def chapa_checkout(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    if order.total_price <= 0:
        messages.error(request, "Price not yet quoted.")
        return redirect('buyer_orders')

    USD_TO_ETB_RATE = 156.00
    etb_amount = float(order.total_price) * USD_TO_ETB_RATE
    
    headers = {"Authorization": f"Bearer {settings.CHAPA_SECRET_KEY}", "Content-Type": "application/json"}
    callback_url = request.build_absolute_uri(f'/payment-success/{order.id}/')

    data = {
        "amount": etb_amount,
        "currency": "ETB",
        "email": request.user.email,
        "callback_url": callback_url,
        "return_url": callback_url,
        "title": f"Payment for {order.product.name}"
    }
    
    response = requests.post("https://api.chapa.co/v1/transaction/initialize", json=data, headers=headers)
    result = response.json()
    
    if result.get('status') == 'success':
        return redirect(result['data']['checkout_url'])
    else:
        messages.error(request, "Payment gateway error.")
        return redirect('payment_page', order_id=order.id)



@login_required
def iyzico_checkout(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # 1. Basic Validation
    if order.total_price <= 0:
        messages.error(request, "Price not yet quoted.")
        return redirect('buyer_orders')

    seller_config = getattr(order.product.seller, 'payment_config', None)
    if not seller_config or not seller_config.iyzico_api_key:
        messages.error(request, "Payment configuration missing.")
        return redirect('buyer_orders')

    # 2. Currency Conversion (Keep as float for calculation, then str for Iyzico)
    USD_TO_TRY_RATE = 32.50 
    total_amount = str(round(float(order.total_price) * USD_TO_TRY_RATE, 2))
    
    # 3. Iyzico Config (No https://)
    options = {
        'api_key': seller_config.iyzico_api_key,
        'secret_key': seller_config.iyzico_secret_key,
        'base_url': 'sandbox-api.iyzipay.com' 
    }

    # Use a generic callback for testing if localhost fails
    callback_url = request.build_absolute_uri(f'/payment-success/{order.id}/')

    # 4. Request Payload
    request_data = {
        'locale': 'en',
        'conversationId': str(order.id),
        'price': total_amount,
        'paidPrice': total_amount,
        'currency': 'TRY',
        'basketId': f"B{order.id}",
        'callbackUrl': callback_url,
        'buyer': {
            'id': str(request.user.id),
            'name': 'John',
            'surname': 'Doe',
            'email': 'test@email.com',
            'gsmNumber': '+905321234567', 
            'identityNumber': '11111111111', 
            'registrationAddress': 'Adalet Mahallesi, No:41',
            'city': 'Istanbul',
            'country': 'Turkey',
            'zipCode': '34732',
            'ip': '127.0.0.1' 
        },
        'shippingAddress': {
            'contactName': 'John Doe',
            'city': 'Istanbul',
            'country': 'Turkey',
            'address': 'Adalet Mahallesi, No:41',
            'zipCode': '34732'
        },
        'billingAddress': {
            'contactName': 'John Doe',
            'city': 'Istanbul',
            'country': 'Turkey',
            'address': 'Adalet Mahallesi, No:41',
            'zipCode': '34732'
        },
        'basketItems': [
            {
                'id': f"PR{order.product.id}",
                'name': 'Luxury Furniture Item', 
                'category1': 'Furniture',
                'itemType': 'PHYSICAL',
                'price': total_amount
            }
        ]
    }

    # 5. Execute
    checkout_form_initialize = iyzipay.CheckoutFormInitialize().create(request_data, options)
    response_json = json.loads(checkout_form_initialize.read().decode('utf-8'))
    
    if response_json.get('status') == 'success':
        # REDIRECT DIRECTLY to the hosted page URL
        payment_url = response_json.get('paymentPageUrl')
        return redirect(payment_url)
    else:
        error_msg = response_json.get('errorMessage', 'Payment gateway error.')
        messages.error(request, f"Iyzico Error: {error_msg}")
        return redirect('buyer_orders')
    
@login_required
def payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    if order.status == 'Paid': return redirect('buyer_orders')

    order.status = 'Paid'
    order.save()

    # Notification Logic
    msg_buyer = f"Payment Successful: Order #{order.id} for {order.product.name}."
    msg_seller = f"New Payment! {request.user.username} paid ${order.total_price} for {order.product.name}."
    
    Notification.objects.create(recipient=request.user, notification_type='order', message=msg_buyer, link=reverse('buyer_orders'))
    Notification.objects.create(recipient=order.product.seller, notification_type='order', message=msg_seller, link=reverse('seller_orders'))
    
    messages.success(request, "Payment confirmed!")
    return redirect('buyer_orders')

@login_required
def cancel_order(request, order_id):
    # We look for the order
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # Check if it's in a state where cancellation is allowed
    if order.status in ['Pending', 'Quoted']:
        order.status = 'Cancelled' # Or add 'Cancelled' to your STATUS_CHOICES
        order.save()
        messages.info(request, "Inquiry cancelled.")
    else:
        messages.error(request, "Cannot cancel an order that is already being processed or paid.")
        
    return redirect('buyer_orders')

@login_required
def seller_payment_setup(request):
    if request.user.role != 'seller':
        return redirect('home')

    config, created = SellerPaymentConfig.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. DELETE ACTIONS
        if action == 'delete_stripe':
            config.stripe_account_id = None
            config.save()
            messages.success(request, "Stripe account removed successfully.")
            return redirect('seller_payment_setup')
            
        elif action == 'delete_chapa':
            config.chapa_account_id = None
            config.save()
            messages.success(request, "Chapa account removed successfully.")
            return redirect('seller_payment_setup')

        elif action == 'delete_iyzico':
            config.iyzico_api_key = None
            config.iyzico_secret_key = None
            config.save()
            messages.success(request, "Iyzico account removed successfully.")
            return redirect('seller_payment_setup')

        # 2. SAVE / UPDATE ACTIONS
        elif action == 'save_all':
            stripe_id = request.POST.get('stripe_account_id', '').strip()
            chapa_id = request.POST.get('chapa_account_id', '').strip()
            iyzico_api = request.POST.get('iyzico_api_key', '').strip()
            iyzico_secret = request.POST.get('iyzico_secret_key', '').strip()
            is_cod = request.POST.get('is_cod_enabled') == 'on' 

            # Validation
            if stripe_id and not stripe_id.startswith('acct_'):
                messages.error(request, "Invalid Stripe ID. It must start with 'acct_'")
            else:
                config.stripe_account_id = stripe_id if stripe_id else None
                config.chapa_account_id = chapa_id if chapa_id else None
                config.iyzico_api_key = iyzico_api if iyzico_api else None
                config.iyzico_secret_key = iyzico_secret if iyzico_secret else None
                config.is_cod_enabled = is_cod
                config.save()
                messages.success(request, "Payment preferences updated successfully.")

        return redirect('seller_payment_setup')

    return render(request, 'seller_panel/seller_payment.html', {'config': config})

@login_required
def seller_transactions(request):
    # FIXED ACCESS CHECK: Use the role system
    if request.user.role != 'seller':
        messages.error(request, "Access denied. Seller account required.")
        return redirect('home')

    # Get all successful orders for this seller
    completed_orders = Order.objects.filter(
        product__seller=request.user,
        status__in=['Paid', 'Shipped', 'Delivered']
    ).select_related('product', 'buyer').order_by('-created_at')

    # Safely aggregate totals
    stats = completed_orders.aggregate(total_gross=Sum('total_price'))
    gross_total = stats['total_gross'] or 0.00
    
    platform_fee_total = float(gross_total) * 0.05
    net_earnings_total = float(gross_total) * 0.95

    # Manually attach calculated fields for the template
    for order in completed_orders:
        order.gross = float(order.total_price)
        order.fee = order.gross * 0.05
        order.net = order.gross * 0.95

    context = {
        'transactions': completed_orders,
        'total_gross': gross_total,
        'total_fee': platform_fee_total,
        'total_net': net_earnings_total,
    }
    return render(request, 'seller_panel/seller_transaction.html', context)

# ==========================
# 3. UNIFIED BUSINESS PROFILE
# ==========================
@login_required
def business_profile(request):
    profile, created = BusinessProfile.objects.get_or_create(user=request.user)
    cert_form = CertificationForm()

    # --- 1. HANDLE FORMS ---
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            profile.company_name = request.POST.get('company_name', '')
            profile.country = request.POST.get('country', '')
            profile.city = request.POST.get('city', '')
            profile.description = request.POST.get('description', '')
            profile.core_products = request.POST.get('core_products', '')
            
            # Roles
            profile.is_farmer = 'is_farmer' in request.POST
            profile.is_roaster = 'is_roaster' in request.POST
            profile.is_exporter = 'is_exporter' in request.POST
            profile.is_supplier = 'is_supplier' in request.POST

            if 'logo' in request.FILES:
                profile.logo = request.FILES['logo']
            
            profile.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('business_profile')

        elif 'upload_cert' in request.POST:
            cert_form = CertificationForm(request.POST, request.FILES)
            if cert_form.is_valid():
                cert = cert_form.save(commit=False)
                cert.profile = profile 
                cert.save()
                messages.success(request, "Document uploaded successfully.")
                return redirect('business_profile')
            else:
                messages.error(request, "Error uploading document.")

    # --- 2. ANALYTICS & REVENUE ---
    now = timezone.now()
    valid_status = ['Paid', 'Shipped', 'Delivered']
    
    # Defaults
    val_today = 0
    val_month = 0
    val_year = 0
    label_1 = "Revenue Today" # Default to Seller terminology
    label_2 = "Active Listings"
    label_3 = "Total Sales"
    count_1 = 0 
    count_2 = 0
    
    # Ranking Defaults
    my_rank = "N/A"
    total_sellers = 0

    if request.user.role == 'seller':
        # SELLER LOGIC
        orders = Order.objects.filter(product__seller=request.user, status__in=valid_status)
        
        # Financials
        val_today = orders.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_month = orders.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_year = orders.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        
        count_1 = Product.objects.filter(seller=request.user, is_active=True).count()
        count_2 = orders.count()

        # --- MARKET RANKING ALGORITHM ---
        # 1. Annotate every seller with their total revenue
        sellers_ranked = User.objects.filter(role='seller').annotate(
            total_revenue=Coalesce(
                Sum('product__order__total_price', 
                    filter=Q(product__order__status__in=valid_status)
                ), 
                Value(0), 
                output_field=DecimalField()
            )
        ).order_by('-total_revenue')

        total_sellers = sellers_ranked.count()
        
        # 2. Find my index
        for rank, seller in enumerate(sellers_ranked, start=1):
            if seller.id == request.user.id:
                my_rank = rank
                break

    else:
        # BUYER LOGIC (Spend Analysis)
        label_1 = "Spend Today"
        label_2 = "Orders Placed"
        label_3 = "-" 
        
        orders = Order.objects.filter(buyer=request.user, status__in=valid_status)
        val_today = orders.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_month = orders.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_year = orders.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        
        count_1 = orders.count()

    # --- 3. CONTEXT ---
    context = {
        'profile': profile,
        'cert_form': cert_form,
        
        # Financial Values
        'val_today': val_today,
        'val_month': val_month,
        'val_year': val_year,
        
        # Dynamic Labels (So it works for Buyer & Seller)
        'label_1': label_1, 
        'label_2': label_2, 
        'label_3': label_3,
        
        # Stats
        'count_1': count_1,
        'count_2': count_2,
        
        # Ranking
        'my_rank': my_rank,
        'total_sellers': total_sellers,
        
        # Chart
        'chart_labels': json.dumps(['Today', 'This Month', 'This Year']),
        'chart_data': json.dumps([float(val_today), float(val_month), float(val_year)])
    }
    
    return render(request, 'market/business_profile.html', context)

@login_required
def view_business_profile(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    profile, created = BusinessProfile.objects.get_or_create(user=user_obj)

    # The SAME analytics logic you already have
    now = timezone.now()
    valid_status = ['Paid', 'Shipped', 'Delivered']

    # Financial defaults
    val_today = val_month = val_year = 0
    label_1 = "Revenue Today"
    label_2 = "Active Listings"
    label_3 = "Total Sales"
    count_1 = count_2 = 0
    my_rank = "N/A"
    total_sellers = 0

    # If seller → seller analytics
    if user_obj.role == 'seller':
        orders = Order.objects.filter(product__seller=user_obj, status__in=valid_status)

        val_today = orders.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_month = orders.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_year = orders.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0

        count_1 = Product.objects.filter(seller=user_obj, is_active=True).count()
        count_2 = orders.count()

        sellers_ranked = User.objects.filter(role='seller').annotate(
            total_revenue=Coalesce(
                Sum('product__order__total_price',
                    filter=Q(product__order__status__in=valid_status)
                ),
                Value(0),
                output_field=DecimalField()
            )
        ).order_by('-total_revenue')

        total_sellers = sellers_ranked.count()

        for rank, seller in enumerate(sellers_ranked, start=1):
            if seller.id == user_obj.id:
                my_rank = rank
                break

    # If buyer → buyer analytics
    else:
        label_1 = "Spend Today"
        label_2 = "Orders Placed"
        label_3 = "-"

        orders = Order.objects.filter(buyer=user_obj, status__in=valid_status)

        val_today = orders.filter(created_at__date=now.date()).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_month = orders.filter(created_at__month=now.month, created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0
        val_year = orders.filter(created_at__year=now.year).aggregate(Sum('total_price'))['total_price__sum'] or 0

        count_1 = orders.count()

    context = {
        'profile': profile,
        'view_user': user_obj,   # important!
        
        'val_today': val_today,
        'val_month': val_month,
        'val_year': val_year,

        'label_1': label_1,
        'label_2': label_2,
        'label_3': label_3,

        'count_1': count_1,
        'count_2': count_2,

        'my_rank': my_rank,
        'total_sellers': total_sellers,

        'chart_labels': json.dumps(['Today', 'This Month', 'This Year']),
        'chart_data': json.dumps([float(val_today), float(val_month), float(val_year)]),
    }

    return render(request, 'market/business_profile.html', context)

@login_required
def delete_certificate(request, cert_id):
    cert = get_object_or_404(BusinessCertification, id=cert_id, profile__user=request.user)
    cert.delete()
    messages.warning(request, "Document removed.")
    return redirect('business_profile')

def business_directory(request):
    """
    Directory to find Sellers.
    """
    profiles = BusinessProfile.objects.filter(user__role='seller')
    
    valid_statuses = ['Paid', 'Shipped', 'Delivered']
    profiles = profiles.annotate(
        successful_orders=Count(
            'user__product__order', 
            filter=Q(user__product__order__status__in=valid_statuses)
        )
    )

    query = request.GET.get('q')
    country = request.GET.get('country')
    verified = request.GET.get('verified_seller')

    if query:
        profiles = profiles.filter(
            Q(company_name__icontains=query) | 
            Q(core_products__icontains=query) |
            Q(user__username__icontains=query)
        )
    if country:
        profiles = profiles.filter(country=country)
    if verified == 'on':
        profiles = profiles.filter(user__is_verified=True)

    countries = BusinessProfile.objects.exclude(country='').values_list('country', flat=True).distinct()

    context = {'profiles': profiles, 'countries': countries}
    return render(request, 'market/business_directory.html', context)

def public_business_profile(request, seller_id):
    seller = get_object_or_404(User, id=seller_id)
    profile = get_object_or_404(BusinessProfile, user=seller)
    
    products = Product.objects.filter(seller=seller, is_active=True)
    certs = BusinessCertification.objects.filter(profile=profile, is_verified=True)
    
    valid_status = ['Paid', 'Shipped', 'Delivered']
    successful_orders = Order.objects.filter(product__seller=seller, status__in=valid_status).count()
    product_count_all = Product.objects.filter(seller=seller).count()

    
    context = {
        'seller': seller,
        'profile': profile,
        'products': products,
        'certs': certs,
        'successful_orders': successful_orders,
        'product_count_all': product_count_all,
    }
    return render(request, 'market/public_profile.html', context)

