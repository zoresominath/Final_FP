import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # --- Security Keys ---
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-hard-to-guess-secret-key')
    SECRET_ADMIN_CODE = os.environ.get('SECRET_ADMIN_CODE', "Pass@123")

    # --- Database Configuration ---
    # Priority 1: Check for DATABASE_URL (Neon / Render / Production)
    if os.environ.get('DATABASE_URL'):
        db_url = os.environ.get('DATABASE_URL')
        # Fix for SQLAlchemy compatibility with Postgres
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = db_url
    
    # Priority 2: Vercel Read-Only Fallback (If no DB URL is set)
    elif os.environ.get('VERCEL'):
        SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/mess_system.db'
        
    # Priority 3: Local Development (Your Computer)
    else:
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "mess_system.db")}'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- Razorpay Payment Configuration (NEW) ---
    # Get these from: Razorpay Dashboard -> Settings -> API Keys -> Generate Test Key
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_YOUR_KEY_HERE')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'YOUR_SECRET_HERE')

    # --- File Uploads (Cloudinary) ---
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'my_cloud_name')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', 'my_api_key')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'my_api_secret')

    # Local paths (Used as temporary storage or fallback)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'profile_pics')
    
    # --- Email Settings (SendGrid) ---
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', "SG.my_sendgrid_api_key")
    SENDGRID_SENDER = os.environ.get('SENDGRID_SENDER', "example@gmail.com")
    
    # --- Pricing Constants ---
    
    # Standard (Two Time Mess - Lunch & Dinner)
    MALE_MONTHLY = 2800.0
    FEMALE_MONTHLY = 2400.0
    
    # One Time Mess (Any 1 Meal/Day)
    MALE_ONE_TIME = 1500.0
    FEMALE_ONE_TIME = 1300.0