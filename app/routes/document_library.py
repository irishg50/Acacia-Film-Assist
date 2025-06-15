from flask import Blueprint, request, Response, stream_with_context, current_app, jsonify, session
from flask_wtf.csrf import CSRFProtect
from flask_login import current_user, login_required
import json
import chardet
import docx2txt
import PyPDF2
import pandas as pd
import io
import tiktoken
import traceback
from datetime import datetime
from functools import wraps
import uuid
from app.services.auth_decorators import login_required, admin_required
from app.models.models import Document, DocumentChunk, Project
from app.extensions import db
from typing import Generator, List, Optional, Union
from dataclasses import dataclass, asdict
import openai
import os

document_bp = Blueprint('document_bp', __name__)
csrf = CSRFProtect()

# Constants
MAX_CHUNK_SIZE = 50000  # Maximum tokens per chunk


@dataclass
class ProcessingProgress:
    stage: str
    message: str
    percentage: float
    current_step: Optional[int] = None
    total_steps: Optional[int] = None


def get_token_count(text: str) -> int:
    """Count tokens in text using tiktoken"""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception as e:
        print(f"Error in token counting: {str(e)}")
        return len(text.split()) * 2  # Rough approximation


def chunk_document(content: str) -> Generator[Union[ProcessingProgress, DocumentChunk], None, None]:
    """Split document into chunks and yield progress updates"""
    print(f"\nStarting document chunking...")
    print(f"Input content length: {len(content)} characters")

    yield ProcessingProgress(
        stage="splitting",
        message="Starting document analysis",
        percentage=0
    )

    total_tokens = get_token_count(content)
    print(f"Total tokens in document: {total_tokens}")

    if total_tokens == 0:
        raise ValueError("Document contains no tokens")

    paragraphs = content.split('\n\n')
    chunks = []
    current_chunk = []
    current_token_count = 0
    processed_chars = 0
    total_chars = len(content)

    for i, paragraph in enumerate(paragraphs):
        paragraph_tokens = get_token_count(paragraph)
        processed_chars += len(paragraph)

        if current_token_count + paragraph_tokens > MAX_CHUNK_SIZE and current_chunk:
            chunk_content = '\n\n'.join(current_chunk)
            chunk = DocumentChunk(
                content=chunk_content,
                chunk_number=len(chunks) + 1,
                token_count=current_token_count
            )
            chunks.append(chunk)
            current_chunk = [paragraph]
            current_token_count = paragraph_tokens
        else:
            current_chunk.append(paragraph)
            current_token_count += paragraph_tokens

        progress = (processed_chars / total_chars) * 80 + 10
        if len(chunks) > 0 and len(chunks) % max(1, len(paragraphs) // 10) == 0:
            yield ProcessingProgress(
                stage="splitting",
                message=f"Processing document content ({len(chunks)} chunks created)",
                percentage=progress,
                current_step=len(chunks),
                total_steps=None
            )

    if current_chunk:
        chunk_content = '\n\n'.join(current_chunk)
        chunk = DocumentChunk(
            content=chunk_content,
            chunk_number=len(chunks) + 1,
            token_count=current_token_count
        )
        chunks.append(chunk)

    yield ProcessingProgress(
        stage="complete",
        message=f"Document split into {len(chunks)} chunks",
        percentage=100
    )

    for chunk in chunks:
        yield chunk


def process_file(file, project_id: int) -> Generator[Union[ProcessingProgress, tuple], None, None]:
    """Process file and yield progress updates"""
    filename = file.filename
    file_extension = filename.split('.')[-1].lower()
    print(f"\nProcessing file: {filename}")

    if file_extension not in ['txt', 'pdf', 'doc', 'docx', 'csv', 'xlsx']:
        raise ValueError(f"Unsupported file type: {file_extension}")

    yield ProcessingProgress(
        stage="processing",
        message=f"Processing {file_extension.upper()} file",
        percentage=0
    )

    try:
        content = None
        file_size = 0

        file_bytes = file.read()
        file_size = len(file_bytes)

        if file_extension == 'pdf':
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            content_parts = []
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text.strip():
                    content_parts.append(text)
            content = "\n\n".join(content_parts)

        elif file_extension == 'txt':
            detected = chardet.detect(file_bytes)
            content = file_bytes.decode(detected['encoding'])

        elif file_extension in ['doc', 'docx']:
            content = docx2txt.process(io.BytesIO(file_bytes))

        elif file_extension == 'csv':
            content = file_bytes.decode('utf-8')

        elif file_extension == 'xlsx':
            df = pd.read_excel(io.BytesIO(file_bytes))
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            content = csv_buffer.getvalue()

        if not content or not content.strip():
            raise ValueError(f"No content could be extracted from {file_extension.upper()} file")

        yield ProcessingProgress(
            stage="processing",
            message="File content extracted successfully",
            percentage=50
        )

        # Create database document record
        document = Document(
            user_id=current_user.id,
            project_id=project_id,
            filename=filename,
            file_type=file_extension,
            file_size=file_size,
            content=content,
            content_preview=content[:1000] if content else None,
            is_processed=False
        )
        db.session.add(document)
        db.session.flush()  # Get document ID without committing

        # Process chunks
        chunks = []
        total_tokens = 0
        for result in chunk_document(content):
            if isinstance(result, ProcessingProgress):
                yield result
            elif isinstance(result, DocumentChunk):
                chunks.append(result)
                total_tokens += result.token_count

        # Add chunks to database
        for chunk in chunks:
            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_number=chunk.chunk_number,
                content=chunk.content,
                token_count=chunk.token_count
            )
            db.session.add(db_chunk)

        # Update document with final metadata
        document.total_chunks = len(chunks)
        document.token_count = total_tokens
        document.is_processed = True
        db.session.commit()

        yield (document, chunks)

    except Exception as e:
        print(f"Error in process_file: {str(e)}")
        traceback.print_exc()
        if 'document' in locals():
            document.processing_error = str(e)
            document.is_processed = True
            db.session.commit()
        yield ProcessingProgress(
            stage="error",
            message=f"Error processing file: {str(e)}",
            percentage=100
        )
        raise


@document_bp.route('/api/upload', methods=['POST'])
@csrf.exempt
@login_required
def upload_document():
    """Handle document upload and processing"""
    print("\n=== Starting File Upload ===")

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    project_id = request.form.get('project_id')
    if not project_id:
        return jsonify({'error': 'Project ID is required'}), 400

    # Verify project exists and belongs to user
    project = Project.query.filter_by(
        id=project_id,
        user_id=current_user.id
    ).first()

    if not project:
        return jsonify({'error': 'Invalid project'}), 404

    file = request.files['file']

    # Clear any previous file info in session before storing new upload
    for key in ['openai_file_ids', 'openai_file_names', 'openai_file_types']:
        if key in session:
            del session[key]
    session.modified = True

    # Upload file to OpenAI and store file_id in session
    openai.api_key = current_app.config.get('OPENAI_API_KEY')
    openai_file = openai.files.create(file=(file.filename, file.stream, "application/octet-stream"), purpose='assistants')
    file_id = openai_file.id
    file.seek(0)  # Reset file pointer so backend processing works
    if 'openai_file_ids' not in session:
        session['openai_file_ids'] = []
    session['openai_file_ids'].append(file_id)
    # Store file name and type in session for assistant context
    if 'openai_file_names' not in session:
        session['openai_file_names'] = []
    if 'openai_file_types' not in session:
        session['openai_file_types'] = []
    session['openai_file_names'].append(file.filename)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext == '.csv':
        session['openai_file_types'].append('CSV')
    elif ext in ['.xlsx', '.xls']:
        session['openai_file_types'].append('Excel spreadsheet')
    elif ext == '.pdf':
        session['openai_file_types'].append('PDF')
    elif ext in ['.doc', '.docx']:
        session['openai_file_types'].append('Word document')
    else:
        session['openai_file_types'].append('unknown type')
    session.modified = True

    def generate():
        try:
            final_document = None
            final_chunks = None

            for result in process_file(file, project.id):
                if isinstance(result, ProcessingProgress):
                    yield f"data: {json.dumps(asdict(result))}\n\n"
                elif isinstance(result, tuple) and len(result) == 2:
                    final_document, final_chunks = result

            if not final_document:
                raise ValueError("Processing completed but no document was produced")

            completion_message = {
                'done': True,
                'documentId': final_document.id,
                'document': final_document.to_dict()
            }
            yield f"data: {json.dumps(completion_message)}\n\n"

        except Exception as e:
            print(f"Error in upload_document: {str(e)}")
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )


@document_bp.route('/api/documents', methods=['GET'])
@login_required
def get_documents():
    """Get all documents for the current user and project"""
    try:
        project_id = request.args.get('project_id', type=int)
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        documents = Document.query.filter_by(
            user_id=current_user.id,
            project_id=project_id
        ).order_by(Document.created_at.desc()).all()

        return jsonify({
            "documents": [doc.to_dict() for doc in documents]
        })
    except Exception as e:
        print(f"Error getting documents: {str(e)}")
        return jsonify({"error": str(e)}), 500


@document_bp.route('/api/documents/<int:doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    """Retrieve a specific document"""
    document = Document.query.filter_by(
        id=doc_id,
        user_id=current_user.id
    ).first_or_404()

    return jsonify(document.to_dict())


@document_bp.route('/api/documents/<int:doc_id>/content', methods=['GET'])
@login_required
def get_document_content(doc_id):
    """Retrieve document content and chunks"""
    document = Document.query.filter_by(
        id=doc_id,
        user_id=current_user.id
    ).first_or_404()

    chunks = [chunk.to_dict() for chunk in document.chunks]

    return jsonify({
        'document': document.to_dict(),
        'content': document.content,
        'chunks': chunks
    })


@document_bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    """Delete a document"""
    document = Document.query.filter_by(
        id=doc_id,
        user_id=current_user.id
    ).first_or_404()

    try:
        db.session.delete(document)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Document deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': f'Error deleting document: {str(e)}'
        }), 500


@document_bp.route('/api/projects/<int:project_id>/documents', methods=['DELETE'])
@login_required
def clear_project_documents(project_id):
    """Clear all documents in a project"""
    try:
        documents = Document.query.filter_by(
            project_id=project_id,
            user_id=current_user.id
        ).all()

        for doc in documents:
            db.session.delete(doc)

        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'All documents cleared successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': f'Error clearing documents: {str(e)}'
        }), 500