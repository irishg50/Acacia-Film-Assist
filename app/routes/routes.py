from flask import Blueprint, render_template, request, Response, stream_with_context, current_app, session, flash, redirect, url_for
from flask_wtf.csrf import CSRFProtect
import json
import os
import anthropic
import chardet
import docx2txt
import PyPDF2
import pandas as pd
import io
import tiktoken
from datetime import datetime, timedelta
from threading import Lock
from functools import wraps
import uuid
from app.services.auth_decorators import login_required
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential
from dataclasses import dataclass, asdict
from typing import Generator, List, Optional, Union
from app.admin.forms import SignupForm
from app.models.models import User, Project, UserSurvey
from app import db

chat_bp = Blueprint('chat_bp', __name__)
csrf = CSRFProtect()

MAX_HISTORY_LENGTH = 10
DOCUMENT_EXPIRY = timedelta(hours=1)
MAX_CHUNK_SIZE = 50000  # Maximum tokens per chunk

# Utility functions and decorators
def get_api_key():
    """Get the Anthropic API key from config or environment"""
    api_key = current_app.config.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Anthropic API key is not set in config or environment")
    return api_key

def get_user_id():
    """Get a unique identifier for the current user's session"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def require_valid_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return json.dumps({'error': 'Invalid session'}), 401
        return f(*args, **kwargs)
    return decorated_function


@dataclass
class DocumentChunk:
    content: str
    chunk_number: int
    total_chunks: int
    token_count: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ProcessingProgress:
    stage: str
    message: str
    percentage: float
    current_step: Optional[int] = None
    total_steps: Optional[int] = None


class DocumentStore:
    def __init__(self):
        self.documents = {}
        self.document_chunks = {}
        self.lock = Lock()
        self.user_documents = {}

    def add_document(self, user_id: str, content: str, filename: str,
                     chunks: List[DocumentChunk] = None) -> str:
        if not self.lock.acquire(timeout=5):
            print("Lock acquisition timed out!")
            raise Exception("Timeout while trying to add document")

        try:
            print(f"\nAdding document to store:")
            print(f"Filename: {filename}")
            print(f"Content length: {len(content)} characters")
            print(f"Number of chunks: {len(chunks) if chunks else 0}")

            if not content or not content.strip():
                raise ValueError("Cannot add document with empty content")

            doc_id = str(uuid.uuid4())
            self.documents[doc_id] = {
                'filename': filename,
                'content': content,
                'user_id': user_id,
                'timestamp': datetime.utcnow()
            }

            if chunks:
                print(f"Storing {len(chunks)} chunks for document {doc_id}")
                self.document_chunks[doc_id] = chunks
                for i, chunk in enumerate(chunks):
                    print(f"Chunk {i + 1}/{len(chunks)}: {len(chunk.content)} chars, "
                          f"{chunk.token_count} tokens")

            if user_id not in self.user_documents:
                self.user_documents[user_id] = set()

            self.user_documents[user_id].add(doc_id)
            print(f"Document added successfully with ID: {doc_id}")

            return doc_id
        except Exception as e:
            print(f"Error in add_document: {str(e)}")
            raise
        finally:
            print("Releasing lock")
            self.lock.release()

    def get_document(self, doc_id: str, user_id: str) -> Optional[dict]:
        with self.lock:
            doc = self.documents.get(doc_id)
            if doc and doc['user_id'] == user_id:
                chunks = self.document_chunks.get(doc_id, [])
                doc['chunks'] = chunks
                return doc
            return None

    def cleanup_old_documents(self):
        current_time = datetime.utcnow()
        with self.lock:
            expired_docs = [
                doc_id for doc_id, doc in self.documents.items()
                if current_time - doc['timestamp'] > DOCUMENT_EXPIRY
            ]
            for doc_id in expired_docs:
                doc = self.documents.pop(doc_id)
                self.document_chunks.pop(doc_id, None)
                user_id = doc['user_id']
                if user_id in self.user_documents:
                    self.user_documents[user_id].discard(doc_id)

    def clear_user_documents(self, user_id: str):
        with self.lock:
            if user_id in self.user_documents:
                for doc_id in self.user_documents[user_id]:
                    self.documents.pop(doc_id, None)
                    self.document_chunks.pop(doc_id, None)
                self.user_documents.pop(user_id)

    def _debug_document(self, doc_id: str):
        """Print debug information about a document"""
        print("\n=== Document Debug Info ===")
        print(f"Document ID: {doc_id}")

        doc = self.documents.get(doc_id)
        if not doc:
            print("Document not found!")
            return

        print(f"Filename: {doc['filename']}")
        print(f"User ID: {doc['user_id']}")
        print(f"Content length: {len(doc['content'])} characters")
        print(f"Timestamp: {doc['timestamp']}")

        chunks = self.document_chunks.get(doc_id, [])
        print(f"\nChunks: {len(chunks)}")
        for i, chunk in enumerate(chunks):
            print(f"\nChunk {i + 1}/{chunk.total_chunks}:")
            print(f"Token count: {chunk.token_count}")
            print(f"Content length: {len(chunk.content)} characters")
            print(f"Content preview: {chunk.content[:100]}...")

    def add_document(self, user_id: str, content: str, filename: str,
                     chunks: List[DocumentChunk] = None) -> str:
        if not self.lock.acquire(timeout=5):
            print("Lock acquisition timed out!")
            raise Exception("Timeout while trying to add document")

        try:
            print(f"\nAdding document to store:")
            print(f"Filename: {filename}")
            print(f"Content length: {len(content)} characters")
            print(f"Number of chunks: {len(chunks) if chunks else 0}")

            if not content or not content.strip():
                raise ValueError("Cannot add document with empty content")

            doc_id = str(uuid.uuid4())
            self.documents[doc_id] = {
                'filename': filename,
                'content': content,
                'user_id': user_id,
                'timestamp': datetime.utcnow()
            }

            if chunks:
                print(f"Storing {len(chunks)} chunks for document {doc_id}")
                self.document_chunks[doc_id] = chunks
                for i, chunk in enumerate(chunks):
                    print(f"Chunk {i + 1}/{len(chunks)}: {len(chunk.content)} chars, "
                          f"{chunk.token_count} tokens")

            if user_id not in self.user_documents:
                self.user_documents[user_id] = set()

            self.user_documents[user_id].add(doc_id)
            print(f"Document added successfully with ID: {doc_id}")

            # Debug the newly added document
            self._debug_document(doc_id)

            return doc_id
        except Exception as e:
            print(f"Error in add_document: {str(e)}")
            raise
        finally:
            print("Releasing lock")
            self.lock.release()


# Create a single instance of DocumentStore
document_store = DocumentStore()


def get_token_count(text: str) -> int:
    """Count tokens in text using tiktoken"""
    try:
        # Use cl100k_base encoding which is compatible with Claude models
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception as e:
        print(f"Error in token counting: {str(e)}")
        # Fallback to approximate counting if tokenizer fails
        return len(text.split()) * 2  # Rough approximation


def chunk_document(content: str) -> Generator[Union[ProcessingProgress, DocumentChunk], None, None]:
    """Split document into chunks and yield progress updates"""
    print("\nStarting document chunking...")
    print(f"Input content length: {len(content)} characters")

    yield ProcessingProgress(
        stage="splitting",
        message="Starting document analysis",
        percentage=0
    )

    # First pass: count total tokens
    total_tokens = get_token_count(content)
    print(f"Total tokens in document: {total_tokens}")

    yield ProcessingProgress(
        stage="splitting",
        message=f"Analyzing document structure ({total_tokens:,} tokens)",
        percentage=10
    )

    if total_tokens == 0:
        print("Warning: Document contains 0 tokens")
        raise ValueError("Document contains no tokens")

    # Split into paragraphs
    paragraphs = content.split('\n\n')
    print(f"Document split into {len(paragraphs)} paragraphs")

    chunks = []
    current_chunk = []
    current_token_count = 0
    processed_chars = 0
    total_chars = len(content)

    for i, paragraph in enumerate(paragraphs):
        paragraph_tokens = get_token_count(paragraph)
        processed_chars += len(paragraph)
        print(f"Paragraph {i + 1}: {len(paragraph)} chars, {paragraph_tokens} tokens")

        if current_token_count + paragraph_tokens > MAX_CHUNK_SIZE and current_chunk:
            # Create new chunk
            chunk_content = '\n\n'.join(current_chunk)
            chunk = DocumentChunk(
                content=chunk_content,
                chunk_number=len(chunks) + 1,
                total_chunks=0,  # Will update later
                token_count=current_token_count
            )
            chunks.append(chunk)
            print(f"Created chunk {len(chunks)} with {current_token_count} tokens")
            current_chunk = [paragraph]
            current_token_count = paragraph_tokens
        else:
            current_chunk.append(paragraph)
            current_token_count += paragraph_tokens

        # Yield progress update every ~10%
        progress = (processed_chars / total_chars) * 80 + 10
        if len(chunks) > 0 and len(chunks) % max(1, len(paragraphs) // 10) == 0:
            yield ProcessingProgress(
                stage="splitting",
                message=f"Processing document content ({len(chunks)} chunks created)",
                percentage=progress,
                current_step=len(chunks),
                total_steps=None
            )

    # Add final chunk if exists
    if current_chunk:
        chunk_content = '\n\n'.join(current_chunk)
        chunk = DocumentChunk(
            content=chunk_content,
            chunk_number=len(chunks) + 1,
            total_chunks=0,
            token_count=current_token_count
        )
        chunks.append(chunk)
        print(f"Created final chunk with {current_token_count} tokens")

    # Update total chunks count
    total_chunks = len(chunks)
    print(f"Updating chunk numbers. Total chunks: {total_chunks}")
    for chunk in chunks:
        chunk.total_chunks = total_chunks

    print(f"Chunking complete. Created {total_chunks} chunks")
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i + 1}: {chunk.token_count} tokens")
        yield chunk

    yield ProcessingProgress(
        stage="complete",
        message=f"Document split into {total_chunks} chunks",
        percentage=100
    )


def process_file(file) -> Generator[Union[ProcessingProgress, tuple], None, None]:
    """Process file and yield progress updates"""
    filename = file.filename
    file_extension = filename.split('.')[-1].lower()
    print(f"\nProcessing file: {filename}")
    print(f"File extension: {file_extension}")

    if file_extension not in ['txt', 'pdf', 'doc', 'docx', 'csv', 'xlsx']:
        raise ValueError(f"Unsupported file type: {file_extension}")

    yield ProcessingProgress(
        stage="processing",
        message=f"Processing {file_extension.upper()} file",
        percentage=0
    )

    try:
        if file_extension == 'pdf':
            print("Processing PDF file...")
            file_bytes = file.read()
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            print(f"PDF has {len(pdf_reader.pages)} pages")
            content_parts = []

            for i, page in enumerate(pdf_reader.pages):
                print(f"Extracting text from page {i + 1}")
                text = page.extract_text()
                if text.strip():
                    content_parts.append(text)
                print(f"Page {i + 1} extracted: {len(text)} characters")

            content = "\n\n".join(content_parts)
            print(f"Total PDF content: {len(content)} characters")

        elif file_extension == 'txt':
            print("Processing text file...")
            file_bytes = file.read()
            print(f"Read {len(file_bytes)} bytes")

            detected = chardet.detect(file_bytes)
            print(f"Detected encoding: {detected}")
            content = file_bytes.decode(detected['encoding'])
            print(f"Decoded content length: {len(content)} characters")

        elif file_extension in ['doc', 'docx']:
            content = docx2txt.process(io.BytesIO(file.read()))
        elif file_extension == 'csv':
            file_bytes = file.read()
            content = file_bytes.decode('utf-8')
        elif file_extension == 'xlsx':
            file_bytes = file.read()
            df = pd.read_excel(io.BytesIO(file_bytes))
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            content = csv_buffer.getvalue()

        if not content or not content.strip():
            raise ValueError(f"No content could be extracted from {file_extension.upper()} file")

        print(f"Content extracted successfully: {len(content)} characters")
        print(f"Content sample (first 100 chars): {content[:100]}")

        yield ProcessingProgress(
            stage="processing",
            message="File content extracted successfully",
            percentage=50
        )

        # Process chunks
        chunks = []
        print("\nStarting document chunking...")
        for result in chunk_document(content):
            if isinstance(result, ProcessingProgress):
                yield result
            elif isinstance(result, DocumentChunk):
                chunks.append(result)

        if not chunks:
            raise ValueError("No chunks were created during processing")

        # Important: Return the content and chunks as the final yield
        content_chunks = (content, chunks)
        print(f"\nReturning processed content and {len(chunks)} chunks")
        yield content_chunks

    except Exception as e:
        print(f"Error in process_file: {str(e)}")
        import traceback
        traceback.print_exc()
        yield ProcessingProgress(
            stage="error",
            message=f"Error processing file: {str(e)}",
            percentage=100
        )
        raise

@chat_bp.route('/')
def home_page():
    """Serve the main index.html page"""
    return render_template('index.html')


@chat_bp.route('/chat')
def chat_page():
    # Reset chat history when the page loads
    session['chat_history'] = []
    session['user_id'] = str(uuid.uuid4())
    return render_template('chat.html')


@chat_bp.route('/api/upload', methods=['POST'])
@csrf.exempt
@require_valid_session
def upload_document():
    print("\n=== Starting File Upload ===")
    if 'file' not in request.files:
        return json.dumps({'error': 'No file provided'}), 400

    file = request.files['file']
    user_id = get_user_id()
    print(f"Processing file: {file.filename} for user: {user_id}")

    def generate():
        try:
            final_content = None
            final_chunks = None

            # Process the file and collect results
            for result in process_file(file):
                if isinstance(result, ProcessingProgress):
                    print(f"Progress: {result.stage} - {result.message} ({result.percentage}%)")
                    yield f"data: {json.dumps(asdict(result))}\n\n"
                elif isinstance(result, tuple) and len(result) == 2:
                    # This is our content and chunks tuple
                    final_content, final_chunks = result
                    print(f"Received final content ({len(final_content)} chars) "
                          f"and {len(final_chunks)} chunks")

            if not final_content or not final_chunks:
                raise ValueError("Processing completed but no content or chunks were produced")

            # Add document to storage
            print(f"\nAdding document to storage...")
            print(f"Content length: {len(final_content)} characters")
            print(f"Number of chunks: {len(final_chunks)}")

            doc_id = document_store.add_document(
                user_id=user_id,
                content=final_content,
                filename=file.filename,
                chunks=final_chunks
            )

            print(f"Document added successfully with ID: {doc_id}")

            # Send completion message with document ID
            completion_message = {
                'done': True,
                'documentId': doc_id
            }
            print(f"Sending completion message: {completion_message}")
            yield f"data: {json.dumps(completion_message)}\n\n"

        except Exception as e:
            print(f"Error in upload_document: {str(e)}")
            import traceback
            traceback.print_exc()
            error_message = {'error': str(e)}
            print(f"Sending error message: {error_message}")
            yield f"data: {json.dumps(error_message)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )


@chat_bp.route('/api/clear_files', methods=['POST'])
@csrf.exempt
@require_valid_session
def clear_files():
    user_id = get_user_id()
    document_store.clear_user_documents(user_id)
    return json.dumps({
        "status": "success",
        "message": "Files cleared successfully"
    }), 200, {'Content-Type': 'application/json'}


@chat_bp.route('/api/new_chat', methods=['POST'])
@csrf.exempt
@require_valid_session
def new_chat():
    user_id = get_user_id()
    chat_history_key = f'chat_history_{user_id}'
    session[chat_history_key] = []
    document_store.clear_user_documents(user_id)
    session.modified = True
    return json.dumps({
        "status": "success",
        "message": "New chat started"
    }), 200, {'Content-Type': 'application/json'}


@chat_bp.route('/api/chat', methods=['POST'])
@csrf.exempt
@require_valid_session
def chat():
    try:
        print("\n=== Starting Chat Request ===")
        data = request.get_json()
        prompt = data.get('prompt')
        document_ids = data.get('documentIds', [])
        user_id = get_user_id()

        print(f"User ID: {user_id}")
        print(f"Document IDs: {document_ids}")
        print(f"Prompt: {prompt}")

        # Get chat history
        chat_history_key = f'chat_history_{user_id}'
        if chat_history_key not in session:
            session[chat_history_key] = []

        # Build system messages
        system_messages = [{
            "type": "text",
            "text": "You are an AI assistant. Provide helpful, detailed, and accurate responses."
        }]

        # Process documents and their chunks
        print("\nProcessing documents:")
        MAX_TOTAL_TOKENS = 180000  # Leave room for response
        total_tokens = 0
        document_content = []

        for doc_id in document_ids:
            print(f"Looking up document {doc_id}")
            doc = document_store.get_document(doc_id, user_id)
            if doc and 'chunks' in doc:
                print(f"Found document: {doc['filename']}")
                chunks = doc['chunks']
                print(f"Document has {len(chunks)} chunks")

                # Sort chunks by token count to prioritize smaller chunks
                chunks.sort(key=lambda x: x.token_count)

                for chunk in chunks:
                    # Check if adding this chunk would exceed the token limit
                    if total_tokens + chunk.token_count > MAX_TOTAL_TOKENS:
                        print(f"Skipping remaining chunks - would exceed token limit")
                        # Add a note about skipped content
                        system_messages.append({
                            "type": "text",
                            "text": f"Note: Some content from {doc['filename']} was too large to process fully. "
                                    f"I'll work with the {len(document_content)} sections I could load.",
                            "cache_control": {"type": "ephemeral"}
                        })
                        break

                    chunk_instruction = (
                        f"Part {chunk.chunk_number} of {chunk.total_chunks} from {doc['filename']}. "
                        "Use this information when responding to queries:\n\n"
                    )
                    full_content = chunk_instruction + chunk.content
                    document_content.append(full_content)
                    system_messages.append({
                        "type": "text",
                        "text": full_content,
                        "cache_control": {"type": "ephemeral"}
                    })

                    total_tokens += chunk.token_count
                    print(f"Added chunk {chunk.chunk_number}/{chunk.total_chunks} "
                          f"({chunk.token_count} tokens)")
                    print(f"Total tokens so far: {total_tokens}")
            else:
                print(f"Document {doc_id} not found")

        print(f"\nTotal system messages: {len(system_messages)}")
        print(f"Document content pieces: {len(document_content)}")
        print(f"Total tokens: {total_tokens}")

        # Process messages
        messages = []
        for msg in session[chat_history_key]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        current_message = {
            "role": "user",
            "content": prompt
        }
        messages.append(current_message)
        session[chat_history_key].append(current_message)

        if len(session[chat_history_key]) > MAX_HISTORY_LENGTH:
            session[chat_history_key] = session[chat_history_key][-MAX_HISTORY_LENGTH:]
        session.modified = True

        return Response(
            stream_with_context(claude_stream(messages, user_id, system_messages)),
            content_type='text/event-stream'
        )

    except Exception as e:
        print(f"\nError in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": str(e)}), 500


def get_api_key():
    """Get the Anthropic API key from config or environment"""
    api_key = current_app.config.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Anthropic API key is not set in config or environment")
    return api_key


def get_user_id():
    """Get a unique identifier for the current user's session"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']


def require_valid_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return json.dumps({'error': 'Invalid session'}), 401
        return f(*args, **kwargs)

    return decorated_function


@retry(
    retry=tenacity.retry_if_exception_type(anthropic.RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    before_sleep=lambda retry_state: print(f"Rate limit hit, waiting {retry_state.next_action.sleep} seconds..."),
    after=lambda retry_state: print(f"Attempt {retry_state.attempt_number} completed")
)
def stream_claude_response(client, message_args, user_id):
    """Wrapper function for Claude API calls with retry logic"""
    print("\n=== Starting Claude Stream Request ===")
    print(f"Time: {datetime.utcnow()}")
    print(f"Message count: {len(message_args.get('messages', []))}")
    print(f"System message count: {len(message_args.get('system', [])) if 'system' in message_args else 0}")

    try:
        stream = client.messages.stream(**message_args)
        return stream
    except Exception as e:
        print(f"\nError in stream_claude_response: {str(e)}")
        print("Headers if available:", getattr(e, 'response', {}).headers if hasattr(e, 'response') else 'No headers')
        raise

def claude_stream(messages, user_id, system_messages=None):
    api_key = get_api_key()
    client = anthropic.Anthropic(
        api_key=api_key,
        default_headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31"
        }
    )

    def generate():
        try:
            yield json.dumps({
                "progress": {
                    "stage": "initialization",
                    "message": "Starting request...",
                    "percentage": 0
                }
            }) + "\n"

            message_args = {
                "model": current_app.config.get('CLAUDE_MODEL'),
                "max_tokens": current_app.config.get('CLAUDE_MAX_TOKENS', 8192),
                "messages": messages,
                "system": system_messages or []
            }

            try:
                with stream_claude_response(client, message_args, user_id) as stream:
                    buffer = ""
                    for text in stream.text_stream:
                        buffer += text
                        if len(buffer) >= 20 or text.endswith(('.', '!', '?', '\n')):
                            yield json.dumps({"chunk": buffer}) + "\n"
                            buffer = ""

                    if buffer:
                        yield json.dumps({"chunk": buffer}) + "\n"

                    # Get the final message which contains usage information
                    final_message = stream.get_final_message()

                    # Add to chat history
                    chat_history_key = f'chat_history_{user_id}'
                    if final_message.content:
                        session[chat_history_key].append({
                            "role": "assistant",
                            "content": final_message.content
                        })
                        session.modified = True

            except anthropic.RateLimitError as e:
                print(f"Rate limit error: {str(e)}")
                yield json.dumps({
                    "error": "The system is currently experiencing high demand. Please try breaking your request into smaller "
                            "pieces or wait a few minutes before trying again."
                }) + "\n"
                return
            except Exception as e:
                print(f"Error in stream: {str(e)}")
                raise

        except Exception as e:
            print(f"\nError in claude_stream: {str(e)}")
            error_message = str(e)
            if "rate_limit" in error_message.lower():
                error_message = ("The system is currently experiencing high demand. Please try breaking your request into "
                               "smaller pieces or wait a few minutes before trying again.")
            yield json.dumps({
                "error": error_message
            }) + "\n"

    return generate()


public_bp = Blueprint('public_bp', __name__)

@public_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    # Promo code gate
    if 'promo_verified' not in session or not session['promo_verified']:
        if request.method == 'POST' and 'promo_code' in request.form:
            promo_code = request.form.get('promo_code', '').strip()
            valid_codes = current_app.config.get('PROMO_CODES', [])
            if promo_code in valid_codes:
                session['promo_verified'] = True
            else:
                return render_template('admin/signup.html', show_promo_modal=True, promo_error='Invalid promotion code.')
        else:
            return render_template('admin/signup.html', show_promo_modal=True)
    # Normal signup form logic
    form = SignupForm()
    if form.validate_on_submit():
        # Check for duplicate username or email
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists. Please choose another.', 'danger')
            return render_template('admin/signup.html', form=form)
        if User.query.filter_by(email_address=form.email_address.data).first():
            flash('Email address already registered. Please use another.', 'danger')
            return render_template('admin/signup.html', form=form)
        user = User(
            username=form.username.data,
            firstname=form.firstname.data,
            lastname=form.lastname.data,
            org_name=form.org_name.data,
            email_address=form.email_address.data,
            is_active=False,  # Require admin approval
            role='user',
            signup_date=datetime.utcnow()
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        # Create default project
        default_project = Project(
            name="General Chat",
            description="Default project for general chat sessions.",
            user_id=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(default_project)
        db.session.commit()
        flash('Signup successful! Your account is pending admin approval.', 'success')
        session.pop('promo_verified', None)
        return render_template('admin/signup.html', account_created=True, new_user_id=user.id, form=form)
    return render_template('admin/signup.html', form=form)


@public_bp.route('/profile_after_signup', methods=['POST'])
def profile_after_signup():
    # Save the optional profile details to UserSurvey
    user_id = request.form.get('new_user_id') or session.get('new_user_id')
    # For demo, just use the most recent user if not found
    if not user_id:
        user = User.query.order_by(User.id.desc()).first()
        user_id = user.id if user else None
    if not user_id:
        flash('Could not find user to update profile.', 'danger')
        return render_template('admin/signup.html', account_created=True, form=SignupForm())
    survey = UserSurvey.query.filter_by(user_id=user_id).first()
    if not survey:
        survey = UserSurvey(user_id=user_id)
        db.session.add(survey)
    survey.job_title = request.form.get('job_title')
    survey.primary_responsibilities = request.form.get('primary_responsibilities')
    survey.top_priorities = request.form.get('top_priorities')
    survey.special_interests = request.form.get('special_interests')
    survey.learning_goals = request.form.get('learning_goals')
    db.session.commit()
    flash('Thank you for sharing your profile details! Your information has been saved. You can log in once your account is approved.', 'success')
    return redirect(url_for('admin.login'))
