from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
import json
from .models import ChatSession, ChatMessage
from .ai_logic import AsortieBrain

@login_required(login_url='login')
def ai(request, session_id=None):
    # Because you use account.User, you can do this:
    is_pro = request.user.package_tier == 'professional'
    
    sessions = ChatSession.objects.filter(user=request.user).order_by('-created_at')
    
    if session_id:
        current_session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    else:
        current_session = sessions.first() or ChatSession.objects.create(user=request.user)
    
    chat_history = ChatMessage.objects.filter(session=current_session).order_by('timestamp')
    
    return render(request, 'ai/index.html', {
        'sessions': sessions, 
        'current_session': current_session, 
        'chat_history': chat_history,
        'is_pro': is_pro # Pass this to template to show "Pro" badges
    })

@csrf_exempt
@login_required
def ask_ai(request, session_id):
    if request.method == "POST":
        try:
            # FormData handles text in .POST and files in .FILES
            query = request.POST.get('text', '').strip()
            image_file = request.FILES.get('image') # The Furniture Image
            
            session = get_object_or_404(ChatSession, id=session_id, user=request.user)
            
            # Start the brain
            brain = AsortieBrain()
            result = brain.ask(query, session, image_file=image_file)
            
            return JsonResponse({
                'reply': result['answer'], 
                'user_msg_id': result['user_msg_id']
            })
            
        except Exception as e:
            return JsonResponse({'reply': f"Inquiry Error: {str(e)}"}, status=200)


@login_required
def start_new_ai_chat(request):
    new_session = ChatSession.objects.create(user=request.user)
    return redirect('ai_with_session', session_id=new_session.id)

@login_required
def delete_session(request, session_id):
    get_object_or_404(ChatSession, id=session_id, user=request.user).delete()
    return redirect('ai')

@csrf_exempt
@login_required
def delete_message(request, msg_id):
    with transaction.atomic():
        user_msg = get_object_or_404(ChatMessage, id=msg_id, session__user=request.user)
        ai_msg = ChatMessage.objects.filter(session=user_msg.session, role='assistant', timestamp__gt=user_msg.timestamp).order_by('timestamp').first()
        if ai_msg: ai_msg.delete()
        user_msg.delete()
    return JsonResponse({'status': 'ok'})


# train ai
from .models import AsortieKnowledge

@login_required
def trainer_page(request):
    # Only show the last 10 facts added
    recent_facts = AsortieKnowledge.objects.order_by('-id')[:10]
    return render(request, 'ai/trainer.html', {'recent_facts': recent_facts})

@csrf_exempt
@login_required
def train_ai_endpoint(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            text = data.get('text', '').strip()
            
            if text:
                # Import inside the function to avoid circular imports
                from .ai_logic import AsortieBrain
                brain = AsortieBrain()
                brain.teach(text) # Now this will work!
                return JsonResponse({'status': 'ok'})
            
            return JsonResponse({'status': 'error', 'message': 'Empty text'}, status=400)
        except Exception as e:
            print(f"CRITICAL TRAIN ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

brain = AsortieBrain()

@csrf_exempt
def train_visual_endpoint(request):
    if request.method == 'POST':
        label = request.POST.get('label')
        image_file = request.FILES.get('image')
        if label and image_file:
            success = brain.teach_visual_asset(image_file, label)
            return JsonResponse({'status': 'ok' if success else 'error'})
    return JsonResponse({'status': 'error'}, status=400)

@csrf_exempt
def edit_knowledge_endpoint(request, knowledge_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        new_text = data.get('text')
        if new_text:
            success = brain.edit_knowledge(knowledge_id, new_text)
            return JsonResponse({'status': 'ok' if success else 'error'})
    return JsonResponse({'status': 'error'}, status=400)

@csrf_exempt
def delete_knowledge_endpoint(request, knowledge_id):
    if request.method == 'POST':
        success = brain.delete_knowledge(knowledge_id)
        return JsonResponse({'status': 'ok' if success else 'error'})
    return JsonResponse({'status': 'error'}, status=400)
