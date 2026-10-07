import os
from pathlib import Path
from sqlalchemy import func, text
from .app import create_app, password_hash
from .models import db, User, Part, Manufacturer, CrossReference
from .importers import import_csv

app = create_app()
with app.app_context():
    version = db.session.execute(text('SELECT VERSION()')).scalar()
    print('MySQL server:', version)
    db.create_all()
    username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
    if not db.session.scalar(db.select(User).filter_by(username=username)):
        db.session.add(User(username=username, password_hash=password_hash(os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')), admin=True, staff=True, active=True))
        db.session.commit()
        print('Administrator created; password was not logged.')
    if not db.session.scalar(db.select(func.count()).select_from(CrossReference)):
        with (Path(__file__).resolve().parent.parent/'data/example.csv').open('rb') as file:
            created, updated = import_csv(file, 'references')
        db.session.commit()
        print('Imported references:', created, 'updated:', updated)
    else:
        print('Existing catalogue and accounts preserved.')
    print('Parts:', db.session.scalar(db.select(func.count()).select_from(Part)),
          'Manufacturers:', db.session.scalar(db.select(func.count()).select_from(Manufacturer)),
          'References:', db.session.scalar(db.select(func.count()).select_from(CrossReference)))
