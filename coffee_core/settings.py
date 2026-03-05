import os
from pathlib import Path
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY SETTINGS ---
# Get SECRET_KEY from Environment or use fallback for local dev
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fallback-key-change-this')

# DEBUG is True locally, but False on Render
DEBUG = 'RENDER' not in os.environ

# Allow Render to host the site
ALLOWED_HOSTS = ['*']

# CSRF Trust for Render URLs
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

# --- INSTALLED APPS (Order is Critical) ---
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Add Cloudinary
    'cloudinary',
    'cloudinary_storage',

    # Custom Apps
    'accounts',
    'market',
    'chat',
    'core',
]

# --- MIDDLEWARE ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # <--- Critical for CSS
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'coffee_core.urls'

# --- TEMPLATES ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Looks for HTML in 'coffee_project/templates'
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.user_notifications', # Custom Notifications
            ],
        },
    },
]

# --- WSGI / ASGI ---
WSGI_APPLICATION = 'coffee_core.wsgi.application'
ASGI_APPLICATION = 'coffee_core.asgi.application'

# --- DATABASE (Auto-Switching) ---
# If on Render (DATABASE_URL exists), use Neon.
# If Local, use Local Postgres.
# DATABASES = {
#     'default': dj_database_url.config(
#         default='postgresql://postgres:yourlocalpassword@localhost:5432/coffee_db',
#         conn_max_age=600,
#         ssl_require='RENDER' in os.environ # Only require SSL on Render
#     )
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'coffee_db',
        'USER': 'postgres',        # Default user
        'PASSWORD': 'Bilal1234', # <--- PUT YOUR POSTGRES PASSWORD HERE
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# --- CHANNELS (REDIS for Chat) ---
if 'REDIS_URL' in os.environ:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [os.environ.get('REDIS_URL')],
            },
        },
    }
else:
    # Local Development Fallback (In-Memory)
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

# --- AUTHENTICATION ---
AUTH_USER_MODEL = 'accounts.User'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'landing_page'

# Custom Settings
ADMIN_SIGNUP_PASSCODE = "COFFEE_MASTER_2025"

# --- PASSWORDS ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =========================================================
# 1. STATIC FILES (CSS/JS) - Served by WhiteNoise
# =========================================================

# --- STATIC FILES (CSS/JS) ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# CHANGE THIS LINE: Use the "Safe" storage (removes 'Manifest')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Look for static files in 'coffee_project/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# ============================
# CLOUDINARY MEDIA STORAGE
# ============================
CLOUDINARY = {
    'cloud_name': 'dhfyolanv',
    'api_key': '399471574245624',
    'api_secret': 'kFY9tTVdDfUTLT9-oux8SMFuNGQ',
}

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': 'dhfyolanv',
    'API_KEY': '399471574245624',
    'API_SECRET': 'kFY9tTVdDfUTLT9-oux8SMFuNGQ',
}
# CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
# CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
# CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

MEDIA_URL = '/media/'   # Not used on render but safe

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'