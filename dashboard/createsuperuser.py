from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.management.commands.createsuperuser import Command as BaseCommand
from django.core.management import CommandError
from dashboard.models import CustomUser, Organization

class Command(BaseCommand):
    help = 'Create a new superuser'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--first_name', required=True)
        parser.add_argument('--last_name', required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username=options['username']).exists():
            raise CommandError('User "%s" already exists' % options['username'])

        user = User.objects.create_superuser(
            username=options['username'],
            email=options['email'],
            password=options['password'],
            first_name=options['first_name'],
            last_name=options['last_name']
        )
        self.stdout.write(self.style.SUCCESS('Successfully created new superuser'))

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
        