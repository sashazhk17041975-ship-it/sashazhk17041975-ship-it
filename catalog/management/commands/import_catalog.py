from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from catalog.importers import import_csv

class Command(BaseCommand):
    help = 'Import UTF-8 CSV parts or analogue links atomically.'

    def add_arguments(self, parser):
        parser.add_argument('kind', choices=['parts', 'analogues', 'references'])
        parser.add_argument('file')

    def handle(self, *args, **options):
        try:
            with open(options['file'], 'rb') as file:
                if len(file.read(2 * 1024 * 1024 + 1)) > 2 * 1024 * 1024:
                    raise ValueError('Maximum file size is 2 MB.')
                file.seek(0)
                created, updated = import_csv(file, options['kind'])
        except (OSError, ValueError, IntegrityError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f'Created: {created}; updated: {updated}'))
