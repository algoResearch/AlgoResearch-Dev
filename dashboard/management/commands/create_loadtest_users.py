# dashboard/management/commands/create_loadtest_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create or reset lt_user_* accounts for load testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=100,
            help="Number of lt_user_* accounts to ensure exist (starting at 0).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="testpass123!",
            help="Password to set for all lt_user_* accounts.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="If set, reset password even for existing lt_user_* accounts.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        password = options["password"]
        reset = options["reset"]

        created = 0
        updated = 0

        self.stdout.write(
            self.style.WARNING(
                f"Ensuring lt_user_0 ... lt_user_{count-1} exist "
                f"with password: {password!r} (reset={reset})"
            )
        )

        for i in range(count):
            username = f"lt_user_{i}"
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": "Load",
                    "last_name": f"Tester{i}",
                },
            )

            if was_created:
                user.set_password(password)
                user.is_active = True
                user.save()
                created += 1
                self.stdout.write(f"  [CREATED] {username}")
            else:
                if reset:
                    user.set_password(password)
                    user.is_active = True
                    user.save()
                    updated += 1
                    self.stdout.write(f"  [UPDATED PW] {username}")
                else:
                    self.stdout.write(f"  [EXISTS] {username} (password unchanged)")

        self.stdout.write()
        self.stdout.write(self.style.SUCCESS(
            f"Done. Created={created}, Password-reset={updated}, "
            f"Total lt_user_* ensured={count}."
        ))
        self.stdout.write(
            self.style.SUCCESS(
                f"All lt_user_* use password: {password!r} "
                "(unless you skipped --reset for existing accounts)."
            )
        )
