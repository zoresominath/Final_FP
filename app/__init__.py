from flask import Flask
from config import Config
from .extensions import db, login_manager
from flask_wtf.csrf import CSRFProtect  # Import CSRFProtect

# Initialize CSRF here (globally) so it can be used by the app
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)  # Enable CSRF protection

    # specific settings for login manager
    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'info'

    # Import and register blueprints
    from . import routes
    app.register_blueprint(routes.bp)

    return app