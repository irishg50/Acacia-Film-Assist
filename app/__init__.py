from flask import Flask, redirect, url_for, request
from flask_login import current_user
from app.extensions import db, csrf, login_manager
from app import config


def create_app():
    app = Flask(__name__)
    app.config.from_object(config.Config)

    # Initialize extensions with app
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.models import User
        return User.query.get(int(user_id))

    @app.before_request
    def require_login():
        public_routes = ['admin.login', 'static', 'public_bp.signup']
        if not current_user.is_authenticated and request.endpoint not in public_routes:
            return redirect(url_for('admin.login'))

    # Register blueprints
    from app.routes.chat_routes import chat_bp
    from app.admin import admin as admin_blueprint
    from app.routes.project_routes import project_bp
    from app.routes.document_library import document_bp
    from app.routes.routes import public_bp
    from app.routes.user_routes import user_bp
    from app.routes.research_routes import research_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    app.register_blueprint(project_bp)
    app.register_blueprint(document_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(research_bp)

    # Create tables
    with app.app_context():
        db.create_all()

    return app