from django.contrib import admin
from .models import SellerCertification

@admin.register(SellerCertification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ('seller', 'name', 'expiry_date', 'is_verified')
    list_filter = ('is_verified', 'name')
    search_fields = ('seller__user__username', 'authority_name')
    actions = ['verify_certificates']

    def verify_certificates(self, request, queryset):
        queryset.update(is_verified=True)
    verify_certificates.short_description = "Mark selected certificates as Verified"