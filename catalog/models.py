import re
import unicodedata
from django.core.exceptions import ValidationError
from django.db import models


def normalize_article(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value), flags=re.UNICODE).upper()


class Manufacturer(models.Model):
    name = models.CharField('Производитель', max_length=120, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'производитель'
        verbose_name_plural = 'производители'

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    make = models.CharField('Марка автомобиля', max_length=80)
    model = models.CharField('Модель / поколение', max_length=120)
    engine = models.CharField('Двигатель / модификация', max_length=120, blank=True)
    year_from = models.PositiveSmallIntegerField('Год с')
    year_to = models.PositiveSmallIntegerField('Год по', null=True, blank=True)

    class Meta:
        ordering = ['make', 'model', 'year_from']
        verbose_name = 'автомобиль'
        verbose_name_plural = 'автомобили'
        constraints = [models.CheckConstraint(condition=models.Q(year_to__isnull=True) | models.Q(year_to__gte=models.F('year_from')), name='vehicle_year_range')]

    def clean(self):
        if self.year_from < 1900 or (self.year_to and self.year_to < self.year_from):
            raise ValidationError('Проверьте диапазон годов выпуска.')

    def __str__(self):
        return f'{self.make} {self.model} · {self.engine} · {self.year_from}–{self.year_to or "н.в."}'


class Part(models.Model):
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT, verbose_name='Производитель')
    article = models.CharField('Артикул', max_length=80)
    article_key = models.CharField(max_length=80, editable=False, db_index=True)
    name = models.CharField('Название', max_length=200)
    category = models.CharField('Категория', max_length=100, blank=True)
    description = models.TextField('Описание', blank=True)
    source = models.CharField('Источник данных', max_length=255, blank=True)
    vehicles = models.ManyToManyField(Vehicle, blank=True, verbose_name='Применяемость')
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        ordering = ['manufacturer__name', 'article']
        verbose_name = 'запчасть'
        verbose_name_plural = 'запчасти'
        constraints = [models.UniqueConstraint(fields=['manufacturer', 'article_key'], name='unique_manufacturer_article')]

    def clean(self):
        self.article_key = normalize_article(self.article)
        if not self.article_key:
            raise ValidationError({'article': 'Артикул должен содержать буквы или цифры.'})
        if Part.objects.filter(manufacturer_id=self.manufacturer_id, article_key=self.article_key).exclude(pk=self.pk).exists():
            raise ValidationError({'article': 'Такой артикул у этого производителя уже есть.'})

    def save(self, *args, **kwargs):
        self.article_key = normalize_article(self.article)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.manufacturer} {self.article} — {self.name}'


class Analogue(models.Model):
    part_a = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='links_a', verbose_name='Деталь 1')
    part_b = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='links_b', verbose_name='Деталь 2')
    source = models.CharField('Источник / каталог', max_length=255)
    note = models.TextField('Условия замены / примечание', blank=True)
    verified = models.BooleanField('Проверено специалистом', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'связь аналогов'
        verbose_name_plural = 'связи аналогов'
        constraints = [
            models.UniqueConstraint(fields=['part_a', 'part_b'], name='unique_analogue_pair'),
            models.CheckConstraint(condition=models.Q(part_a__lt=models.F('part_b')), name='ordered_distinct_analogue_pair'),
        ]

    def clean(self):
        if self.part_a_id and self.part_b_id:
            if self.part_a_id == self.part_b_id:
                raise ValidationError('Нельзя связать деталь с самой собой.')
            self.part_a_id, self.part_b_id = sorted([self.part_a_id, self.part_b_id])
            if Analogue.objects.filter(part_a_id=self.part_a_id, part_b_id=self.part_b_id).exclude(pk=self.pk).exists():
                raise ValidationError('Эта связь аналогов уже существует.')

    def save(self, *args, **kwargs):
        self.part_a_id, self.part_b_id = sorted([self.part_a_id, self.part_b_id])
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.part_a.article} ↔ {self.part_b.article}'


class CrossReference(models.Model):
    """Source records are retained independently of manually verified analogue pairs."""
    source_part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='references_from', verbose_name='Исходная деталь')
    related_part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='references_to', verbose_name='Связанная деталь')
    relation_code = models.CharField('Код отношения', max_length=80)
    relation_name = models.CharField('Название отношения', max_length=120)
    direction = models.CharField('Направление источника', max_length=16, choices=[('forward', 'forward'), ('reverse', 'reverse')])
    weight = models.DecimalField('Вес из источника', max_digits=16, decimal_places=6, null=True, blank=True)
    rate = models.DecimalField('Рейтинг из источника', max_digits=12, decimal_places=4, null=True, blank=True)
    last_seen_at = models.DateTimeField('Дата из источника', null=True, blank=True)
    source = models.CharField('Источник / файл', max_length=255)

    class Meta:
        verbose_name = 'связь из каталога'
        verbose_name_plural = 'связи из каталога'
        constraints = [models.UniqueConstraint(fields=['source_part', 'related_part', 'relation_code', 'direction'], name='unique_source_reference')]

    def __str__(self):
        return f'{self.source_part.article} / {self.related_part.article} ({self.direction})'
