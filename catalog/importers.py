import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Analogue, CrossReference, Manufacturer, Part, normalize_article


def required(row, key):
    value = (row.get(key) or '').strip()
    if not value:
        raise ValueError(f'Не заполнено поле {key}.')
    return value


def find_part(row, prefix):
    try:
        return Part.objects.get(manufacturer__name__iexact=required(row, prefix + 'manufacturer'),
                                article_key=normalize_article(required(row, prefix + 'article')))
    except Part.DoesNotExist:
        raise ValueError(f'Деталь {prefix} не найдена. Сначала импортируйте запчасти.')


def source_part(brand, article):
    manufacturer = Manufacturer.objects.filter(name__iexact=brand).first()
    if not manufacturer:
        manufacturer = Manufacturer(name=brand)
        manufacturer.full_clean()
        manufacturer.save()
    part = Part.objects.filter(manufacturer=manufacturer, article_key=normalize_article(article)).first()
    if not part:
        part = Part(manufacturer=manufacturer, article=article, name='Название не указано')
        part.full_clean()
        part.save()
    return part


def nullable_decimal(value):
    value = (value or '').strip()
    if value in ('', '\\N'):
        return None
    try:
        return Decimal(value.replace(',', '.'))
    except InvalidOperation:
        raise ValueError('Некорректное число: ' + value)


@transaction.atomic
def import_csv(upload, kind):
    try:
        text = upload.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Сохраните CSV в кодировке UTF-8.')
    if kind not in ('parts', 'analogues', 'references'):
        raise ValueError('Неизвестный тип импорта.')
    delimiter = ';' if kind == 'references' else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = {
        'parts': ['manufacturer', 'article', 'name'],
        'analogues': ['manufacturer', 'article', 'analog_manufacturer', 'analog_article', 'source'],
        'references': ['source_oem', 'source_brand', 'relation_code', 'relation_name', 'direction', 'related_oem', 'related_brand', 'weight', 'rate', 'last_seen_at'],
    }[kind]
    if not reader.fieldnames or not set(fields).issubset(reader.fieldnames):
        raise ValueError('Нужны колонки: ' + ', '.join(fields))
    created = updated = 0
    for line, row in enumerate(reader, start=2):
        if line > 5001:
            raise ValueError('За один импорт допускается до 5000 строк.')
        try:
            if None in row:
                raise ValueError('Лишние колонки. Проверьте кавычки и разделитель-запятую.')
            if kind == 'references':
                first = source_part(required(row, 'source_brand'), required(row, 'source_oem'))
                second = source_part(required(row, 'related_brand'), required(row, 'related_oem'))
                code = required(row, 'relation_code')
                direction = required(row, 'direction')
                if direction not in ('forward', 'reverse'):
                    raise ValueError('direction: допустимы forward или reverse.')
                ref = CrossReference.objects.filter(source_part=first, related_part=second, relation_code=code, direction=direction).first()
                is_new = ref is None
                ref = ref or CrossReference(source_part=first, related_part=second, relation_code=code, direction=direction)
                ref.relation_name = required(row, 'relation_name')
                ref.weight = nullable_decimal(row['weight'])
                ref.rate = nullable_decimal(row['rate'])
                date = (row['last_seen_at'] or '').strip()
                parsed = datetime.fromisoformat(date) if date not in ('', '\\N') else None
                ref.last_seen_at = timezone.make_aware(parsed) if parsed and timezone.is_naive(parsed) else parsed
                ref.source = Path(str(getattr(upload, 'name', 'CSV'))).name[:255]
                ref.full_clean()
                ref.save()
            elif kind == 'parts':
                manufacturer_name = required(row, 'manufacturer')
                manufacturer = Manufacturer.objects.filter(name__iexact=manufacturer_name).first()
                if not manufacturer:
                    manufacturer = Manufacturer(name=manufacturer_name)
                    manufacturer.full_clean()
                    manufacturer.save()
                article = required(row, 'article')
                part = Part.objects.filter(manufacturer=manufacturer, article_key=normalize_article(article)).first()
                is_new = part is None
                part = part or Part(manufacturer=manufacturer)
                part.article = article
                part.name = required(row, 'name')
                for field in ['category', 'description', 'source']:
                    if field in row:
                        setattr(part, field, (row[field] or '').strip())
                part.full_clean()
                part.save()
            else:
                first, second = find_part(row, ''), find_part(row, 'analog_')
                a, b = sorted([first.pk, second.pk])
                link = Analogue.objects.filter(part_a_id=a, part_b_id=b).first()
                is_new = link is None
                link = link or Analogue(part_a_id=a, part_b_id=b)
                link.source = required(row, 'source')
                if 'note' in row:
                    link.note = (row['note'] or '').strip()
                if 'verified' in row:
                    flag = (row['verified'] or '').strip().lower()
                    if flag not in ('', '0', '1', 'true', 'false'):
                        raise ValueError('verified: допустимы 0, 1, true, false.')
                    link.verified = flag in ('1', 'true')
                link.full_clean()
                link.save()
            created += int(is_new)
            updated += int(not is_new)
        except (ValueError, ValidationError) as error:
            raise ValueError(f'Строка {line}: {error}') from error
    if not created and not updated:
        raise ValueError('Файл не содержит строк данных.')
    return created, updated
