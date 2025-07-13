-- Nomad Chatbot Database Schema
-- PostgreSQL script to create all tables

-- Drop existing tables if they exist (be careful with this in production!)
DROP TABLE IF EXISTS nomadchat_research_session CASCADE;
DROP TABLE IF EXISTS nomadchat_user_survey CASCADE;
DROP TABLE IF EXISTS nomadchat_user_agreement CASCADE;
DROP TABLE IF EXISTS nomadchat_project_memory CASCADE;
DROP TABLE IF EXISTS nomadchat_user_chat_memory CASCADE;
DROP TABLE IF EXISTS nomadchat_document_chunks CASCADE;
DROP TABLE IF EXISTS nomadchat_documents CASCADE;
DROP TABLE IF EXISTS nomadchat_chatsession CASCADE;
DROP TABLE IF EXISTS nomadchat_project CASCADE;
DROP TABLE IF EXISTS nomadchat_login_record CASCADE;
DROP TABLE IF EXISTS nomadchat_api_log CASCADE;
DROP TABLE IF EXISTS nomadchat_users CASCADE;
DROP TABLE IF EXISTS nomadchat_organization CASCADE;

-- Create Organization table
CREATE TABLE nomadchat_organization (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    domain VARCHAR(100) UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for Organization
CREATE INDEX ix_organization_name ON nomadchat_organization (name);
CREATE INDEX ix_organization_domain ON nomadchat_organization (domain);

-- Create User table
CREATE TABLE nomadchat_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    firstname VARCHAR(75),
    lastname VARCHAR(75),
    signup_date TIMESTAMP,
    is_active BOOLEAN DEFAULT FALSE,
    org_name VARCHAR(150),
    email_address VARCHAR(75),
    agreement_date TIMESTAMP,
    agreement_text TEXT,
    organization_id INTEGER REFERENCES nomadchat_organization(id)
);

-- Create indexes for User
CREATE INDEX ix_users_organization_id ON nomadchat_users (organization_id);
CREATE INDEX ix_users_username ON nomadchat_users (username);

-- Create LoginRecord table
CREATE TABLE nomadchat_login_record (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    login_time TIMESTAMP NOT NULL
);

-- Create APILog table
CREATE TABLE nomadchat_api_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prompt TEXT,
    message TEXT,
    completion_tokens INTEGER,
    prompt_tokens INTEGER,
    cache_tokens INTEGER,
    model VARCHAR(50),
    thread_id VARCHAR(100),
    user_id INTEGER REFERENCES nomadchat_users(id) ON DELETE SET NULL
);

-- Create Project table
CREATE TABLE nomadchat_project (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    system_instructions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create ChatSession table
CREATE TABLE nomadchat_chatsession (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES nomadchat_project(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL,
    model VARCHAR(50) NOT NULL,
    chat_history TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pinned BOOLEAN DEFAULT FALSE
);

-- Create Document table
CREATE TABLE nomadchat_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES nomadchat_project(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size INTEGER NOT NULL,
    content TEXT,
    content_preview VARCHAR(1000),
    total_chunks INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_processed BOOLEAN DEFAULT FALSE,
    processing_error TEXT
);

-- Create DocumentChunk table
CREATE TABLE nomadchat_document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES nomadchat_documents(id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create UserChatMemory table
CREATE TABLE nomadchat_user_chat_memory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create ProjectMemory table
CREATE TABLE nomadchat_project_memory (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE REFERENCES nomadchat_project(id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    status VARCHAR(100),
    goals TEXT,
    timeline TEXT,
    key_topics TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_chat_count INTEGER DEFAULT 0
);

-- Create UserAgreement table
CREATE TABLE nomadchat_user_agreement (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content_markdown TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create UserSurvey table
CREATE TABLE nomadchat_user_survey (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    job_title VARCHAR(100),
    primary_responsibilities TEXT,
    top_priorities TEXT,
    special_interests TEXT,
    learning_goals TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create ResearchSession table
CREATE TABLE nomadchat_research_session (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES nomadchat_users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES nomadchat_project(id) ON DELETE CASCADE,
    topic VARCHAR(255) NOT NULL,
    focus_areas TEXT,
    research_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    perplexity_response TEXT
);

-- Create additional indexes for performance
CREATE INDEX ix_chatsession_user_id ON nomadchat_chatsession (user_id);
CREATE INDEX ix_chatsession_project_id ON nomadchat_chatsession (project_id);
CREATE INDEX ix_chatsession_session_id ON nomadchat_chatsession (session_id);
CREATE INDEX ix_chatsession_created_at ON nomadchat_chatsession (created_at);

CREATE INDEX ix_documents_user_id ON nomadchat_documents (user_id);
CREATE INDEX ix_documents_project_id ON nomadchat_documents (project_id);
CREATE INDEX ix_documents_filename ON nomadchat_documents (filename);

CREATE INDEX ix_document_chunks_document_id ON nomadchat_document_chunks (document_id);
CREATE INDEX ix_document_chunks_chunk_number ON nomadchat_document_chunks (chunk_number);

CREATE INDEX ix_project_user_id ON nomadchat_project (user_id);
CREATE INDEX ix_project_name ON nomadchat_project (name);

CREATE INDEX ix_api_log_user_id ON nomadchat_api_log (user_id);
CREATE INDEX ix_api_log_timestamp ON nomadchat_api_log (timestamp);

CREATE INDEX ix_login_record_user_id ON nomadchat_login_record (user_id);
CREATE INDEX ix_login_record_login_time ON nomadchat_login_record (login_time);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
CREATE TRIGGER update_organization_updated_at BEFORE UPDATE ON nomadchat_organization FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_project_updated_at BEFORE UPDATE ON nomadchat_project FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_chatsession_updated_at BEFORE UPDATE ON nomadchat_chatsession FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON nomadchat_documents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_survey_updated_at BEFORE UPDATE ON nomadchat_user_survey FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_research_session_updated_at BEFORE UPDATE ON nomadchat_research_session FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default organization if needed
INSERT INTO nomadchat_organization (name, description) 
VALUES ('Default Organization', 'Default organization for system users')
ON CONFLICT (name) DO NOTHING;

-- Grant permissions (adjust as needed for your database user)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_database_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_database_user;

COMMIT; 