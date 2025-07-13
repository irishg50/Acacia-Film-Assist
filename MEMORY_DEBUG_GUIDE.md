# Project Memory Debug Guide

## Issue Analysis
The project memory system isn't working as expected. Here's a systematic approach to diagnose and fix the issue.

## Step 1: Check Current Memory State

### 1.1 Check if Project Memory Exists
Run this SQL query to see if any project memory exists:

```sql
SELECT 
    pm.id,
    pm.project_id,
    p.name as project_name,
    pm.memory_text,
    pm.last_updated,
    pm.last_chat_count
FROM nomadchat_project_memory pm
JOIN nomadchat_project p ON pm.project_id = p.id
WHERE p.user_id = [YOUR_USER_ID];
```

### 1.2 Check Chat Sessions
Run this SQL query to see chat sessions for your test project:

```sql
SELECT 
    cs.id,
    cs.session_id,
    cs.chat_history,
    cs.created_at,
    cs.updated_at
FROM nomadchat_chatsession cs
JOIN nomadchat_project p ON cs.project_id = p.id
WHERE p.name = 'Test Project 1' 
AND p.user_id = [YOUR_USER_ID]
ORDER BY cs.created_at;
```

## Step 2: Manual Memory Trigger

### 2.1 Force Memory Update
You can manually trigger a project memory update using the API endpoint:

```bash
curl -X POST "http://localhost:5000/api/projects/[PROJECT_ID]/memory" \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: [YOUR_CSRF_TOKEN]"
```

### 2.2 Check Memory Content
Get the current memory content:

```bash
curl -X GET "http://localhost:5000/api/projects/[PROJECT_ID]/memory" \
  -H "X-CSRFToken: [YOUR_CSRF_TOKEN]"
```

## Step 3: Debug the Memory System

### 3.1 Add Debug Logging
Add these debug prints to `app/services/project_memory_service.py`:

```python
def get_project_memory(project_id):
    """
    Get project memory text for use in system prompts
    """
    print(f"[DEBUG] Getting project memory for project_id: {project_id}")
    
    memory = ProjectMemory.query.filter_by(project_id=project_id).first()
    if not memory:
        print(f"[DEBUG] No project memory found for project_id: {project_id}")
        return None
    
    print(f"[DEBUG] Found project memory: {memory.memory_text[:200]}...")
    
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
    
    print(f"[DEBUG] Returning formatted memory: {memory_text[:200]}...")
    return memory_text
```

### 3.2 Add Debug Logging to Chat Route
Add this debug print to `app/routes/chat_routes.py` in the chat function:

```python
# Build system prompt with user memory, user background, and project memory
user_memory = get_user_memory(current_user.id)
user_background = generate_user_background(current_user.id)
project_memory = get_project_memory(project_id)

print(f"[DEBUG] Project memory retrieved: {project_memory[:200] if project_memory else 'None'}...")

system_prompt_full = ""

# Add project memory context
if project_memory:
    system_prompt_full += (
        "==== PROJECT CONTEXT ===="
        f"\n{project_memory}\n"
        "==== END OF PROJECT CONTEXT ====\n\n"
        "**Use this project context to:**\n"
        "- Align recommendations with project goals and timeline\n"
        "- Reference relevant previous discussions and decisions\n"
        "- Build upon established strategies and progress\n\n"
    )
    print(f"[DEBUG] Added project memory to system prompt")
else:
    print(f"[DEBUG] No project memory to add to system prompt")
```

## Step 4: Quick Fix - Force Memory Creation

### 4.1 Create a Test Script
Create a file called `debug_memory.py` in your project root:

```python
#!/usr/bin/env python3
"""
Debug script to force create project memory
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.models import Project, ChatSession, ProjectMemory
from app.services.project_memory_service import generate_project_memory, get_project_memory
from flask_login import current_user

app = create_app()

def debug_project_memory():
    with app.app_context():
        # Find your test project
        project = Project.query.filter_by(name='Test Project 1').first()
        if not project:
            print("Test Project 1 not found!")
            return
        
        print(f"Found project: {project.name} (ID: {project.id})")
        
        # Check existing memory
        existing_memory = ProjectMemory.query.filter_by(project_id=project.id).first()
        if existing_memory:
            print(f"Existing memory found: {existing_memory.memory_text[:200]}...")
        else:
            print("No existing memory found")
        
        # Check chat sessions
        chat_sessions = ChatSession.query.filter_by(project_id=project.id).all()
        print(f"Found {len(chat_sessions)} chat sessions")
        
        for i, session in enumerate(chat_sessions):
            print(f"Session {i+1}: {session.session_id}")
            chat_history = session.get_chat_history()
            print(f"  Messages: {len(chat_history)}")
            for msg in chat_history:
                print(f"    {msg['role']}: {msg['content'][:100]}...")
        
        # Force create memory
        print("\nForcing memory creation...")
        try:
            memory = generate_project_memory(project.id)
            if memory:
                print(f"Memory created successfully: {memory.memory_text[:200]}...")
            else:
                print("Failed to create memory")
        except Exception as e:
            print(f"Error creating memory: {e}")
            import traceback
            traceback.print_exc()
        
        # Test retrieval
        print("\nTesting memory retrieval...")
        retrieved_memory = get_project_memory(project.id)
        if retrieved_memory:
            print(f"Retrieved memory: {retrieved_memory[:200]}...")
        else:
            print("Failed to retrieve memory")

if __name__ == "__main__":
    debug_project_memory()
```

### 4.2 Run the Debug Script
```bash
python debug_memory.py
```

## Step 5: Potential Issues and Fixes

### 5.1 Issue: Memory Update Logic Too Restrictive
**Problem**: Memory only updates after 3+ sessions or 24+ hours
**Fix**: Modify the update logic in `app/services/project_memory_service.py`:

```python
def should_update_project_memory(project_id):
    """
    Check if project memory should be updated based on smart logic:
    - 1+ new chat sessions since last update, OR  # Changed from 3+
    - 1+ hours have passed since last update, OR  # Changed from 24+
    - Force update is requested
    """
    memory = ProjectMemory.query.filter_by(project_id=project_id).first()
    if not memory:
        return True  # No memory exists, create it
    
    # Check if 1+ hours have passed  # Changed from 24+
    if datetime.utcnow() - memory.last_updated > timedelta(hours=1):  # Changed from 24
        return True
    
    # Count new chat sessions since last update
    new_sessions = ChatSession.query.filter(
        ChatSession.project_id == project_id,
        ChatSession.created_at > memory.last_updated
    ).count()
    
    # Update if 1+ new sessions  # Changed from 3+
    if new_sessions >= 1:  # Changed from 3
        return True
    
    return False
```

### 5.2 Issue: Background Processing Fails Silently
**Problem**: Memory updates run in background and fail without notification
**Fix**: Add better error handling in `app/routes/chat_routes.py`:

```python
# Background project memory update (non-blocking)
try:
    # Trigger project memory update in background
    print(f"[DEBUG] Starting background memory update for project {project_id}")
    memory_result = get_incremental_project_memory(project_id)
    if memory_result:
        print(f"[DEBUG] Memory update successful: {memory_result.memory_text[:100]}...")
    else:
        print(f"[DEBUG] Memory update returned None")
except Exception as e:
    print(f"[DEBUG] Background project memory update failed: {e}")
    import traceback
    traceback.print_exc()
    # Continue with chat even if memory update fails
```

### 5.3 Issue: Memory Not Being Retrieved
**Problem**: Memory exists but isn't being retrieved properly
**Fix**: Add explicit memory retrieval in chat route:

```python
# Build system prompt with user memory, user background, and project memory
user_memory = get_user_memory(current_user.id)
user_background = generate_user_background(current_user.id)

# Force memory retrieval with debug info
print(f"[DEBUG] Attempting to get project memory for project_id: {project_id}")
project_memory = get_project_memory(project_id)
print(f"[DEBUG] Project memory result: {'Found' if project_memory else 'None'}")

if not project_memory:
    print(f"[DEBUG] No project memory found, attempting to create...")
    try:
        get_incremental_project_memory(project_id)
        project_memory = get_project_memory(project_id)
        print(f"[DEBUG] After creation attempt: {'Found' if project_memory else 'Still None'}")
    except Exception as e:
        print(f"[DEBUG] Error creating memory: {e}")
```

## Step 6: Test the Fix

### 6.1 Run the Test Again
1. Create a new chat session
2. Tell the system: "My documentary is about climate change in the Arctic, and my main character is Dr. Sarah Chen, a marine biologist."
3. Start a new chat session
4. Ask: "What is my documentary about and who is my main character?"

### 6.2 Check the Logs
Look for the debug messages in your console/logs to see:
- Whether memory is being created
- Whether memory is being retrieved
- What content is in the memory
- Whether the memory is being added to the system prompt

## Step 7: Alternative Quick Test

If the above doesn't work, you can manually test the memory system by:

1. **Direct Database Check**: Look directly in the database to see if chat sessions are being saved
2. **Manual Memory Creation**: Use the debug script to force create memory
3. **API Testing**: Use the memory API endpoints to manually trigger updates

## Expected Results

After implementing these fixes, you should see:
- Debug messages showing memory creation and retrieval
- Project memory being included in the system prompt
- The AI correctly recalling information from previous sessions

If you're still having issues, the debug output will help identify exactly where the problem is occurring. 