# app/__init__.py
# Flask 應用程式工廠

import os
from flask import Flask
from flask_login import LoginManager
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from app.models import db, User
from config import config


login_manager = LoginManager()
jwt = JWTManager()
migrate = Migrate()


def create_app(config_name=None):
    """應用程式工廠函數"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # 載入配置
    app.config.from_object(config[config_name])

    # 初始化擴展
    db.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    # 設定 login_manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '請先登入'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # JWT 配置
    @jwt.user_identity_loader
    def user_identity_lookup(user):
        if isinstance(user, str):
            return user
        return user.username

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return User.query.filter_by(username=identity).first()

    # 確保上傳目錄存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'tax_ai_ocr'), exist_ok=True)

    # 註冊藍圖
    from app.routes import main_bp, auth_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    # 建立資料庫表格（開發用）
    with app.app_context():
        db.create_all()

    return app
