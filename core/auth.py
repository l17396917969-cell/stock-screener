import os
import time
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db
from .models import User

auth_bp = Blueprint('auth', __name__)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user_row = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        
        if user_row and check_password_hash(user_row['password_hash'], password):
            if not user_row['is_active']:
                flash('账号已被禁用', 'error')
                return render_template('login.html')
            
            user = User(user_row['id'], user_row['username'], user_row['is_admin'], user_row['is_active'], user_row['must_change_password'])
            login_user(user)
            
            db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (time.time(), user.id))
            db.commit()
            
            return redirect(url_for('index'))
        
        flash('用户名或密码错误', 'error')
        
    return render_template('login.html')

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

def init_admin():
    """Initialize admin user if no users exist."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    if count == 0:
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        password_hash = generate_password_hash(admin_password)
        
        db.execute(
            "INSERT INTO users (username, password_hash, is_active, is_admin, must_change_password, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ('admin', password_hash, 1, 1, 1, time.time())
        )
        db.commit()
        current_app.logger.info("Admin user initialized.")
