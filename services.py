import os
import fitz  # PyMuPDF
import docx
import textstat
import textract
from openai import OpenAI
import time
from flask import current_app
from app.models.models import db, APILog
from anthropic import Anthropic
import google.generativeai as genai
import tiktoken
import re
from typing import Dict, Any

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_file_contents(file_paths):
    contents = []
    for file_path in file_paths:
        file_ext = file_path.rsplit('.', 1)[1].lower()

        try:
            if file_ext == 'txt':
                with open(file_path, 'r', encoding='utf-8') as file:
                    contents.append(file.read())
            elif file_ext == 'pdf':
                with fitz.open(file_path) as doc:
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    contents.append(text)
            elif file_ext in ['doc', 'docx']:
                doc = docx.Document(file_path)
                text = "\n".join([para.text for para in doc.paragraphs])
                contents.append(text)
            else:
                # For other file types, use textract
                text = textract.process(file_path).decode('utf-8')
                contents.append(text)

        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin1') as file:
                    contents.append(file.read())
            except Exception as e:
                contents.append(f"Could not read file {file_path}: {e}")
        except Exception as e:
            contents.append(f"Could not process file {file_path}: {e}")

    return "\n\n".join(contents)




def generate_openai_response(prompt, temperature, chat_history, file_contents, session, user_id):
    client = OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
    assistant_id = current_app.config['ASSISTANT_ID']

    try:
        # Retrieve or create thread_id
        if 'openai_thread_id' not in session:
            thread = client.beta.threads.create()
            thread_id = thread.id
            session['openai_thread_id'] = thread_id
            session['documents_uploaded'] = False
            print(f"\nNew thread created: {thread_id}")
        else:
            thread_id = session['openai_thread_id']
            print(f"\nUsing existing thread: {thread_id}")

        print("\n--- OpenAI API Request ---")
        print(f"Assistant ID: {assistant_id}")
        print(f"Thread ID: {thread_id}")
        print(f"Temperature: {temperature}")

        print("\nChat History:")
        for message in chat_history:
            print(f"Role: {message['role']}")
            print(f"Content: {message['content'][:100]}...")  # Print first 100 chars of content

        print("\nPrompt:")
        print(prompt)

        # Only append file contents if they haven't been uploaded in this thread
        if file_contents and not session.get('documents_uploaded', False):
            prompt += f"\n\nConsider the following information from the uploaded files:\n{file_contents}"
            session['documents_uploaded'] = True
            print("\nFile contents added to the prompt.")
        elif file_contents:
            print("\nFile contents already uploaded in this thread, skipping re-upload.")
        else:
            print("\nNo file contents to upload.")

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )

        print(f"\nMessage added to thread: {thread_id}")

        try:
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                temperature=temperature
            )
            print(f"\nRun created: {run.id}")
        except Exception as e:
            print(f"\nError creating run: {str(e)}")
            return str(e)

        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            print(f"\nRun status: {run_status.status}")
            if run_status.status == 'completed':
                break
            elif run_status.status == "failed":
                print(f"Run failed: {run_status.last_error}")
                break
            time.sleep(2)

        log_entry = APILog(
            prompt=prompt,
            completion_tokens=run_status.usage.completion_tokens,
            prompt_tokens=run_status.usage.prompt_tokens,
            cache_tokens=0 if session.get('documents_uploaded', False) else run_status.usage.prompt_tokens,  # New field
            model=run_status.model,
            thread_id=thread_id,
        user_id=user_id
        )
        db.session.add(log_entry)
        db.session.commit()

        # Print the token usage
        print(f"\nToken Usage: {run_status.usage}")

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        assistant_response = messages.data[0].content[0].text.value

        print("\nAssistant Response (first 200 characters):")
        print(assistant_response[:200] + "...")

        print("\n--- End of OpenAI API Request ---\n")

        return assistant_response

    except Exception as e:
        print(f"\nError in generate_openai_response: {str(e)}")
        return str(e)

# Global variable to track if file contents have been sent
file_contents_sent = False


def count_tokens(text):
    """Count the number of tokens in a given text."""
    try:
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")  # This should work for Claude too
        return len(encoding.encode(text))
    except Exception as e:
        print(f"Error in token counting: {str(e)}")
        return 0


def generate_claude_response(prompt, temperature, chat_history, file_contents, session_id, file_contents_sent, user_id):
    client = Anthropic(
        api_key=current_app.config['CLAUDE_API_KEY'],
        default_headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31"
        }
    )

    try:
        print("\n--- Claude API Request ---")
        print(f"Temperature: {temperature}")
        print(f"Session ID: {session_id}")

        data = {
            "model": "claude-3-5-sonnet-20240620",
            "max_tokens": 2000,
            "temperature": temperature,
            "system": [
                {
                    "type": "text",
                    "text": "You are an AI assistant. Provide helpful, detailed, and accurate responses."
                }
            ],
            "messages": []
        }

        file_token_count = count_tokens(file_contents) if file_contents else 0
        if file_contents:
            file_instruction = ("The following content is from uploaded files. "
                                "Use this information when responding to queries. "
                                "Incorporate relevant details from these files into your answers:\n\n")
            file_content_with_instruction = file_instruction + file_contents

            if not file_contents_sent:
                data["system"].append({
                    "type": "text",
                    "text": file_content_with_instruction,
                    "cache_control": {"type": "ephemeral"}
                })
                print(f"\nFile Contents added to system with instruction. Token count: {file_token_count}")
                file_contents_sent = True
            else:
                print("\nFile contents already sent in previous request. Relying on cache.")
        else:
            print("\nNo file contents included.")

        # Process chat history to ensure strict alternation between user and assistant
        processed_messages = []
        expected_role = 'user'  # Start with user role
        for message in chat_history:
            if message['role'] == expected_role:
                processed_messages.append({
                    "role": message['role'],
                    "content": message['content']
                })
                expected_role = 'assistant' if expected_role == 'user' else 'user'
            elif message['role'] == 'assistant' and expected_role == 'user':
                # If we expect a user message but get an assistant message, skip it
                continue
            elif message['role'] == 'user' and expected_role == 'assistant':
                # If we expect an assistant message but get a user message,
                # add a placeholder assistant message
                processed_messages.append({
                    "role": 'assistant',
                    "content": "I understand. How can I assist you further?"
                })
                processed_messages.append({
                    "role": 'user',
                    "content": message['content']
                })
                expected_role = 'assistant'

        # Ensure the last message is from the user
        if not processed_messages or processed_messages[-1]['role'] == 'assistant':
            processed_messages.append({
                "role": "user",
                "content": prompt
            })
        else:
            # If the last message is already from the user, append the new prompt to it
            processed_messages[-1]['content'] += f"\n\n{prompt}"

        data["messages"] = processed_messages

        print("\nProcessed Messages:")
        for msg in data["messages"]:
            print(f"Role: {msg['role']}, Content: {msg['content'][:50]}...")

        # Make the API call to Claude
        response = client.messages.create(**data)

        assistant_response = response.content[0].text

        print("\nAssistant Response (first 200 characters):")
        print(assistant_response[:200] + "...")

        # Calculate and log the API usage
        non_file_input_tokens = response.usage.input_tokens
        total_input_tokens = non_file_input_tokens + (file_token_count if not file_contents_sent else 0)
        cache_tokens = file_token_count if file_contents_sent else 0

        print(f"\nToken Usage:")
        print(f"  Input tokens (excluding file contents): {non_file_input_tokens}")
        print(f"  File content tokens: {file_token_count} ({'sent' if not file_contents_sent else 'cached'})")
        print(f"  Total input tokens: {total_input_tokens}")
        print(f"  Output tokens: {response.usage.output_tokens}")
        print(f"  Cached tokens: {cache_tokens}")

        # Log the API call
        log_entry = APILog(
            prompt=prompt,
            completion_tokens=response.usage.output_tokens,
            prompt_tokens=total_input_tokens,
            cache_tokens=cache_tokens,
            model=response.model,
            thread_id=session_id,
            user_id=user_id
        )

        db.session.add(log_entry)
        db.session.commit()

        print("\n--- End of Claude API Request ---\n")

        return assistant_response, file_contents_sent

    except Exception as e:
        print(f"\nError in generate_claude_response: {str(e)}")
        return str(e), file_contents_sent


def generate_gemini_response(prompt, temperature, chat_history, file_contents, session_id, file_contents_sent,
                             is_first_gemini_request, user_id):
    try:
        api_key = current_app.config.get('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in the application configuration or environment variables")

        genai.configure(api_key=api_key)

        print("\n--- Google Gemini API Request ---")
        print(f"Temperature: {temperature}")
        print(f"Session ID: {session_id}")
        print(f"File contents sent status at start: {file_contents_sent}")
        print(f"Chat history length: {len(chat_history)}")
        print(f"Is first Gemini request: {is_first_gemini_request}")

        model = genai.GenerativeModel('gemini-1.5-pro')

        def count_tokens(text):
            try:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
                return len(encoding.encode(text))
            except Exception as e:
                print(f"Error in token counting: {str(e)}")
                return 0

        messages = []

        file_token_count = count_tokens(file_contents) if file_contents else 0

        # Calculate tokens for chat history
        chat_history_tokens = sum(count_tokens(message['content']) for message in chat_history)

        if is_first_gemini_request and file_contents:
            file_instruction = ("The following content is from uploaded files. "
                                "Use this information when responding to queries. "
                                "Incorporate relevant details from these files into your answers:\n\n")
            file_content_with_instruction = file_instruction + file_contents

            messages.append({
                "role": "user",
                "parts": [{"text": file_content_with_instruction}]
            })
            print(f"\nFile Contents added to chat. Token count: {file_token_count}")
            file_contents_sent = True
        elif file_contents and file_contents_sent:
            print(
                f"\nFile contents already sent in previous request. Relying on cached content. Cached token count: {file_token_count}")
        else:
            print("\nNo file contents included.")

        # Process chat history
        for message in chat_history:
            messages.append({
                "role": "user" if message['role'] == 'user' else "model",
                "parts": [{"text": message['content']}]
            })

        # Add the current prompt
        messages.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        print("\nChat History:")
        for message in chat_history:
            print(f"Role: {message['role']}")
            print(f"Content: {message['content'][:100]}...")  # Print first 100 chars of content

        print("\nPrompt:")
        print(prompt)

        print("\nFinal messages structure:")
        for msg in messages:
            print(f"Role: {msg['role']}, Content: {msg['parts'][0]['text'][:50]}...")

        # Generate the response
        response = model.generate_content(
            messages,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=2000,
            )
        )

        assistant_response = response.text

        print("\nAssistant Response (first 200 characters):")
        print(assistant_response[:200] + "...")

        # Calculate and log the API usage
        prompt_tokens = count_tokens(prompt)
        completion_tokens = count_tokens(assistant_response)

        if is_first_gemini_request:
            total_input_tokens = prompt_tokens + chat_history_tokens + file_token_count
            cache_tokens = 0
        else:
            total_input_tokens = prompt_tokens + chat_history_tokens
            cache_tokens = file_token_count if file_contents_sent else 0

        print(f"\nEstimated Token Usage:")
        print(f"  Input tokens (including chat history): {total_input_tokens}")
        print(f"  Chat history tokens: {chat_history_tokens}")
        print(f"  Current prompt tokens: {prompt_tokens}")
        print(f"  Output tokens: {completion_tokens}")
        print(f"  Cached tokens: {cache_tokens}")

        log_entry = APILog(
            prompt=prompt,
            completion_tokens=completion_tokens,
            prompt_tokens=total_input_tokens,
            cache_tokens=cache_tokens,
            model='gemini-1.5-pro',
            thread_id=session_id,
            user_id=user_id
        )

        db.session.add(log_entry)
        db.session.commit()

        print(f"\nFile contents sent status at end: {file_contents_sent}")
        print("\n--- End of Google Gemini API Request ---\n")

        return assistant_response, file_contents_sent

    except Exception as e:
        print(f"\nError in generate_gemini_response: {str(e)}")
        return str(e), file_contents_sent

def reset_file_contents_sent():
    global file_contents_sent
    file_contents_sent = False




def get_sentence_context(text: str, word: str) -> str:
    """Extract the full sentence containing the matched word"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sentence in sentences:
        if word.lower() in sentence.lower():
            return sentence.strip()
    return word  # fallback to just the word if sentence not found