from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as django_auth_views
from django.conf import settings
from django.conf.urls.static import static

# Import Views from the apps
from core import views as core_views
from market import views as market_views
from accounts import views as auth_views
from chat import views as chat_views
from core.views import mark_notification_read, all_notifications
from chat import views as chat_views 
from accounts.views import ChangePasswordView 
from market import views

urlpatterns = [
    # --- MARKETING SITE ---
    # Access this at http://127.0.0.1:8000/welcome_home/
    path('welcome_home/', core_views.marketing_home, name='landing_page'), 
    path('about/', core_views.marketing_about, name='about'),
    path('shop-info/', core_views.marketing_shop, name='marketing_shop'),
    path('contact/', core_views.marketing_contact, name='contact'),
    
    # --- AUTHENTICATION ---
    path('admin-site/', admin.site.urls), # Renamed to avoid confusion
    path('logout/', django_auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    
    # Generic Login (Default)
    path('login/', auth_views.buyer_login, name='login'), 
    path('register/', auth_views.buyer_register, name='register'),
    
    # Specific Role Auth Paths
    path('auth/admin/login/', auth_views.admin_login, name='admin_login'),
    path('auth/admin/register/', auth_views.admin_register, name='admin_register'),
    path('auth/seller/login/', auth_views.seller_login, name='seller_login'),
    path('auth/seller/register/', auth_views.seller_register, name='seller_register'),
    path('auth/buyer/login/', auth_views.buyer_login, name='buyer_login'),
    path('auth/buyer/register/', auth_views.buyer_register, name='buyer_register'),

    # --- CORE PAGES ---
    path('', core_views.home, name='home'),
    path('features/future/', core_views.coming_soon, name='coming_soon'),
    path('login-redirect/', core_views.login_redirect_view, name='login_redirect'),

    # --- ADMIN PANEL (Updated to use Analytics views) ---
    path('manager/dashboard/', core_views.admin_dashboard, name='admin_dashboard'),
    path('manager/users/', core_views.admin_users, name='admin_users'),
    path('manager/products/', core_views.admin_product_analytics, name='admin_product_analytics'),
    path('manager/orders/', core_views.admin_order_analytics, name='admin_order_analytics'),

    # --- SELLER PANEL ---
    path('seller/dashboard/', market_views.seller_dashboard, name='seller_dashboard'),
    path('seller/products/', market_views.seller_products, name='seller_products'),
    path('seller/orders/', market_views.seller_orders, name='seller_orders'),

    # --- MARKETPLACE (PUBLIC) ---
    path('market/', market_views.product_list, name='product_list'),
    path('market/product/<int:product_id>/', market_views.product_detail, name='product_detail'),
    path('market/order/<int:product_id>/', market_views.create_order, name='create_order'),
    path('market/pay/<int:order_id>/', market_views.payment_page, name='payment_page'),
    path('market/my-orders/', market_views.buyer_orders, name='buyer_orders'),

    # --- CHAT ---
    path('messages/', chat_views.chat_inbox, name='chat_inbox'),
    path('messages/<int:user_id>/', chat_views.chat_room, name='chat_room'),
    path('messages/support/', chat_views.contact_admin, name='contact_admin'), 
    # API Routes
    path('api/chat/send/<int:room_id>/', chat_views.send_message_api, name='api_send_message'),
    path('api/chat/manage/', chat_views.manage_message, name='api_manage_message'),
    path('api/chat/get/<int:room_id>/', chat_views.get_updates, name='api_get_updates'),
    path('api/chat/clear/<int:room_id>/', chat_views.clear_chat_history, name='api_clear_chat'),
    
    # --- notifications ---
    path('notifications/read/<int:notif_id>/', mark_notification_read, name='mark_read'),
    path('notifications/all/', all_notifications, name='all_notifications'),
    path('notifications/read-all/', core_views.mark_all_read, name='mark_all_read'),
    path('notifications/delete-all/', core_views.delete_all_notifications, name='delete_all_notifications'),
    
    # --- Profile ---
    path('profile/', auth_views.profile_view, name='profile'),
    path('profile/change-password/', ChangePasswordView.as_view(), name='change_password'),

    # ... business paths ...
    path('seller/business-profile/', views.business_profile, name='business_profile'),
    path('seller/cert/delete/<int:cert_id>/', views.delete_certificate, name='delete_certificate'),
    path('market/seller/<int:seller_id>/', views.public_seller_profile, name='public_seller_profile'),
    
    path('directory/', views.business_directory, name='business_directory'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)