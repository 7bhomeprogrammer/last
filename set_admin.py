"""Запусти один раз: python set_admin.py — пользователь Azat станет админом с золотой галочкой."""
from app import db, User, app

with app.app_context():
    me = User.query.filter_by(username='Azat').first()
    if me:
        me.is_admin = True
        me.is_verified = True
        me.verification_type = 'gold'
        db.session.commit()
        print("Azat теперь админ с золотой галочкой.")
    else:
        print("Пользователь с ником Azat не найден. Создай его через регистрацию, затем снова запусти этот скрипт.")
