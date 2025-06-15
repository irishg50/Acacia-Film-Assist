print('user_routes.py loading')
try:
    from flask import Blueprint, jsonify, request
    from flask_login import login_required, current_user
    from datetime import datetime
    from app.extensions import db
    # Adjust import to use direct import instead of models.models
    from app.models.models import UserAgreement
    print('user_routes.py imports successful')
except Exception as e:
    print(f'ERROR IMPORTING IN USER_ROUTES: {e}')
    raise

user_bp = Blueprint('user_bp', __name__)

# Test route that doesn't require any models
@user_bp.route('/api/user/test', methods=['GET'])
def test_route():
    return 'User routes are working!'

@user_bp.route('/api/user/agreement-status', methods=['GET'])
@login_required
def agreement_status():
    # Always return as if user has agreed
    return jsonify({'agreed': True})

@user_bp.route('/api/user-agreement', methods=['GET'])
@login_required
def get_user_agreement():
    # Return empty agreement since it won't be shown
    return jsonify({
        'version': '1.0',
        'title': 'Beta Test User Agreement',
        'content_markdown': ''
    })

@user_bp.route('/api/user/accept-agreement', methods=['POST'])
@login_required
def accept_agreement():
    # Always return success
    return jsonify({'status': 'success'})