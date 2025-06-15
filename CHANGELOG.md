# Changelog

## [Unreleased]

### Added
- **User Chat History Memory**: The system now summarizes each user's previous chat sessions and injects a memory summary into the assistant's context. This enables the assistant to reference past topics, preferences, and recurring questions when appropriate.
- **User Memory in System Prompt**: The system prompt and OpenAI Assistant instructions now include guidance for referencing user memory, including a new instruction to remind users when a previously discussed topic is revisited, with a short summary.
- **Chat UI Improvements**: Chat history now scrolls within the available window, and the chat request area is pinned to the bottom for a modern chat experience. Messages alternate between user and AI in a single scrollable area.

### Changed
- **System Prompt and Assistant Instructions**: Updated to clarify when and how user memory should be referenced, and to avoid repeating or summarizing previous questions unless requested.

## [POC Prototype] - 2024-04-20

### Added
- **Promotion Code Security Gate**: Signup now requires a valid promotion code before the registration form is shown.
- **Secure User Signup**: Public registration form for new users, with validation for unique username and email.
- **Default Project Creation**: Every new user automatically receives a "General Chat" project upon signup or admin creation.
- **Admin Approval Workflow**: New users are inactive by default and require admin approval before they can log in. Admin dashboard includes signup approval and rejection tools.
- **Signup Modal**: Bootstrap modal prompts for promotion code before signup.
- **Navigation Improvements**: "Sign Up" link added for unauthenticated users; navigation bar updated for clarity and access control.
- **Session Management**: Improved session handling for file uploads and chat sessions.
- **Blueprint Refactor**: Public routes (like signup) moved to a dedicated `public_bp` blueprint for clarity and security.

### Fixed
- **Foreign Key Violations**: Ensured chat sessions cannot be created without a valid project, preventing database errors.
- **File Upload Session Bugs**: Cleared session variables on new uploads to prevent duplicate/phantom file issues.
- **Route Registration**: Ensured all API and public routes are properly registered and accessible.
- **Login Authentication**: Restored and improved login authentication, including password hash checks and user activation status.

### Changed
- **Template Structure**: Scripts are now loaded in the correct `{% block scripts %}` for better performance and maintainability.
- **Admin User Creation**: Admin-created users also receive a default project.
- **User Feedback**: Improved flash messages and error handling throughout the signup and login process.

### Removed
- Deprecated or duplicate files and routes (e.g., old chat.html, arc/ directory).

---

This release marks the POC (Proof of Concept) prototype checkpoint for TAL-E. The system now supports secure onboarding, project management, and a robust chat foundation for further development. 