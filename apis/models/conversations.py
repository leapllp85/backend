from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class Conversation(models.Model):
    """Model to store chat conversations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-updated_at']
        db_table = 'apis_conversation'
    
    def __str__(self):
        return f"Conversation {self.id} - {self.user.username}"
    
    @property
    def message_count(self):
        return self.messages.count()
    
    @property
    def last_message_at(self):
        last_message = self.messages.order_by('-created_at').first()
        return last_message.created_at if last_message else self.created_at


class ConversationMessage(models.Model):
    """Model to store individual messages in conversations"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    # For assistant messages, store structured response data
    analysis_data = models.JSONField(null=True, blank=True)
    queries_data = models.JSONField(null=True, blank=True)
    dataset = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['created_at']
        db_table = 'apis_conversationmessage'
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
    
    @property
    def is_user_message(self):
        return self.role == 'user'
    
    @property
    def is_assistant_message(self):
        return self.role == 'assistant'


class ConversationShare(models.Model):
    """Model to handle conversation sharing between users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='shares')
    shared_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_conversations')
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_conversations')
    permission_level = models.CharField(
        max_length=10, 
        choices=[('read', 'Read Only'), ('write', 'Read & Write')],
        default='read'
    )
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['conversation', 'shared_with']
        db_table = 'apis_conversationshare'
    
    def __str__(self):
        return f"{self.conversation.id} shared with {self.shared_with.username}"
