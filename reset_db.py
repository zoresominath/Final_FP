from app import create_app, db

app = create_app()

with app.app_context():
    print("Dropping old tables...")
    db.drop_all()
    
    print("Creating new tables with Name & Phone columns...")
    db.create_all()
    
    print("✅ Database reset successfully on Neon!")