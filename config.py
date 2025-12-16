import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # --- Security Keys ---
    # Use environment variable for production, fallback to hardcoded for local
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-hard-to-guess-secret-key')
    SECRET_ADMIN_CODE = os.environ.get('SECRET_ADMIN_CODE', "Pass@123")

    # --- Database Configuration ---
    # Checks for DATABASE_URL (provided by Vercel/Render), otherwise uses local sqlite
    db_url = os.environ.get('DATABASE_URL')
    
    if not db_url:
        # Local SQLite database
        db_url = f'sqlite:///{os.path.join(BASE_DIR, "mess_system.db")}'
    
    # Fix for Postgres URLs on some platforms (they use postgres:// instead of postgresql://)
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- File Uploads (Cloudinary) ---
    # REPLACE THESE WITH YOUR REAL KEYS FROM CLOUDINARY DASHBOARD
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'my_cloud_name')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', 'my_api_key')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'my_api_secret' )

    # Local paths (Used as temporary storage or fallback)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'profile_pics')
    STATIC_FOLDER = os.path.join(BASE_DIR, 'app', 'static')
    
    # --- Email Settings (SendGrid) ---
    # Ideally, put these in Environment Variables too, but hardcoded works for testing
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', "SG.my_sendgrid_api_key")
    SENDGRID_SENDER = os.environ.get('SENDGRID_SENDER', "example@gmail.com")
    
    # --- Pricing Constants ---
    MALE_MONTHLY = 2800.0
    FEMALE_MONTHLY = 2400.0