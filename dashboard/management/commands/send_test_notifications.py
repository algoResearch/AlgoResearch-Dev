import time
import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

User = get_user_model()


class Command(BaseCommand):
    help = "Send test notifications to notification WS groups (loadtest + real users)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=5,
            help="How many notifications to send per user",
        )
        parser.add_argument(
            "--only-lt",
            action="store_true",
            help="Send only to users whose usernames start with lt_user_",
        )
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Send only to a specific username",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit how many users to target (useful for ramp tests)",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.0,
            help="Sleep seconds between sends (burst control)",
        )
        parser.add_argument(
            "--group-prefix",
            type=str,
            default="user_",
            help="Group name prefix (default user_). Consumer uses user_{id}.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        only_lt = options["only_lt"]
        target_username = options["user"]
        limit = options["limit"]
        sleep_s = options["sleep"]
        group_prefix = options["group_prefix"]

        channel_layer = get_channel_layer()
        if channel_layer is None:
            self.stderr.write(self.style.ERROR("No channel layer configured!"))
            return

        qs = User.objects.all().order_by("id")

        if only_lt:
            qs = qs.filter(username__startswith="lt_user_")

        if target_username:
            qs = qs.filter(username=target_username)

        if limit:
            qs = qs[:limit]

        users = list(qs)
        if not users:
            self.stdout.write(self.style.WARNING("No users matched query."))
            return

        self.stdout.write(
            f"Sending {count} notifications to {len(users)} users "
            f"(only_lt={only_lt}, user={target_username}, limit={limit})"
        )

        total_sent = 0
        start = time.perf_counter()

        for n in range(count):
            for user in users:
                group_name = f"{group_prefix}{user.id}"

                notif_client_id = f"{user.username}-{n}-{uuid.uuid4().hex[:8]}"
                payload = {
                    # internal dispatch type -> calls notification_message() on consumer
                    "type": "notification.message",

                    # payload
                    "notification_client_id": notif_client_id,
                    "title": "Test Notification",
                    "message": f"Test notification {n+1} for {user.username}",
                    "org_id": None,
                    "conversation_id": None,
                    "sender": "System",
                    "sender_profile_picture": "/static/img/default-profile.jpg",
                    "conversation_url": "#",
                    "timestamp": time.time(),
                }

                async_to_sync(channel_layer.group_send)(group_name, payload)
                total_sent += 1

                if sleep_s > 0:
                    time.sleep(sleep_s)

        dt = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(
            f"Done. Sent {total_sent} notifications in {dt:.2f}s "
            f"({total_sent/dt:.1f} notifs/sec)."
        ))
