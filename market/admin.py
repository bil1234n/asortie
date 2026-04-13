from django.contrib import admin
from .models import Product, Order, BusinessProfile, BusinessCertification

# 1. Product & Order
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'category', 'price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'product', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'created_at')

# 2. Business Profile
@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'country', 'is_farmer', 'is_exporter')
    search_fields = ('company_name', 'user__username')

# 3. Certifications (Admin Verification)
@admin.register(BusinessCertification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'is_verified', 'expiry_date')
    list_filter = ('is_verified', 'name')
    actions = ['verify_documents']

    def verify_documents(self, request, queryset):
        queryset.update(is_verified=True)
    verify_documents.short_description = "Mark selected documents as Verified"
