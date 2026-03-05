from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
from django.db.models.signals import post_save
from django.dispatch import receiver

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('Green', 'Green Coffee Beans'),
        ('Roasted', 'Roasted Coffee'),
        ('Ground', 'Ground Coffee'),
        ('Equipment', 'Machinery'),
    ]

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Green')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField('image', folder='products', blank=True, null=True)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Declined', 'Declined'),
        ('Paid', 'Paid'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'), # Added Delivered for revenue logic
    ]

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    quantity = models.IntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.total_price = self.product.price * self.quantity
        super().save(*args, **kwargs)

class SellerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='seller_profile')
    is_farmer = models.BooleanField(default=False)
    is_roaster = models.BooleanField(default=False)
    is_exporter = models.BooleanField(default=False)
    is_supplier = models.BooleanField(default=False)
    
    company_name = models.CharField(max_length=100, blank=True)
    logo = CloudinaryField('image', folder='seller_logos', blank=True, null=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True, max_length=500)
    core_products = models.CharField(max_length=255, blank=True)
    certifications = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f"Profile: {self.user.username}"

class SellerCertification(models.Model):
    CERT_CHOICES = [
        ('Fair Trade', 'Fair Trade International'),
        ('USDA Organic', 'USDA Organic'),
        ('Rainforest', 'Rainforest Alliance'),
        ('UTZ', 'UTZ Certified'),
        ('Bird Friendly', 'Bird Friendly (Smithsonian)'),
        ('C.A.F.E.', 'C.A.F.E. Practices (Starbucks)'),
        ('Other', 'Other / Local Government'),
    ]

    seller = models.ForeignKey('SellerProfile', on_delete=models.CASCADE, related_name='certificates')
    name = models.CharField(max_length=50, choices=CERT_CHOICES)
    document_image = CloudinaryField('image', folder='seller_certs')
    authority_name = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.seller.user.username}"

# # Ensure profile is created automatically
# @receiver(post_save, sender=settings.AUTH_USER_MODEL)
# def create_seller_profile(sender, instance, created, **kwargs):
#     if created:
#         SellerProfile.objects.create(user=instance)
#     instance.seller_profile.save()
    