from flask import Flask, redirect, url_for, request
from flask_login import current_user
from sqlalchemy import inspect
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

    # Initialize database tables
    with app.app_context():
        try:
            # Check if tables exist before creating them
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if not existing_tables:
                # Only create tables if database is empty
                print("Creating database tables...")
                db.create_all()
                print("Database tables created successfully")
            else:
                print(f"Database already has {len(existing_tables)} tables, skipping creation")
                
        except Exception as e:
            print(f"Database initialization error: {e}")
            
            # If there's an index conflict, try to create tables without indexes
            if "already exists" in str(e) and "ix_organization_name" in str(e):
                print("Attempting to create tables without indexes...")
                try:
                    # Drop the problematic index if it exists
                    with db.engine.connect() as conn:
                        conn.execute(db.text("DROP INDEX IF EXISTS ix_organization_name"))
                        conn.commit()
                    
                    # Try creating tables again
                    db.create_all()
                    print("Database tables created successfully after index cleanup")
                except Exception as retry_error:
                    print(f"Retry failed: {retry_error}")
                    # Continue anyway - tables might already be functional
            
            # Continue with app startup even if there are issues

    return app