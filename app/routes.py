import os
import io
import qrcode
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_, extract
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from .extensions import db
from .models import User, Subscription, Attendance, WeeklyMenu, Feedback, Notification, MealRequest, LeaveRequest, Payment
# Added upload_file to imports
from .utils import is_valid_username, is_strong_password, generate_unique_id, utc_to_ist_str, send_email, upload_file

bp = Blueprint('main', __name__)

# Constants
MALE_MEAL_COST = round(2800.0 / 60.0, 2)
FEMALE_MEAL_COST = round(2400.0 / 60.0, 2)

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

# --- Routes ---

@bp.context_processor
def inject_ist_helper():
    return dict(to_ist=utc_to_ist_str)

@bp.route('/')
def home():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        dob_raw = request.form.get('dob')
        password_raw = request.form['password']
        form_admin_code = request.form.get('admin_code', '').strip()
        
        user_type = 'owner' if form_admin_code == current_app.config.get('SECRET_ADMIN_CODE') else 'customer'
        gender = request.form.get('gender', 'Male')

        if not is_valid_username(username): flash('Invalid username.', 'danger'); return redirect(url_for('main.register'))
        if not is_strong_password(password_raw): flash('Weak password.', 'danger'); return redirect(url_for('main.register'))
        if User.query.filter_by(username=username).first(): flash('Username taken.', 'danger'); return redirect(url_for('main.register'))
        
        # Check if owner exists
        if user_type == 'owner' and User.query.filter_by(user_type='owner').first():
            flash('Owner already exists.', 'danger'); return redirect(url_for('main.register'))

        # Handle Image Upload (Cloudinary)
        image_url = None
        file = request.files.get('image')
        if file and file.filename:
            # Upload to Cloudinary and get the URL
            image_url = upload_file(file)

        dob = datetime.strptime(dob_raw, "%Y-%m-%d").date() if dob_raw else None
        unique_id = generate_unique_id()
        
        # Note: We save the Cloudinary URL into 'image_filename'
        u = User(username=username, email=email, password=generate_password_hash(password_raw),
                 user_type=user_type, gender=gender, image_filename=image_url, date_of_birth=dob, unique_id=unique_id)
        db.session.add(u)
        db.session.commit()
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form['username'].strip()).first()
        if u and check_password_hash(u.password, request.form['password']):
            login_user(u)
            return redirect(url_for('main.dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    current_date = date.today()
    
    # OWNER DASHBOARD LOGIC
    if current_user.user_type == 'owner':
        q = request.args.get('q', '').strip()
        base_query = User.query.filter(User.id != current_user.id, User.user_type == 'customer')
        if q:
            base_query = base_query.filter(or_(User.unique_id.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")))
        all_users = base_query.order_by(User.username.asc()).all()
        
        # Stats
        stats_users = User.query.filter(User.user_type == 'customer').count()
        stats_meals = Attendance.query.count()
        total_rev = sum([2400.0 if s.user.gender == 'Female' else 2800.0 for s in Subscription.query.all() if s.user])
        
        # Pass all_leave_requests explicitly for the chart logic
        all_leave_requests = LeaveRequest.query.all()
        pending_leave = [req for req in all_leave_requests if req.status == 'Pending']
        
        meal_reqs = MealRequest.query.order_by(MealRequest.date_requested.desc()).all()
        feedbacks = Feedback.query.order_by(Feedback.date.desc()).all()
        
        # Menu
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_menu = sorted(WeeklyMenu.query.all(), key=lambda x: days_order.index(x.day) if x.day in days_order else 99)
        
        # Birthdays
        birthday_list = []
        today_ordinal = current_date.timetuple().tm_yday
        for u in User.query.filter(User.date_of_birth.isnot(None), User.user_type == 'customer').all():
            bday_ordinal = u.date_of_birth.replace(year=current_date.year).timetuple().tm_yday
            day_diff = (bday_ordinal - today_ordinal + 366) % 366
            if 0 <= day_diff <= 5:
                birthday_list.append({'username': u.username, 'date_of_birth': u.date_of_birth, 'days_until': day_diff})
        birthday_list.sort(key=lambda x: x['days_until'])

        return render_template('dashboard_owner.html', all_users=all_users, stats_users=stats_users,
                               stats_meals=stats_meals, stats_revenue=f"{total_rev:,.0f}",
                               feedbacks=feedbacks, pending_leave_requests=pending_leave, all_leave_requests=all_leave_requests,
                               all_meal_requests=meal_reqs, weekly_menu=weekly_menu,
                               birthday_list=birthday_list, current_date=current_date)

    # CUSTOMER DASHBOARD LOGIC
    else:
        sub = Subscription.query.filter_by(user_id=current_user.id, is_active=True).first()
        days_remaining = (sub.end_date - current_date).days if sub and sub.end_date and sub.end_date >= current_date else 0
        attendance = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.timestamp.desc()).all()
        notifications = Notification.query.filter((Notification.to_user_id == None) | (Notification.to_user_id == current_user.id)).order_by(Notification.date.desc()).all()
        leave_requests = LeaveRequest.query.filter_by(user_id=current_user.id).all()
        payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.timestamp.desc()).all()
        
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_menu = sorted(WeeklyMenu.query.all(), key=lambda x: days_order.index(x.day) if x.day in days_order else 99)

        return render_template('dashboard_customer.html', sub=sub, attendance=attendance, notifications=notifications,
                               sub_balance=f"{sub.balance:,.2f}" if sub else '0.00', leave_requests=leave_requests,
                               weekly_menu=weekly_menu, days_remaining=days_remaining, payments=payments, current_date=current_date)

@bp.route('/view_user/<int:user_id>')
@login_required
def view_user(user_id):
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    u = User.query.get_or_404(user_id)
    attendance = Attendance.query.filter_by(user_id=u.id).order_by(Attendance.timestamp.desc()).all()
    return render_template('view_user.html', u=u, attendance=attendance)

@bp.route('/update_profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    u = User.query.get(current_user.id)
    if request.method == 'POST':
        u.username = request.form['username']
        u.email = request.form['email']
        if request.form.get('password'):
            u.password = generate_password_hash(request.form['password'])
        
        # Handle Image Upload (Cloudinary)
        file = request.files.get('image')
        if file and file.filename:
            image_url = upload_file(file)
            if image_url:
                u.image_filename = image_url
            
        db.session.commit()
        flash('Updated.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('update_profile.html', u=u)

@bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    # Only allow customers to delete their own account
    if current_user.user_type == 'owner':
        flash('Owners cannot delete their account directly.', 'danger')
        return redirect(url_for('main.dashboard'))
        
    try:
        db.session.delete(current_user)
        db.session.commit()
        logout_user()
        flash('Your account has been deleted.', 'info')
        return redirect(url_for('main.register'))
    except Exception as e:
        db.session.rollback()
        flash('Error deleting account.', 'danger')
        return redirect(url_for('main.dashboard'))

@bp.route('/purchase_subscription', methods=['POST'])
@login_required
def purchase_subscription():
    start = date.today()
    end = start + timedelta(days=30)
    cost = 2400.0 if current_user.gender == 'Female' else 2800.0
    
    # Check existing
    s = Subscription.query.filter_by(user_id=current_user.id, is_active=True).first()
    if s and s.end_date >= start:
        flash('Active subscription exists.', 'warning')
    else:
        db.session.add(Subscription(user_id=current_user.id, start_date=start, end_date=end, balance=cost))
        db.session.add(Payment(user_id=current_user.id, amount=cost))
        db.session.commit()
        flash('Purchased successfully.', 'success')
    return redirect(url_for('main.dashboard'))

@bp.route('/scanner')
@login_required
def scanner():
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    return render_template('scanner.html')

@bp.route('/user_qr/<int:user_id>')
@login_required
def user_qr(user_id):
    u = User.query.get_or_404(user_id)
    img_buffer = io.BytesIO()
    qrcode.make(u.unique_id).save(img_buffer, 'PNG')
    img_buffer.seek(0)
    return send_file(img_buffer, mimetype='image/png')

@bp.route('/scan_attendance', methods=['POST'])
@login_required
def scan_attendance():
    if current_user.user_type != 'owner': return jsonify({'success': False}), 403
    data = request.get_json()
    uid_str = str(data.get('user_id')).upper()
    meal = data.get('meal_type')
    
    u = User.query.filter((User.unique_id == uid_str) | (User.id == int(uid_str) if uid_str.isdigit() else False)).first()
    if not u: return jsonify({'success': False, 'error': 'User not found'})

    sub = Subscription.query.filter_by(user_id=u.id, is_active=True).first()
    if not sub or (sub.end_date and sub.end_date < date.today()):
        return jsonify({'success': False, 'error': 'Subscription expired'})
    
    # Check duplicate
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if Attendance.query.filter(Attendance.user_id==u.id, Attendance.meal_type==meal, Attendance.timestamp >= today_start).first():
        return jsonify({'success': False, 'error': 'Already ate this meal'})

    # Cost
    cost = FEMALE_MEAL_COST if u.gender == 'Female' else MALE_MEAL_COST
    # Free if birthday
    is_bday = (u.date_of_birth and u.date_of_birth.month == date.today().month and u.date_of_birth.day == date.today().day)
    if not is_bday:
        if sub.balance < cost: return jsonify({'success': False, 'error': 'Low balance'})
        sub.balance -= cost

    db.session.add(Attendance(user_id=u.id, meal_type=meal))
    db.session.commit()
    
    msg = "Happy Birthday! Meal is free." if is_bday else f"Marked for {u.username}"
    return jsonify({'success': True, 'username': u.username, 'balance': f"{sub.balance:.2f}", 'message': msg})

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@bp.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    content = request.form.get('content')
    if content:
        db.session.add(Feedback(user_id=current_user.id, content=content))
        db.session.commit()
        flash('Feedback submitted.', 'success')
    return redirect(url_for('main.dashboard'))

@bp.route('/send_notification', methods=['POST'])
@login_required
def send_notification():
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    title = request.form['title']
    message = request.form['message']
    to_user_id = request.form.get('to_user_id')
    
    note = Notification(title=title, message=message, 
                        to_user_id=int(to_user_id) if to_user_id else None)
    db.session.add(note)
    db.session.commit()
    flash('Notification sent.', 'success')
    return redirect(url_for('main.dashboard'))

@bp.route('/update_menu', methods=['POST'])
@login_required
def update_menu():
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    day = request.form['day']
    lunch = request.form['lunch']
    dinner = request.form['dinner']
    
    ex = WeeklyMenu.query.filter_by(day=day).first()
    if ex:
        ex.lunch = lunch
        ex.dinner = dinner
    else:
        db.session.add(WeeklyMenu(day=day, lunch=lunch, dinner=dinner, created_by=current_user.id))
    db.session.commit()
    flash(f'Menu updated for {day}.', 'success')
    return redirect(url_for('main.dashboard'))

@bp.route('/request_meal', methods=['POST'])
@login_required
def request_meal():
    content = request.form.get('content')
    if content:
        db.session.add(MealRequest(user_id=current_user.id, content=content))
        db.session.commit()
        flash('Request submitted.', 'success')
    return redirect(url_for('main.dashboard'))

@bp.route('/request_leave', methods=['POST'])
@login_required
def request_leave():
    start_raw = request.form.get('start_date')
    days = int(request.form.get('days', 0))
    reason = request.form.get('reason')
    
    if start_raw and days > 0:
        start_date = datetime.strptime(start_raw, '%Y-%m-%d').date()
        db.session.add(LeaveRequest(user_id=current_user.id, start_date=start_date, days=days, reason=reason))
        db.session.commit()
        flash('Leave requested.', 'success')
    else:
        flash('Invalid data.', 'danger')
    return redirect(url_for('main.dashboard'))

@bp.route('/process_leave/<int:request_id>', methods=['POST'])
@login_required
def process_leave(request_id):
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    req = LeaveRequest.query.get_or_404(request_id)
    action = request.form.get('action')
    
    if action == 'approve':
        sub = Subscription.query.filter_by(user_id=req.user_id, is_active=True).first()
        if sub and sub.end_date:
            sub.end_date += timedelta(days=req.days)
            req.status = 'Approved'
            db.session.commit()
            flash(f'Approved. Subscription extended by {req.days} days.', 'success')
        else:
            flash('User has no active subscription to extend.', 'warning')
    elif action == 'reject':
        req.status = 'Rejected'
        db.session.commit()
        flash('Leave rejected.', 'info')
        
    return redirect(url_for('main.dashboard'))

@bp.route('/process_meal_request/<int:request_id>', methods=['POST'])
@login_required
def process_meal_request(request_id):
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    
    req = MealRequest.query.get_or_404(request_id)
    action = request.form.get('action')
    
    if action == 'approve':
        req.status = 'Approved'
        # Optional: You could send a notification here
        db.session.add(Notification(to_user_id=req.user_id, title="Meal Request Update", message=f"Your request '{req.content}' has been APPROVED."))
        flash('Meal request approved.', 'success')
    elif action == 'reject':
        req.status = 'Rejected'
        db.session.add(Notification(to_user_id=req.user_id, title="Meal Request Update", message=f"Your request '{req.content}' has been REJECTED."))
        flash('Meal request rejected.', 'info')
        
    db.session.commit()
    return redirect(url_for('main.dashboard'))

@bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            s = get_serializer()
            token = s.dumps(user.email, salt='reset-salt')
            link = url_for('main.reset_password', token=token, _external=True)
            
            email_body = f"Click here to reset your password: {link}"
            send_email(user.email, "Reset Password", email_body)
            
        flash('If registered, a reset link was sent.', 'info')
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html')

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = get_serializer()
    try:
        email = s.loads(token, salt='reset-salt', max_age=900)
    except (SignatureExpired, BadSignature):
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('main.forgot_password'))
    
    if request.method == 'POST':
        p1 = request.form['password']
        if not is_strong_password(p1):
            flash('Weak password.', 'danger')
        else:
            u = User.query.filter_by(email=email).first()
            if u:
                u.password = generate_password_hash(p1)
                db.session.commit()
                flash('Password reset.', 'success')
                return redirect(url_for('main.login'))
    return render_template('reset_password.html')