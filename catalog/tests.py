import io
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from .importers import import_csv
from .models import Analogue, CrossReference, Manufacturer, Part, Vehicle


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Manufacturer.objects.create(name='Test Brand')
        cls.a = Part.objects.create(manufacturer=cls.brand, article='AB-123', name='Тестовый фильтр')
        cls.b = Part.objects.create(manufacturer=cls.brand, article='CD456', name='Второй фильтр')
        cls.c = Part.objects.create(manufacturer=cls.brand, article='EF789', name='Третья деталь')
        cls.reader = get_user_model().objects.create_user('reader', password='Test-reader-47!')
        cls.editor = get_user_model().objects.create_user('editor', password='Test-editor-47!', is_staff=True)

    def test_anonymous_access_requires_login(self):
        for url in ['/', reverse('catalog:part_detail', args=[self.a.pk]), '/import/', '/parts/new/']:
            self.assertRedirects(self.client.get(url), '/accounts/login/?next=' + url, fetch_redirect_response=False)

    def test_login_logout_and_safe_redirect(self):
        response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Test-reader-47!', 'next': 'https://example.org/'})
        self.assertRedirects(response, '/')
        self.assertEqual(self.client.get('/accounts/logout/').status_code, 405)
        self.assertRedirects(self.client.post('/accounts/logout/'), '/accounts/login/')
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_wrong_password_does_not_authenticate(self):
        self.client.post('/accounts/login/', {'username': 'reader', 'password': 'wrong'})
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_login_is_rate_limited(self):
        for _ in range(5):
            response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)
        response = self.client.post('/accounts/login/', {'username': 'reader', 'password': 'Test-reader-47!'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_normalized_article_search(self):
        self.client.force_login(self.reader)
        for query in ['ab 123', 'AB.123', 'AB-123', 'фильтр']:
            response = self.client.get('/', {'q': query})
            self.assertContains(response, 'AB-123')
        response = self.client.get('/', {'q': 'does-not-exist'})
        self.assertContains(response, 'Ничего не найдено')

    def test_reader_cannot_mutate_data(self):
        self.client.force_login(self.reader)
        link = Analogue.objects.create(part_a=self.a, part_b=self.b, source='Test')
        urls = ['/parts/new/', reverse('catalog:part_edit', args=[self.a.pk]),
                reverse('catalog:analogue_add', args=[self.a.pk]),
                reverse('catalog:analogue_delete', args=[link.pk]), '/import/']
        for url in urls:
            self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertTrue(Analogue.objects.filter(pk=link.pk).exists())

    def test_editor_creates_part_and_analogue(self):
        self.client.force_login(self.editor)
        response = self.client.post('/parts/new/', {'manufacturer': self.brand.pk, 'article': 'NEW-1', 'name': 'Новая деталь'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Part.objects.filter(article_key='NEW1').exists())
        response = self.client.post(reverse('catalog:analogue_add', args=[self.a.pk]), {'other': self.b.pk, 'source': 'Каталог', 'verified': 'on'})
        self.assertEqual(response.status_code, 302)
        link = Analogue.objects.get()
        self.assertTrue(link.verified)
        self.assertContains(self.client.get(reverse('catalog:part_detail', args=[self.b.pk])), 'AB-123')

    def test_no_transitive_analogue_inference(self):
        Analogue.objects.create(part_a=self.a, part_b=self.b, source='Test')
        Analogue.objects.create(part_a=self.b, part_b=self.c, source='Test')
        self.client.force_login(self.reader)
        response = self.client.get(reverse('catalog:part_detail', args=[self.a.pk]))
        self.assertContains(response, self.b.article)
        self.assertNotContains(response, self.c.article)

    def test_canonical_pair_unique_and_no_self_link(self):
        link = Analogue(part_a=self.b, part_b=self.a, source='Test')
        link.full_clean()
        link.save()
        self.assertEqual(link.part_a_id, self.a.pk)
        with self.assertRaises(ValidationError):
            Analogue(part_a=self.a, part_b=self.b, source='Test').full_clean()
        with self.assertRaises(ValidationError):
            Analogue(part_a=self.a, part_b=self.a, source='Test').full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Analogue.objects.create(part_a=self.a, part_b=self.a, source='Test')

    def test_normalized_duplicate_rejected(self):
        with self.assertRaises(ValidationError):
            Part(manufacturer=self.brand, article='ab 123', name='Duplicate').full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Part.objects.create(manufacturer=self.brand, article='AB123', name='Duplicate')

    def test_csv_parts_repeatable_and_atomic(self):
        text = 'manufacturer,article,name\nImport brand,001-A,Test\n'
        self.assertEqual(import_csv(io.BytesIO(text.encode()), 'parts'), (1, 0))
        self.assertEqual(import_csv(io.BytesIO(text.encode()), 'parts'), (0, 1))
        invalid = 'manufacturer,article,name\nRolled back,1,Test\nRolled back,2,\n'
        with self.assertRaises(ValueError):
            import_csv(io.BytesIO(invalid.encode()), 'parts')
        self.assertFalse(Manufacturer.objects.filter(name='Rolled back').exists())

    def test_csv_analogues(self):
        text = 'manufacturer,article,analog_manufacturer,analog_article,source,verified\nTest Brand,AB123,Test Brand,CD456,CSV,0\n'
        self.assertEqual(import_csv(io.BytesIO(text.encode()), 'analogues'), (1, 0))
        self.assertEqual(import_csv(io.BytesIO(text.encode()), 'analogues'), (0, 1))
        self.assertFalse(Analogue.objects.get().verified)

    def test_source_csv_preserves_metadata_and_leading_zeros(self):
        text = 'source_oem;source_brand;relation_code;relation_name;direction;related_oem;related_brand;weight;rate;last_seen_at\n001;CSV Brand;replacement;Замена;reverse;002;Other Brand;0,29;4;2026-10-06 16:47:21\n'
        upload = SimpleUploadedFile('example.csv', text.encode('utf-8-sig'))
        self.assertEqual(import_csv(upload, 'references'), (1, 0))
        ref = CrossReference.objects.get()
        self.assertEqual(ref.source_part.article, '001')
        self.assertEqual(ref.direction, 'reverse')
        self.assertEqual(ref.weight, Decimal('0.29'))
        self.assertEqual(ref.rate, Decimal('4'))
        self.assertEqual(ref.source, 'example.csv')
        self.assertEqual(ref.last_seen_at.hour, 13)  # Moscow converted to UTC.
        self.assertFalse(Analogue.objects.exists())
        self.assertEqual(import_csv(SimpleUploadedFile('example.csv', text.encode()), 'references'), (0, 1))
        self.client.force_login(self.reader)
        response = self.client.get(reverse('catalog:part_detail', args=[ref.related_part_id]))
        self.assertContains(response, '001')
        self.assertContains(response, 'reverse')

    def test_source_null_and_invalid_direction_rolls_back(self):
        header = 'source_oem;source_brand;relation_code;relation_name;direction;related_oem;related_brand;weight;rate;last_seen_at\n'
        good = '1;CSV;replacement;Замена;forward;2;CSV;\\N;\\N;\\N\n'
        import_csv(io.BytesIO((header + good).encode()), 'references')
        ref = CrossReference.objects.get()
        self.assertIsNone(ref.weight)
        self.assertIsNone(ref.rate)
        self.assertIsNone(ref.last_seen_at)
        bad = '3;Uncommitted;replacement;Замена;invalid;4;Uncommitted;0;1;\\N\n'
        with self.assertRaises(ValueError):
            import_csv(io.BytesIO((header + bad).encode()), 'references')
        self.assertFalse(Manufacturer.objects.filter(name='Uncommitted').exists())

    def test_import_web_upload(self):
        self.client.force_login(self.editor)
        upload = SimpleUploadedFile('parts.csv', b'manufacturer,article,name\nUpload,1,Uploaded\n')
        self.assertEqual(self.client.post('/import/', {'kind': 'parts', 'file': upload}).status_code, 302)
        self.assertTrue(Part.objects.filter(manufacturer__name='Upload').exists())

    def test_csrf_protects_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        self.assertEqual(client.post('/parts/new/', {}).status_code, 403)
        self.assertEqual(client.post('/accounts/logout/').status_code, 403)

    def test_vehicle_filter(self):
        vehicle = Vehicle.objects.create(make='Test', model='Car', year_from=2010)
        self.a.vehicles.add(vehicle)
        self.client.force_login(self.reader)
        response = self.client.get('/', {'vehicle': vehicle.pk})
        self.assertContains(response, 'AB-123')
        self.assertNotContains(response, 'CD456')

    def test_html_escaped(self):
        self.a.name = '<script>alert(1)</script>'
        self.a.save()
        self.client.force_login(self.reader)
        self.assertContains(self.client.get(reverse('catalog:part_detail', args=[self.a.pk])), '&lt;script&gt;')
