from app import create_app, db
from app.utils import migrate_add_unique_id

# Vercel looks for this 'app' variable to start the server
app = create_app()

# Initialize Database (Runs on Vercel Cold Start)
with app.app_context():
    # Create tables if they don't exist
    db.create_all()
    
    # Run migrations safely
    try:
        migrate_add_unique_id()
    except Exception as e:
        print(f"Migration logic skipped or failed: {e}")

# This block only runs when you type 'python index.py' locally
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)