from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from apis.models import Conversation, ConversationMessage, ConversationShare
from apis.serializers.conversations import (
    ConversationListSerializer, ConversationDetailSerializer,
    ConversationCreateSerializer, ConversationUpdateSerializer,
    ConversationMessageSerializer, ConversationShareSerializer
)
from apis.permissions import IsManager
import logging

logger = logging.getLogger(__name__)


class ConversationListCreateView(generics.ListCreateAPIView):
    """List user's conversations or create a new conversation"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ConversationCreateSerializer
        return ConversationListSerializer
    
    def get_queryset(self):
        user = self.request.user
        # Get user's own conversations and shared conversations
        return Conversation.objects.filter(
            Q(user=user) | Q(shares__shared_with=user, shares__is_active=True)
        ).distinct()


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a specific conversation"""
    permission_classes = [IsAuthenticated, IsManager]
    lookup_field = 'id'
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ConversationUpdateSerializer
        return ConversationDetailSerializer
    
    def get_queryset(self):
        user = self.request.user
        return Conversation.objects.filter(
            Q(user=user) | Q(shares__shared_with=user, shares__is_active=True)
        ).distinct()


class ConversationMessageListView(generics.ListAPIView):
    """List messages for a specific conversation"""
    serializer_class = ConversationMessageSerializer
    permission_classes = [IsAuthenticated, IsManager]
    
    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        user = self.request.user
        
        # Verify user has access to this conversation
        conversation = get_object_or_404(
            Conversation.objects.filter(
                Q(user=user) | Q(shares__shared_with=user, shares__is_active=True)
            ).distinct(),
            id=conversation_id
        )
        
        return ConversationMessage.objects.filter(conversation=conversation)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsManager])
def add_message_to_conversation(request, conversation_id):
    """Add a message to an existing conversation"""
    try:
        user = request.user
        
        # Verify user has access to this conversation
        conversation = get_object_or_404(
            Conversation.objects.filter(
                Q(user=user) | Q(shares__shared_with=user, shares__is_active=True)
            ).distinct(),
            id=conversation_id
        )
        
        # Check if user has write permission (owner or shared with write access)
        has_write_permission = (
            conversation.user == user or 
            conversation.shares.filter(
                shared_with=user, 
                permission_level='write', 
                is_active=True
            ).exists()
        )
        
        if not has_write_permission:
            return Response(
                {"error": "You don't have permission to add messages to this conversation"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create the message
        message_data = {
            'conversation': conversation.id,
            'role': request.data.get('role', 'user'),
            'content': request.data.get('content', ''),
            'metadata': request.data.get('metadata', {}),
            'analysis_data': request.data.get('analysis_data'),
            'queries_data': request.data.get('queries_data'),
            'dataset': request.data.get('dataset')
        }
        
        serializer = ConversationMessageSerializer(data=message_data)
        if serializer.is_valid():
            serializer.save()
            
            # Update conversation's updated_at timestamp
            conversation.save()
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error adding message to conversation: {e}")
        return Response(
            {"error": "Failed to add message to conversation"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class ConversationShareListCreateView(generics.ListCreateAPIView):
    """List conversation shares or create a new share"""
    serializer_class = ConversationShareSerializer
    permission_classes = [IsAuthenticated, IsManager]
    
    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        user = self.request.user
        
        # Verify user owns this conversation
        conversation = get_object_or_404(Conversation, id=conversation_id, user=user)
        
        return ConversationShare.objects.filter(conversation=conversation)
    
    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        conversation = get_object_or_404(Conversation, id=conversation_id, user=self.request.user)
        serializer.save(conversation=conversation)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsManager])
def remove_conversation_share(request, conversation_id, share_id):
    """Remove a conversation share"""
    try:
        user = request.user
        
        # Verify user owns the conversation
        conversation = get_object_or_404(Conversation, id=conversation_id, user=user)
        
        # Get and delete the share
        share = get_object_or_404(ConversationShare, id=share_id, conversation=conversation)
        share.delete()
        
        return Response({"message": "Share removed successfully"}, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error removing conversation share: {e}")
        return Response(
            {"error": "Failed to remove conversation share"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManager])
def get_shared_conversations(request):
    """Get conversations shared with the current user"""
    try:
        user = request.user
        
        shared_conversations = Conversation.objects.filter(
            shares__shared_with=user,
            shares__is_active=True
        ).distinct()
        
        serializer = ConversationListSerializer(shared_conversations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting shared conversations: {e}")
        return Response(
            {"error": "Failed to get shared conversations"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
