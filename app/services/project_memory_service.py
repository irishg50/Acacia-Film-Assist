from app.models.models import ChatSession, ProjectMemory, Project, Document
from app.extensions import db
from datetime import datetime, timedelta
import openai
import json

def should_update_project_memory(project_id):
    """
    Check if project memory should be updated based on smart logic:
    - 3+ new chat sessions since last update, OR
    - 24+ hours have passed since last update, OR
    - Force update is requested
    """
    memory = ProjectMemory.query.filter_by(project_id=project_id).first()
    if not memory:
        return True  # No memory exists, create it
    
    # Check if 24+ hours have passed
    if datetime.utcnow() - memory.last_updated > timedelta(hours=24):
        return True
    
    # Count new chat sessions since last update
    new_sessions = ChatSession.query.filter(
        ChatSession.project_id == project_id,
        ChatSession.created_at > memory.last_updated
    ).count()
    
    # Update if 3+ new sessions
    if new_sessions >= 3:
        return True
    
    return False

def get_incremental_project_memory(project_id):
    """
    Get project memory with smart update logic
    """
    memory = ProjectMemory.query.filter_by(project_id=project_id).first()
    if not memory:
        return generate_project_memory(project_id)
    
    if should_update_project_memory(project_id):
        return update_project_memory_incrementally(project_id, memory)
    
    return memory

def generate_project_memory(project_id):
    """
    Generate initial project memory from project info and existing chat sessions
    """
    project = Project.query.get(project_id)
    if not project:
        return None
    
    # Gather project info and chat history
    project_info = f"Project: {project.name}\nDescription: {project.description or 'No description'}\nSystem Instructions: {project.system_instructions or 'None'}"
    
    chat_sessions = ChatSession.query.filter_by(project_id=project_id).order_by(ChatSession.created_at).all()
    chat_history = []
    for session in chat_sessions:
        chat_history.extend(session.get_chat_history())
    
    # Gather document info
    documents = Document.query.filter_by(project_id=project_id).all()
    document_info = ""
    if documents:
        document_info = f"\n\nDocuments ({len(documents)}):\n"
        for doc in documents:
            document_info += f"- {doc.filename} ({doc.file_type})\n"
    
    # Create comprehensive memory
    memory_content = project_info + document_info
    if chat_history:
        chat_text = '\n'.join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history])
        memory_content += f"\n\nChat History:\n{chat_text}"
    
    # Generate structured memory using LLM
    structured_memory = generate_structured_project_memory(memory_content, project.name)
    
    # Create memory record
    memory = ProjectMemory(
        project_id=project_id,
        memory_text=structured_memory['memory_text'],
        status=structured_memory.get('status'),
        goals=structured_memory.get('goals'),
        timeline=structured_memory.get('timeline'),
        key_topics=structured_memory.get('key_topics'),
        last_updated=datetime.utcnow(),
        last_chat_count=len(chat_sessions)
    )
    
    db.session.add(memory)
    db.session.commit()
    return memory

def update_project_memory_incrementally(project_id, existing_memory):
    """
    Update project memory incrementally with only new content
    """
    # Get new content since last update
    new_sessions = ChatSession.query.filter(
        ChatSession.project_id == project_id,
        ChatSession.created_at > existing_memory.last_updated
    ).order_by(ChatSession.created_at).all()
    
    new_documents = Document.query.filter(
        Document.project_id == project_id,
        Document.created_at > existing_memory.last_updated
    ).all()
    
    if not new_sessions and not new_documents:
        return existing_memory  # No new content
    
    # Gather new content
    new_content = ""
    if new_sessions:
        new_messages = []
        for session in new_sessions:
            new_messages.extend(session.get_chat_history())
        new_content += f"\n\nNew Chat Content:\n"
        new_content += '\n'.join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in new_messages])
    
    if new_documents:
        new_content += f"\n\nNew Documents:\n"
        for doc in new_documents:
            new_content += f"- {doc.filename} ({doc.file_type})\n"
    
    # Combine with existing memory and update
    combined_content = existing_memory.memory_text + new_content
    updated_memory = generate_structured_project_memory(combined_content, existing_memory.project.name)
    
    # Update existing memory
    existing_memory.memory_text = updated_memory['memory_text']
    existing_memory.status = updated_memory.get('status', existing_memory.status)
    existing_memory.goals = updated_memory.get('goals', existing_memory.goals)
    existing_memory.timeline = updated_memory.get('timeline', existing_memory.timeline)
    existing_memory.key_topics = updated_memory.get('key_topics', existing_memory.key_topics)
    existing_memory.last_updated = datetime.utcnow()
    existing_memory.last_chat_count = ChatSession.query.filter_by(project_id=project_id).count()
    
    db.session.commit()
    return existing_memory

def generate_structured_project_memory(content, project_name):
    """
    Generate structured project memory using LLM
    """
    prompt = f"""
Create a comprehensive, structured summary of this documentary project based on the provided content. 
Focus on documentary filmmaking context and organize the information clearly.

Project: {project_name}

Content to analyze:
{content}

Please provide a structured response in the following JSON format:
{{
    "memory_text": "A comprehensive summary of the project, key discussions, decisions, and current status",
    "status": "Current project status (e.g., 'Pre-production', 'Production', 'Post-production', 'Distribution')",
    "goals": "Main project goals and objectives",
    "timeline": "Key timeline information and deadlines",
    "key_topics": "Important topics, themes, or subjects discussed"
}}

Focus on documentary filmmaking context and be concise but comprehensive.
"""
    
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )
        
        result = response.choices[0].message.content.strip()
        
        # Try to parse JSON response
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            # Fallback to simple text if JSON parsing fails
            return {
                "memory_text": result,
                "status": None,
                "goals": None,
                "timeline": None,
                "key_topics": None
            }
            
    except Exception as e:
        print(f"Error generating structured memory: {e}")
        # Fallback to simple summary
        return {
            "memory_text": f"Project memory for {project_name}. Content available but structured analysis failed.",
            "status": None,
            "goals": None,
            "timeline": None,
            "key_topics": None
        }

def get_project_memory(project_id):
    """
    Get project memory text for use in system prompts
    """
    memory = ProjectMemory.query.filter_by(project_id=project_id).first()
    if not memory:
        return None
    
    # Return formatted memory for system prompt
    memory_text = f"PROJECT: {memory.project.name}\n"
    if memory.status:
        memory_text += f"STATUS: {memory.status}\n"
    if memory.goals:
        memory_text += f"GOALS: {memory.goals}\n"
    if memory.timeline:
        memory_text += f"TIMELINE: {memory.timeline}\n"
    if memory.key_topics:
        memory_text += f"KEY TOPICS: {memory.key_topics}\n"
    memory_text += f"\nPROJECT MEMORY:\n{memory.memory_text}"
    
    return memory_text 