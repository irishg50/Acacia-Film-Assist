from flask import Blueprint
from app import db

admin = Blueprint('admin', __name__, url_prefix='/admin')

from . import routes