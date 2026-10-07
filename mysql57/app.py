import os
import re
import hashlib
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_, func
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from .models import db, User, LoginAttempt, Manufacturer, Part, Vehicle, Analogue, CrossReference, now
from .importers import import_csv, normalize_article, required

ROOT = Path(__file__).resolve().parent.parent


def password_hash(password):
    if len(password) < 12 or len(password) > 256 or not re.search(r'\d', password) or not re.search(r'[^\W\d_]', password):
        raise ValueError('Пароль: 12–256 символов, хотя бы одна буква и цифра.')
    return generate_password_hash(password, method='pbkdf2:sha256:600000')


def create_app(config=None):
    app = Flask(__name__, static_folder=str(ROOT/'static'), template_folder='templates')
    app.config.update(
        SECRET_KEY=os.environ.get('DJANGO_SECRET_KEY', ''),
        SQLALCHEMY_DATABASE_URI=URL.create('mysql+mysqldb',
            username=os.environ.get('MYSQL_USER', 'autoparts'), password=os.environ.get('MYSQL_PASSWORD', ''),
            host=os.environ.get('DB_HOST', '127.0.0.1'), port=int(os.environ.get('DB_PORT', '3306')),
            database=os.environ.get('MYSQL_DATABASE', 'autoparts'), query={'charset': 'utf8mb4'}),
        SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True, 'pool_recycle': 300},
        MAX_CONTENT_LENGTH=2*1024*1024+128*1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if config:
        app.config.update(config)
    if len(app.config['SECRET_KEY']) < 32:
        raise ValueError('DJANGO_SECRET_KEY must contain at least 32 characters.')
    db.init_app(app)
    CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Войдите для работы с каталогом.'

    @login_manager.user_loader
    def load_user(identity):
        return db.session.get(User, int(identity)) if identity.isdecimal() else None

    @app.before_request
    def check_active():
        if current_user.is_authenticated and (not current_user.active or session.get('auth_revision') != hashlib.sha256(current_user.password_hash.encode()).hexdigest()):
            logout_user()
            return redirect(url_for('login'))

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.template_filter('moscow')
    def moscow(value):
        from datetime import timezone
        return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M:%S') if value else '—'

    @app.errorhandler(ValueError)
    def invalid(error):
        db.session.rollback()
        return render_template('error.html', message=str(error)), 400

    @app.errorhandler(IntegrityError)
    def conflict(error):
        db.session.rollback()
        return render_template('error.html', message='Запись уже существует или связана с другими данными. Изменения отменены.'), 400

    def role_required(admin=False):
        def decorate(view):
            @wraps(view)
            @login_required
            def wrapped(*args, **kwargs):
                if not (current_user.admin if admin else current_user.staff or current_user.admin):
                    abort(403)
                return view(*args, **kwargs)
            return wrapped
        return decorate

    def field(name, label, value='', kind='text', choices=None, required=True):
        return dict(name=name, label=label, value=value, kind=kind, choices=choices or [], required=required)

    @app.route('/accounts/login/', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()[:150]
            ip = (request.remote_addr or '')[:45]
            attempt = db.session.scalar(db.select(LoginAttempt).filter_by(username=username, ip=ip).with_for_update())
            if attempt and now() - attempt.last_failure >= timedelta(minutes=15):
                db.session.delete(attempt)
                db.session.commit()
                attempt = None
            if attempt and attempt.failures >= 5:
                return render_template('error.html', message='Слишком много попыток. Повторите вход через 15 минут.'), 429
            user = db.session.scalar(db.select(User).filter_by(username=username))
            if user and user.active and check_password_hash(user.password_hash, request.form.get('password', '')[:256]):
                if attempt:
                    db.session.delete(attempt)
                    db.session.commit()
                login_user(user)
                session['auth_revision'] = hashlib.sha256(user.password_hash.encode()).hexdigest()
                session.permanent = True
                target = request.args.get('next', '')
                parsed = urlsplit(target)
                # Redirect only to normal paths on this application.
                if not target.startswith('/') or target.startswith('//') or '\\' in target or parsed.scheme or parsed.netloc:
                    target = url_for('part_list')
                return redirect(target)
            attempt = attempt or LoginAttempt(username=username, ip=ip, failures=0)
            attempt.failures += 1
            attempt.last_failure = now()
            db.session.add(attempt)
            db.session.commit()
            if attempt.failures >= 5:
                return render_template('error.html', message='Слишком много попыток. Повторите вход через 15 минут.'), 429
            flash('Неверный логин или пароль.')
        return render_template('login.html')

    @app.post('/accounts/logout/')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/accounts/password/', methods=['GET', 'POST'])
    @login_required
    def password_change():
        if request.method == 'POST':
            if not check_password_hash(current_user.password_hash, request.form.get('old', '')):
                raise ValueError('Текущий пароль неверен.')
            if request.form.get('new') != request.form.get('confirmation'):
                raise ValueError('Новые пароли не совпадают.')
            current_user.password_hash = password_hash(request.form.get('new', ''))
            db.session.commit()
            session['auth_revision'] = hashlib.sha256(current_user.password_hash.encode()).hexdigest()
            flash('Пароль изменён.')
            return redirect(url_for('part_list'))
        return render_template('form.html', title='Изменить пароль', fields=[field('old', 'Текущий пароль', kind='password'), field('new', 'Новый пароль', kind='password'), field('confirmation', 'Повторите новый пароль', kind='password')])

    @app.get('/')
    @login_required
    def part_list():
        query = db.select(Part).join(Manufacturer)
        q = request.args.get('q', '').strip()[:200]
        if q:
            conditions = [Part.name.contains(q, autoescape=True), Part.article.contains(q, autoescape=True), Manufacturer.name.contains(q, autoescape=True)]
            if normalize_article(q):
                conditions.append(Part.article_key.contains(normalize_article(q), autoescape=True))
            query = query.where(or_(*conditions))
        for name, column in [('manufacturer', Part.manufacturer_id), ('vehicle', Vehicle.id)]:
            value = request.args.get(name, '')
            if value.isdecimal():
                if name == 'vehicle':
                    query = query.join(Part.vehicles)
                query = query.where(column == int(value))
        if request.args.get('category'):
            query = query.where(Part.category == request.args['category'])
        query = query.order_by(Manufacturer.name, Part.article)
        page = db.paginate(query, per_page=25, max_per_page=25, error_out=False)
        totals = [db.session.scalar(db.select(func.count()).select_from(model)) for model in (Part, CrossReference, Analogue, Manufacturer)]
        filters = dict(request.args)
        filters.pop('page', None)
        return render_template('list.html', page=page, q=q, totals=totals, filters=filters,
            manufacturers=db.session.scalars(db.select(Manufacturer).order_by(Manufacturer.name)).all(),
            vehicles=db.session.scalars(db.select(Vehicle).order_by(Vehicle.make, Vehicle.model)).all(),
            categories=db.session.scalars(db.select(Part.category).distinct().where(Part.category != '').order_by(Part.category)).all())

    @app.get('/parts/<int:pk>/')
    @login_required
    def part_detail(pk):
        part = db.get_or_404(Part, pk)
        links = db.session.scalars(db.select(Analogue).where(or_(Analogue.part_a_id == pk, Analogue.part_b_id == pk))).all()
        refs = db.session.scalars(db.select(CrossReference).where(or_(CrossReference.source_part_id == pk, CrossReference.related_part_id == pk)).order_by(CrossReference.rate.desc())).all()
        return render_template('detail.html', part=part, links=links, references=refs)

    @app.route('/parts/new/', defaults={'pk': None}, methods=['GET', 'POST'])
    @app.route('/parts/<int:pk>/edit/', methods=['GET', 'POST'])
    @role_required()
    def part_edit(pk):
        part = db.get_or_404(Part, pk) if pk else Part()
        if request.method == 'POST':
            part.manufacturer = db.get_or_404(Manufacturer, int(request.form.get('manufacturer', '0')))
            part.article, part.name = required(request.form, 'article', 80), required(request.form, 'name', 200)
            for name, limit in [('category', 100), ('description', 16000), ('source', 255)]:
                value = request.form.get(name, '').strip()
                if len(value) > limit:
                    raise ValueError(f'Поле {name} слишком длинное.')
                setattr(part, name, value)
            vehicles = []
            for identity in request.form.getlist('vehicles'):
                vehicles.append(db.get_or_404(Vehicle, int(identity)))
            part.vehicles = vehicles
            db.session.add(part)
            db.session.commit()
            flash('Запчасть сохранена.')
            return redirect(url_for('part_detail', pk=part.id))
        fields = [field('manufacturer', 'Производитель', part.manufacturer_id or '', 'select', [(v.id, v.name) for v in db.session.scalars(db.select(Manufacturer).order_by(Manufacturer.name))]),
                  field('article', 'Артикул', part.article or ''), field('name', 'Название', part.name or ''),
                  field('category', 'Категория', part.category or '', required=False), field('description', 'Описание', part.description or '', 'textarea', required=False),
                  field('source', 'Источник', part.source or '', required=False),
                  field('vehicles', 'Автомобили (Ctrl для выбора нескольких)', [v.id for v in part.vehicles], 'multiple', [(v.id, str(v)) for v in db.session.scalars(db.select(Vehicle))], False)]
        return render_template('form.html', title='Редактировать запчасть' if pk else 'Новая запчасть', fields=fields)

    @app.route('/parts/<int:pk>/analogues/new/', methods=['GET', 'POST'])
    @role_required()
    def analogue_add(pk):
        db.get_or_404(Part, pk)
        if request.method == 'POST':
            other = db.get_or_404(Part, int(request.form.get('other', '0')))
            db.session.add(Analogue(part_a_id=pk, part_b_id=other.id, source=required(request.form, 'source'), note=request.form.get('note', '')[:16000], verified='verified' in request.form))
            db.session.commit()
            return redirect(url_for('part_detail', pk=pk))
        return render_template('form.html', title='Добавить аналог', fields=[field('other', 'Деталь-аналог', kind='select', choices=[(p.id, f'{p.manufacturer.name} {p.article} — {p.name}') for p in db.session.scalars(db.select(Part).where(Part.id != pk).order_by(Part.article))]), field('source', 'Источник'), field('note', 'Условия замены', kind='textarea', required=False), field('verified', 'Проверено специалистом', kind='checkbox', required=False)])

    @app.post('/analogues/<int:pk>/delete/')
    @role_required()
    def analogue_delete(pk):
        link = db.get_or_404(Analogue, pk)
        identity = link.part_a_id
        db.session.delete(link)
        db.session.commit()
        return redirect(url_for('part_detail', pk=identity))

    @app.route('/import/', methods=['GET', 'POST'])
    @role_required()
    def csv_import():
        if request.method == 'POST':
            upload = request.files.get('file')
            if not upload:
                raise ValueError('Выберите CSV-файл.')
            created, updated = import_csv(upload, request.form.get('kind'))
            db.session.commit()
            flash(f'Добавлено: {created}; обновлено: {updated}.')
            return redirect(url_for('part_list'))
        return render_template('import.html')

    @app.route('/manage/', methods=['GET', 'POST'])
    @role_required()
    def manage():
        if request.method == 'POST':
            if request.form.get('kind') == 'manufacturer':
                db.session.add(Manufacturer(name=required(request.form, 'name', 120)))
            elif request.form.get('kind') == 'vehicle':
                db.session.add(Vehicle(make=required(request.form, 'make', 80), model=required(request.form, 'model', 120), engine=request.form.get('engine', '')[:120], year_from=int(required(request.form, 'year_from', 4)), year_to=int(request.form['year_to']) if request.form.get('year_to') else None))
            else:
                raise ValueError('Неизвестное действие.')
            db.session.commit()
            flash('Запись добавлена.')
            return redirect(url_for('manage'))
        return render_template('manage.html', manufacturers=db.session.scalars(db.select(Manufacturer).order_by(Manufacturer.name)), vehicles=db.session.scalars(db.select(Vehicle).order_by(Vehicle.make)))

    @app.route('/admin/users/', methods=['GET', 'POST'])
    @role_required(admin=True)
    def users():
        if request.method == 'POST':
            username = required(request.form, 'username', 150)
            if not re.fullmatch(r'[\w.@+-]+', username):
                raise ValueError('Недопустимые символы в имени пользователя.')
            db.session.add(User(username=username, password_hash=password_hash(request.form.get('password', '')), staff='staff' in request.form, admin=False, active=True))
            db.session.commit()
            flash('Пользователь создан.')
            return redirect(url_for('users'))
        return render_template('users.html', users=db.session.scalars(db.select(User).order_by(User.username)))

    @app.route('/admin/users/<int:pk>/', methods=['GET', 'POST'])
    @role_required(admin=True)
    def user_edit(pk):
        user = db.get_or_404(User, pk)
        if request.method == 'POST':
            if user.id == current_user.id and ('active' not in request.form or 'admin' not in request.form):
                raise ValueError('Нельзя отключить свою административную учётную запись.')
            user.active, user.admin = 'active' in request.form, 'admin' in request.form
            user.staff = user.admin or 'staff' in request.form
            if request.form.get('password'):
                user.password_hash = password_hash(request.form['password'])
                db.session.query(LoginAttempt).filter_by(username=user.username).delete()
            db.session.commit()
            return redirect(url_for('users'))
        return render_template('form.html', title=f'Пользователь {user.username}', fields=[field('password', 'Новый пароль (оставьте пустым для сохранения)', kind='password', required=False), field('active', 'Активен', user.active, 'checkbox', required=False), field('staff', 'Редактирует каталог', user.staff, 'checkbox', required=False), field('admin', 'Управляет пользователями', user.admin, 'checkbox', required=False)])

    return app
