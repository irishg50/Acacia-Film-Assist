import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Security settings
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'your_secret_key')
    WTF_CSRF_ENABLED = True

    # Upload settings
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit
    MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB limit (adjustable)

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///nomad_chat.db')
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # API keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')
    OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
    print("Loaded OPENAI_ASSISTANT_ID:", OPENAI_ASSISTANT_ID)

    # Multi-model provider setting
    MODEL_PROVIDER = os.getenv('MODEL_PROVIDER', 'openai')  # 'anthropic' or 'openai'

    # Model settings
    OPENAI_MODEL = "gpt-4.1-mini"
    OPENAI_SUMMATION_MODEL = "gpt-4.1-nano"
    OPENAI_MAX_TOKENS = 16384  # Increased from 4096 for better response quality
    OPENAI_CHAT_MODEL = "gpt-4.1-mini"  # Add explicit chat model setting
    OPENAI_CHAT_MAX_TOKENS = 16384  # Higher limit for chat completions
    CLAUDE_MODEL = "claude-3-7-sonnet-20250219"
    CLAUDE_MAX_TOKENS = 16384
    GEMINI_MODEL = "gemini-1"
    GEMINI_MAX_TOKENS = 2048

    CLAUDE_CHAT_MODEL = "claude-3-7-sonnet-20250219"
    CLAUDE_CHAT_MAX_TOKENS = 16384

    # Project memory settings
    PROJECT_MEMORY_UPDATE_HOURS = 24  # How often to update long-term memory
    PROJECT_MEMORY_UPDATE_SESSIONS = 3  # How many sessions before updating memory
    RECENT_CONTEXT_HOURS = 24  # How far back to look for recent context
    RECENT_CONTEXT_MAX_MESSAGES = 50  # Max messages to include in recent context

    PROMO_CODES = ["FoundationAIconf", "BuildGoodAI"]

    if not OPENAI_API_KEY:
        raise ValueError("No OpenAI API key provided. Set the OPENAI_API_KEY environment variable")

    WTF_CSRF_ENABLED = False  # Temporary disable for testing