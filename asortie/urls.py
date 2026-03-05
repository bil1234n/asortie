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
from core.views import mark_notification_read, all_notifications, coming_soon_2
from chat import views as chat_views 
from accounts.views import ChangePasswordView 
from market import views

from ai import views as ai_views
from AR_3D import views as ar_3d_views 


urlpatterns = [
    # --- MARKETING SITE ---
    # Access this at http://127.0.0.1:8000/welcome_home/
    path('', core_views.marketing_home, name='landing_page'), 
    # path('welcome_home/', core_views.marketing_home, name='landing_page'), 
    path('about/', core_views.marketing_about, name='about'),
    path('producers/', core_views.marketing_producers, name='producers'),
    path('roasters/', core_views.marketing_roasters, name='roasters'),
    path('shop-info/', core_views.marketing_shop, name='marketing_shop'),
    path('contact/', core_views.marketing_contact, name='contact'),
    
    # --- AUTHENTICATION ---
    path('admin-site/', admin.site.urls), # Renamed to avoid confusion
    path('logout/', django_auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    
    # Unified Buyer & Seller Auth
    path('login/', auth_views.unified_login_view, name='login'),
    path('register/', auth_views.unified_register_view, name='register'),
    
    
    path('auth/admin/login/', auth_views.admin_login, name='admin_login'),
    path('auth/admin/register/', auth_views.admin_register, name='admin_register'),

    # --- CORE PAGES ---
    path('home/', core_views.home, name='home'),
    path('features/future/', core_views.coming_soon, name='coming_soon'),
    path('features/future_2/', core_views.coming_soon_2, name='coming_soon_2'),
    path('login-redirect/', core_views.login_redirect_view, name='login_redirect'),

    # --- ADMIN PANEL (Updated to use Analytics views) ---
    path('manager/dashboard/', core_views.admin_dashboard, name='admin_dashboard'),
    path('manager/users/', core_views.admin_users, name='admin_users'),
    path('manager/products/', core_views.admin_product_analytics, name='admin_product_analytics'),
    path('manager/orders/', core_views.admin_order_analytics, name='admin_order_analytics'),

    # --- SELLER PANEL ---
    path('seller/dashboard/', market_views.seller_dashboard, name='seller_dashboard'),
    path('seller/orders/', market_views.seller_orders, name='seller_orders'),

    path('seller/products/', market_views.seller_products, name='seller_products'),
    path('seller/products/add/', market_views.seller_product_add, name='seller_product_add'),
    path('seller/products/edit/<int:pk>/', market_views.seller_product_edit, name='seller_product_edit'),
    path('seller/products/delete/<int:pk>/', market_views.seller_product_delete, name='seller_product_delete'),
    
    # --- MARKETPLACE (PUBLIC) ---
    path('market/', market_views.product_list, name='product_list'),
    path('market/product/<int:product_id>/', market_views.product_detail, name='product_detail'),
    path('market/order/<int:product_id>/', market_views.create_order, name='create_order'),
    path('market/my-orders/', market_views.buyer_orders, name='buyer_orders'),
    # path('market/pay/<int:order_id>/', market_views.payment_page, name='payment_page'),

    # --- PAYMENT ---
    path('payment/<int:order_id>/', market_views.payment, name='payment'),
    path('stripe/<int:order_id>/', market_views.stripe_checkout, name='stripe_checkout'),
    path('chapa/<int:order_id>/', market_views.chapa_checkout, name='chapa_checkout'),
    # path('payment-success/', market_views.payment_success, name='payment_success'),
    
    path('payment-success/<int:order_id>/', views.payment_success, name='payment_success'),
    path('order/cancel/<int:order_id>/', views.cancel_order, name='cancel_order'),


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
    path('market/seller/<int:seller_id>/', views.public_business_profile, name='public_business_profile'),
    path('business-profile/<int:user_id>/', views.view_business_profile, name='view_business_profile'),

    path('directory/', views.business_directory, name='business_directory'),
    
    
    # Ai Dashboard & Session Management
    path('ai/', ai_views.ai, name='ai'),
    path('ai_chat/<int:session_id>/', ai_views.ai, name='ai_with_session'),
    path('new-ai_chat/', ai_views.start_new_ai_chat, name='new_ai_chat'),
    path('delete-session/<int:session_id>/', ai_views.delete_session, name='delete_session'),
    path('ask/<int:session_id>/', ai_views.ask_ai, name='ask_ai'),
    path('delete-msg/<int:msg_id>/', ai_views.delete_message, name='delete_message'),
    
    # train ai
    path('trainer/', ai_views.trainer_page, name='trainer'),
    path('train-ai/', ai_views.train_ai_endpoint, name='train_ai_endpoint'),
    
        # --- ADD THESE THREE LINES ---
    path('train-visual/', ai_views.train_visual_endpoint, name='train_visual_endpoint'),
    path('edit-knowledge/<int:knowledge_id>/', ai_views.edit_knowledge_endpoint, name='edit_knowledge_endpoint'),
    path('delete-knowledge/<int:knowledge_id>/', ai_views.delete_knowledge_endpoint, name='delete_knowledge_endpoint'),

    # AR & 3D Model
    path('ar_3d/', ar_3d_views.index, name='ar_showroom'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)