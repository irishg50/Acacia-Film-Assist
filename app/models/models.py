from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from datetime import datetime
import json
from flask_login import UserMixin
from sqlalchemy import Index

class APILog(db.Model):
    __tablename__ = 'montechat_api_log'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    prompt = db.Column(db.Text)
    message = db.Column(db.Text)
    completion_tokens = db.Column(db.Integer)
    prompt_tokens = db.Column(db.Integer)
    cache_tokens = db.Column(db.Integer)
    model = db.Column(db.String(50))
    thread_id = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=True)
    user = db.relationship('User', back_populates='api_logs')

    def __repr__(self):
        return f'<APILog {self.id}>'

class Organization(db.Model):
    __tablename__ = 'montechat_organization'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True, index=True)
    domain = db.Column(db.String(100), nullable=True, unique=True, index=True)  # e.g. example.org
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Relationship to users
    users = db.relationship('User', back_populates='organization', lazy=True)

    def __repr__(self):
        return f'<Organization {self.name}>'

class User(UserMixin, db.Model):
    __tablename__ = 'montechat_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), nullable=False, default='user')
    firstname = db.Column(db.String(75), nullable=True)
    lastname = db.Column(db.String(75), nullable=True)
    signup_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    org_name = db.Column(db.String(150), nullable=True)
    email_address = db.Column(db.String(75), nullable=True)
    agreement_date = db.Column(db.DateTime, nullable=True)
    agreement_text = db.Column(db.Text, nullable=True)
    login_records = db.relationship('LoginRecord', back_populates='user')
    api_logs = db.relationship('APILog', back_populates='user')
    organization_id = db.Column(db.Integer, db.ForeignKey('montechat_organization.id'), nullable=True, index=True)
    organization = db.relationship('Organization', back_populates='users')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    login_records = db.relationship('LoginRecord', backref='user_account',
                                  cascade='all, delete-orphan')

    @property
    def is_admin(self):
        return self.role == 'admin'


class LoginRecord(db.Model):
    __tablename__ = 'montechat_login_record'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=False)
    login_time = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User', back_populates='login_records')


class ChatSession(db.Model):
    __tablename__ = 'montechat_chatsession'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('montechat_project.id'), nullable=False)
    session_id = db.Column(db.String(36), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    chat_history = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    pinned = db.Column(db.Boolean, default=False)

    def set_chat_history(self, chat_history):
        self.chat_history = json.dumps(chat_history)

    def get_chat_history(self):
        return json.loads(self.chat_history)

class Project(db.Model):
    __tablename__ = 'montechat_project'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    system_instructions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to chat sessions
    chat_sessions = db.relationship('ChatSession', backref='project', lazy=True)

class Document(db.Model):
    __tablename__ = 'montechat_documents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('montechat_project.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # e.g., 'pdf', 'txt', 'csv'
    file_size = db.Column(db.Integer, nullable=False)  # size in bytes
    content = db.Column(db.Text, nullable=True)  # For text-based files
    content_preview = db.Column(db.String(1000), nullable=True)  # Short preview of content
    total_chunks = db.Column(db.Integer, default=0)
    token_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_processed = db.Column(db.Boolean, default=False)
    processing_error = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', backref=db.backref('documents', lazy=True))
    project = db.relationship('Project', backref=db.backref('documents', lazy=True))

    def __repr__(self):
        return f'<Document {self.filename}>'

    def to_dict(self):
        """Convert document to dictionary for API responses"""
        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'total_chunks': self.total_chunks,
            'token_count': self.token_count,
            'content_preview': self.content_preview,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_processed': self.is_processed,
            'processing_error': self.processing_error
        }


class DocumentChunk(db.Model):
    __tablename__ = 'montechat_document_chunks'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('montechat_documents.id', ondelete='CASCADE'), nullable=False)
    chunk_number = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    token_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    document = db.relationship('Document', backref=db.backref('chunks', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<DocumentChunk {self.document_id}-{self.chunk_number}>'

    def to_dict(self):
        """Convert chunk to dictionary for API responses"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'chunk_number': self.chunk_number,
            'token_count': self.token_count,
            'created_at': self.created_at.isoformat()
        }

class UserChatMemory(db.Model):
    __tablename__ = 'montechat_user_chat_memory'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), nullable=False, unique=True)
    memory_text = db.Column(db.Text, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('chat_memory', uselist=False))

    def __repr__(self):
        return f'<UserChatMemory user_id={self.user_id}>'

class UserAgreement(db.Model):
    __tablename__ = 'montechat_user_agreement'
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content_markdown = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<UserAgreement {self.version}>'

class UserSurvey(db.Model):
    __tablename__ = 'montechat_user_survey'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('montechat_users.id'), unique=True)
    job_title = db.Column(db.String(100))
    primary_responsibilities = db.Column(db.Text)
    top_priorities = db.Column(db.Text)
    special_interests = db.Column(db.Text)
    learning_goals = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('survey', uselist=False))

# Add indexes for organization
Index('ix_organization_name', Organization.name)
Index('ix_organization_domain', Organization.domain)