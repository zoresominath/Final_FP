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
from .utils import is_valid_username, is_strong_password, generate_next_customer_id, utc_to_ist_str, send_email, upload_file
from config import Config
from sqlalchemy import text

bp = Blueprint('main', __name__)

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

# --- Context Processors & Home ---

@bp.context_processor
def inject_ist_helper():
    return dict(to_ist=utc_to_ist_str)

@bp.route('/')
def home():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

# --- Authentication Routes ---

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
        mess_type = request.form.get('mess_type', 'Two Time') 

        if not is_valid_username(username): 
            flash('Invalid username. Use letters and numbers only.', 'danger')
            return redirect(url_for('main.register'))
        
        if not is_strong_password(password_raw): 
            flash('Weak password. Must be 8+ chars.', 'danger')
            return redirect(url_for('main.register'))
        
        if User.query.filter_by(username=username).first(): 
            flash('Username taken.', 'danger')
            return redirect(url_for('main.register'))
        
        if user_type == 'owner' and User.query.filter_by(user_type='owner').first():
            flash('Owner already exists.', 'danger')
            return redirect(url_for('main.register'))

        # Pricing Logic
        monthly_charge = 0.0
        cost_per_meal = 0.0
        
        if mess_type == 'One Time':
            if gender == 'Male':
                monthly_charge = Config.MALE_ONE_TIME
            else:
                monthly_charge = Config.FEMALE_ONE_TIME
            cost_per_meal = monthly_charge / 30.0
        else: 
            if gender == 'Male':
                monthly_charge = Config.MALE_MONTHLY
            else:
                monthly_charge = Config.FEMALE_MONTHLY
            cost_per_meal = monthly_charge / 60.0

        image_url = None
        file = request.files.get('image')
        if file and file.filename:
            image_url = upload_file(file)

        dob = datetime.strptime(dob_raw, "%Y-%m-%d").date() if dob_raw else None
        
        # --- ID GENERATION (Only for Customers) ---
        unique_id = None
        if user_type == 'customer':
            # Get the last customer to generate the next sequential ID
            last_customer = User.query.filter_by(user_type='customer').order_by(User.id.desc()).first()
            last_id_str = last_customer.unique_id if last_customer else None
            unique_id = generate_next_customer_id(last_id_str)
        # ------------------------------------------
        
        u = User(
            username=username, 
            email=email, 
            password=generate_password_hash(password_raw),
            user_type=user_type, 
            gender=gender, 
            image_filename=image_url, 
            date_of_birth=dob, 
            unique_id=unique_id,
            mess_type=mess_type,
            monthly_charge=monthly_charge,
            cost_per_meal=cost_per_meal,
            balance=0.0
        )
        
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

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

# --- Dashboard & Profile ---

@bp.route('/dashboard')
@login_required
def dashboard():
    current_date = date.today()
    
    # OWNER DASHBOARD
    if current_user.user_type == 'owner':
        # 1. Monthly Reset Logic (Stats)
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)

        q = request.args.get('q', '').strip()
        base_query = User.query.filter(User.id != current_user.id, User.user_type == 'customer')
        if q:
            base_query = base_query.filter(or_(User.unique_id.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")))
        all_users = base_query.order_by(User.username.asc()).all()
        
        stats_users = User.query.filter(User.user_type == 'customer').count()
        stats_meals = Attendance.query.filter(Attendance.timestamp >= start_of_month).count()
        
        monthly_approved_payments = Payment.query.filter(
            Payment.status == 'Approved',
            Payment.timestamp >= start_of_month
        ).all()
        stats_revenue = sum(p.amount for p in monthly_approved_payments)
        
        # --- HISTORY DATA AGGREGATION ---
        history_data = {}
        
        # Aggregate Revenue
        all_payments = Payment.query.filter_by(status='Approved').all()
        for p in all_payments:
            y = str(p.timestamp.year)
            m = p.timestamp.strftime('%B')
            m_num = p.timestamp.month
            if y not in history_data: history_data[y] = {}
            if m not in history_data[y]: history_data[y][m] = {'revenue': 0, 'meals': 0, 'num': m_num}
            history_data[y][m]['revenue'] += p.amount

        # Aggregate Meals
        all_attendance = Attendance.query.all()
        for a in all_attendance:
            y = str(a.timestamp.year)
            m = a.timestamp.strftime('%B')
            m_num = a.timestamp.month
            if y not in history_data: history_data[y] = {}
            if m not in history_data[y]: history_data[y][m] = {'revenue': 0, 'meals': 0, 'num': m_num}
            history_data[y][m]['meals'] += 1
            
        sorted_history = []
        for year in sorted(history_data.keys(), reverse=True):
            months_list = []
            for month_name, data in history_data[year].items():
                months_list.append({
                    'month': month_name,
                    'revenue': data['revenue'],
                    'meals': data['meals'],
                    'num': data['num']
                })
            months_list.sort(key=lambda x: x['num'])
            sorted_history.append({'year': year, 'data': months_list})
        # -------------------------------------

        all_leave_requests = LeaveRequest.query.all()
        pending_leave = [req for req in all_leave_requests if req.status == 'Pending']
        pending_payments = Payment.query.filter_by(status='Pending').order_by(Payment.timestamp.desc()).all()
        meal_reqs = MealRequest.query.order_by(MealRequest.date_requested.desc()).all()
        feedbacks = Feedback.query.order_by(Feedback.date.desc()).all()
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_menu = sorted(WeeklyMenu.query.all(), key=lambda x: days_order.index(x.day) if x.day in days_order else 99)
        
        birthday_list = []
        today_ordinal = current_date.timetuple().tm_yday
        for u in User.query.filter(User.date_of_birth.isnot(None), User.user_type == 'customer').all():
            bday_ordinal = u.date_of_birth.replace(year=current_date.year).timetuple().tm_yday
            day_diff = (bday_ordinal - today_ordinal + 366) % 366
            if 0 <= day_diff <= 5:
                birthday_list.append({'username': u.username, 'date_of_birth': u.date_of_birth, 'days_until': day_diff})
        birthday_list.sort(key=lambda x: x['days_until'])

        return render_template('dashboard_owner.html', all_users=all_users, stats_users=stats_users,
                               stats_meals=stats_meals, stats_revenue=f"{stats_revenue:,.0f}",
                               feedbacks=feedbacks, pending_leave_requests=pending_leave, all_leave_requests=all_leave_requests,
                               all_meal_requests=meal_reqs, weekly_menu=weekly_menu,
                               birthday_list=birthday_list, current_date=current_date,
                               pending_payments=pending_payments, history_data=sorted_history)

    # CUSTOMER DASHBOARD
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
                               sub_balance=f"{current_user.balance:,.2f}", leave_requests=leave_requests,
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
        file = request.files.get('image')
        if file and file.filename:
            image_url = upload_file(file)
            if image_url: u.image_filename = image_url
        db.session.commit()
        flash('Updated.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('update_profile.html', u=u)

@bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
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

# -----------------------------------------------------------
#  MANUAL PAYMENT REQUEST (UNIQUE ID FLOW)
# -----------------------------------------------------------

@bp.route('/submit_payment', methods=['POST'])
@login_required
def submit_payment():
    # 'transaction_id' field now holds the User's Unique ID from the frontend form
    submitted_id = request.form.get('transaction_id')
    amount = current_user.monthly_charge
    
    if not submitted_id:
        flash('Please enter a valid Unique ID.', 'danger')
        return redirect(url_for('main.dashboard'))

    # CHECK FOR PENDING REQUESTS ONLY
    # Block ONLY if there is already a Pending request with this ID.
    existing_pending = Payment.query.filter_by(
        transaction_id=submitted_id,
        status='Pending'
    ).first()

    if existing_pending:
        flash('A renewal request with this ID is already pending approval.', 'warning')
        return redirect(url_for('main.dashboard'))

    # Create new Pending Payment
    new_payment = Payment(
        user_id=current_user.id,
        amount=amount,
        transaction_id=submitted_id,
        status='Pending'
    )
    db.session.add(new_payment)
    db.session.commit()
    
    flash('Renewal request sent! Please wait for approval.', 'info')
    return redirect(url_for('main.dashboard'))

@bp.route('/verify_payment/<int:payment_id>/<action>')
@login_required
def verify_payment(payment_id, action):
    if current_user.user_type != 'owner': return redirect(url_for('main.dashboard'))
    payment = Payment.query.get_or_404(payment_id)
    user = User.query.get(payment.user_id)
    
    if action == 'approve':
        payment.status = 'Approved'
        # --- RENEWAL LOGIC ---
        start = date.today()
        end = start + timedelta(days=30)
        sub = Subscription.query.filter_by(user_id=user.id, is_active=True).first()
        
        if sub and sub.end_date >= start:
            # Extend existing subscription
            sub.end_date += timedelta(days=30)
        else:
            # Create new subscription
            new_sub = Subscription(user_id=user.id, start_date=start, end_date=end, balance=0)
            db.session.add(new_sub)
            
        user.balance += payment.amount
        db.session.add(Notification(to_user_id=user.id, title="Subscription Renewed", message="Your payment is verified. Your plan has been extended."))
        flash(f'Request approved for {user.username}.', 'success')
        
    elif action == 'reject':
        payment.status = 'Rejected'
        db.session.add(Notification(to_user_id=user.id, title="Payment Rejected", message="Your renewal request was rejected. Contact Owner."))
        flash('Request rejected.', 'danger')
        
    db.session.commit()
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
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    meals_eaten_today = Attendance.query.filter(Attendance.user_id==u.id, Attendance.timestamp >= today_start).count()
    
    limit = 1 if u.mess_type == 'One Time' else 2
    
    if meals_eaten_today >= limit:
        return jsonify({'success': False, 'error': f'Daily limit reached! ({limit} meal/day)'})

    if Attendance.query.filter(Attendance.user_id==u.id, Attendance.meal_type==meal, Attendance.timestamp >= today_start).first():
        return jsonify({'success': False, 'error': f'Already ate {meal} today'})

    cost = u.cost_per_meal
    is_bday = (u.date_of_birth and u.date_of_birth.month == date.today().month and u.date_of_birth.day == date.today().day)
    
    if not is_bday:
        if u.balance < cost: 
            return jsonify({'success': False, 'error': f'Low balance! Need {cost}'})
        u.balance -= cost

    db.session.add(Attendance(user_id=u.id, meal_type=meal))
    db.session.commit()
    
    msg = "Happy Birthday! Meal is free." if is_bday else f"Marked for {u.username}"
    return jsonify({'success': True, 'username': u.username, 'balance': f"{u.balance:.2f}", 'message': msg})

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
@bp.route('/init_db_fix')
def init_db_fix():
    try:
        with current_app.app_context():
            db.create_all() # This creates missing tables/columns
            return "Database Updated Successfully! Try Registering now."
    except Exception as e:
        return f"Error: {str(e)}"
@bp.route('/fix_db_null')
def fix_db_null():
    try:
        # This SQL command removes the "NOT NULL" constraint from unique_id
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ALTER COLUMN unique_id DROP NOT NULL;'))
            conn.commit()
        return "Database Fixed! 'unique_id' now accepts NULL values. You can Register the Owner now."
    except Exception as e:
        return f"Error fixing DB: {str(e)}"    