import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from .models import db, Manufacturer, Part, Analogue, CrossReference, normalize_article


def required(row, field, limit=255):
    value = (row.get(field) or '').strip()
    if not value or len(value) > limit:
        raise ValueError(f'Поле {field}: требуется значение до {limit} символов.')
    return value


def manufacturer(name):
    item = db.session.scalar(db.select(Manufacturer).filter_by(name=name))
    if not item:
        item = Manufacturer(name=name)
        db.session.add(item)
        db.session.flush()
    return item


def part(brand, article, create=False):
    key = normalize_article(article)
    if not key:
        raise ValueError('Пустой нормализованный артикул.')
    item = db.session.scalar(db.select(Part).join(Manufacturer).where(Manufacturer.name == brand, Part.article_key == key))
    if not item and create:
        item = Part(manufacturer=manufacturer(brand), article=article, name='Название не указано')
        db.session.add(item)
        db.session.flush()
    if not item:
        raise ValueError(f'Деталь {brand} {article} не найдена. Сначала импортируйте запчасти.')
    return item


def decimal(value, precision, scale):
    value = (value or '').strip()
    if value in ('', '\\N'):
        return None
    try:
        number = Decimal(value.replace(',', '.'))
        if not number.is_finite() or abs(number) >= Decimal(10) ** (precision-scale) or number != number.quantize(Decimal(10) ** -scale):
            raise ValueError('Число выходит за допустимый диапазон или точность.')
        return number
    except InvalidOperation:
        raise ValueError('Некорректное число.')


def import_csv(upload, kind):
    """Caller commits on success and rolls back the entire import on any error."""
    data = upload.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Максимальный размер файла — 2 МБ.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Сохраните CSV в UTF-8.')
    fields = {
        'parts': ['manufacturer', 'article', 'name'],
        'analogues': ['manufacturer', 'article', 'analog_manufacturer', 'analog_article', 'source'],
        'references': ['source_oem', 'source_brand', 'relation_code', 'relation_name', 'direction', 'related_oem', 'related_brand', 'weight', 'rate', 'last_seen_at'],
    }
    if kind not in fields:
        raise ValueError('Неизвестный формат импорта.')
    reader = csv.DictReader(io.StringIO(text), delimiter=';' if kind == 'references' else ',')
    if not reader.fieldnames or not set(fields[kind]).issubset(reader.fieldnames):
        raise ValueError('Нужны колонки: ' + ', '.join(fields[kind]))
    created = updated = 0
    for line, row in enumerate(reader, 2):
        try:
            if line > 5001 or None in row:
                raise ValueError('До 5000 строк. Проверьте количество колонок и кавычки.')
            if kind == 'references':
                first = part(required(row, 'source_brand', 120), required(row, 'source_oem', 80), True)
                other = part(required(row, 'related_brand', 120), required(row, 'related_oem', 80), True)
                identity = dict(source_part_id=first.id, related_part_id=other.id,
                                relation_code=required(row, 'relation_code', 80), direction=required(row, 'direction', 16))
                item = db.session.scalar(db.select(CrossReference).filter_by(**identity))
                new = item is None
                item = item or CrossReference(**identity)
                item.relation_name = required(row, 'relation_name', 120)
                item.weight, item.rate = decimal(row['weight'], 16, 6), decimal(row['rate'], 12, 4)
                date = (row['last_seen_at'] or '').strip()
                parsed = datetime.fromisoformat(date) if date not in ('', '\\N') else None
                if parsed and parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ZoneInfo('Europe/Moscow'))
                item.last_seen_at = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed else None
                item.source = Path(str(getattr(upload, 'filename', None) or getattr(upload, 'name', 'CSV'))).name[:255]
            elif kind == 'parts':
                brand = required(row, 'manufacturer', 120)
                article = required(row, 'article', 80)
                item = db.session.scalar(db.select(Part).join(Manufacturer).where(Manufacturer.name == brand, Part.article_key == normalize_article(article)))
                new = item is None
                item = item or Part(manufacturer=manufacturer(brand))
                item.article, item.name = article, required(row, 'name', 200)
                for field, limit in [('category', 100), ('description', 16000), ('source', 255)]:
                    if field in row:
                        value = (row[field] or '').strip()
                        if len(value) > limit:
                            raise ValueError(f'Поле {field} слишком длинное.')
                        setattr(item, field, value)
            else:
                first = part(required(row, 'manufacturer', 120), required(row, 'article', 80))
                other = part(required(row, 'analog_manufacturer', 120), required(row, 'analog_article', 80))
                a, b = sorted([first.id, other.id])
                item = db.session.scalar(db.select(Analogue).filter_by(part_a_id=a, part_b_id=b))
                new = item is None
                item = item or Analogue(part_a_id=a, part_b_id=b)
                item.source = required(row, 'source')
                if 'note' in row:
                    item.note = (row['note'] or '').strip()
                if 'verified' in row:
                    flag = (row['verified'] or '').strip().lower()
                    if flag not in ('', '0', '1', 'true', 'false'):
                        raise ValueError('verified: допустимы 0, 1, true, false.')
                    item.verified = flag in ('1', 'true')
            db.session.add(item)
            db.session.flush()
            created += int(new)
            updated += int(not new)
        except ValueError as error:
            raise ValueError(f'Строка {line}: {error}') from error
    if not created and not updated:
        raise ValueError('В файле нет строк данных.')
    return created, updated
