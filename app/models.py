from datetime import datetime
from flask_login import UserMixin
from .extensions import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # --- NEW FIELDS ---
    name = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(15), nullable=True)
    # ------------------

    # The Unique ID column (A1, A2... B1...)
    unique_id = db.Column(db.String(20), unique=True, nullable=True)
    
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    user_type = db.Column(db.String(20), default='customer')
    gender = db.Column(db.String(10), default='Male')
    image_filename = db.Column(db.String(200), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)

    # Mess Details
    mess_type = db.Column(db.String(20), default='Two Time')
    monthly_charge = db.Column(db.Float, default=2800.0)
    cost_per_meal = db.Column(db.Float, default=0.0)
    balance = db.Column(db.Float, default=0.0)

    # Relationships
    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    attendance = db.relationship('Attendance', backref='user', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
    meal_requests = db.relationship('MealRequest', backref='user', lazy=True)
    leave_requests = db.relationship('LeaveRequest', backref='user', lazy=True)
    feedback = db.relationship('Feedback', backref='user', lazy=True)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    balance = db.Column(db.Float, default=2800.0)
    is_active = db.Column(db.Boolean, default=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    meal_type = db.Column(db.String(20))

class WeeklyMenu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20), unique=True)
    lunch = db.Column(db.String(200))
    dinner = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150))
    message = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    to_user_id = db.Column(db.Integer, nullable=True)

class MealRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_requested = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending')
    date_requested = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    transaction_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='Pending')