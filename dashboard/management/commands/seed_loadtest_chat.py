# dashboard/management/commands/seed_loadtest_chat.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from dashboard.models import Organization, Conversation, GroupMember  # adjust if needed

User = get_user_model()


class Command(BaseCommand):
    help = "Seed 1000 users + conversations for chat load testing"

    def add_arguments(self, parser):
        parser.add_argument('--org', type=int, required=True)
        parser.add_argument('--users', type=int, default=1000)
        parser.add_argument('--rooms', type=int, default=10)

    def handle(self, *args, **options):
        org_id = options['org']
        total_users = options['users']
        rooms = options['rooms']

        org = Organization.objects.get(id=org_id)
        self.stdout.write(self.style.SUCCESS(f"Using org {org_id} for load test"))

        # 1) Create users and attach them to org
        users = []
        for i in range(total_users):
            username = f"lt_user_{i}"
            email = f"{username}@example.com"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "organization": org,
                }
            )
            if created:
                user.set_password("testpassword")
                user.organization = org
                user.save()
            else:
                # Ensure existing user belongs to this org
                if user.organization_id != org.id:
                    user.organization = org
                    user.save(update_fields=["organization"])

            users.append(user)

        self.stdout.write(self.style.SUCCESS(f"Ensured {len(users)} users exist"))

        # 2) Create group conversations for this org
        conversations = []
        for r in range(rooms):
            convo, _ = Conversation.objects.get_or_create(
                organization=org,                    # ✅ field name is 'organization'
                name=f"LoadTest Room {r}",
                defaults={"type": "group"},
            )
            conversations.append(convo)

        self.stdout.write(self.style.SUCCESS(f"Ensured {len(conversations)} conversations exist"))

        # 3) Assign users evenly across rooms using GroupMember
        per_room = total_users // rooms
        idx = 0

        for convo in conversations:
            room_users = users[idx:idx + per_room]
            idx += per_room

            for u in room_users:
                GroupMember.objects.get_or_create(
                    conversation=convo,
                    user=u,
                    defaults={"role": "member"},
                )

        self.stdout.write(self.style.SUCCESS("Users assigned to conversations"))
