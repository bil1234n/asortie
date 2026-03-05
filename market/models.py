from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from django.db.models.signals import post_save
from django.dispatch import receiver
from pgvector.django import VectorField 

# NOTE: User model is imported from settings.AUTH_USER_MODEL via ForeignKey

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('Classic', 'Classic'),
        ('Modern', 'Modern'),
        ('Decoration', 'Decoration'),
        ('Office', 'Office'),
        ('Hotel', 'Hotel'),
    ]

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Green')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField('image', folder='products', blank=True, null=True)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # AI Vector Field: CLIP-ViT-B/32 uses 512 dimensions
    image_embedding = VectorField(dimensions=512, null=True, blank=True)
    
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
        ('Quoted', 'Price Offered'), # Seller has set the price
        ('Accepted', 'Accepted by Buyer'),
        ('Declined', 'Declined'),
        ('Paid', 'Paid'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
    ]

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    quantity = models.IntegerField(default=1)
    
    # This will be edited by the seller later
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    seller_note = models.TextField(blank=True, null=True) # For custom specs/negotiations
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # We REMOVE the automatic total_price = product.price logic 
        # so the seller can manually set it.
        super().save(*args, **kwargs)

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

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_business_profile(sender, instance, created, **kwargs):
    if created:
        BusinessProfile.objects.create(user=instance)
  