from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.management.commands.createsuperuser import Command as BaseCommand
from django.core.management import CommandError
from dashboard.models import CustomUser, Organization
from django.core.management.base import CommandError
from django.contrib.auth.management.commands.createsuperuser import Command as BaseCommand
from dashboard.models import Organization
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a new superuser with an organization'

    def add_arguments(self, parser):
        super().add_arguments(parser)  # Inherit default arguments
        parser.add_argument(
            '--organization',
            required=True,
            help='Specify the organization for the superuser'
        )

    def handle(self, *args, **options):
        # Ensure the organization exists
        organization_name = options['organization']
        try:
            organization = Organization.objects.get(name=organization_name)
        except Organization.DoesNotExist:
            raise CommandError(f'Organization "{organization_name}" does not exist. Please create it first.')

        # Check if the user already exists
        User = get_user_model()
        username = options.get('username')
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User "{username}" already exists.')

        # Create the superuser
        super().handle(*args, **options)

        # Update the user's organization
        user = User.objects.get(username=username)
        user.organization = organization
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f'Successfully created superuser "{username}" and assigned to organization "{organization_name}".'
        ))

class Command(BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--organization',
            help='Specify the organization for the superuser'
        )

    def handle(self, *args, **options):
        organization_name = options.get('organization')
        if not organization_name:
            raise CommandError('You must provide an organization for the superuser using --organization')

        try:
            organization = Organization.objects.get(name=organization_name)
        except Organization.DoesNotExist:
            raise CommandError(f'Organization "{organization_name}" does not exist.')

        options['organization'] = organization

        super().handle(*args, **options)

    def save(self, *args, **kwargs):
        # Override save to include organization when creating superuser
        self.instance.organization = kwargs.pop('organization')
        super().save(*args, **kwargs)
        