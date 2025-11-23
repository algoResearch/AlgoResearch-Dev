# dashboard/management/commands/send_test_notifications.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

User = get_user_model()

class Command(BaseCommand):
    help = "Send test notifications to lt_user_* groups for load testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=5,
            help="How many notifications to send per user",
        )

    def handle(self, *args, **options):
        count = options["count"]
        channel_layer = get_channel_layer()

        qs = User.objects.filter(username__startswith="lt_user_").order_by("id")
        users = list(qs)
        self.stdout.write(f"Sending {count} notifications to {len(users)} lt_user_* accounts")

        for n in range(count):
            for user in users:
                group_name = f"user_{user.id}"
                payload = {
                    "type": "notification_message",
                    "message": f"Test notification {n+1} for {user.username}",
                    "org_id": None,
                    "conversation_id": None,
                    "sender": "System",
                    "sender_profile_picture": "/static/img/default-profile.jpg",
                    "conversation_url": "#",
                }
                async_to_sync(channel_layer.group_send)(group_name, payload)

        self.stdout.write(self.style.SUCCESS("Done sending test notifications."))
