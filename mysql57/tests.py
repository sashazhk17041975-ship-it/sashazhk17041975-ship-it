"""Run with AUTOPARTS_TEST_DATABASE_URI pointing to an isolated test_* MySQL DB."""
import io
import os
import re
import unittest
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from .app import create_app, password_hash
from .models import db, User, Part, Manufacturer, Analogue, CrossReference, Vehicle
from .importers import import_csv


class MySQL57Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ['AUTOPARTS_TEST_DATABASE_URI']
        if not (make_url(uri).database or '').startswith('test_'):
            raise ValueError('Tests require an explicitly configured test_* database.')
        cls.app = create_app({'SQLALCHEMY_DATABASE_URI': uri, 'SECRET_KEY': 'test-only-secret-'*4, 'TESTING': True, 'WTF_CSRF_ENABLED': False})

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.brand = Manufacturer(name='Test')
        db.session.add(self.brand)
        self.a = Part(manufacturer=self.brand, article='AB-123', name='Фильтр')
        self.b = Part(manufacturer=self.brand, article='CD456', name='Другой фильтр')
        self.c = Part(manufacturer=self.brand, article='EF789', name='Третья деталь')
        db.session.add_all([self.a, self.b, self.c,
            User(username='reader', password_hash=password_hash('Reader-test-123!'), active=True),
            User(username='editor', password_hash=password_hash('Editor-test-123!'), staff=True, active=True),
            User(username='admin', password_hash=password_hash('Admin-test-123!'), staff=True, admin=True, active=True)])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.context.pop()
        self.app.config['WTF_CSRF_ENABLED'] = False

    def login(self, user='reader'):
        return self.client.post('/accounts/login/', data={'username': user, 'password': user.capitalize()+'-test-123!'})

    def test_actual_mysql57(self):
        self.assertTrue(db.session.execute(text('SELECT VERSION()')).scalar().startswith('5.7.31'))

    def test_anonymous_requires_login(self):
        for path in ['/', '/parts/1/', '/import/', '/manage/', '/admin/users/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.location)

    def test_login_logout_and_redirect(self):
        response = self.client.post('/accounts/login/?next=https://evil.example/', data={'username': 'reader', 'password': 'Reader-test-123!'})
        self.assertEqual(response.location, '/')
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/accounts/logout/').status_code, 405)
        self.assertEqual(self.client.post('/accounts/logout/').status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_rate_limit(self):
        for _ in range(5):
            response = self.client.post('/accounts/login/', data={'username': 'reader', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.login().status_code, 429)

    def test_search(self):
        self.login()
        for q in ['ab 123', 'AB.123', 'AB-123', 'фильтр']:
            self.assertIn('AB-123', self.client.get('/', query_string={'q': q}).text)
        self.assertIn('Ничего не найдено', self.client.get('/?q=unknown').text)

    def test_reader_cannot_edit(self):
        self.login()
        for path in ['/parts/new/', f'/parts/{self.a.id}/edit/', f'/parts/{self.a.id}/analogues/new/', '/import/', '/manage/', '/admin/users/']:
            self.assertEqual(self.client.post(path, data={}).status_code, 403)

    def test_editor_cannot_create_users(self):
        self.login('editor')
        self.assertEqual(self.client.post('/admin/users/', data={}).status_code, 403)

    def test_admin_creates_reader(self):
        self.login('admin')
        self.assertEqual(self.client.post('/admin/users/', data={'username':'newuser','password':'New-user-password123'}).status_code, 302)
        user = db.session.scalar(db.select(User).filter_by(username='newuser'))
        self.assertFalse(user.staff)
        self.assertNotEqual(user.password_hash, 'New-user-password123')

    def test_disabled_user_loses_access(self):
        self.login()
        user = db.session.scalar(db.select(User).filter_by(username='reader'))
        user.active = False
        db.session.commit()
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_password_change(self):
        self.login()
        response = self.client.post('/accounts/password/', data={'old':'Reader-test-123!','new':'Changed-password123','confirmation':'Changed-password123'})
        self.assertEqual(response.status_code, 302)
        self.client.post('/accounts/logout/')
        self.assertEqual(self.client.post('/accounts/login/', data={'username':'reader','password':'Changed-password123'}).status_code, 302)

    def test_password_reset_revokes_existing_session(self):
        self.login()
        user=db.session.scalar(db.select(User).filter_by(username='reader'))
        user.password_hash=password_hash('Reset-password-123')
        db.session.commit()
        self.assertEqual(self.client.get('/').status_code,302)

    def test_part_create_and_duplicate(self):
        self.login('editor')
        fields={'manufacturer':self.brand.id,'article':'NEW-1','name':'Новая'}
        self.assertEqual(self.client.post('/parts/new/', data=fields).status_code, 302)
        fields['article']='new 1'
        self.assertEqual(self.client.post('/parts/new/', data=fields).status_code, 400)

    def test_bidirectional_analogue_without_transitivity(self):
        self.login('editor')
        self.assertEqual(self.client.post(f'/parts/{self.b.id}/analogues/new/', data={'other':self.a.id,'source':'Test'}).status_code, 302)
        db.session.add(Analogue(part_a_id=self.b.id, part_b_id=self.c.id, source='Test'))
        db.session.commit()
        self.assertIn('AB-123', self.client.get(f'/parts/{self.b.id}/').text)
        self.assertNotIn('EF789', self.client.get(f'/parts/{self.a.id}/').text)

    def test_self_analogue_rejected_without_check_constraints(self):
        self.login('editor')
        self.assertEqual(self.client.post(f'/parts/{self.a.id}/analogues/new/', data={'other':self.a.id,'source':'Test'}).status_code, 400)
        self.assertEqual(db.session.query(Analogue).count(), 0)

    def test_vehicle_validation_and_filter(self):
        self.login('editor')
        self.assertEqual(self.client.post('/manage/', data={'kind':'vehicle','make':'Test','model':'Car','year_from':'2020','year_to':'2010'}).status_code, 400)
        vehicle=Vehicle(make='Test',model='Car',year_from=2010)
        self.a.vehicles.append(vehicle)
        db.session.commit()
        response=self.client.get('/', query_string={'vehicle':vehicle.id})
        self.assertIn('AB-123',response.text)
        self.assertNotIn('CD456',response.text)

    def test_import_repeatable_and_atomic(self):
        self.login('editor')
        content=b'manufacturer,article,name\nCSV,001,Imported\n'
        for _ in range(2):
            self.assertEqual(self.client.post('/import/', data={'kind':'parts','file':(io.BytesIO(content),'parts.csv')}).status_code, 302)
        self.assertEqual(db.session.query(Part).filter_by(article_key='001').count(), 1)
        invalid=b'manufacturer,article,name\nUncommitted,1,Valid\nUncommitted,2,\n'
        self.assertEqual(self.client.post('/import/', data={'kind':'parts','file':(io.BytesIO(invalid),'bad.csv')}).status_code, 400)
        self.assertIsNone(db.session.scalar(db.select(Manufacturer).filter_by(name='Uncommitted')))

    def test_source_metadata(self):
        data='source_oem;source_brand;relation_code;relation_name;direction;related_oem;related_brand;weight;rate;last_seen_at\n001;CSV;replacement;Замена;reverse;002;Other;0,29;4;2026-10-06 16:47:21\n'
        created,updated=import_csv(io.BytesIO(data.encode()),'references')
        db.session.commit()
        self.assertEqual((created,updated),(1,0))
        ref=db.session.scalar(db.select(CrossReference))
        self.assertEqual(ref.source_part.article,'001')
        self.assertEqual(ref.direction,'reverse')
        self.assertEqual(ref.weight,Decimal('0.29'))
        self.assertEqual(ref.last_seen_at.hour,13)
        self.assertEqual(db.session.query(Analogue).count(),0)
        self.assertEqual(import_csv(io.BytesIO(data.encode()),'references'),(0,1))

    def test_csrf(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/accounts/login/',data={'username':'reader','password':'Reader-test-123!'}).status_code,400)
        response=self.client.get('/accounts/login/')
        token=re.search(r'name="csrf_token" value="([^"]+)"',response.text).group(1)
        self.assertEqual(self.client.post('/accounts/login/',data={'username':'reader','password':'Reader-test-123!','csrf_token':token}).status_code,302)
        self.assertEqual(self.client.post('/accounts/logout/').status_code,400)

    def test_html_escaped(self):
        self.a.name='<script>alert(1)</script>'
        db.session.commit()
        self.login()
        self.assertIn('&lt;script&gt;',self.client.get(f'/parts/{self.a.id}/').text)


if __name__ == '__main__':
    unittest.main()
