from django.db import models
from django.conf import settings

class ChatRoom(models.Model):
    participant_1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chats_1')
    participant_2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chats_2')
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True) # Allow blank for voice/file only messages
    is_read = models.BooleanField(default=False)
    
    is_edited = models.BooleanField(default=False)
    is_deleted_everyone = models.BooleanField(default=False)
    hidden_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='hidden_messages', blank=True)
    
    # NEW: Store reactions as a dictionary e.g., {"user_id": "👍"}
    reactions = models.JSONField(default=dict, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    
    file = models.FileField(upload_to='chat_media/', blank=True, null=True)
    message_type = models.CharField(
        max_length=10, 
        # NEW: Added 'audio'
        choices=[('text', 'Text'), ('image', 'Image'), ('video', 'Video'), ('file', 'File'), ('audio', 'Audio')],
        default='text'
    )

    class Meta:
        indexes = [
            models.Index(fields=['room', 'timestamp']),
        ]
    
    def __str__(self):
        return f"Message {self.id} from {self.sender}"
