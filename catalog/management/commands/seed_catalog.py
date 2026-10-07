from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from catalog.importers import import_csv
from catalog.models import CrossReference


class Command(BaseCommand):
    help = 'Load the provided catalogue only if no source references exist.'

    def handle(self, *args, **options):
        if CrossReference.objects.exists():
            self.stdout.write('Catalogue already contains source references; existing data preserved.')
            return
        with (Path(settings.BASE_DIR) / 'data' / 'example.csv').open('rb') as file:
            created, updated = import_csv(file, 'references')
        self.stdout.write(f'Catalogue initialized: {created} created, {updated} updated.')
