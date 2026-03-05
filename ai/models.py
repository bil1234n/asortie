from django.db import models
from django.conf import settings  
from pgvector.django import VectorField

class AsortieKnowledge(models.Model):
    content = models.TextField()
    # For text search
    embedding = VectorField(dimensions=384, null=True, blank=True)
    # For visual recognition
    image_embedding = VectorField(dimensions=512, null=True, blank=True)
    # NEW: To store the Cloudinary URL for the chat
    knowledge_image = models.URLField(max_length=500, null=True, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    
class ChatSession(models.Model):
    # Change 'User' to 'settings.AUTH_USER_MODEL'
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, default="New Luxury Inquiry")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10) 
    message = models.TextField()
    image = models.ImageField(upload_to='chat_images/', null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)