from app import create_app, db
from app.utils import migrate_add_unique_id, ensure_default_image
import os

app = create_app()

def initialize():
    with app.app_context():
        # Create DB if not exists
        db.create_all()
        # Create folders
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        # Run migrations
        migrate_add_unique_id()
        ensure_default_image()

if __name__ == '__main__':
    initialize()
    app.run(debug=True, host='127.0.0.1', port=5000)