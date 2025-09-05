from rest_framework import serializers
from apis.models import Conversation, ConversationMessage, ConversationShare
from django.contrib.auth.models import User


class ConversationMessageSerializer(serializers.ModelSerializer):
    """Serializer for conversation messages"""
    
    class Meta:
        model = ConversationMessage
        fields = [
            'id', 'role', 'content', 'metadata', 'created_at',
            'analysis_data', 'queries_data', 'dataset'
        ]
        read_only_fields = ['id', 'created_at']


class ConversationListSerializer(serializers.ModelSerializer):
    """Serializer for conversation list view"""
    message_count = serializers.ReadOnlyField()
    last_message_at = serializers.ReadOnlyField()
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'created_at', 'updated_at', 'is_active',
            'message_count', 'last_message_at', 'last_message'
        ]
    
    def get_last_message(self, obj):
        last_message = obj.messages.order_by('-created_at').first()
        if last_message:
            return {
                'role': last_message.role,
                'content': last_message.content[:100] + '...' if len(last_message.content) > 100 else last_message.content,
                'created_at': last_message.created_at
            }
        return None


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Serializer for conversation detail view with messages"""
    messages = ConversationMessageSerializer(many=True, read_only=True)
    message_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'created_at', 'updated_at', 'is_active',
            'message_count', 'messages'
        ]


class ConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating conversations"""
    
    class Meta:
        model = Conversation
        fields = ['title']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ConversationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating conversations"""
    
    class Meta:
        model = Conversation
        fields = ['title', 'is_active']


class ConversationShareSerializer(serializers.ModelSerializer):
    """Serializer for conversation sharing"""
    shared_with_username = serializers.CharField(write_only=True)
    shared_with = serializers.StringRelatedField(read_only=True)
    shared_by = serializers.StringRelatedField(read_only=True)
    conversation_title = serializers.CharField(source='conversation.title', read_only=True)
    
    class Meta:
        model = ConversationShare
        fields = [
            'id', 'conversation', 'shared_with_username', 'shared_with', 'shared_by',
            'conversation_title', 'permission_level', 'created_at', 'is_active'
        ]
        read_only_fields = ['id', 'shared_by', 'created_at']
    
    def validate_shared_with_username(self, value):
        try:
            user = User.objects.get(username=value)
            return user
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this username does not exist.")
    
    def create(self, validated_data):
        shared_with_user = validated_data.pop('shared_with_username')
        validated_data['shared_with'] = shared_with_user
        validated_data['shared_by'] = self.context['request'].user
        return super().create(validated_data)
