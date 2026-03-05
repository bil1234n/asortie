from django.contrib.auth.models import AbstractUser
from django.db import models
from cloudinary.models import CloudinaryField

class User(AbstractUser):
    # Roles
    BUYER = 'buyer'
    SELLER = 'seller'
    ADMIN = 'admin'
    
    ROLE_CHOICES = [
        (BUYER, 'Buyer'),
        (SELLER, 'Seller'),
        (ADMIN, 'Admin'),
    ]

    # Packages
    BASIC = 'basic'
    PREMIUM = 'premium'
    PROFESSIONAL = 'professional'

    PACKAGE_CHOICES = [
        (BASIC, 'Basic'),
        (PREMIUM, 'Premium'),
        (PROFESSIONAL, 'Professional'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=BUYER)
    package_tier = models.CharField(max_length=15, choices=PACKAGE_CHOICES, default=BASIC) # <--- Added
    is_verified = models.BooleanField(default=False)

    def is_seller(self):
        return self.role == self.SELLER

class VerificationDoc(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification_doc')
    
    # Use CloudinaryField with resource_type='auto' to allow PDFs and Images
    business_license = CloudinaryField(
        'business_license', 
        resource_type='auto', 
        folder='legal_docs/licenses'
    )
    
    id_card = CloudinaryField(
        'id_card', 
        resource_type='auto', 
        folder='legal_docs/ids'
    )
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Docs for {self.user.username}"