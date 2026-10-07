import os
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create initial administrator from environment; never reset existing credentials.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        users = get_user_model().objects
        if users.filter(username=username).exists():
            self.stdout.write('Account already exists; left unchanged.')
            return
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        if not password:
            raise CommandError('Set DJANGO_SUPERUSER_PASSWORD or use createsuperuser interactively.')
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(str(error)) from error
        users.create_superuser(username, email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''), password=password)
        self.stdout.write(self.style.SUCCESS('Administrator created. Password was not logged.'))
