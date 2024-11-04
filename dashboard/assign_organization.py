from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from dashboard.models import Organization

class Command(BaseCommand):
    help = 'Assign an organization to existing superusers without one'

    def add_arguments(self, parser):
        parser.add_argument('--organization', required=True, help='Specify the organization name')

    def handle(self, *args, **options):
        organization_name = options['organization']
        try:
            organization = Organization.objects.get(name=organization_name)
        except Organization.DoesNotExist:
            raise CommandError(f'Organization "{organization_name}" does not exist.')

        User = get_user_model()
        superusers_without_org = User.objects.filter(is_superuser=True, organization__isnull=True)

        for user in superusers_without_org:
            user.organization = organization
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Assigned organization "{organization_name}" to superuser "{user.username}"'))

        if not superusers_without_org.exists():
            self.stdout.write(self.style.WARNING('No superusers found without an organization.'))
