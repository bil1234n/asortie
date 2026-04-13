from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from django.db.models.signals import post_save
from django.dispatch import receiver
from pgvector.django import VectorField 

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('Classic', 'Classic'),
        ('Modern', 'Modern'),
        ('Decoration', 'Decoration'),
        ('Office', 'Office'),
        ('Hotel', 'Hotel'),
    ]
    
    TRANSPORT_CHOICES = [
        ('Land', 'Land Transport'),
        ('Air', 'Air Freight'),
        ('Sea', 'Sea Freight'),
    ]

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Classic')
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField('image', folder='products', blank=True, null=True)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # --- New Delivery System Fields ---
    pickup_country = models.CharField(max_length=100, default="Ethiopia", help_text="Used to check if delivery is domestic or international")
    pickup_lat = models.FloatField(null=True, blank=True)
    pickup_lng = models.FloatField(null=True, blank=True)
    free_delivery_km = models.FloatField(default=0.0)
    price_per_country = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    price_per_0_1_km = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    maximum_delivery_km = models.FloatField(default=100.0)
    container_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    container_number = models.IntegerField(default=1)
    transport_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    transport_type = models.CharField(max_length=50, choices=TRANSPORT_CHOICES, default='Land')
    
    stock = models.IntegerField(default=1)
    address = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name

class ProductVariant(models.Model):
    """
    Imported from AR_3D System.
    Handles different 3D models (GLB/USDZ) or colors for a specific product.
    """
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    variant_name = models.CharField(max_length=200, help_text="e.g., Red sofa with green corner")
    
    model_3d = models.FileField(upload_to='products/models/variants/', blank=True, null=True)
    model_3d_link = models.URLField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.product.name} - {self.variant_name}"

    @property
    def get_model_url(self):
        """Returns the uploaded file URL or the external link"""
        if self.model_3d:
            return self.model_3d.url
        return self.model_3d_link


class ProductImage(models.Model):
    """
    Imported from AR_3D System.
    Handles the product gallery (multiple images).
    """
    product = models.ForeignKey(Product, related_name='gallery', on_delete=models.CASCADE)
    # Converted to CloudinaryField to match the main market system's storage logic
    image = CloudinaryField('image', folder='products/gallery')

    def __str__(self):
        return f"Gallery Image for {self.product.name}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Inquiry Received'),
        ('Quoted', 'Price Offered'),
        ('Accepted', 'Accepted by Buyer'),
        ('Declined', 'Declined'),
        ('Expired', 'Quote Expired'),
        ('Paid', 'Paid'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
    ]
    
    DELIVERY_CHOICES = [
        ('Pickup', 'Pickup in Store'),
        ('Delivery', 'Delivery'),
    ]

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    quantity = models.IntegerField(default=1)
    
    # Pricing
    product_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Delivery details
    delivery_option = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default='Pickup')
    delivery_lat = models.FloatField(null=True, blank=True)
    delivery_lng = models.FloatField(null=True, blank=True)
    buyer_country = models.CharField(max_length=100, blank=True, null=True)
    
    
    # ADD THIS NEW FIELD
    payment_gateway = models.CharField(max_length=50, blank=True, null=True, help_text="Stripe or Chapa")
    
    seller_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    quoted_at = models.DateTimeField(null=True, blank=True) 
    
class BusinessProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='business_profile')
    
    # Roles
    is_farmer = models.BooleanField(default=False)
    is_roaster = models.BooleanField(default=False)
    is_exporter = models.BooleanField(default=False)
    is_supplier = models.BooleanField(default=False)
    
    # Details
    company_name = models.CharField(max_length=100, blank=True)
    logo = CloudinaryField('image', folder='business_logos', blank=True, null=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True, max_length=500)
    core_products = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f"Profile: {self.user.username}"

class BusinessCertification(models.Model):
    CERT_CHOICES = [
        ('Fair Trade', 'Fair Trade International'),
        ('USDA Organic', 'USDA Organic'),
        ('Rainforest', 'Rainforest Alliance'),
        ('UTZ', 'UTZ Certified'),
        ('Bird Friendly', 'Bird Friendly (Smithsonian)'),
        ('Import License', 'Import License (Gov)'),
        ('Export License', 'Export License (Gov)'),
        ('C.A.F.E.', 'C.A.F.E. Practices (Starbucks)'),
        ('Other', 'Other'),
    ]

    profile = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='certificates')
    name = models.CharField(max_length=50, choices=CERT_CHOICES)
    document_image = CloudinaryField('image', folder='business_certs')
    authority_name = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.profile.user.username}"

class SellerPaymentConfig(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_config')
    
    # Gateway Accounts
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True, help_text="Starts with acct_")
    chapa_account_id = models.CharField(max_length=255, blank=True, null=True, help_text="Chapa Merchant / Bank ID")
    
    # --- NEW: Iyzico for Turkey ---
    iyzico_api_key = models.CharField(max_length=255, blank=True, null=True, help_text="Iyzico API Key")
    iyzico_secret_key = models.CharField(max_length=255, blank=True, null=True, help_text="Iyzico Secret Key")
    
    # Toggles
    is_cod_enabled = models.BooleanField(default=False, help_text="Allow Cash on Delivery")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Payment Config"
    
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_business_profile(sender, instance, created, **kwargs):
    if created:
        BusinessProfile.objects.create(user=instance)
  
