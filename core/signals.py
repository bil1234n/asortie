from django.db.models.signals import post_save
from django.dispatch import receiver
from market.models import Order
from chat.models import Message
from .models import Notification
from django.urls import reverse

@receiver(post_save, sender=Order)
def order_notification(sender, instance, created, **kwargs):
    print(f"--- SIGNAL FIRED: Order #{instance.id} ---") # Debug Line 1
    
    if created:
        print("--- NEW ORDER DETECTED ---") # Debug Line 2
        # 1. NEW ORDER -> Notify Seller
        Notification.objects.create(
            recipient=instance.product.seller,
            sender=instance.buyer,
            notification_type='order',
            message=f"New Order: {instance.quantity}set of {instance.product.name}",
            link=reverse('seller_orders')
        )
        print(f"--- NOTIFICATION CREATED FOR SELLER: {instance.product.seller.username} ---") # Debug Line 3
        
    else:
        # 2. STATUS CHANGE -> Notify Buyer
        msg = None
        if instance.status == 'Accepted':
            msg = f"Order Accepted! The seller is preparing {instance.product.name}."
        elif instance.status == 'Shipped':
            msg = f"On the way! Your order for {instance.product.name} has been Shipped."
        elif instance.status == 'Delivered':
            msg = f"Delivered! Your coffee {instance.product.name} has arrived."
        elif instance.status == 'Declined':
            msg = f"Order Declined. Please check your order for {instance.product.name}."
            
        if msg:
            Notification.objects.create(
                recipient=instance.buyer,
                sender=instance.product.seller,
                notification_type='order',
                message=msg,
                link=reverse('buyer_orders')
            )
            print(f"--- NOTIFICATION CREATED FOR BUYER: {instance.buyer.username} ---") 
            
@receiver(post_save, sender=Message)
def message_notification(sender, instance, created, **kwargs):
    if created:
        room = instance.room
        recipient = room.participant_2 if instance.sender == room.participant_1 else room.participant_1
        
        Notification.objects.create(
            recipient=recipient,
            sender=instance.sender,
            notification_type='message',
            message=f"New message from {instance.sender.username}",
            link=reverse('chat_room', args=[instance.sender.id])
        )
