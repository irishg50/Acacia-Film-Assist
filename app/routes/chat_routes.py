from flask import Blueprint, render_template, request, Response, stream_with_context, current_app, session, jsonify, redirect, url_for, send_file, flash
from flask_wtf.csrf import CSRFProtect
from flask_login import current_user, login_required
from app.services.auth_decorators import login_required, admin_required
import json
import os
import anthropic
import traceback
from datetime import datetime, timedelta
from functools import wraps
import uuid
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential
from app.extensions import db
from app.models.models import ChatSession, Project, Document, UserSurvey
from typing import Generator, List, Optional
import openai
import requests
from io import BytesIO
from app.services.chat_memory_service import generate_user_memory, get_user_memory
import tempfile
from tempfile import NamedTemporaryFile
import pandas as pd
import random
from app.services.user_background_service import generate_user_background


chat_bp = Blueprint('chat_bp', __name__)
csrf = CSRFProtect()

# Constants
MAX_HISTORY_LENGTH = 10


# Utility functions and decorators
def get_api_key():
    """Get the Anthropic API key from config or environment"""
    api_key = current_app.config.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("Anthropic API key is not set in config or environment")
    return api_key


def get_user_id():
    """Get a unique identifier for the current user's session"""
    if not current_user.is_authenticated:
        return None
    return current_user.id




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


def stream_openai_assistant(messages, user_id, assistant_id):
    # Create a thread
    thread = openai.beta.threads.create()
    thread_id = thread.id

    # Get file_ids from session
    file_ids = session.get('openai_file_ids', [])
    print("File IDs attached to message:", file_ids)
    
    # Prepare file attachment information
    attachments = []
    file_names = session.get('openai_file_names', [])
    file_types = session.get('openai_file_types', [])
    for i, fid in enumerate(file_ids):
        ftype = file_types[i] if i < len(file_types) else ""
        tools = []
        # Attach code_interpreter for csv/xlsx
        if ftype.lower() in ["csv", "xlsx", "xls"]:
            tools.append({"type": "code_interpreter"})
        # Attach file_search for txt/docx/pdf
        if ftype.lower() in ["txt", "docx", "pdf"]:
            tools.append({"type": "file_search"})
        # Optionally, also attach code_interpreter for txt/docx/pdf if you want code execution
        if ftype.lower() in ["txt", "docx", "pdf"]:
            tools.append({"type": "code_interpreter"})
        attachments.append({
            "file_id": fid, 
            "tools": tools
        })
    print("Attachments for OpenAI message:", attachments)
    
    # Add file information to message if needed
    file_info_message = ""
    if file_ids:
        file_descriptions = []
        for i, fid in enumerate(file_ids):
            name = file_names[i] if i < len(file_names) else f"file {i+1}"
            ftype = file_types[i] if i < len(file_types) else "unknown type"
            file_descriptions.append(f"'{name}' ({ftype})")
        
        file_list_str = ', '.join(file_descriptions)
        file_info_message = (
            f"I've attached the following files: {file_list_str}. "
            "Please analyze these files to help answer my question. "
        )
        
        print(f"[Assistant] Attaching {len(file_ids)} files: {file_list_str}")
    
    # Add user messages to thread
    for idx, m in enumerate(messages):
        if m["role"] == "user":
            content = m["content"]
            
            # For the most recent message, add file info if available
            if idx == len(messages) - 1 and file_info_message:
                content = f"{file_info_message}\n\n{content}"
                
            # Create message with attachments if this is the last message
            kwargs = {
                "thread_id": thread_id,
                "role": "user",
                "content": content
            }
            
            # Only attach files to the last message
            if attachments and idx == len(messages) - 1:
                kwargs["attachments"] = attachments
                
            openai.beta.threads.messages.create(**kwargs)
    
    # Clear file session data after use
    for key in ["openai_file_ids", "openai_file_names", "openai_file_types"]:
        if key in session:
            del session[key]
            session.modified = True

    # Run the assistant
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        stream=True
    )

    # Stream the response
    buffer = ""
    for event in run:
        if hasattr(event, 'data') and hasattr(event.data, 'delta') and getattr(event.data.delta, 'content', None):
            delta = event.data.delta.content
            if isinstance(delta, list):
                parts = []
                for part in delta:
                    value = getattr(getattr(part, 'text', None), 'value', None)
                    if value is not None:
                        parts.append(value)
                    else:
                        parts.append(str(part))
                delta = ''.join(parts)
            buffer += delta
            if len(buffer) >= 20 or buffer.endswith(('.', '!', '?', '\n')):
                yield json.dumps({"chunk": buffer}) + "\n"
                buffer = ""
    if buffer:
        yield json.dumps({"chunk": buffer}) + "\n"


def stream_ai_response(messages, user_id, system_messages=None):
    provider = current_app.config.get('MODEL_PROVIDER', 'anthropic')
    print(f"Using provider: {provider}")
    
    if provider == 'anthropic':
        api_key = current_app.config.get('CLAUDE_API_KEY')
        client = anthropic.Anthropic(
            api_key=api_key,
            default_headers={
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31"
            }
        )
        message_args = {
            "model": current_app.config.get('CLAUDE_MODEL'),
            "max_tokens": current_app.config.get('CLAUDE_MAX_TOKENS', 8192),
            "messages": messages,
        }
        if system_messages:
            message_args["system"] = system_messages
        with stream_claude_response(client, message_args, user_id) as stream:
            buffer = ""
            for text in stream.text_stream:
                buffer += text
                if len(buffer) >= 20 or text.endswith(('.', '!', '?', '\n')):
                    yield json.dumps({"chunk": buffer}) + "\n"
                    buffer = ""
            if buffer:
                yield json.dumps({"chunk": buffer}) + "\n"
    elif provider == 'openai':
        openai.api_key = current_app.config.get('OPENAI_API_KEY')
        assistant_id = current_app.config.get('OPENAI_ASSISTANT_ID')
        yield from stream_openai_assistant(messages, user_id, assistant_id)
    else:
        yield json.dumps({"error": "Invalid MODEL_PROVIDER setting."}) + "\n"


def stream_openai_chat_completion(messages, system_prompt=None):
    """Stream response from OpenAI ChatCompletion endpoint (not Assistant API), compatible with openai>=1.0.0"""
    from openai import OpenAI
    client = OpenAI(api_key=current_app.config.get('OPENAI_API_KEY'))
    model = current_app.config.get('OPENAI_CHAT_MODEL', 'gpt-4o')
    openai_messages = []
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    for m in messages:
        openai_messages.append({"role": m["role"], "content": m["content"]})
    response = client.chat.completions.create(
        model=model,
        messages=openai_messages,
        stream=True,
        temperature=0.7
    )
    buffer = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content if chunk.choices[0].delta else None
        if delta:
            buffer += delta
            if len(buffer) >= 20 or buffer.endswith((".", "!", "?", "\n")):
                yield json.dumps({"chunk": buffer}) + "\n"
                buffer = ""
    if buffer:
        yield json.dumps({"chunk": buffer}) + "\n"


# Routes
@chat_bp.route('/')
@login_required
def index_page():
    """Render the main chat page at root URL"""
    # Remove welcome message initialization from session
    session['chat_history'] = []  # Initialize with empty history
    session['user_id'] = str(uuid.uuid4())
    return render_template('index.html')

# Keep this route as a redirect to maintain backward compatibility
@chat_bp.route('/chat')
@login_required
def chat_page():
    """Redirect to the main page"""
    return redirect(url_for('chat_bp.index_page'))


@chat_bp.route('/api/new_chat', methods=['POST'])
@csrf.exempt
@login_required
def new_chat():
    """Initialize a new chat interface without creating a database record"""
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        print(f"[DEBUG] /api/new_chat received project_id: {project_id}")
        print(f"[DEBUG] /api/new_chat current_user.id: {current_user.id}")

        if not project_id:
            return json.dumps({"error": "Project ID is required"}), 400

        # Verify project exists and belongs to user
        project = Project.query.filter_by(
            id=project_id,
            user_id=current_user.id
        ).first()

        if not project:
            print(f"[DEBUG] /api/new_chat: No project found for id={project_id} and user_id={current_user.id}")
            return json.dumps({"error": "Invalid project"}), 404

        # Clear session data without creating database record
        session['current_session_id'] = None
        session['chat_history'] = []
        # Clear any file-related session variables (always clear on new chat)
        for key in ['openai_file_ids', 'openai_file_names', 'openai_file_types']:
            if key in session:
                del session[key]
        session.modified = True

        # List of 12 advanced, expert-focused quick start offers (documentary filmmaking)
        suggested_questions_pool = [
            "Let's outline a multi-threaded narrative structure for your documentary.",
            "Let's design a shot list optimized for vérité and hybrid shooting styles.",
            "Let's set up a metadata tagging system for your raw footage.",
            "Let's draft a festival submission strategy targeting top-tier documentary festivals.",
            "Let's develop a workflow for integrating archival and newly shot material.",
            "Let's build a detailed post-production schedule with color grading and sound design milestones.",
            "Let's create a plan for managing complex releases and subject consent forms.",
            "Let's prepare a pitch deck with visual references and impact statements.",
            "Let's review advanced interview techniques for sensitive or high-profile subjects.",
            "Let's strategize a multi-platform distribution rollout for maximum audience reach.",
            "Let's set up a collaborative editing environment for remote team workflows.",
            "Let's analyze your budget for potential cost-saving opportunities in international shoots."
        ]
        random_selected_questions = random.sample(suggested_questions_pool, 2)
        static_question = "What were we discussing recently?"
        
        # Create personalized welcome message
        welcome_message = f"""<img src='{url_for('static', filename='img/ACACIA_sq.png')}' alt='ACACIA Icon' style='height: 2em; width: 2em; border-radius: 50%; vertical-align: middle; margin-right: 0.5em;'> <b>Hi there!</b> I'm ACACIA, your intelligent production assistant. What can I help you with?

<div class=\"suggested-questions\">\n    <button class=\"suggested-question\" onclick=\"submitSuggestedQuestion('{random_selected_questions[0]}')\">{random_selected_questions[0]}</button>\n    <button class=\"suggested-question\" onclick=\"submitSuggestedQuestion('{random_selected_questions[1]}')\">{random_selected_questions[1]}</button>\n    <button class=\"suggested-question\" onclick=\"submitSuggestedQuestion('{static_question}')\">{static_question}</button>\n</div>"""

        return json.dumps({
            "status": "success",
            "welcome_message": welcome_message
        }), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        print(f"Error initializing new chat: {str(e)}")
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/chat', methods=['POST'])
@csrf.exempt
@login_required
def chat():
    """Handle chat messages and responses"""
    try:
        print("\n=== Starting Chat Request ===")
        data = request.get_json()
        prompt = data.get('prompt')
        document_ids = data.get('documentIds', [])
        project_id = data.get('project_id')
        using_documents = bool(document_ids)
        if not project_id:
            return json.dumps({"error": "Project ID is required"}), 400
        # --- Insert system_prompt here ---
        system_prompt = """
You are MONT-E, a professional Documentary Film Production Assistant dedicated to supporting filmmakers at Nomad Films in all aspects of their documentary production work. Your expertise covers proposal writing, script development, production logistics, budgeting, storyboarding, editing workflows, and marketing strategies. Your purpose is to help documentary filmmakers achieve their creative vision efficiently, ethically, and with maximum impact.

When responding:
1. Always begin your response by acknowledging the filmmaker's question or request.
2. Provide clear, actionable advice tailored to the specific documentary project, production phase, or creative challenge.
3. Incorporate documentary filmmaking best practices, ethical standards, and industry trends in your suggestions.
4. Be concise and direct, while offering enough detail to be immediately useful.
5. When appropriate, explain the reasoning and methodology behind your recommendations.
6. Respond primarily in full sentences, using bullet points and lists sparingly.
7. Organize longer responses with clear headings and structure for easy reading.
8. Offer examples or templates where helpful, especially for proposals, scripts, shot lists, or marketing materials.
9. Proactively identify potential gaps or opportunities in production plans, narrative structures, or distribution strategies.
For documentary project and strategy questions:
- Suggest effective production approaches and techniques (e.g., observational, interview-based, archival, hybrid styles).
- Consider the project's subject matter, resources, and target audience.
- Recommend ways to structure narrative and communicate impact.

For subject engagement and ethics:
- Advise on building and maintaining ethical relationships with documentary subjects.
- Suggest personalized approaches for different types of interviews and subject interactions.
- Highlight ways to ensure authentic representation and informed consent.

For proposal and grant writing:
- Provide guidance on crafting compelling documentary treatments and pitches.
- Suggest ways to align proposals with funder priorities and festival requirements.
- Offer tips for clear, persuasive writing and strong supporting visual materials.

When reviewing materials or production plans:
- Help position the documentary's story in a compelling, audience-engaging way.
- Identify strengths and areas for improvement in narrative structure, visual approach, or technical execution.
- Suggest ways to increase clarity, emotional resonance, and thematic depth.

After providing your response, conclude with a thoughtful follow-up question that:
- Encourages the filmmaker to consider next steps or alternative approaches.
- Invites them to share more about their creative vision, technical challenges, or audience.
- Suggests ways to deepen storytelling impact or distribution effectiveness.

Remember: Your goal is to empower documentary filmmakers to succeed, balancing creativity with proven techniques, and always upholding the ethical standards of documentary practice.

Areas of expertise include:
- Documentary storytelling and narrative structure
- Production planning and logistics
- Interview techniques and subject engagement
- Visual style and cinematography approaches
- Editing and post-production workflows
- Impact campaigns and distribution strategies
- Documentary ethics and best practices

IMPORTANT! When processing production data, budgets, or any tabular information, you must follow these strict protocols:

    1. ALWAYS perform careful data validation before any calculations:
    - Check and report data types for each column
    - Identify and report missing values, zeroes, or null entries
    - Detect outliers or anomalous values that could skew results
    - Verify date formats are consistent before temporal analysis

    2. For ALL numeric calculations:
    - Process values individually and explicitly, never relying on mental approximations
    - Show intermediate calculation steps when the operation involves more than 20 values
    - For averages, calculate the exact sum first, then divide by the precise count
    - Round only at the final step, maintaining full precision throughout calculations
    - When reporting percentages, show both the percentage and the raw counts

    3. When aggregating data:
    - Use precise counting mechanisms for each group or category
    - Verify totals match across different calculation methods
    - Double-check that group counts sum to the total record count
    - For complex operations, break calculations into distinct steps

    4. Before presenting final results:
    - Verify that all mathematical operations balance correctly
    - Confirm that record counts in aggregations match the source data
    - Cross-check calculations using alternative methods when possible
    - Report any processing challenges that might affect accuracy

    5. For financial or sensitive numeric data:
    - Preserve exact decimal precision through all calculations
    - Avoid floating point approximations for currency values
    - Use appropriate aggregation methods based on the statistical properties of the data
    - Report sample sizes alongside all summary statistics

    CRITICAL DATA PROCESSING PROTOCOL:            

    1. Data Validation (MANDATORY BEFORE CALCULATION)

    Identify and report the data type of each column (numeric, text, date, etc.).

    Explicitly count and report:  

    Total number of data rows (excluding headers and blanks).  

    Number and location of missing, zero, or null values in numeric columns.

    Scan for outliers or anomalous values that could affect results; report any found.

    Verify consistency of date formats before any temporal grouping or analysis.

    Confirm that the column used for calculations contains only valid numeric entries; ignore or flag any non-numeric or corrupted data.

    2. Numeric Calculations (STRICT SEQUENCE)

    Process each numeric value individually and explicitly—never estimate or infer.

    Show all intermediate steps for sums, averages, or aggregations involving more than 20 values.

    For sums:  

    Add each value step-by-step, showing running totals in batches of 20.

    Report both subtotal and final total.

    For averages:  

    Calculate the exact sum first, then divide by the precise count of valid entries.

    Rounding:  

    Preserve full decimal precision through all steps; round only in the final answer (to two decimal places for currency).

    Percentages:  

    Always show both the raw counts and the calculated percentage.

    3. Aggregation and Grouping

    Use precise, explicit counting for each group/category.

    Ensure group subtotals sum exactly to the full dataset total; report if there is any discrepancy.

    For complex operations:  

    Break calculations into clear, stepwise components.

    Show how each subtotal is derived.

    4. Pre-Result Verification (BEFORE OUTPUT)

    Check that all mathematical operations are correct and balanced.

    Confirm that the number of processed records matches the reported total row count.

    Cross-validate totals using a secondary method (e.g., manual sample, formula check).

    Clearly report any issues, anomalies, or uncertainties that may affect the accuracy of results.

    5. Financial and Sensitive Data

    Maintain exact decimal precision for all currency or financial values.

    Avoid floating point approximations—use string-to-decimal conversion where possible.

    Report the sample size (number of included transactions) alongside all summary statistics.

    Flag and explain any records excluded from calculations (e.g., due to invalid data).

    6. Output Reporting

    State the final result with explicit reference to the total number of rows and any exclusions.

    Include a summary of data validation findings (missing values, outliers, etc.).

    Provide a reproducible calculation trail (e.g., subtotal breakdowns, formulas used).

    REMINDER:
    Never skip validation or intermediate steps, even if the operation appears simple. Always prioritize accuracy, transparency, and reproducibility.

When discussing a topic that has been previously discussed with a filmmaker, remind them that you have previously discussed this topic and provide a very short summary.

Do not repeat or summarize previous questions and answers from the current session unless the filmmaker requests it. You may use the provided user memory to inform your response if the filmmaker asks about their production history or recurring topics.
"""

        # Get or create chat session
        session_id = session.get('current_session_id')
        if not session_id:
            # This is the first message in a new chat, create the session
            session_id = str(uuid.uuid4())
            session['current_session_id'] = session_id
            chat_session = ChatSession(
                user_id=current_user.id,
                project_id=project_id,
                session_id=session_id,
                model=current_app.config.get('CLAUDE_MODEL'),
                chat_history='[]'
            )
            db.session.add(chat_session)
            db.session.commit()
        else:
            chat_session = ChatSession.query.filter_by(
                user_id=current_user.id,
                session_id=session_id,
                project_id=project_id
            ).first()

            if not chat_session:
                # Session ID exists but no database record - create it
                chat_session = ChatSession(
                    user_id=current_user.id,
                    project_id=project_id,
                    session_id=session_id,
                    model=current_app.config.get('CLAUDE_MODEL'),
                    chat_history='[]'
                )
                db.session.add(chat_session)
                db.session.commit()

        # Get project and its system instructions
        project = Project.query.get(project_id)
        if not project:
            return json.dumps({"error": "Invalid project"}), 404

        # Get documents content only if document_ids is provided
        documents_content = ""
        spreadsheet_attached = False
        if document_ids:
            documents = Document.query.filter(
                Document.id.in_(document_ids),
                Document.user_id == current_user.id,
                Document.project_id == project_id
            ).all()

            if documents:
                documents_content = f"\n\n===== REFERENCE DOCUMENTS ({len(documents)}) =====\n\n"
                for doc in documents:
                    print(f"[DOC DEBUG] Filename: {doc.filename}, Content type: {type(doc.content)}, First 100 chars: {doc.content[:100] if doc.content else 'EMPTY'}")
                    documents_content += f"Document: {doc.filename}\n"
                    documents_content += f"Content:\n{doc.content}\n"
                    documents_content += "=" * 50 + "\n"
                    if doc.file_type.lower() in ["csv", "xls", "xlsx"]:
                        spreadsheet_attached = True
            else:
                using_documents = False

        # Build system prompt with user memory and user background
        user_memory = get_user_memory(current_user.id)
        user_background = generate_user_background(current_user.id)
        system_prompt_full = ""
        if user_memory:
            system_prompt_full += (
                "==== USER MEMORY: SUMMARY OF PREVIOUS CONVERSATIONS ===="
                f"\n{user_memory}\n"
                "==== END OF USER MEMORY ====\n\nYou may use the above summary ONLY if the user asks about their history, previous topics, or recurring themes. "
                "Otherwise, focus on the current request. Do not let this memory override or distract from the user's current question or request.\n\n"
            )
        if user_background:
            system_prompt_full += (
                "==== USER PROFILE CONTEXT ===="
                f"\n{user_background}\n"
                "==== END OF USER PROFILE CONTEXT ====\n\n"
            )

        # Add research capability instructions
        system_prompt_full += """
You have access to a research tool powered by Perplexity AI that can help with documentary research. 
When a user asks for research on a topic, you should:

1. Identify if the request requires research (e.g., "research about X", "find information on Y", "what do we know about Z")
2. If research is needed, respond with a special format:
   [RESEARCH_REQUEST]
   topic: [the topic to research]
   focus_areas: [optional list of specific aspects to focus on]
   [/RESEARCH_REQUEST]

3. After receiving research results, synthesize them into a clear, documentary-focused response that includes:
   - Key historical context
   - Main figures or subjects
   - Current relevance
   - Potential visual elements
   - Notable controversies
   - Related documentary films

Remember to maintain your role as a documentary production assistant while incorporating research findings.
"""

        system_prompt_full += system_prompt

        provider = current_app.config.get('MODEL_PROVIDER', 'anthropic')
        system_messages = [{"type": "text", "text": system_prompt_full}]

        # Only add document content as a system message for Claude
        if provider == 'anthropic':
            if documents_content:
                system_messages.append({"type": "text", "text": documents_content, "cache_control": {"type": "ephemeral"}})
        else:
            # For OpenAI, do NOT add documents_content to system_messages
            if not documents_content:
                # No documents selected, add a system message reminder
                system_messages.append({
                    "type": "text",
                    "text": "No documents are currently attached. Please answer based only on your general knowledge."
                })

        # Debug print system messages
        print("=== SYSTEM MESSAGES SENT TO LLM ===")
        for msg in system_messages:
            print(msg)

        # Prepare messages for the model
        chat_history = json.loads(chat_session.chat_history) if chat_session.chat_history else []
        messages = []
        for msg in chat_history:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        current_message = {
            "role": "user",
            "content": prompt
        }
        messages.append(current_message)
        chat_history.append(current_message)
        chat_session.chat_history = json.dumps(chat_history)
        db.session.commit()

        def generate_and_save():
            full_ai_response = ""
            try:
                if spreadsheet_attached:
                    # Route to OpenAI Assistant API (code interpreter)
                    for chunk in stream_ai_response(messages, current_user.id, [{"type": "text", "text": system_prompt_full}]):
                        try:
                            data = json.loads(chunk)
                            if 'chunk' in data:
                                full_ai_response += data['chunk']
                        except Exception:
                            pass
                        yield chunk
                else:
                    # Route to OpenAI ChatCompletion endpoint
                    for chunk in stream_openai_chat_completion(messages, system_prompt_full):
                        try:
                            data = json.loads(chunk)
                            if 'chunk' in data:
                                full_ai_response += data['chunk']
                        except Exception:
                            pass
                        yield chunk
            finally:
                if full_ai_response.strip():
                    chat_history.append({
                        "role": "assistant",
                        "content": full_ai_response
                    })
                    chat_session.chat_history = json.dumps(chat_history)
                    db.session.commit()

        return Response(
            stream_with_context(generate_and_save()),
            content_type='text/event-stream'
        )
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        traceback.print_exc()
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/chats', methods=['GET'])
@csrf.exempt
@login_required
def list_chats():
    """List all chats for the current project"""
    try:
        project_id = request.args.get('project_id', type=int)
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        query = ChatSession.query.filter_by(
            user_id=current_user.id,
            project_id=project_id
        ).order_by(
            db.desc(ChatSession.pinned),
            db.desc(ChatSession.updated_at)
        )

        chat_sessions = query.all()
        chats = []

        for chat in chat_sessions:
            try:
                chat_history = chat.get_chat_history()
                preview = "New Chat"
                if chat_history and len(chat_history) > 0:
                    preview = chat_history[0]['content']
                    preview = preview[:100] + '...' if len(preview) > 100 else preview

                chats.append({
                    'id': chat.id,
                    'session_id': chat.session_id,
                    'preview': preview,
                    'pinned': chat.pinned,
                    'created_at': chat.created_at.isoformat(),
                    'updated_at': chat.updated_at.isoformat()
                })

            except Exception as e:
                print(f"Error processing chat {chat.id}: {str(e)}")
                continue

        return json.dumps({"chats": chats}), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        print(f"Error listing chats: {str(e)}")
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/chats/<session_id>', methods=['GET'])
@csrf.exempt
@login_required
def load_chat(session_id):
    """Load a specific chat session"""
    try:
        # Clear any file-related session variables (always clear on chat load)
        for key in ['openai_file_ids', 'openai_file_names', 'openai_file_types']:
            if key in session:
                del session[key]
        session.modified = True

        chat_session = ChatSession.query.filter_by(
            user_id=current_user.id,
            session_id=session_id
        ).first_or_404()

        # Load chat history into session
        chat_history_key = f'chat_history_{current_user.id}'
        session[chat_history_key] = chat_session.get_chat_history()
        session['current_session_id'] = session_id
        session.modified = True

        return json.dumps({
            'status': 'success',
            'chat_history': chat_session.get_chat_history()
        }), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        print(f"Error loading chat: {str(e)}")
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/chats/<session_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_chat(session_id):
    """Delete a chat session"""
    try:
        chat_session = ChatSession.query.filter_by(
            user_id=current_user.id,
            session_id=session_id
        ).first_or_404()

        # Check if this was the current chat
        was_current_chat = session.get('current_session_id') == session_id

        # Delete the chat
        db.session.delete(chat_session)
        db.session.commit()

        # Clear session if this was the current chat
        if was_current_chat:
            chat_history_key = f'chat_history_{current_user.id}'
            session[chat_history_key] = []
            session['current_session_id'] = None
            session.modified = True

        return json.dumps({
            'status': 'success',
            'message': 'Chat deleted successfully',
            'was_current_chat': was_current_chat
        }), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        print(f"Error deleting chat: {str(e)}")
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/chats/<session_id>/toggle-pin', methods=['POST'])
@csrf.exempt
@login_required
def toggle_pin(session_id):
    """Toggle pin status of a chat session"""
    try:
        chat_session = ChatSession.query.filter_by(
            user_id=current_user.id,
            session_id=session_id
        ).first_or_404()

        chat_session.pinned = not chat_session.pinned
        db.session.commit()

        return json.dumps({
            'status': 'success',
            'pinned': chat_session.pinned
        }), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        print(f"Error toggling pin: {str(e)}")
        return json.dumps({"error": str(e)}), 500


@chat_bp.route('/api/download/openai/<file_id>')
@login_required
def download_openai_file(file_id):
    api_key = current_app.config.get('OPENAI_API_KEY')
    url = f'https://api.openai.com/v1/files/{file_id}/content'
    headers = {'Authorization': f'Bearer {api_key}'}
    r = requests.get(url, headers=headers, stream=True)
    if r.status_code == 200:
        return send_file(BytesIO(r.content), download_name=f'{file_id}.png', mimetype='image/png')
    else:
        return jsonify({'error': 'File not found'}), 404


def upload_document_to_openai(document):
    """Upload a document to OpenAI and return the file ID"""
    try:
        # Create a temp file
        with tempfile.NamedTemporaryFile(suffix=f".{document.file_type or 'txt'}", delete=False) as temp:
            temp.write(document.content)  # <-- Write binary content directly!
            temp_path = temp.name
        
        # Upload to OpenAI
        openai.api_key = current_app.config.get('OPENAI_API_KEY')
        with open(temp_path, 'rb') as file:
            response = openai.files.create(
                file=file,
                purpose="assistants"
            )
        
        # Clean up temp file
        os.unlink(temp_path)
        
        return {
            'file_id': response.id,
            'filename': document.filename,
            'file_type': document.file_type or 'txt'
        }
    except Exception as e:
        print(f"Error uploading document to OpenAI: {str(e)}")
        raise


@chat_bp.route('/api/select_document', methods=['POST'])
@csrf.exempt
@login_required
def select_document():
    """Handle document selection for OpenAI (multi-select safe)"""
    try:
        data = request.get_json()
        document_id = data.get('document_id')
        selected = data.get('selected', True)
        
        if not document_id:
            return jsonify({"error": "Document ID required"}), 400
            
        # Get the document
        document = Document.query.filter_by(
            id=document_id, 
            user_id=current_user.id
        ).first()
        
        if not document:
            return jsonify({"error": "Document not found"}), 404
            
        if selected:
            print(f"Uploading file to OpenAI for doc id: {document_id}")
            # Upload to OpenAI
            file_info = upload_document_to_openai(document)
            
            # Store the file ID in session (multi-select safe)
            file_ids = session.get('openai_file_ids', [])
            file_names = session.get('openai_file_names', [])
            file_types = session.get('openai_file_types', [])
            if file_info['file_id'] not in file_ids:
                file_ids.append(file_info['file_id'])
                file_names.append(file_info['filename'])
                file_types.append(file_info['file_type'])
            session['openai_file_ids'] = file_ids
            session['openai_file_names'] = file_names
            session['openai_file_types'] = file_types
            session.modified = True
            print("Session openai_file_ids after select:", session['openai_file_ids'])
            
            return jsonify({
                "status": "success", 
                "message": f"Document {document.filename} uploaded to OpenAI"
            }), 200
        else:
            # Remove only the deselected document's file info (multi-select safe)
            file_ids = session.get('openai_file_ids', [])
            file_names = session.get('openai_file_names', [])
            file_types = session.get('openai_file_types', [])
            # Find the file_id for this document (by filename and user/project)
            # We'll need to look up the OpenAI file_id for this document
            # For safety, remove by filename
            remove_idx = None
            for idx, name in enumerate(file_names):
                if name == document.filename:
                    remove_idx = idx
                    break
            if remove_idx is not None:
                file_ids.pop(remove_idx)
                file_names.pop(remove_idx)
                file_types.pop(remove_idx)
            session['openai_file_ids'] = file_ids
            session['openai_file_names'] = file_names
            session['openai_file_types'] = file_types
            session.modified = True
            
            return jsonify({
                "status": "success",
                "message": "Document deselected"
            }), 200
        
    except Exception as e:
        print(f"Error selecting document: {str(e)}")
        return jsonify({"error": str(e)}), 500


@chat_bp.route('/api/upload', methods=['POST'])
@csrf.exempt
@login_required
def upload_document():
    """Upload a document, preventing duplicates by filename/user/project."""
    try:
        # 1. Check for file and project_id in the request
        if 'file' not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
        file = request.files['file']
        project_id = request.form.get('project_id')
        if not project_id:
            return jsonify({"error": "Project ID is required"}), 400

        # 2. Get filename and file type
        filename = file.filename
        if not filename:
            return jsonify({"error": "No selected file"}), 400
        file_type = filename.split('.')[-1].lower()

        # 3. Read file content (once)
        file_bytes = file.read()
        file_size = len(file_bytes)

        # Enforce backend file size limit from config
        max_file_size = current_app.config.get('MAX_FILE_SIZE_BYTES', 1 * 1024 * 1024)
        if file_size > max_file_size:
            return jsonify({"error": f"File exceeds {max_file_size // (1024 * 1024)}MB size limit"}), 400

        # Improved .txt handling: decode and debug
        if file_type == 'txt':
            import chardet
            detected = chardet.detect(file_bytes)
            print(f"[TXT UPLOAD] Detected encoding: {detected}")
            try:
                content = file_bytes.decode(detected['encoding'])
            except Exception as e:
                print(f"[TXT UPLOAD] Failed to decode with detected encoding: {e}")
                try:
                    content = file_bytes.decode('utf-8')
                    print("[TXT UPLOAD] Decoded with utf-8 fallback.")
                except Exception as e2:
                    print(f"[TXT UPLOAD] Failed to decode with utf-8: {e2}")
                    content = file_bytes.decode('latin1', errors='replace')
                    print("[TXT UPLOAD] Decoded with latin1 fallback.")
            print(f"[TXT UPLOAD] First 100 chars: {content[:100]}")
        else:
            # No decoding! Store as binary for non-txt
            content = file_bytes

        # 4. Prevent duplicate uploads (same filename/user/project)
        existing_doc = Document.query.filter_by(
            filename=filename,
            user_id=current_user.id,
            project_id=project_id
        ).first()

        if existing_doc:
            document = existing_doc
            # Optionally update content if you want to allow overwriting
            # document.content = content
            # db.session.commit()
        else:
            document = Document(
                filename=filename,
                user_id=current_user.id,
                project_id=project_id,
                file_type=file_type,
                file_size=file_size,
                content=content
            )
            db.session.add(document)
            db.session.commit()

        # 5. Return document info
        return jsonify({
            "status": "success",
            "documentId": document.id,
            "document": {
                "id": document.id,
                "filename": document.filename,
                "file_type": document.file_type,
                "file_size": document.file_size
            }
        }), 200

    except Exception as e:
        print(f"Error uploading document: {str(e)}")
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@chat_bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_document(doc_id):
    try:
        document = Document.query.filter_by(
            id=doc_id,
            user_id=current_user.id
        ).first_or_404()

        # Remove file info from session if present
        file_names = session.get('openai_file_names', [])
        file_ids = session.get('openai_file_ids', [])
        file_types = session.get('openai_file_types', [])
        remove_idx = None
        for idx, name in enumerate(file_names):
            if name == document.filename:
                remove_idx = idx
                break
        if remove_idx is not None:
            file_names.pop(remove_idx)
            file_ids.pop(remove_idx)
            file_types.pop(remove_idx)
            session['openai_file_names'] = file_names
            session['openai_file_ids'] = file_ids
            session['openai_file_types'] = file_types
            session.modified = True

        db.session.delete(document)
        db.session.commit()

        return jsonify({"status": "success", "message": "Document deleted"}), 200
    except Exception as e:
        print(f"Error deleting document: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Removed example usage of append_spreadsheet_data_to_message to prevent FileNotFoundError

@chat_bp.route('/profile', methods=['GET'])
@login_required
def profile():
    """Display user profile page"""
    survey = UserSurvey.query.filter_by(user_id=current_user.id).first()
    return render_template('profile.html', survey=survey)

@chat_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information"""
    try:
        # Update user fields
        current_user.firstname = request.form.get('firstname')
        current_user.lastname = request.form.get('lastname')
        current_user.org_name = request.form.get('org_name')
        
        # Update or create survey
        survey = UserSurvey.query.filter_by(user_id=current_user.id).first()
        if not survey:
            survey = UserSurvey(user_id=current_user.id)
            db.session.add(survey)
        
        survey.job_title = request.form.get('job_title')
        survey.primary_responsibilities = request.form.get('primary_responsibilities')
        survey.top_priorities = request.form.get('top_priorities')
        survey.special_interests = request.form.get('special_interests')
        survey.learning_goals = request.form.get('learning_goals')
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating profile. Please try again.', 'error')
        print(f"Error updating profile: {str(e)}")
    
    return redirect(url_for('chat_bp.profile'))

