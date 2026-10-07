import re
import unicodedata
from datetime import datetime, timezone
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_article(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value)).upper()


class User(UserMixin, db.Model):
    __tablename__ = 'compat_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    staff = db.Column(db.Boolean, nullable=False, default=False)
    admin = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def is_active(self):
        return self.active


class LoginAttempt(db.Model):
    __tablename__ = 'compat_login_attempts'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    ip = db.Column(db.String(45), nullable=False)
    failures = db.Column(db.Integer, nullable=False, default=0)
    last_failure = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (db.UniqueConstraint('username', 'ip'),)


class Manufacturer(db.Model):
    __tablename__ = 'compat_manufacturers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


part_vehicles = db.Table('compat_part_vehicles',
    db.Column('part_id', db.Integer, db.ForeignKey('compat_parts.id', ondelete='CASCADE'), primary_key=True),
    db.Column('vehicle_id', db.Integer, db.ForeignKey('compat_vehicles.id', ondelete='CASCADE'), primary_key=True))


class Vehicle(db.Model):
    __tablename__ = 'compat_vehicles'
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(120), nullable=False)
    engine = db.Column(db.String(120), nullable=False, default='')
    year_from = db.Column(db.Integer, nullable=False)
    year_to = db.Column(db.Integer)

    def __str__(self):
        return f'{self.make} {self.model} · {self.engine} · {self.year_from}–{self.year_to or "н.в."}'


class Part(db.Model):
    __tablename__ = 'compat_parts'
    id = db.Column(db.Integer, primary_key=True)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('compat_manufacturers.id'), nullable=False)
    manufacturer = db.relationship(Manufacturer, lazy='joined')
    article = db.Column(db.String(80), nullable=False)
    article_key = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False, default='')
    description = db.Column(db.Text, nullable=False, default='')
    source = db.Column(db.String(255), nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=now, onupdate=now, nullable=False)
    vehicles = db.relationship(Vehicle, secondary=part_vehicles)
    __table_args__ = (db.UniqueConstraint('manufacturer_id', 'article_key'),)


class Analogue(db.Model):
    __tablename__ = 'compat_analogues'
    id = db.Column(db.Integer, primary_key=True)
    part_a_id = db.Column(db.Integer, db.ForeignKey('compat_parts.id', ondelete='CASCADE'), nullable=False)
    part_b_id = db.Column(db.Integer, db.ForeignKey('compat_parts.id', ondelete='CASCADE'), nullable=False)
    part_a = db.relationship(Part, foreign_keys=[part_a_id], lazy='joined')
    part_b = db.relationship(Part, foreign_keys=[part_b_id], lazy='joined')
    source = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text, nullable=False, default='')
    verified = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint('part_a_id', 'part_b_id'),)


class CrossReference(db.Model):
    __tablename__ = 'compat_references'
    id = db.Column(db.Integer, primary_key=True)
    source_part_id = db.Column(db.Integer, db.ForeignKey('compat_parts.id', ondelete='CASCADE'), nullable=False)
    related_part_id = db.Column(db.Integer, db.ForeignKey('compat_parts.id', ondelete='CASCADE'), nullable=False)
    source_part = db.relationship(Part, foreign_keys=[source_part_id], lazy='joined')
    related_part = db.relationship(Part, foreign_keys=[related_part_id], lazy='joined')
    relation_code = db.Column(db.String(80), nullable=False)
    relation_name = db.Column(db.String(120), nullable=False)
    direction = db.Column(db.String(16), nullable=False)
    weight = db.Column(db.Numeric(16, 6))
    rate = db.Column(db.Numeric(12, 4))
    last_seen_at = db.Column(db.DateTime)
    source = db.Column(db.String(255), nullable=False)
    __table_args__ = (db.UniqueConstraint('source_part_id', 'related_part_id', 'relation_code', 'direction'),)


@event.listens_for(Part, 'before_insert')
@event.listens_for(Part, 'before_update')
def validate_part(mapper, connection, part):
    part.article_key = normalize_article(part.article)
    if not part.article_key or len(part.article_key) > 80:
        raise ValueError('Артикул должен содержать буквы или цифры (до 80 символов).')


@event.listens_for(Analogue, 'before_insert')
@event.listens_for(Analogue, 'before_update')
def validate_analogue(mapper, connection, link):
    if link.part_a_id == link.part_b_id:
        raise ValueError('Нельзя связать деталь с самой собой.')
    link.part_a_id, link.part_b_id = sorted([link.part_a_id, link.part_b_id])


@event.listens_for(Vehicle, 'before_insert')
@event.listens_for(Vehicle, 'before_update')
def validate_vehicle(mapper, connection, vehicle):
    if not 1900 <= vehicle.year_from <= 2100 or (vehicle.year_to and not vehicle.year_from <= vehicle.year_to <= 2100):
        raise ValueError('Проверьте диапазон годов выпуска.')


@event.listens_for(CrossReference, 'before_insert')
@event.listens_for(CrossReference, 'before_update')
def validate_reference(mapper, connection, ref):
    if ref.direction not in ('forward', 'reverse'):
        raise ValueError('Направление должно быть forward или reverse.')
