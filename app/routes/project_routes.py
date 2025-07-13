from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models.models import Project, db
from datetime import datetime

project_bp = Blueprint('project_bp', __name__)

@project_bp.route('/api/projects', methods=['GET'])
@login_required
def list_projects():
    projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.updated_at.desc()).all()
    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'system_instructions': p.system_instructions,  # Added this
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in projects]
    })

@project_bp.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    data = request.get_json()
    project = Project(
        user_id=current_user.id,
        name=data['name'],
        description=data.get('description', ''),
        system_instructions=data.get('system_instructions', '')  # Added this
    )
    db.session.add(project)
    db.session.commit()
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'system_instructions': project.system_instructions,  # Added this
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat()
    })

@project_bp.route('/api/projects/<int:project_id>', methods=['GET'])  # Added this route
@login_required
def get_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'system_instructions': project.system_instructions,
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat()
    })

@project_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def update_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    project.name = data.get('name', project.name)
    project.description = data.get('description', project.description)
    project.system_instructions = data.get('system_instructions', project.system_instructions)  # Added this
    project.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'system_instructions': project.system_instructions,  # Added this
        'updated_at': project.updated_at.isoformat()
    })

@project_bp.route('/api/projects/<int:project_id>/memory', methods=['POST'])
@login_required
def update_project_memory(project_id):
    """Manually trigger project memory update"""
    try:
        from app.services.project_memory_service import get_incremental_project_memory, get_project_memory
        
        # Verify project belongs to user
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        
        # Force memory update
        memory = get_incremental_project_memory(project_id)
        
        if memory:
            return jsonify({
                'status': 'success',
                'message': 'Project memory updated successfully',
                'memory': get_project_memory(project_id)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to update project memory'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error updating project memory: {str(e)}'
        }), 500

@project_bp.route('/api/projects/<int:project_id>/memory', methods=['GET'])
@login_required
def get_project_memory_endpoint(project_id):
    """Get current project memory"""
    try:
        from app.services.project_memory_service import get_project_memory
        
        # Verify project belongs to user
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
        
        memory_text = get_project_memory(project_id)
        
        return jsonify({
            'status': 'success',
            'memory': memory_text
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving project memory: {str(e)}'
        }), 500

@project_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Project deleted successfully'})