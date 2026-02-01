import os
import sys

import re
import random
import string
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import or_, and_
from markupsafe import Markup, escape
from urllib.parse import quote

app = Flask(__name__)
app.config['SECRET_KEY'] = 'azayuur_secret_key_2026'    
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///azaunur.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/avatars'
app.config['UPLOAD_FOLDER_POSTS'] = 'static/uploads/posts'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_POSTS'], exist_ok=True)

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(200), default='default.jpg')
    bio = db.Column(db.String(500), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_type = db.Column(db.String(20), nullable=True)  # gold, vip, exclusive
    custom_status = db.Column(db.String(100), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    banned_until = db.Column(db.DateTime, nullable=True)

    def is_banned(self):
        return self.banned_until and self.banned_until > datetime.utcnow()

    def followers_count(self):
        return Follow.query.filter_by(following_id=self.id).count()

    def following_count(self):
        return Follow.query.filter_by(follower_id=self.id).count()

    def posts_count(self):
        return Post.query.filter_by(user_id=self.id).count()


class VerificationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')
    user = db.relationship('User', backref=db.backref('verification_requests', lazy='dynamic'))


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', backref=db.backref('posts', lazy='dynamic'))

    def likes_count(self):
        return PostLike.query.filter_by(post_id=self.id).count()

    def comments_count(self):
        return Comment.query.filter_by(post_id=self.id).count()

    def reposts_count(self):
        return Repost.query.filter_by(post_id=self.id).count()

    def views_count(self):
        return PostView.query.filter_by(post_id=self.id).count()

    def ordered_comments(self):
        return self.comments.order_by(Comment.created_at.asc()).all()


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    following_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('follower_id', 'following_id', name='uq_follow'),)


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_post_like'),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    post = db.relationship('Post', backref=db.backref('comments', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))

    def likes_count(self):
        return CommentLike.query.filter_by(comment_id=self.id).count()


class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='uq_comment_like'),)


class Repost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    post = db.relationship('Post', backref=db.backref('reposts', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('reposts', lazy='dynamic'))
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_repost'),)


class PostView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='uq_post_view'),)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    type = db.Column(db.String(30), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    from_user = db.relationship('User', foreign_keys=[from_user_id])


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reporter = db.relationship('User', foreign_keys=[reporter_id])
    reported = db.relationship('User', foreign_keys=[reported_id])


class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('blocker_id', 'blocked_id', name='uq_block'),)


class SavedPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_saved_post'),)


class EmailVerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


class PasswordResetCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


# Предустановленные статусы (админ выбирает из списка или вводит свой)
PREDEFINED_STATUSES = [
    'Пикми', 'Король', 'Королева', 'Легенда', 'Икона', 'Звезда', 'Огонь', 'Топ',
    'Меньше слов – больше дела', 'Делай, что любишь', 'Время – лучший судья',
    'Главное то, что внутри', 'Дорогу осилит идущий', 'Живи сейчас',
    'Улыбка лечит быстрее слов', 'Свобода начинается внутри', 'Учись прощать',
    'Каждый миг неповторим', 'Ты – главный герой своей жизни', 'Всё пройдёт, и это тоже',
    'Aynura', 'Отарбай', 'Мужик', 'Женщина', 'Троль', 'Дракон', 'Кентавр', 'Эльф', 'Гоблин', 'Орк', 'Тролль', 'Демон', 'Дракон', 'Кентавр', 'Эльф', 'Гоблин', 'Орк', 'Тролль', 'Демон', 'Дракон', 'Кентавр', 'Эльф', 'Гоблин', 'Орк', 'Тролль', 'Демон',
]


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}


def notify(user_id, from_user_id, ntype, post_id=None, comment_id=None):
    if user_id == from_user_id:
        return
    n = Notification(user_id=user_id, from_user_id=from_user_id, type=ntype, post_id=post_id, comment_id=comment_id)
    db.session.add(n)


def get_blocked_user_ids(user_id):
    """Возвращает set id пользователей, с которыми user_id не должен видеть контент друг друга (кто кого заблокировал)."""
    blocked_by_me = {b.blocked_id for b in Block.query.filter_by(blocker_id=user_id).all()}
    blocked_me = {b.blocker_id for b in Block.query.filter_by(blocked_id=user_id).all()}
    return blocked_by_me | blocked_me


def is_blocked(viewer_id, target_id):
    if viewer_id == target_id:
        return False
    return (Block.query.filter_by(blocker_id=viewer_id, blocked_id=target_id).first() is not None or
            Block.query.filter_by(blocker_id=target_id, blocked_id=viewer_id).first() is not None)



    

    # T: подключить SMTP (flask-mail или smtplib) по app.config.get('MAIL_SERVER')


def linkify_post(text):
    """Делает #тег и @username кликабельными ссылками. Возвращает Markup (безопасно для вывода в шаблоне)."""
    if not text:
        return Markup('')
    text = escape(text)
    def repl_hashtag(m):
        tag = m.group(1)
        return f'<a href="/tag/{quote(tag)}" class="hashtag">#{tag}</a>'
    text = re.sub(r'#([a-zA-Zа-яА-ЯёЁ0-9_]+)', repl_hashtag, text)
    text = re.sub(r'@([a-zA-Z0-9_]+)', r'<a href="/u/\1" class="mention">@\1</a>', text)
    return Markup(text)


def extract_mentions(text):
    """Извлекает список username из текста (упоминания @username)."""
    return list(set(re.findall(r'@([a-zA-Z0-9_]+)', text)))


def notify_mentions(text, from_user_id, post_id=None, comment_id=None):
    for username in extract_mentions(text):
        u = User.query.filter_by(username=username).first()
        if u and u.id != from_user_id:
            notify(u.id, from_user_id, 'mention', post_id=post_id, comment_id=comment_id)


# --- ROUTES ---
@app.route('/')
@login_required
def index():
    if request.method == 'POST':
        body = (request.form.get('body') or '').strip()
        if not body:
            flash('Введите текст поста')
            return redirect(url_for('index'))
        post = Post(user_id=current_user.id, body=body)
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                try:
                    filename = f"post_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER_POSTS'], filename)
                    img = Image.open(file)
                    img = img.convert('RGB')
                    img.thumbnail((1200, 1200))
                    img.save(filepath, 'JPEG', quality=85)
                    post.image = filename
                except Exception:
                    pass
        db.session.add(post)
        db.session.commit()
        notify_mentions(body, current_user.id, post_id=post.id)
        db.session.commit()
        return redirect(url_for('index'))

    blocked_ids = get_blocked_user_ids(current_user.id)
    all_posts = Post.query.order_by(Post.created_at.desc()).all()
    all_reposts = Repost.query.order_by(Repost.created_at.desc()).all()
    feed_items = []
    for p in all_posts:
        if p.user_id not in blocked_ids:
            feed_items.append(('post', p, None))
    for r in all_reposts:
        if r.user_id not in blocked_ids and r.post.user_id not in blocked_ids:
            feed_items.append(('repost', r.post, r))
    feed_items.sort(key=lambda x: x[1].created_at if x[0] == 'post' else x[2].created_at, reverse=True)

    for item in feed_items:
        p = item[1]
        if PostView.query.filter_by(post_id=p.id, user_id=current_user.id).first() is None:
            db.session.add(PostView(post_id=p.id, user_id=current_user.id))
    db.session.commit()

    post_ids = [item[1].id for item in feed_items]
    liked = {r.post_id for r in PostLike.query.filter(PostLike.post_id.in_(post_ids), PostLike.user_id == current_user.id).all()}
    reposted = {r.post_id for r in Repost.query.filter(Repost.post_id.in_(post_ids), Repost.user_id == current_user.id).all()}
    saved = {s.post_id for s in SavedPost.query.filter(SavedPost.post_id.in_(post_ids), SavedPost.user_id == current_user.id).all()} if post_ids else set()
    return render_template('index.html', feed_items=feed_items, liked=liked, reposted=reposted, saved=saved)


@app.route('/post/<int:post_id>/view')
@login_required
def post_view(post_id):
    post = Post.query.get_or_404(post_id)
    existing = PostView.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if not existing:
        db.session.add(PostView(post_id=post_id, user_id=current_user.id))
        db.session.commit()
    return '', 204


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def post_like(post_id):
    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if like:
        db.session.delete(like)
        db.session.commit()
        return jsonify({'liked': False, 'count': post.likes_count()})
    db.session.add(PostLike(post_id=post_id, user_id=current_user.id))
    notify(post.user_id, current_user.id, 'like', post_id=post_id)
    db.session.commit()
    return jsonify({'liked': True, 'count': post.likes_count()})


@app.route('/post/<int:post_id>/repost', methods=['POST'])
@login_required
def post_repost(post_id):
    post = Post.query.get_or_404(post_id)
    r = Repost.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if r:
        db.session.delete(r)
        db.session.commit()
        return jsonify({'reposted': False, 'count': post.reposts_count()})
    db.session.add(Repost(post_id=post_id, user_id=current_user.id))
    notify(post.user_id, current_user.id, 'repost', post_id=post_id)
    db.session.commit()
    return jsonify({'reposted': True, 'count': post.reposts_count()})


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def post_comment(post_id):
    post = Post.query.get_or_404(post_id)
    body = (request.form.get('body') or '').strip()
    if not body:
        return redirect(url_for('index'))
    c = Comment(post_id=post_id, user_id=current_user.id, body=body)
    db.session.add(c)
    db.session.commit()
    notify(post.user_id, current_user.id, 'comment', post_id=post_id, comment_id=c.id)
    notify_mentions(body, current_user.id, post_id=post_id, comment_id=c.id)
    db.session.commit()
    return redirect(request.referrer or url_for('index'))


@app.route('/comment/<int:comment_id>/like', methods=['POST'])
@login_required
def comment_like(comment_id):
    c = Comment.query.get_or_404(comment_id)
    like = CommentLike.query.filter_by(comment_id=comment_id, user_id=current_user.id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(CommentLike(comment_id=comment_id, user_id=current_user.id))
    db.session.commit()
    return jsonify({'count': c.likes_count()})


@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        return redirect(request.referrer or url_for('index'))
    if is_blocked(current_user.id, target.id):
        return jsonify({'error': 'blocked'}), 403
    f = Follow.query.filter_by(follower_id=current_user.id, following_id=target.id).first()
    if f:
        db.session.delete(f)
        db.session.commit()
        return jsonify({'following': False})
    db.session.add(Follow(follower_id=current_user.id, following_id=target.id))
    notify(target.id, current_user.id, 'follow')
    db.session.commit()
    return jsonify({'following': True})


@app.route('/tag/<path:tag>')
@login_required
def tag_page(tag):
    blocked_ids = get_blocked_user_ids(current_user.id)
    posts = Post.query.filter(Post.body.ilike(f'%#{tag}%')).order_by(Post.created_at.desc()).limit(100).all()
    posts = [p for p in posts if p.user_id not in blocked_ids]
    post_ids = [p.id for p in posts]
    liked = {r.post_id for r in PostLike.query.filter(PostLike.post_id.in_(post_ids), PostLike.user_id == current_user.id).all()} if post_ids else set()
    reposted = {r.post_id for r in Repost.query.filter(Repost.post_id.in_(post_ids), Repost.user_id == current_user.id).all()} if post_ids else set()
    saved = {s.post_id for s in SavedPost.query.filter(SavedPost.post_id.in_(post_ids), SavedPost.user_id == current_user.id).all()} if post_ids else set()
    feed_items = [('post', p, None) for p in posts]
    return render_template('tag.html', tag=tag, feed_items=feed_items, liked=liked, reposted=reposted, saved=saved)


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        return "Access Denied", 403
    if request.method == 'POST':
        body = (request.form.get('body') or '').strip()
        if not body:
            flash('Введите текст')
            return redirect(request.referrer or url_for('index'))
        post.body = body
        post.edited_at = datetime.utcnow()
        db.session.commit()
        flash('Пост обновлён')
        return redirect(request.referrer or url_for('index'))
    return render_template('edit_post.html', post=post)


@app.route('/post/<int:post_id>/save', methods=['POST'])
@login_required
def save_post(post_id):
    post = Post.query.get_or_404(post_id)
    s = SavedPost.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    if s:
        db.session.delete(s)
        db.session.commit()
        return jsonify({'saved': False})
    db.session.add(SavedPost(post_id=post_id, user_id=current_user.id))
    db.session.commit()
    return jsonify({'saved': True})


@app.route('/saved')
@login_required
def saved():
    saved_list = SavedPost.query.filter_by(user_id=current_user.id).order_by(SavedPost.created_at.desc()).all()
    saved_ids = [s.post_id for s in saved_list]
    posts = Post.query.filter(Post.id.in_(saved_ids)).all() if saved_ids else []
    order = {pid: i for i, pid in enumerate(saved_ids)}
    posts.sort(key=lambda p: order.get(p.id, 999))
    post_ids = [p.id for p in posts]
    liked = {r.post_id for r in PostLike.query.filter(PostLike.post_id.in_(post_ids), PostLike.user_id == current_user.id).all()} if post_ids else set()
    reposted = {r.post_id for r in Repost.query.filter(Repost.post_id.in_(post_ids), Repost.user_id == current_user.id).all()} if post_ids else set()
    saved = set(post_ids)
    feed_items = [('post', p, None) for p in posts]
    return render_template('saved.html', feed_items=feed_items, liked=liked, reposted=reposted, saved=saved)


@app.route('/comment/<int:comment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_comment_page(comment_id):
    c = Comment.query.get_or_404(comment_id)
    if c.user_id != current_user.id and not current_user.is_admin:
        return "Access Denied", 403
    if request.method == 'POST':
        body = (request.form.get('body') or '').strip()
        if body:
            c.body = body
            c.edited_at = datetime.utcnow()
            db.session.commit()
        return redirect(request.referrer or url_for('index'))
    return render_template('edit_comment.html', comment=c)


@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    c = Comment.query.get_or_404(comment_id)
    if c.user_id != current_user.id and not current_user.is_admin:
        return "Access Denied", 403
    for cl in CommentLike.query.filter_by(comment_id=comment_id).all():
        db.session.delete(cl)
    db.session.delete(c)
    db.session.commit()
    flash('Комментарий удалён')
    return redirect(request.referrer or url_for('index'))


@app.route('/block/<int:user_id>', methods=['POST'])
@login_required
def block_user(user_id):
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        return redirect(request.referrer or url_for('index'))
    b = Block.query.filter_by(blocker_id=current_user.id, blocked_id=target.id).first()
    if b:
        db.session.delete(b)
        db.session.commit()
        return jsonify({'blocked': False})
    db.session.add(Block(blocker_id=current_user.id, blocked_id=target.id))
    db.session.commit()
    return jsonify({'blocked': True})


@app.route('/search')
@login_required
def search():
    q = (request.args.get('q') or '').strip()
    users = []
    posts = []
    if q:
        if q.startswith('#'):
            tag = q[1:].lower()
            posts = Post.query.filter(Post.body.ilike(f'%#{tag}%')).order_by(Post.created_at.desc()).limit(50).all()
        else:
            users = User.query.filter(User.username.ilike(f'%{q}%')).limit(30).all()
            posts = Post.query.filter(Post.body.ilike(f'%{q}%')).order_by(Post.created_at.desc()).limit(30).all()
    return render_template('search.html', q=q or '', users=users, posts=posts)


@app.route('/notifications')
@login_required
def notifications():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return render_template('notifications.html', notifications=items)


@app.route('/chats')
@login_required
def chats():
    blocked_ids = get_blocked_user_ids(current_user.id)
    msgs = Message.query.filter(
        or_(Message.sender_id == current_user.id, Message.receiver_id == current_user.id)
    ).order_by(Message.created_at.desc()).all()
    seen = set()
    convos = []
    for m in msgs:
        pid = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        if pid not in seen and pid not in blocked_ids:
            seen.add(pid)
            convos.append((User.query.get(pid), m))
    return render_template('chats.html', convos=convos)


@app.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    peer = User.query.get_or_404(user_id)
    if is_blocked(current_user.id, peer.id):
        flash('Чат недоступен')
        return redirect(url_for('chats'))
    if request.method == 'POST':
        body = (request.form.get('body') or '').strip()
        if body:
            db.session.add(Message(sender_id=current_user.id, receiver_id=user_id, body=body))
            db.session.commit()
        return redirect(url_for('chat', user_id=user_id))
    messages = Message.query.filter(
        or_(
            and_(Message.sender_id == current_user.id, Message.receiver_id == user_id),
            and_(Message.sender_id == user_id, Message.receiver_id == current_user.id)
    )).order_by(Message.created_at.asc()).all()
    return render_template('chat.html', peer=peer, messages=messages)


def _generate_code():
    return ''.join(random.choices(string.digits, k=6))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')  # убедись, что в форме есть это поле
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not email or not password:
            flash('Заполните все поля')
            return render_template('register.html')

        # Проверка на существующего пользователя
        if User.query.filter((User.email == email) | (User.username == username)).first():
            flash('Пользователь уже существует')
            return render_template('register.html')

        # Если хочешь оставлять пароль без хэширования (не безопасно)
        new_user = User(
            username=username,
            email=email,
            password=password,  # здесь лучше generate_password_hash(password)
            avatar='default.jpg'
        )

        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация прошла успешно!')
        return redirect(url_for('login'))  # Важно вернуть redirect

    return render_template('register.html')  # Это на случай GET-запроса








@app.route('/reset', methods=['GET', 'POST'])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if 'reset_email' not in session:
        flash('Сначала укажите email')
        return redirect(url_for('forgot_password'))
    email = session['reset_email']
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        new_password = request.form.get('password')
        if not code or not new_password:
            flash('Введите код и новый пароль')
            return redirect(url_for('reset_password'))
        row = PasswordResetCode.query.filter_by(email=email, code=code).first()
        if not row or row.expires_at < datetime.utcnow():
            flash('Неверный или устаревший код')
            return redirect(url_for('reset_password'))
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            PasswordResetCode.query.filter_by(email=email).delete()
            db.session.commit()
        session.pop('reset_email', None)
        flash('Пароль обновлён. Войдите.')
        return redirect(url_for('login'))
    return render_template('reset_password.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Неверный email или пароль')
            return render_template('login.html')

        # Если пароль хранится в открытом виде (не безопасно):
        if user.password != password:
            flash('Неверный email или пароль')
            return render_template('login.html')

        # Если пользователь забанен
        if getattr(user, 'banned_until', None):
            if user.banned_until and user.banned_until > datetime.utcnow():
                flash(f'Аккаунт заблокирован до {user.banned_until.strftime("%d.%m.%Y %H:%M")}')
                return render_template('login.html')

        login_user(user)
        flash('Вы успешно вошли!')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.before_request
def check_banned():
    if current_user.is_authenticated and getattr(current_user, 'banned_until', None) and current_user.banned_until and current_user.banned_until > datetime.utcnow():
        from flask_login import logout_user
        logout_user()
        flash('Ваш аккаунт заблокирован. Ожидайте окончания блокировки.')
        return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/u/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    if is_blocked(current_user.id, user.id):
        flash('Профиль недоступен')
        return redirect(url_for('index'))
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    is_following = Follow.query.filter_by(follower_id=current_user.id, following_id=user.id).first() is not None
    is_blocking = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user.id).first() is not None
    post_ids = [p.id for p in posts]
    liked = {r.post_id for r in PostLike.query.filter(PostLike.post_id.in_(post_ids), PostLike.user_id == current_user.id).all()} if post_ids else set()
    reposted = {r.post_id for r in Repost.query.filter(Repost.post_id.in_(post_ids), Repost.user_id == current_user.id).all()} if post_ids else set()
    saved = {s.post_id for s in SavedPost.query.filter(SavedPost.post_id.in_(post_ids), SavedPost.user_id == current_user.id).all()} if post_ids else set()
    return render_template('profile.html', user=user, posts=posts, is_following=is_following, is_blocking=is_blocking, liked=liked, reposted=reposted, saved=saved)


@app.route('/u/<username>/followers')
@login_required
def followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    fol = Follow.query.filter_by(following_id=user.id).all()
    users = [User.query.get(f.follower_id) for f in fol]
    following_ids = {f.following_id for f in Follow.query.filter_by(follower_id=current_user.id).all()}
    return render_template('follow_list.html', title='Подписчики', user=user, users=users, following_ids=following_ids)


@app.route('/u/<username>/following')
@login_required
def following(username):
    user = User.query.filter_by(username=username).first_or_404()
    fol = Follow.query.filter_by(follower_id=user.id).all()
    users = [User.query.get(f.following_id) for f in fol]
    following_ids = {f.following_id for f in Follow.query.filter_by(follower_id=current_user.id).all()}
    return render_template('follow_list.html', title='Подписки', user=user, users=users, following_ids=following_ids)


@app.route('/report/<int:user_id>', methods=['POST'])
@login_required
def report_user(user_id):
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        return redirect(request.referrer or url_for('index'))
    reason = (request.form.get('reason') or '').strip()
    db.session.add(Report(reporter_id=current_user.id, reported_id=target.id, reason=reason))
    db.session.commit()
    flash('Жалоба отправлена')
    return redirect(request.referrer or url_for('profile', username=target.username))


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and not current_user.is_admin:
        return "Access Denied", 403
    for c in list(post.comments.all()):
        for cl in CommentLike.query.filter_by(comment_id=c.id).all():
            db.session.delete(cl)
        db.session.delete(c)
    for pl in PostLike.query.filter_by(post_id=post_id).all():
        db.session.delete(pl)
    for r in Repost.query.filter_by(post_id=post_id).all():
        db.session.delete(r)
    for pv in PostView.query.filter_by(post_id=post_id).all():
        db.session.delete(pv)
    db.session.delete(post)
    db.session.commit()
    flash('Пост удалён')
    return redirect(request.referrer or url_for('index'))


@app.route('/admin/grant_verification/<int:user_id>/<v_type>')
@login_required
def admin_grant_verification(user_id, v_type):
    if not current_user.is_admin:
        return "Access Denied", 403
    user = User.query.get_or_404(user_id)
    if v_type == 'none':
        user.is_verified = False
        user.verification_type = None
    else:
        user.is_verified = True
        user.verification_type = v_type  # vip, exclusive, gold
    db.session.commit()
    return redirect(request.referrer or url_for('profile', username=user.username))


@app.route('/admin/grant_admin/<int:user_id>')
@login_required
def admin_grant_admin(user_id):
    if not current_user.is_admin:
        return "Access Denied", 403
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    flash('Права админа обновлены' if user.is_admin else 'Админка снята')
    return redirect(request.referrer or url_for('profile', username=user.username))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        user = User.query.get(current_user.id)
        user.bio = request.form.get('bio')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename and allowed_file(file.filename):
                try:
                    filename = f"user_{user.id}.jpg"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    img = Image.open(file)
                    img = img.convert('RGB')
                    img.thumbnail((400, 400))
                    img.save(filepath, 'JPEG', quality=90)
                    user.avatar = filename
                except Exception:
                    flash('Не удалось загрузить фото')
        db.session.commit()
        return redirect(url_for('profile', username=user.username))
    pending = VerificationRequest.query.filter_by(user_id=current_user.id, status='pending').first()
    return render_template('settings.html', pending=pending)


@app.route('/request_verification', methods=['POST'])
@login_required
def request_verification():
    reason = (request.form.get('reason') or '').strip()
    existing = VerificationRequest.query.filter_by(user_id=current_user.id, status='pending').first()
    if not existing:
        db.session.add(VerificationRequest(user_id=current_user.id, reason=reason))
        db.session.commit()
        flash('Заявка на верификацию отправлена')
    else:
        flash('У вас уже есть активная заявка')
    return redirect(url_for('settings'))


@app.route('/admin/requests')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Access Denied", 403
    requests = VerificationRequest.query.filter_by(status='pending').order_by(VerificationRequest.id.desc()).all()
    return render_template('admin.html', requests=requests)


@app.route('/admin/verify/<int:request_id>/<v_type>')
@login_required
def verify_user(request_id, v_type):
    if not current_user.is_admin:
        return "Access Denied", 403
    req = VerificationRequest.query.get_or_404(request_id)
    user = User.query.get(req.user_id)
    user.is_verified = True
    user.verification_type = v_type
    req.status = 'approved'
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/reject/<int:request_id>')
@login_required
def reject_verification(request_id):
    if not current_user.is_admin:
        return "Access Denied", 403
    req = VerificationRequest.query.get_or_404(request_id)
    req.status = 'rejected'
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/set_status/<int:user_id>', methods=['POST'])
@login_required
def admin_set_status(user_id):
    if not current_user.is_admin:
        return "Access Denied", 403
    user = User.query.get_or_404(user_id)
    user.custom_status = (request.form.get('custom_status') or '').strip() or None
    db.session.commit()
    return redirect(request.referrer or url_for('admin_panel'))


@app.route('/admin/reports')
@login_required
def admin_reports():
    if not current_user.is_admin:
        return "Access Denied", 403
    reports = Report.query.filter_by(status='pending').order_by(Report.created_at.desc()).all()
    return render_template('admin_reports.html', reports=reports)


@app.route('/admin/report/forgive/<int:report_id>')
@login_required
def admin_report_forgive(report_id):
    if not current_user.is_admin:
        return "Access Denied", 403
    r = Report.query.get_or_404(report_id)
    r.status = 'forgiven'
    db.session.commit()
    flash('Жалоба отклонена (прощено)')
    return redirect(url_for('admin_reports'))


@app.route('/admin/report/ban/<int:report_id>')
@login_required
def admin_report_ban(report_id):
    if not current_user.is_admin:
        return "Access Denied", 403
    r = Report.query.get_or_404(report_id)
    r.status = 'banned'
    user = User.query.get(r.reported_id)
    user.banned_until = datetime.utcnow() + timedelta(hours=5)
    db.session.commit()
    flash(f'Пользователь {user.username} заблокирован на 5 часов')
    return redirect(url_for('admin_reports'))

@app.route('/admin/stats')
@login_required
def admin_stats():
    if not current_user.is_admin:
        return "Access Denied", 403

    total_users = User.query.count()
    total_posts = Post.query.count()
    total_comments = Comment.query.count()
    total_messages = Message.query.count()
    active_today = User.query.filter(User.id.in_(
        [p.user_id for p in Post.query.filter(Post.created_at >= datetime.utcnow() - timedelta(days=1)).all()]
    )).count()

    return render_template('stats.html', total_users=total_users, total_posts=total_posts,
                           total_comments=total_comments, total_messages=total_messages,
                           active_today=active_today)



def time_ago(dt):
    if not dt:
        return ''
    delta = datetime.utcnow() - dt
    if delta.days > 365:
        return f'{delta.days // 365} г назад'
    if delta.days > 30:
        return f'{delta.days // 30} мес назад'
    if delta.days > 0:
        return f'{delta.days} дн назад'
    if delta.seconds >= 3600:
        return f'{delta.seconds // 3600} ч назад'
    if delta.seconds >= 60:
        return f'{delta.seconds // 60} мин назад'
    return 'только что'

app.jinja_env.filters['time_ago'] = time_ago
app.jinja_env.filters['linkify'] = linkify_post


@app.context_processor
def inject_globals():
    d = {'predefined_statuses': PREDEFINED_STATUSES}
    if current_user.is_authenticated:
        d['notifications_count'] = min(Notification.query.filter_by(user_id=current_user.id, read=False).count(), 99)
    else:
        d['notifications_count'] = 0
    return d


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE verification_request ADD COLUMN reason TEXT'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE user ADD COLUMN custom_status VARCHAR(100)'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE user ADD COLUMN banned_until DATETIME'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE post ADD COLUMN edited_at DATETIME'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            from sqlalchemy import text
            db.session.execute(text('ALTER TABLE comment ADD COLUMN edited_at DATETIME'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    app.run(debug=True)
