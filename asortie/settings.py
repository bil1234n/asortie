import os
from pathlib import Path
import dj_database_url
from django.utils.translation import gettext_lazy as _
import django.conf.locale
from django.conf import global_settings
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY SETTINGS ---
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fallback-key')

# DEBUG is True locally, but False on Render
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# Allow Render and Localhost
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.onrender.com']
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# CSRF Trust for Render URLs
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']

# --- INSTALLED APPS ---
INSTALLED_APPS = [
    'daphne', # Must be at the top
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party
    'cloudinary',
    'cloudinary_storage',

    # Custom Apps
    'accounts',
    'market',
    'chat',
    'core',
    'ai',
    'AR_3D',
]

# --- MIDDLEWARE ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # For Static Files on Render
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # <--- CRITICAL: Add this right after SessionMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'asortie.urls'

# --- TEMPLATES ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.user_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'asortie.wsgi.application'
ASGI_APPLICATION = 'asortie.asgi.application'

# --- DATABASE ---
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'postgresql://postgres:Bilal1234@127.0.0.1:5432/asortie_db'),
        conn_max_age=600,
        ssl_require=True if os.environ.get('DATABASE_URL') else False
    )
}


# --- CHANNELS (REDIS for Chat) ---
if os.environ.get('REDIS_URL'):
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [os.environ.get('REDIS_URL')],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# --- AUTHENTICATION ---
AUTH_USER_MODEL = 'accounts.User'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'landing_page'
ADMIN_SIGNUP_PASSCODE = "COFFEE_MASTER_2025"

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- STATIC FILES ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [BASE_DIR / "static"]
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
# DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
# --- STORAGE ENGINES (Django 4.2+ & 5.0+ Standard) ---
STORAGES = {
    "default": {
        # Using RawMediaCloudinaryStorage is highly recommended for 3D Models (.glb, .usdz)
        # so Cloudinary doesn't accidentally try to process them as images and reject them.
        "BACKEND": "cloudinary_storage.storage.RawMediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# --- CLOUDINARY MEDIA STORAGE ---
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

# --- API KEYS ---
STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
CHAPA_SECRET_KEY = os.environ.get('CHAPA_SECRET_KEY')

GROQ_KEY_1 = os.environ.get('GROQ_KEY_1')
GROQ_KEY_2 = os.environ.get('GROQ_KEY_2')
GROQ_KEY_3 = os.environ.get('GROQ_KEY_3')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# Upload limits for 3D Models and Images
FILE_UPLOAD_TEMP_DIR = '/tmp'
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_MAX_MEMORY_SIZE = 2097152      # 2MB in bytes (Spool to disk if larger)
DATA_UPLOAD_MAX_MEMORY_SIZE = 150000000    # ~143MB (Allow large 3D model POST requests)

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
# This allows the Google popup to "talk" back to your website
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# Ensure your session cookies work with the popup redirect
SESSION_COOKIE_SAMESITE = 'Lax'

# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'en' # Changed from 'en-us' to 'en' for broader English matching
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# 3. Ensure your LANGUAGES tuple matches
LANGUAGES = [
    ('en', 'English'),
    ('am', 'Amharic'),
    ('tr', 'Turkish'),
    ('fr', 'French'),
    ('ar', 'Arabic'),
    ('ru', 'Russian'),
]

# 2. Tell Django where to look for translation files
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

EXTRA_LANG_INFO = {
    'am': {
        'bidi': False,
        'code': 'am',
        'name': 'Amharic',
        'name_local': 'አማርኛ', 
    },
}

LANG_INFO = dict(django.conf.locale.LANG_INFO, **EXTRA_LANG_INFO)
django.conf.locale.LANG_INFO = LANG_INFO

LOGIN_URL = '/login/'

GOOGLE_MAPS_API_KEY=os.getenv('GOOGLE_MAPS_API_KEY')
iyzico_api_key=os.getenv('iyzico_api_key')
iyzico_secret_key=os.getenv('iyzico_secret_key')
