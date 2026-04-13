import json
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator

from .models import ChatRoom, Message
from django.db.models import Q, Count

User = get_user_model()


@login_required
def chat_inbox(request):
    # We annotate the room with the count of messages NOT hidden by the user.
    # Then we filter out any rooms where that count is 0.
    rooms = ChatRoom.objects.filter(
        Q(participant_1=request.user) | Q(participant_2=request.user)
    ).annotate(
        visible_msg_count=Count('messages', filter=~Q(messages__hidden_by=request.user))
    ).filter(
        visible_msg_count__gt=0
    ).order_by('-updated_at')
    
    return render(request, 'chat/inbox.html', {'rooms': rooms})

@login_required
def chat_room(request, user_id):
    other_user = get_object_or_404(User, id=user_id)
    
    room = ChatRoom.objects.filter(
        (Q(participant_1=request.user) & Q(participant_2=other_user)) |
        (Q(participant_1=other_user) & Q(participant_2=request.user))
    ).first()

    if not room:
        room = ChatRoom.objects.create(participant_1=request.user, participant_2=other_user)

    all_messages = room.messages.exclude(hidden_by=request.user).order_by('-timestamp')
    
    paginator = Paginator(all_messages, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    chat_messages = list(page_obj)[::-1]
    
    room.messages.filter(sender=other_user, is_read=False).update(is_read=True)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        messages_data = [{
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender.id,
            'timestamp': msg.timestamp.strftime("%H:%M"),
            'is_read': msg.is_read,
            'is_edited': msg.is_edited,               
            'is_deleted': msg.is_deleted_everyone,    
            'msg_type': msg.message_type,             
            'file_url': msg.file.url if msg.file else None,
            # NEW: Add reply_to data for infinite scroll/pagination
            'reply_to': {
                'id': msg.reply_to.id,
                'sender': "You" if msg.reply_to.sender == request.user else msg.reply_to.sender.username,
                'content': msg.reply_to.content,
                'msg_type': msg.reply_to.message_type
            } if msg.reply_to else None
        } for msg in chat_messages]
        return JsonResponse({'messages': messages_data, 'has_next': page_obj.has_next()})

    return render(request, 'chat/room.html', {
        'room': room, 
        'chat_messages': chat_messages, 
        'other_user': other_user,
        'has_older_messages': page_obj.has_next()
    })

def contact_admin(request):
    # ... (No changes needed here)
    if request.user.is_authenticated:
        admins = User.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True)
        
        if admins.exists():
            selected_admin = random.choice(list(admins))
            return redirect('chat_room', user_id=selected_admin.id)
        else:
            messages.error(request, "No support agents are currently available.")
            return redirect('chat_inbox')

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        body = request.POST.get('message')

        admins = list(User.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True))
        
        if not admins:
            messages.error(request, "System Error: No support agents available right now.")
            return redirect('contact_admin')

        target_admin = random.choice(admins)

        guest_user, created = User.objects.get_or_create(username="Website_Guest")
        if created:
            guest_user.email = "guest@system.local"
            guest_user.set_unusable_password()
            guest_user.save()

        room, created = ChatRoom.objects.get_or_create(
            participant_1=guest_user, 
            participant_2=target_admin
        )

        full_message = (
            f"📢 **GUEST INQUIRY**\n"
            f"👤 Name: {name}\n"
            f"📧 Email: {email}\n"
            f"📞 Phone: {phone}\n"
            f"----------------------\n"
            f"{body}"
        )

        Message.objects.create(room=room, sender=guest_user, content=full_message)
        room.save() 

        messages.success(request, f"Thank you, {name}! Your message has been sent.")
        return redirect('contact_admin')

    return render(request, 'chat/guest_contact.html')

@login_required
def clear_chat_history(request, room_id):
    if request.method == 'POST':
        room = get_object_or_404(ChatRoom, id=room_id)
        
        if request.user.id not in [room.participant_1.id, room.participant_2.id]:
            return JsonResponse({'status': 'denied'}, status=403)
            
        messages_to_hide = room.messages.exclude(hidden_by=request.user)
        for msg in messages_to_hide:
            msg.hidden_by.add(request.user)
            
        return JsonResponse({'status': 'cleared'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def manage_message(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        action = data.get('action')
        msg = get_object_or_404(Message, id=data.get('message_id'))
        
        if action == 'delete_me':
            msg.hidden_by.add(request.user)
            return JsonResponse({'status': 'hidden'})
            
        if action == 'react':
            emoji = data.get('emoji')
            user_id_str = str(request.user.id)
            
            if not isinstance(msg.reactions, dict):
                msg.reactions = {}

            if msg.reactions.get(user_id_str) == emoji:
                del msg.reactions[user_id_str]
            else:
                msg.reactions[user_id_str] = emoji
                
            msg.save()
            return JsonResponse({'status': 'reacted', 'reactions': msg.reactions})

        if msg.sender != request.user:
            return JsonResponse({'status': 'denied'}, status=403)

        if action == 'delete_everyone':
            msg.is_deleted_everyone = True
            msg.content = "🚫 This message was deleted."
            msg.updated_at = timezone.now()
            msg.save() 
            return JsonResponse({'status': 'deleted', 'new_content': msg.content})
            
        elif action == 'edit':
            new_content = data.get('new_content')
            if new_content:
                msg.content = new_content
                msg.is_edited = True
                msg.updated_at = timezone.now()
                msg.save()
                return JsonResponse({'status': 'edited', 'new_content': new_content})

    return JsonResponse({'status': 'error'}, status=400)

@login_required
def send_message_api(request, room_id):
    if request.method == 'POST':
        room = get_object_or_404(ChatRoom, id=room_id)
        
        content = request.POST.get('content', '')
        reply_to_id = request.POST.get('reply_to') # NEW: Catch reply ID
        file = request.FILES.get('file')
        msg_type = 'text'

        if file:
            mime = file.content_type
            if mime.startswith('image/'): msg_type = 'image'
            elif mime.startswith('video/'): msg_type = 'video'
            elif mime.startswith('audio/'): msg_type = 'audio' 
            else: msg_type = 'file'

        # NEW: Find the original message being replied to
        reply_message = None
        if reply_to_id:
            try:
                reply_message = Message.objects.get(id=reply_to_id, room=room)
            except Message.DoesNotExist:
                pass

        msg = Message.objects.create(
            room=room, 
            sender=request.user, 
            content=content, 
            file=file, 
            message_type=msg_type,
            reply_to=reply_message  # NEW: Save to DB
        )
        room.save()

        # NEW: Prepare reply data for immediate frontend rendering
        reply_data = None
        if reply_message:
            reply_data = {
                'id': reply_message.id,
                'sender': "You" if reply_message.sender == request.user else reply_message.sender.username,
                'content': reply_message.content,
                'msg_type': reply_message.message_type
            }

        return JsonResponse({
            'status': 'success',
            'message_id': msg.id,
            'content': msg.content,
            'file_url': msg.file.url if msg.file else None,
            'msg_type': msg_type,
            'time': msg.timestamp.strftime("%H:%M"),
            'reply_to': reply_data # NEW
        })

@login_required
def get_updates(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    last_check_str = request.GET.get('last_check', 0)
    
    try:
        last_check_ts = float(last_check_str)
        last_check_dt = timezone.datetime.fromtimestamp(last_check_ts, tz=timezone.utc)
    except:
        last_check_dt = timezone.now() - timezone.timedelta(seconds=10)

    new_msgs_qs = room.messages.filter(timestamp__gt=last_check_dt).exclude(hidden_by=request.user).order_by('timestamp')
    updated_msgs_qs = room.messages.filter(updated_at__gt=last_check_dt, timestamp__lte=last_check_dt).exclude(hidden_by=request.user)

    new_data = []
    for msg in new_msgs_qs:
        # NEW: Attach reply info to incoming messages
        reply_data = None
        if msg.reply_to:
            reply_data = {
                'id': msg.reply_to.id,
                'sender': "You" if msg.reply_to.sender == request.user else msg.reply_to.sender.username,
                'content': msg.reply_to.content,
                'msg_type': msg.reply_to.message_type
            }

        new_data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'content': msg.content,
            'time': msg.timestamp.strftime("%H:%M"),
            'is_me': msg.sender == request.user,
            'is_deleted': msg.is_deleted_everyone,
            'msg_type': msg.message_type,
            'file_url': msg.file.url if msg.file else None,
            'reactions': msg.reactions,
            'reply_to': reply_data # NEW
        })
        if msg.sender != request.user:
            msg.is_read = True
            msg.save()

    updated_data = []
    for msg in updated_msgs_qs:
        updated_data.append({
            'id': msg.id,
            'content': msg.content,
            'is_deleted': msg.is_deleted_everyone,
            'is_edited': msg.is_edited,
            'reactions': msg.reactions
        })

    return JsonResponse({
        'new_messages': new_data,
        'updated_messages': updated_data,
        'server_time': timezone.now().timestamp()
    })
