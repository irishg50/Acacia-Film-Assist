from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, login_required, logout_user, current_user
from . import admin
from app.models.models import User, LoginRecord, Project, ChatSession, Document
from .forms import LoginForm, PasswordUpdateForm, UserCreationForm, UserEditForm, SignupForm
from functools import wraps
from flask import abort
from app import db  # Import db from app package instead of __init__
from datetime import datetime, timedelta
import pytz
from sqlalchemy import func

# set local timezone  - eventually this could be from user table
edt_tz = pytz.timezone('US/Eastern')


@admin.route('/login', methods=['GET', 'POST'])
def login():
    print("Login route accessed (restored authentication mode)")
    if current_user.is_authenticated:
        return redirect(url_for('chat_bp.index_page'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Your account is pending approval by an administrator.', 'warning')
                return render_template('admin/login.html', form=form)
            login_user(user)
            # Record login
            login_record = LoginRecord(user_id=user.id, login_time=datetime.utcnow())
            db.session.add(login_record)
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page or url_for('chat_bp.index_page'))
        else:
            flash('Invalid username or password.')
    return render_template('admin/login.html', form=form)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function



@admin.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('admin.login'))


@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    admin_users = User.query.filter_by(role='admin').count()
    regular_users = User.query.filter_by(role='user').count()

    # Chat sessions per day for last 14 days
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=13)
    chat_activity = (
        db.session.query(
            func.date(ChatSession.created_at).label('date'),
            func.count(ChatSession.id).label('count')
        )
        .filter(ChatSession.created_at >= start_date)
        .group_by(func.date(ChatSession.created_at))
        .order_by(func.date(ChatSession.created_at))
        .all()
    )
    # Fill in missing days with 0
    activity_dict = {row.date: row.count for row in chat_activity}
    chat_activity_list = []
    for i in range(14):
        day = start_date + timedelta(days=i)
        chat_activity_list.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': activity_dict.get(day, 0)
        })

    # Latest 10 user logins
    latest_logins = (
        db.session.query(LoginRecord, User)
        .join(User, LoginRecord.user_id == User.id)
        .order_by(LoginRecord.login_time.desc())
        .limit(10)
        .all()
    )
    login_table = [
        {
            'username': user.username,
            'login_time': login.login_time
        }
        for login, user in latest_logins
    ]

    # Latest 10 file uploads
    latest_uploads = (
        db.session.query(Document, User)
        .join(User, Document.user_id == User.id)
        .order_by(Document.created_at.desc())
        .limit(10)
        .all()
    )
    upload_table = [
        {
            'username': user.username,
            'filename': doc.filename,
            'created_at': doc.created_at
        }
        for doc, user in latest_uploads
    ]

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           admin_users=admin_users,
                           regular_users=regular_users,
                           chat_activity=chat_activity_list,
                           login_table=login_table,
                           upload_table=upload_table)

@admin.route('/update_password', methods=['GET', 'POST'])
@login_required
def update_password():
    form = PasswordUpdateForm()
    if form.validate_on_submit():
        user = User.query.filter_by(id=current_user.id).first()
        user.set_password(form.new_password.data)
        db.session.commit()
        flash('Your password has been updated.')
        return redirect(url_for('admin.dashboard'))  # Redirect to a valid endpoint
    return render_template('admin/update_password.html', form=form)


@admin.route('/create_user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    form = UserCreationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            role='user'  # Set default role to 'user'
        )
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()

            # Create a default project for the new user
            default_project = Project(
                name="General Chat",
                description="Default project for general chat sessions.",
                user_id=user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(default_project)
            db.session.commit()

            flash(f'User {user.username} and their default "General Chat" project have been created successfully.', 'success')
            return redirect(url_for('admin.user_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while creating the user: {str(e)}', 'danger')
    return render_template('admin/create_user.html', form=form)

@admin.route('/users')
@login_required
@admin_required
def user_list():
    users = User.query.all()
    return render_template('admin/user_list.html', users=users, current_user=current_user)


@admin.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)
    if request.method == 'GET':
        form.is_active.data = bool(user.is_active)  # Only set on GET

    if form.validate_on_submit():
        user.username = form.username.data
        user.role = form.role.data
        user.is_active = form.is_active.data  # Save is_active from form
        # Only update password if new password is provided
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash(f'User {user.username} has been updated successfully.', 'success')
        return redirect(url_for('admin.user_list'))

    return render_template('admin/edit_user.html', form=form, user=user)


@admin.route('/delete_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_user(user_id):
    try:
        # Check if user is trying to delete themselves
        if user_id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('admin.user_list'))

        user = User.query.get_or_404(user_id)
        if request.method == 'POST':
            username = user.username  # Store username before deletion
            db.session.delete(user)
            db.session.commit()
            flash(f'User {username} has been deleted successfully.', 'success')
        return redirect(url_for('admin.user_list'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
        return redirect(url_for('admin.user_list'))


@admin.route('/logins')
@login_required
@admin_required
def login_records():
    # Get all users and their login records
    users = User.query.all()
    user_logins = []
    for user in users:
        login_records = LoginRecord.query.filter_by(user_id=user.id).order_by(LoginRecord.login_time.desc()).all()
        total_logins = len(login_records)
        most_recent_login = login_records[0].login_time if login_records else None
        user_logins.append({
            'username': user.username,
            'total_logins': total_logins,
            'most_recent_login': most_recent_login
        })

    return render_template('admin/logins.html', user_logins=user_logins)

@admin.app_template_filter('utc_to_edt')
def utc_to_edt(utc_dt):
    if utc_dt is None:
        return 'Never'
    # Assume stored time is naive UTC
    utc_dt = pytz.utc.localize(utc_dt)
    edt_dt = utc_dt.astimezone(edt_tz)
    return edt_dt.strftime('%Y-%m-%d %H:%M:%S')

@admin.route('/debug-db')
def debug_db():
    try:
        # Check if we can query the User table
        users = User.query.all()
        return f"Database connection successful. Found {len(users)} users."
    except Exception as e:
        return f"Database error: {str(e)}"

@admin.route('/check-user-table')
def check_user_table():
    try:
        # Get table info directly from database
        result = db.session.execute("SELECT column_name FROM information_schema.columns WHERE table_name='univchat_users'")
        columns = [row[0] for row in result]
        return f"User table columns: {', '.join(columns)}"
    except Exception as e:
        return f"Error checking table: {str(e)}"

@admin.route('/create-test-user')
def create_test_user():
    try:
        # Check if test user already exists
        test_user = User.query.filter_by(username='testuser').first()
        if test_user:
            return "Test user already exists"
        
        # Create new test user
        user = User(username='testuser', role='admin')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return f"Test user created with ID: {user.id}"
    except Exception as e:
        db.session.rollback()
        return f"Error creating test user: {str(e)}"

@admin.route('/migrate-user/<username>')
def migrate_user(username):
    try:
        # This assumes you still have access to the old table
        # You'll need to modify this based on your database setup
        old_user_data = db.session.execute(f"SELECT * FROM univ_users WHERE username = '{username}'").fetchone()
        
        if not old_user_data:
            return f"User {username} not found in old table"
        
        # Create user in new table
        new_user = User(
            username=old_user_data.username,
            password_hash=old_user_data.password_hash,  # Copy the password hash directly
            role=old_user_data.role
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return f"User {username} migrated successfully with ID: {new_user.id}"
    except Exception as e:
        db.session.rollback()
        return f"Error migrating user: {str(e)}"

@admin.route('/signup_approvals')
@login_required
@admin_required
def signup_approvals():
    pending_users = User.query.filter_by(is_active=False).all()
    return render_template('admin/dashboard_signup_approvals.html', pending_users=pending_users)

@admin.route('/approve_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    flash(f'User {user.username} has been approved and activated.', 'success')
    return redirect(url_for('admin.signup_approvals'))

@admin.route('/reject_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} has been rejected and deleted.', 'danger')
    return redirect(url_for('admin.signup_approvals'))