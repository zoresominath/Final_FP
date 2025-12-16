import os
import uuid
import re
from datetime import datetime, timedelta
from PIL import Image, ImageDraw

# Flask & Database
from flask import current_app
from sqlalchemy import text, or_
from .extensions import db
from .models import User

# External Libraries
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import cloudinary
import cloudinary.uploader

def upload_file(file_obj):
    """
    Uploads a file to Cloudinary and returns the secure URL.
    Used for profile pictures on Vercel/Production.
    """
    # Configure Cloudinary using keys from config.py
    cloudinary.config(
        cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME'),
        api_key = current_app.config.get('CLOUDINARY_API_KEY'),
        api_secret = current_app.config.get('CLOUDINARY_API_SECRET')
    )

    # Upload the file
    try:
        upload_result = cloudinary.uploader.upload(
            file_obj,
            folder="mess_app_profiles", # This folder will be created in your Cloudinary
            transformation=[
                {'width': 150, 'height': 150, 'crop': 'fill'} # Auto-resize to square
            ]
        )
        # Return the secure HTTPS URL
        return upload_result['secure_url']
    except Exception as e:
        print(f"Cloudinary Upload Error: {e}")
        return None

def is_valid_username(u):
    """Checks if username is 3-30 chars, alphanumeric/underscore/dot/dash."""
    return bool(re.match(r'^[A-Za-z0-9_.-]{3,30}$', u))

def is_strong_password(p):
    """Checks for length >=8, at least one letter, at least one number."""
    return len(p) >= 8 and re.search(r'[A-Za-z]', p) and re.search(r'\d', p)

def generate_unique_id():
    """Generates a short unique ID (e.g., A1B2C3D4) or falls back to timestamp."""
    for _ in range(20):
        candidate = uuid.uuid4().hex[:8].upper()
        if not User.query.filter_by(unique_id=candidate).first():
            return candidate
    return f"U{int(datetime.utcnow().timestamp())}"

def utc_to_ist_str(dt, fmt='%d %b, %Y %H:%M:%S'):
    """Converts a UTC datetime object to an IST string."""
    if not dt: return ''
    try:
        ist = dt + timedelta(hours=5, minutes=30)
        return ist.strftime(fmt)
    except Exception:
        return dt.strftime(fmt)

def ensure_default_image():
    """
    Creates a default profile image locally if it doesn't exist.
    (Note: On Vercel read-only system, this might simply pass silently)
    """
    try:
        static_folder = current_app.config.get('STATIC_FOLDER', 'app/static')
        default_path = os.path.join(static_folder, 'default.png')
        
        # Only try to create if it doesn't exist
        if not os.path.exists(default_path):
            os.makedirs(static_folder, exist_ok=True)
            img = Image.new('RGB', (200, 200), color=(248, 249, 250))
            d = ImageDraw.Draw(img)
            d.ellipse([50, 30, 150, 130], fill=(13, 110, 253))
            img.save(default_path)
    except Exception as e:
        # Fail silently on read-only file systems (like Vercel)
        pass

def send_email(to_email, subject, body):
    """Sends an email using SendGrid."""
    api_key = current_app.config.get('SENDGRID_API_KEY')
    sender_email = current_app.config.get('SENDGRID_SENDER')

    if not api_key or not sender_email:
        print("Mail server not configured. Check config.py.")
        return

    message = Mail(
        from_email=sender_email,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body
    )
    
    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        print(f"Email sent! Status Code: {response.status_code}")
    except Exception as e:
        print(f"Mail Error: {e}")

def migrate_add_unique_id():
    """
    Migration routine to ensure unique_id column exists.
    Useful for existing SQLite databases that need updating.
    """
    from sqlalchemy import inspect
    
    try:
        inspector = inspect(db.engine)
        cols = [col['name'] for col in inspector.get_columns('user')]
    except Exception:
        return

    if 'unique_id' not in cols:
        print("Migration: Adding unique_id column...")
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN unique_id TEXT;'))
    
    # Populate empty unique_ids for existing users
    try:
        users_without = User.query.filter(or_(User.unique_id == None, User.unique_id == '')).all()
        if users_without:
            print(f"Migrating {len(users_without)} users...")
            for u in users_without:
                u.unique_id = generate_unique_id()
                db.session.add(u)
            db.session.commit()
    except Exception as e:
        print(f"Migration Error: {e}")