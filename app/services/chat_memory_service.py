from app.models.models import ChatSession, UserChatMemory
from app.extensions import db
from datetime import datetime
import openai

def generate_user_memory(user_id):
    memory = UserChatMemory.query.filter_by(user_id=user_id).first()
    last_update = memory.last_updated if memory else None

    # Only fetch new chat sessions since last update
    query = ChatSession.query.filter_by(user_id=user_id)
    if last_update:
        query = query.filter(ChatSession.created_at > last_update)
    new_sessions = query.order_by(ChatSession.created_at).all()

    if not new_sessions:
        return memory  # No update needed

    # Gather all previous memory (if any)
    previous_memory = memory.memory_text if memory else ""
    # Gather new chat content
    new_messages = []
    for session in new_sessions:
        new_messages.extend(session.get_chat_history())
    new_history_text = '\n'.join(
        f"{msg['role'].capitalize()}: {msg['content']}" for msg in new_messages
    )

    # Summarize: combine previous memory and new history
    if previous_memory:
        summary_input = previous_memory + '\n' + new_history_text
    else:
        summary_input = new_history_text
    summary = summarize_with_llm(summary_input)

    if not memory:
        memory = UserChatMemory(user_id=user_id, memory_text=summary, last_updated=datetime.utcnow())
        db.session.add(memory)
    else:
        memory.memory_text = summary
        memory.last_updated = datetime.utcnow()
    db.session.commit()
    return memory

def summarize_with_llm(history_text):
    prompt = (
        "Summarize the key topics, facts, and user preferences from the following chat history. "
        "Be concise, do not include sensitive information, and focus on recurring themes or important details:\n\n"
        f"{history_text}"
    )
    client = openai.OpenAI()  # Assumes API key is set in environment or config
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=512,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()

def get_user_memory(user_id):
    memory = UserChatMemory.query.filter_by(user_id=user_id).first()
    return memory.memory_text if memory else None 