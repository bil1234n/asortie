from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, Value, DecimalField, Count
from django.db.models.functions import Coalesce 
from django.contrib.auth import get_user_model
import json
import stripe
import requests
from django.conf import settings
from django.urls import reverse

# Import Models
from .models import Product, Order, BusinessProfile, BusinessCertification, ProductVariant, ProductImage
from core.models import Notification 
from .forms import CertificationForm 

User = get_user_model()

# ==========================
# 1. MARKETPLACE VIEWS (PUBLIC)
# ==========================

def product_list(request):
    products = Product.objects.filter(is_active=True, seller__is_verified=True)
    q = request.GET.get('q')
    category = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    sort_by = request.GET.get('sort')

    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category:
        products = products.filter(category=category)
    if min_price:
        try: products = products.filter(price__gte=float(min_price))
        except: pass
    if max_price:
        try: products = products.filter(price__lte=float(max_price))
        except: pass

    if sort_by == 'price_asc': products = products.order_by('price')
    elif sort_by == 'price_desc': products = products.order_by('-price')
    else: products = products.order_by('-created_at')

    context = {'products': products, 'categories': Product.CATEGORY_CHOICES}
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

@login_required
def seller_product_add(request):
    """Handles creating a new product with Gallery and 3D Variants"""
    if request.user.role != 'seller':
        return redirect('home')
    
    if not request.user.is_verified:
        messages.error(request, "You must be a verified seller to list products.")
        return redirect('seller_products')

    if request.method == 'POST':
        # 1. Basic Product Info
        name = request.POST.get('name')
        category = request.POST.get('category')
        description = request.POST.get('description')
        price = request.POST.get('price')
        
        # Handle empty price for 'Negotiated' strategy
        if not price or price.strip() == "":
            price = 0
            
        main_image = request.FILES.get('image')

        product = Product.objects.create(
            seller=request.user,
            name=name,
            category=category,
            price=price,
            description=description,
            image=main_image
        )

        # 2. Handle Gallery Images (Multiple)
        gallery_files = request.FILES.getlist('gallery_images')
        for f in gallery_files:
            ProductImage.objects.create(product=product, image=f)

        # 3. Handle 3D Variants (Dynamic List)
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

        messages.success(request, "Product added successfully with gallery and variants.")
        return redirect('seller_products')

    return render(request, 'seller_panel/products_form.html', {'edit_mode': False})

@login_required
def seller_product_edit(request, pk):
    """Handles editing existing product with professional deletion logic"""
    product = get_object_or_404(Product, pk=pk, seller=request.user)

    if request.method == 'POST':
        # 1. Update Basic Fields
        product.name = request.POST.get('name')
        product.category = request.POST.get('category')
        product.description = request.POST.get('description')
        
        price = request.POST.get('price')
        product.price = price if price and price.strip() else 0
        
        # Update Main Image if a new one is uploaded
        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
        
        product.save()

        # 2. DELETE Logic (Professional Handling)
        # We receive a comma-separated string of IDs to delete (e.g., "4,8,12")
        del_gallery_ids = request.POST.get('delete_gallery_ids', '').split(',')
        del_variant_ids = request.POST.get('delete_variant_ids', '').split(',')

        # Clean empty strings and Delete from DB
        del_gallery_ids = [id for id in del_gallery_ids if id.isdigit()]
        if del_gallery_ids:
            ProductImage.objects.filter(id__in=del_gallery_ids, product=product).delete()

        del_variant_ids = [id for id in del_variant_ids if id.isdigit()]
        if del_variant_ids:
            ProductVariant.objects.filter(id__in=del_variant_ids, product=product).delete()

        # 3. ADD NEW Gallery Images
        gallery_files = request.FILES.getlist('gallery_images')
        for f in gallery_files:
            ProductImage.objects.create(product=product, image=f)

        # 4. ADD NEW Variants
        v_names = request.POST.getlist('variant_name[]')
        v_files = request.FILES.getlist('variant_file[]')
        v_links = request.POST.getlist('variant_link[]')

        for i in range(len(v_names)):
            if v_names[i]: # Only create if name exists
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

    if request.method == 'POST':
        o_id = request.POST.get('order_id')
        action = request.POST.get('action')
        order = get_object_or_404(Order, id=o_id, product__seller=request.user)
        
        # 1. NEGOTIATION LOGIC
        if action == 'set_quote':
            order.total_price = request.POST.get('total_price')
            order.seller_note = request.POST.get('seller_note')
            order.status = 'Quoted'
            messages.success(request, f"Quote sent for Order #{order.id}")
        
        # 2. STANDARD WORKFLOW LOGIC (Forward)
        elif action == 'accept': 
            order.status = 'Accepted'
        elif action == 'shipped': 
            order.status = 'Shipped'
        elif action == 'delivered': 
            order.status = 'Delivered'
        elif action == 'decline': 
            order.status = 'Declined'
            
        # 3. REVERSE & RE-OPEN LOGIC (Backwards)
        elif action == 'pending': 
            # This handles both "Reset to Pending" and "Re-open Declined Inquiry"
            order.status = 'Pending'
        elif action == 'quoted_reverse': 
            order.status = 'Quoted'
        elif action == 'accepted_reverse': 
            order.status = 'Accepted'
        elif action == 'shipped_reverse': 
            order.status = 'Shipped'
        
        # Save the changes
        order.save()
        
        # 4. PROFESSIONAL NOTIFICATION
        # We use get_status_display() to show the "Human Readable" name (e.g. "Price Offered")
        Notification.objects.create(
            recipient=order.buyer,
            sender=request.user,
            notification_type='order',
            message=f"Order Update: Your inquiry for {order.product.name} is now '{order.get_status_display()}'.",
            link=reverse('buyer_orders')
        )
        
        messages.info(request, f"Order #{order.id} moved to {order.get_status_display()}.")
        return redirect('seller_orders')

    # GET: Fetch all orders including 'Pending'
    orders = Order.objects.filter(product__seller=request.user).order_by('-created_at')
    return render(request, 'seller_panel/orders.html', {'orders': orders})

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
    orders = Order.objects.filter(buyer=request.user).select_related('product', 'product__seller').order_by('-created_at')
    total_spend = orders.filter(status__in=['Paid', 'Shipped', 'Delivered']).aggregate(Sum('total_price'))['total_price__sum'] or 0
    return render(request, 'market/buyer_orders.html', {'orders': orders, 'total_spend': total_spend})

@login_required
def payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # SAFETY: Don't allow payment if price isn't set
    if order.status == 'Pending':
        messages.warning(request, "Awaiting seller quote. You will be able to pay once the price is set.")
        return redirect('buyer_orders')

    return render(request, 'market/payment.html', {'order': order})

@login_required
def stripe_checkout(request, order_id):
    order = get_object_or_404(Order, id=order_id, buyer=request.user)
    
    # Safety Check
    if order.total_price <= 0:
        messages.error(request, "Price not yet quoted.")
        return redirect('buyer_orders')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    success_url = request.build_absolute_uri(f'/payment-success/{order.id}/')
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': order.product.name},
                'unit_amount': int(order.total_price * 100), # Uses Negotiated Price
            },
            'quantity': 1, # Negotiated price usually covers the full set
        }],
        mode='payment',
        success_url=success_url,
        cancel_url=request.build_absolute_uri(f'/payment-page/{order.id}'),
    )
    return redirect(session.url)

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



