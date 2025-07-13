// Constants and Global State
const baseUrl = window.location.origin;
let isFirstAIMessage = true;
let currentAIMessage = '';
let isProcessing = false;
let currentProject = null;
let projectModal = null;
let editingProjectId = null;
let deleteModal = null;
let chatToDelete = null;
let allChats = []; // Store all chats for search functionality

const allowedTypes = ['.txt', '.pdf', '.doc', '.docx', '.csv', '.xlsx'];
const maxFileSize = window.MAX_FILE_SIZE_BYTES || (10 * 1024 * 1024); // 10MB default
const maxFiles = 4;

let thinkingInterval = null;

// Document Management System
const documentStore = {
    documents: new Map(),
    activeDocuments: new Set(),

    async uploadDocument(file, projectId) {
        if (!this.validateFile(file)) return;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('project_id', projectId);

        try {
            const response = await fetch(`${baseUrl}/api/upload`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken()
                },
                body: formData,
                credentials: 'same-origin'
            });

            const data = await response.json();

            if (!response.ok || data.error) {
                throw new Error(data.error || 'Error uploading file');
            }

            // Add the new document to the store
            this.documents.set(data.documentId, data.document);
            // Automatically select the new document as active
            this.activeDocuments.add(data.documentId);
            await this.refreshDocumentList(projectId);
            this.updateCheckboxes();
            this.toggleDocument(data.documentId, true);
            // addMessageToChatHistory('System', `Uploaded: ${data.document.filename}`);
        } catch (error) {
            console.error('Error uploading document:', error);
            addMessageToChatHistory('System', `Error uploading file: ${error.message}`);
        }
    },

    validateFile(file) {
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

        if (file.size > maxFileSize) {
            addMessageToChatHistory('System', `Error: ${file.name} exceeds 10MB size limit`);
            return false;
        }

        if (!allowedTypes.includes(fileExtension)) {
            addMessageToChatHistory('System',
                `Error: ${file.name} is not an allowed file type. Allowed types: ${allowedTypes.join(', ')}`);
            return false;
        }

        return true;
    },

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    getFileTypeIcon(fileType) {
        const icons = {
            'csv': '📊',
            'xlsx': '📈',
            'txt': '📄',
            'pdf': '📑',
            'doc': '📝',
            'docx': '📝'
        };
        return icons[fileType] || '📄';
    },

    updateDocumentCountDisplay() {
        const activeDocButtons = document.getElementById('activeDocButtons');
        if (!activeDocButtons) return;
        activeDocButtons.innerHTML = '';
        if (this.activeDocuments.size === 0) {
            const noDocs = document.createElement('span');
            noDocs.className = 'text-muted';
            noDocs.textContent = 'No active documents';
            activeDocButtons.appendChild(noDocs);
            return;
        }
        this.getActiveDocumentIds().forEach(docId => {
            const doc = this.documents.get(docId);
            if (!doc) return;
            const btn = document.createElement('button');
            btn.className = 'active-doc-btn';
            // Truncate name to 20 chars, add ellipsis if needed
            let truncated = doc.filename;
            if (truncated.length > 20) truncated = truncated.slice(0, 17) + '...';
            btn.textContent = truncated;
            btn.title = doc.filename;
            btn.type = 'button';
            btn.style.position = 'relative';
            // Remove (x) icon
            const remove = document.createElement('span');
            remove.className = 'remove-doc-x';
            remove.innerHTML = '&times;';
            remove.title = 'Remove';
            remove.style.display = 'none';
            remove.style.position = 'absolute';
            remove.style.right = '4px';
            remove.style.top = '2px';
            remove.style.cursor = 'pointer';
            remove.onclick = (e) => {
                e.stopPropagation();
                this.toggleDocument(docId, false);
                this.updateDocumentCountDisplay();
                this.updateCheckboxes();
            };
            btn.appendChild(remove);
            btn.onmouseenter = () => { remove.style.display = 'inline'; };
            btn.onmouseleave = () => { remove.style.display = 'none'; };
            activeDocButtons.appendChild(btn);
        });
    },

    async refreshDocumentList(projectId) {
        try {
            const response = await fetch(`${baseUrl}/api/documents?project_id=${projectId}`);
            if (!response.ok) throw new Error('Failed to fetch documents');

            const data = await response.json();
            const uploadedFileList = document.getElementById('uploadedFileList');
            uploadedFileList.innerHTML = '';

            this.documents.clear();
            // this.activeDocuments.clear();

            data.documents.forEach(doc => {
                this.documents.set(doc.id, doc);
                // Do NOT add to activeDocuments here!
                const isActive = this.activeDocuments.has(doc.id); // will be false for all on new chat
                
                const fileDiv = document.createElement('div');
                fileDiv.className = 'file-item';
                fileDiv.setAttribute('data-id', doc.id);
                if (isActive) {
                    fileDiv.classList.add('active');
                }

                fileDiv.innerHTML = `
                    <div class="form-check d-flex align-items-center">
                        <input class="form-check-input document-toggle me-2" type="checkbox" 
                               value="${doc.id}" id="doc-${doc.id}" ${isActive ? 'checked' : ''}>
                        <label class="form-check-label d-flex align-items-center w-100" for="doc-${doc.id}">
                            <span class="file-type-icon">${this.getFileTypeIcon(doc.file_type)}</span>
                            <span class="file-name">${doc.filename}</span>
                        </label>
                        <button class="delete-file-button ms-2" onclick="documentStore.deleteDocument(${doc.id}, ${projectId})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                `;

                uploadedFileList.appendChild(fileDiv);
                
                const checkbox = fileDiv.querySelector('.document-toggle');
                checkbox.addEventListener('change', (e) => {
                    this.toggleDocument(doc.id, e.target.checked);
                });
            });
            
            document.getElementById('selectAllDocs')?.addEventListener('click', () => this.selectAllDocuments());
            document.getElementById('deselectAllDocs')?.addEventListener('click', () => this.deselectAllDocuments());
            
            this.updateDocumentCountDisplay();
            
        } catch (error) {
            console.error('Error refreshing document list:', error);
            addMessageToChatHistory('System', 'Error loading documents: ' + error.message);
        }
    },

    async deleteDocument(docId, projectId) {
        try {
            const response = await fetch(`${baseUrl}/api/documents/${docId}`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to delete document');

            this.documents.delete(docId);
            this.activeDocuments.delete(docId);
            await this.refreshDocumentList(projectId);
        } catch (error) {
            console.error('Error deleting document:', error);
            addMessageToChatHistory('System', 'Error deleting document: ' + error.message);
        }
    },

    toggleDocument(docId, isActive) {
        if (isActive) {
            this.activeDocuments.add(docId);
        } else {
            this.activeDocuments.delete(docId);
        }
        
        const fileItem = document.querySelector(`.file-item[data-id="${docId}"]`);
        if (fileItem) {
            if (isActive) {
                fileItem.classList.add('active');
            } else {
                fileItem.classList.remove('active');
            }
        }
        
        // --- ADD THIS: Call backend to update OpenAI file session ---
        fetch('/api/select_document', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CSRF_TOKEN
            },
            body: JSON.stringify({
                document_id: docId,
                selected: isActive
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log("Document selection updated:", data.message);
            } else {
                console.error("Error:", data.error);
            }
        })
        .catch(error => {
            console.error("Error selecting document:", error);
        });

        this.updateDocumentCountDisplay();
    },
    
    selectAllDocuments() {
        this.documents.forEach((doc, id) => {
            this.activeDocuments.add(id);
        });
        this.updateCheckboxes();
        this.updateDocumentCountDisplay();
    },
    
    deselectAllDocuments() {
        this.activeDocuments.clear();
        this.updateCheckboxes();
        this.updateDocumentCountDisplay();
    },
    
    updateCheckboxes() {
        document.querySelectorAll('.document-toggle').forEach(checkbox => {
            const docId = parseInt(checkbox.value);
            checkbox.checked = this.activeDocuments.has(docId);
            
            const fileItem = checkbox.closest('.file-item');
            if (this.activeDocuments.has(docId)) {
                fileItem.classList.add('active');
            } else {
                fileItem.classList.remove('active');
            }
        });
    },

    getActiveDocumentIds() {
        return Array.from(this.activeDocuments);
    }
};


// Add this to your document toggle handler in chat.js
function toggleDocument(documentId, selected) {
    // Update UI first for responsiveness
    const checkbox = document.querySelector(`input[data-document-id="${documentId}"]`);
    if (checkbox) {
        checkbox.checked = selected;
    }
    
    // Call API to process the document for OpenAI
    fetch('/api/select_document', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN
        },
        body: JSON.stringify({
            document_id: documentId,
            selected: selected
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            console.log("Document selection updated:", data.message);
        } else {
            console.error("Error:", data.error);
        }
    })
    .catch(error => {
        console.error("Error selecting document:", error);
    });
}

// Connect this to your existing document selection UI
document.addEventListener('DOMContentLoaded', function() {
    // Find all document checkboxes and attach event handlers
    const documentCheckboxes = document.querySelectorAll('#uploadedFileList input[type="checkbox"]');
    documentCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const documentId = this.getAttribute('data-document-id');
            const isSelected = this.checked;
            toggleDocument(documentId, isSelected);
        });
    });

    // Toggle All Documents logic
    const toggleAllDocs = document.getElementById('toggleAllDocs');
    if (toggleAllDocs) {
        toggleAllDocs.addEventListener('change', function() {
            const check = this.checked;
            document.querySelectorAll('.document-toggle').forEach(cb => {
                if (cb.checked !== check) {
                    cb.checked = check;
                    cb.dispatchEvent(new Event('change'));
                }
            });
        });
    }

    // Keep toggleAllDocs in sync with individual checkboxes
    function updateToggleAllCheckbox() {
        const all = Array.from(document.querySelectorAll('.document-toggle'));
        if (!all.length) return;
        const checked = all.filter(cb => cb.checked).length;
        toggleAllDocs.checked = checked === all.length;
        toggleAllDocs.indeterminate = checked > 0 && checked < all.length;
    }
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('document-toggle')) {
            updateToggleAllCheckbox();
        }
    });
    // Initial sync
    updateToggleAllCheckbox();

    // Sidebar tabs logic
    const sidebarTabs = document.querySelectorAll('.sidebar-tab');
    const sectionPanes = {
        'doc-library': document.getElementById('doc-library-pane'),
        'chat-history': document.getElementById('chat-history-pane')
    };
    
    function showSidebarPane(selected) {
        // Update tab states
        sidebarTabs.forEach(tab => {
            if (tab.getAttribute('data-pane') === selected) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });
        
        // Show/hide panes
        Object.keys(sectionPanes).forEach(key => {
            if (key === selected) {
                sectionPanes[key].classList.remove('d-none');
            } else {
                sectionPanes[key].classList.add('d-none');
            }
        });
    }
    
    // Add click handlers to tabs
    sidebarTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const pane = this.getAttribute('data-pane');
            showSidebarPane(pane);
        });
    });
    
    // Add search functionality
    const chatSearchInput = document.getElementById('chatSearchInput');
    const clearSearchBtn = document.getElementById('clearSearchBtn');
    
    if (chatSearchInput) {
        let searchTimeout;
        
        // Handle search input
        chatSearchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchChats(this.value);
            }, 300); // Debounce search for 300ms
            
            // Show/hide clear button based on input value
            if (clearSearchBtn) {
                clearSearchBtn.style.display = this.value.trim() ? 'block' : 'none';
            }
        });
        
        // Handle clear button click
        if (clearSearchBtn) {
            clearSearchBtn.addEventListener('click', function() {
                chatSearchInput.value = '';
                chatSearchInput.focus();
                clearSearchBtn.style.display = 'none';
                searchChats(''); // Clear search results
            });
        }
    }
    
    // Show default pane on load
    showSidebarPane('doc-library');
});

// Message Management
function addMessageToChatHistory(sender, message, isHistoryLoad = false) {
    const chatHistoryContainer = document.querySelector('#chatHistory');
    if (!chatHistoryContainer) {
        console.error('Chat history container not found');
        return;
    }

    let chatHistory = chatHistoryContainer.querySelector('.chat-history-messages');
    if (!chatHistory) {
        chatHistory = document.createElement('div');
        chatHistory.className = 'chat-history-messages';
        chatHistoryContainer.appendChild(chatHistory);
    }

    const messageElement = document.createElement('div');
    messageElement.className = 'message';

    if (sender === 'AI') {
        messageElement.classList.add('ai-message');
        if (!isHistoryLoad && isFirstAIMessage) {
            currentAIMessage = message;
            // Parse the message and split out the suggested questions if present
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = marked.parse(renderImageFileLinks(currentAIMessage));
            // Add the welcome text first
            Array.from(tempDiv.childNodes).forEach(node => {
                // Only add non-suggested-questions nodes here
                if (!node.classList || !node.classList.contains('suggested-questions')) {
                    messageElement.appendChild(node);
                }
            });
            // Then add the suggested questions below the welcome text
            const suggested = tempDiv.querySelector('.suggested-questions');
            if (suggested) {
                messageElement.appendChild(suggested);
                // Attach click handlers to all suggested-question buttons
                messageElement.querySelectorAll('.suggested-question').forEach(btn => {
                    btn.onclick = () => submitSuggestedQuestion(btn.textContent.trim());
                });
            }
            messageElement.classList.add('welcome-message');
            isFirstAIMessage = false;
        } else {
            currentAIMessage = message;
            messageElement.innerHTML = marked.parse(renderImageFileLinks(currentAIMessage));
            addCopyButton(messageElement, currentAIMessage);
        }
    } else if (sender === 'User') {
        messageElement.classList.add('user-message');
        messageElement.textContent = message;
        isFirstAIMessage = true;
        currentAIMessage = '';
    } else {
        messageElement.classList.add('system-message');
        messageElement.textContent = message;
    }

    chatHistory.appendChild(messageElement);
    scrollToBottom();
}

function addCopyButton(messageElement, messageText) {
    const button = document.createElement('button');
    button.className = 'copy-button';
    button.innerHTML = `${createCopyIcon()} Copy`;

    button.addEventListener('click', async () => {
        try {
            // Create a temporary container with the formatted content
            const tempDiv = document.createElement('div');
            
            // Convert markdown to HTML
            const htmlContent = marked.parse(messageText);
            tempDiv.innerHTML = htmlContent;
            
            // Format code blocks specially for Word
            tempDiv.querySelectorAll('pre code').forEach(block => {
                block.style.fontFamily = 'Consolas, monospace';
                block.style.backgroundColor = '#f6f8fa';
                block.style.padding = '8px';
                block.style.display = 'block';
                block.style.whiteSpace = 'pre';
            });
            
            // Format inline code
            tempDiv.querySelectorAll('code:not(pre code)').forEach(code => {
                code.style.fontFamily = 'Consolas, monospace';
                code.style.backgroundColor = '#f6f8fa';
                code.style.padding = '2px 4px';
            });

            // Ensure lists are properly formatted
            tempDiv.querySelectorAll('ul, ol').forEach(list => {
                list.style.paddingLeft = '20px';
                list.style.marginTop = '4px';
                list.style.marginBottom = '4px';
            });

            // Ensure headings are properly styled
            tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
                heading.style.fontWeight = 'bold';
                heading.style.marginTop = '8px';
                heading.style.marginBottom = '4px';
            });

            // Create a Blob with HTML content
            const blob = new Blob([tempDiv.innerHTML], { type: 'text/html' });
            const clipboardItem = new ClipboardItem({
                'text/html': blob,
                'text/plain': new Blob([messageText], { type: 'text/plain' })
            });
            
            await navigator.clipboard.write([clipboardItem]);

            button.classList.add('copied');
            button.innerHTML = `${createCheckIcon()} Copied!`;

            setTimeout(() => {
                button.classList.remove('copied');
                button.innerHTML = `${createCopyIcon()} Copy`;
            }, 2000);
        } catch (err) {
            console.error('Failed to copy text:', err);
            // Fallback to plain text if HTML copy fails
            try {
                await navigator.clipboard.writeText(messageText);
                button.classList.add('copied');
                button.innerHTML = `${createCheckIcon()} Copied!`;
                setTimeout(() => {
                    button.classList.remove('copied');
                    button.innerHTML = `${createCopyIcon()} Copy`;
                }, 2000);
            } catch (fallbackErr) {
                console.error('Fallback copy failed:', fallbackErr);
            }
        }
    });

    messageElement.appendChild(button);
}

// Chat Functions
function addThinkingMessage() {
    removeThinkingMessage(); // Ensure only one at a time
    const chatHistory = document.querySelector('#chatHistory .chat-history-messages');
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'message ai-message thinking-message';
    const span = document.createElement('span');
    span.className = 'thinking-dots';
    span.textContent = '.';
    thinkingDiv.appendChild(span);
    chatHistory.appendChild(thinkingDiv);
    scrollToBottom();
    // Animate dots
    let dots = 1;
    thinkingInterval = setInterval(() => {
        dots = (dots % 4) + 1; // Cycle 1 to 4
        span.textContent = '.'.repeat(dots);
    }, 400);
}

function removeThinkingMessage() {
    const thinking = document.querySelector('.thinking-message');
    if (thinking) thinking.remove();
    if (thinkingInterval) {
        clearInterval(thinkingInterval);
        thinkingInterval = null;
    }
}

async function handleResearchRequest(topic, focusAreas = []) {
    if (!currentProject) {
        addMessageToChatHistory('System', 'Please select a project first.');
        return;
    }

    try {
        addMessageToChatHistory('System', `Researching topic: ${topic}...`);
        
        const response = await fetch(`${baseUrl}/api/research`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                topic: topic,
                focus_areas: focusAreas,
                project_id: currentProject
            })
        });

        if (!response.ok) {
            throw new Error('Research request failed');
        }

        const data = await response.json();
        // Show only a task completed message with a download link
        const sessionId = data.session_id;
        const downloadUrl = `/api/research/${sessionId}/download`;
        const message = `Research task completed. <a href="${downloadUrl}" target="_blank" class="btn btn-sm btn-outline-primary ms-2">Download Report (.docx)</a>`;
        addMessageToChatHistory('AI', message);
        // Optionally, add a button to view research history
        // const historyButton = document.createElement('button');
        // historyButton.className = 'btn btn-sm btn-outline-secondary mt-2';
        // historyButton.textContent = 'View Research History';
        // historyButton.onclick = () => loadResearchHistory();
        // const messageElement = document.querySelector('.ai-message:last-child');
        // if (messageElement) {
        //     messageElement.appendChild(historyButton);
        // }
x``    } catch (error) {
        console.error('Research error:', error);
        addMessageToChatHistory('System', `Error during research: ${error.message}`);
    }
}

async function loadResearchHistory() {
    if (!currentProject) return;

    try {
        const response = await fetch(`${baseUrl}/api/research/history?project_id=${currentProject}`);
        if (!response.ok) throw new Error('Failed to load research history');

        const data = await response.json();
        
        // Create modal to display research history
        const modalHtml = `
            <div class="modal fade" id="researchHistoryModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Research History</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="research-history-list">
                                ${data.research_history.map(item => `
                                    <div class="research-item p-3 mb-3 border rounded">
                                        <h6>${item.topic}</h6>
                                        <div class="text-muted small mb-2">
                                            ${new Date(item.created_at).toLocaleString()}
                                        </div>
                                        <p>${item.preview}</p>
                                        ${item.focus_areas.length ? `
                                            <div class="focus-areas">
                                                <small class="text-muted">Focus areas: ${item.focus_areas.join(', ')}</small>
                                            </div>
                                        ` : ''}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Add modal to document
        const modalContainer = document.createElement('div');
        modalContainer.innerHTML = modalHtml;
        document.body.appendChild(modalContainer);

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('researchHistoryModal'));
        modal.show();

        // Clean up modal after it's hidden
        document.getElementById('researchHistoryModal').addEventListener('hidden.bs.modal', function () {
            this.remove();
        });

    } catch (error) {
        console.error('Error loading research history:', error);
        addMessageToChatHistory('System', 'Error loading research history');
    }
}

// Modify the existing sendMessage function to handle research requests
async function sendMessage(customRequestData = null) {
    if (isProcessing) {
        addMessageToChatHistory('System', 'Please wait for the current message to complete.');
        return;
    }

    if (!currentProject) {
        addMessageToChatHistory('System', 'Please select a project first.');
        return;
    }

    let requestData;
    if (customRequestData) {
        requestData = {
            ...customRequestData,
            project_id: currentProject,
            documentIds: documentStore.getActiveDocumentIds()
        };
    } else {
        const prompt = document.getElementById('prompt').value.trim();
        if (!prompt) return;

        const documentIds = documentStore.getActiveDocumentIds();
        const activeDocCount = documentIds.length;
        
        addMessageToChatHistory('User', prompt);
        document.getElementById('prompt').value = '';
        addThinkingMessage();

        requestData = {
            prompt: prompt,
            project_id: currentProject,
            documentIds: documentIds
        };
    }

    isProcessing = true;
    let processingIndicator = null;
    let buffer = '';
    let hasStartedResponse = false;
    let aiMessageElement = null;

    try {
        const response = await fetch(`${baseUrl}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify(requestData)
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let isResearchRequest = false;
        let researchTopic = '';
        let researchFocusAreas = [];

        while (true) {
            const { done, value } = await reader.read();

            if (!hasStartedResponse) {
                removeThinkingMessage();
                hasStartedResponse = true;
            }

            if (!processingIndicator && !hasStartedResponse) {
                processingIndicator = createProcessingIndicator('Processing response...');
                document.getElementById('chatHistory').appendChild(processingIndicator);
                scrollToBottom();
            }

            if (done) {
                if (processingIndicator) processingIndicator.remove();
                if (aiMessageElement && buffer) {
                    // Only apply renderImageFileLinks after the full message is received
                    aiMessageElement.innerHTML = marked.parse(renderImageFileLinks(buffer));
                    addCopyButton(aiMessageElement, buffer);
                }
                break;
            }

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line) continue;

                try {
                    const data = JSON.parse(line);
                    if (data.error) {
                        if (processingIndicator) processingIndicator.remove();
                        addMessageToChatHistory('System', data.error);
                        break;
                    } else if (data.chunk) {
                        if (processingIndicator) {
                            processingIndicator.remove();
                            processingIndicator = null;
                        }
                        buffer += data.chunk;
                        if (!aiMessageElement) {
                            aiMessageElement = document.createElement('div');
                            aiMessageElement.className = 'message ai-message';
                            document.querySelector('#chatHistory .chat-history-messages').appendChild(aiMessageElement);
                        }
                        // During streaming, show partial markdown (no image parsing)
                        aiMessageElement.innerHTML = marked.parse(buffer);
                        scrollToBottom();
                    }
                } catch (e) {
                    console.error('Error parsing JSON:', e);
                }
            }

            // Check for research request in the response
            if (buffer.includes('[RESEARCH_REQUEST]')) {
                isResearchRequest = true;
                const match = buffer.match(/\[RESEARCH_REQUEST\](.*?)\[\/RESEARCH_REQUEST\]/s);
                if (match) {
                    const content = match[1];
                    const topicMatch = content.match(/topic:\s*(.*?)(?:\n|$)/);
                    const focusMatch = content.match(/focus_areas:\s*\[(.*?)\]/);
                    
                    if (topicMatch) {
                        researchTopic = topicMatch[1].trim();
                        if (focusMatch) {
                            researchFocusAreas = focusMatch[1].split(',').map(area => area.trim());
                        }
                        
                        // Clear the research request from the buffer
                        buffer = buffer.replace(match[0], '');
                        
                        // Handle the research request
                        await handleResearchRequest(researchTopic, researchFocusAreas);
                    }
                }
            }

            // Process remaining content as normal chat message
            if (buffer && !isResearchRequest) {
                try {
                    const data = JSON.parse(buffer);
                    if (data.chunk) {
                        if (!aiMessageElement) {
                            aiMessageElement = document.createElement('div');
                            aiMessageElement.className = 'message ai-message';
                            document.querySelector('#chatHistory .chat-history-messages').appendChild(aiMessageElement);
                        }
                        aiMessageElement.innerHTML = marked.parse(buffer);
                        scrollToBottom();
                    }
                } catch (e) {
                    // Not a complete JSON object yet, continue accumulating
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        addMessageToChatHistory('System', error.message);
    } finally {
        isProcessing = false;
        if (processingIndicator) processingIndicator.remove();
        removeThinkingMessage();
    }
}

// Project Management Functions
async function loadProjects() {
    try {
        const response = await fetch(`${baseUrl}/api/projects`);
        if (!response.ok) throw new Error('Failed to load projects');

        const data = await response.json();
        const projectSelect = document.getElementById('projectSelect');

        // Get all project IDs for the current user
        const userProjectIds = data.projects.map(project => String(project.id));

        // If currentProject is not in the user's projects, reset it
        if (!userProjectIds.includes(localStorage.getItem('currentProject'))) {
            // Look for "General Chat" project first as fallback
            const generalChatProject = data.projects.find(project => project.name === 'General Chat');
            if (generalChatProject) {
                localStorage.setItem('currentProject', String(generalChatProject.id));
                currentProject = String(generalChatProject.id);
            } else if (userProjectIds.length > 0) {
                // Fallback to first available project if no General Chat
                localStorage.setItem('currentProject', userProjectIds[0]);
                currentProject = userProjectIds[0];
            } else {
                localStorage.removeItem('currentProject');
                currentProject = null;
            }
        } else {
            currentProject = localStorage.getItem('currentProject');
        }

        if (projectSelect) {
            projectSelect.innerHTML = `
                <option value="" disabled ${!currentProject ? 'selected' : ''}>Select a Project</option>
                ${data.projects.map(project => `
                    <option value="${project.id}" ${currentProject == project.id ? 'selected' : ''}>
                        ${project.name}
                    </option>
                `).join('')}
                <option value="__add__">➕ Add New Project</option>
            `;

            projectSelect.onchange = function() {
                const projectId = this.value;
                if (projectId === "__add__") {
                    createNewProject();
                    this.value = currentProject; // Reset to current
                } else if (projectId) {
                    switchProject(projectId);
                }
            };
        }
    } catch (error) {
        console.error('Error loading projects:', error);
    }
}

function createNewProject() {
    editingProjectId = null;
    projectModal = projectModal || new bootstrap.Modal(document.getElementById('projectModal'));
    document.getElementById('projectName').value = '';
    document.getElementById('projectDescription').value = '';
            document.querySelector('#projectModal .modal-title').textContent = 'Create New Project';
    projectModal.show();
}

async function saveProject() {
    const name = document.getElementById('projectName').value.trim();
    const description = document.getElementById('projectDescription').value.trim();
    const systemInstructions = document.getElementById('systemInstructions').value.trim();

    if (!name) {
        alert('Project name is required');
        return;
    }

    try {
        const method = editingProjectId ? 'PUT' : 'POST';
        const url = editingProjectId
            ? `/api/projects/${editingProjectId}`
            : '/api/projects';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                name,
                description,
                system_instructions: systemInstructions  // Added this line
            })
        });

        if (!response.ok) throw new Error('Failed to save project');

        const project = await response.json();
        projectModal.hide();
        await loadProjects();

        if (!editingProjectId) {
            switchProject(project.id);
        }
    } catch (error) {
        console.error('Error saving project:', error);
        alert('Failed to save project');
    }
}

async function switchProject(projectId) {
    currentProject = projectId;
    localStorage.setItem('currentProject', projectId);

    // Enable edit button
    const editButton = document.getElementById('editProjectBtn');
    if (editButton) {
        editButton.disabled = !projectId;
    }

    // Clear current chat and start a new one
    document.getElementById('chatHistory').innerHTML = '';
    
    // Clear document store and update UI
    documentStore.documents.clear();
    documentStore.activeDocuments.clear();
    documentStore.updateDocumentCountDisplay();
    const uploadedFileList = document.getElementById('uploadedFileList');
    if (uploadedFileList) uploadedFileList.innerHTML = '';

    try {
        // Initialize new chat interface
        const response = await fetch(`${baseUrl}/api/new_chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({ project_id: projectId })
        });

        if (response.ok) {
            const data = await response.json();
            // Display welcome message
            addMessageToChatHistory('AI', data.welcome_message);
        }
    } catch (error) {
        console.error('Error creating new chat:', error);
    }

    // Refresh documents and chat list
    await Promise.all([
        documentStore.refreshDocumentList(projectId),
        loadChatList()
    ]);
}

// Helper function for user-friendly relative date
function getRelativeDateDescription(dateString) {
    const now = new Date();
    const date = new Date(dateString);
    const diffMs = now - date;
    if (diffMs < 0) return 'just now'; // future date fallback

    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays === 0) {
        if (diffHours === 0) {
            return 'earlier today';
        } else {
            return 'earlier today';
        }
    } else if (diffDays === 1) {
        return 'yesterday';
    } else if (diffDays < 7) {
        return `${diffDays} days ago`;
    } else if (diffDays < 14) {
        return 'last week';
    } else {
        return 'more than a week ago';
    }
}

// Replace the date/time in chat history listings with the relative date
async function loadChatList() {
    if (!currentProject) return;

    try {
        const response = await fetch(`${baseUrl}/api/chats?project_id=${currentProject}`);
        if (!response.ok) throw new Error('Failed to load chat list');

        const data = await response.json();
        const chatList = document.getElementById('previousChats');

        if (chatList && data.chats) {
            // Store all chats for search functionality
            allChats = data.chats;
            
            if (data.chats.length === 0) {
                chatList.innerHTML = '<div class="text-muted">No previous chats in this project</div>';
            } else {
                renderChatList(data.chats);
            }
        }
    } catch (error) {
        console.error('Error loading chat list:', error);
    }
}

// Function to render chat list with search filtering
function renderChatList(chatsToRender) {
    const chatList = document.getElementById('previousChats');
    const searchTerm = document.getElementById('chatSearchInput')?.value?.toLowerCase() || '';
    
    if (chatsToRender.length === 0) {
        chatList.innerHTML = '<div class="text-muted">No chats found</div>';
        return;
    }
    
    // Separate pinned and unpinned chats
    const pinnedChats = chatsToRender.filter(chat => chat.pinned);
    const unpinnedChats = chatsToRender.filter(chat => !chat.pinned);
    
    // Sort unpinned chats by date (most recent first)
    unpinnedChats.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    // Take the most recent unpinned chats to fill remaining slots
    const maxUnpinnedChats = 50 - pinnedChats.length;
    const recentUnpinnedChats = unpinnedChats.slice(0, Math.max(0, maxUnpinnedChats));
    
    // Combine pinned chats with recent unpinned chats
    const displayChats = [...pinnedChats, ...recentUnpinnedChats];
    
    // Sort by date for display (pinned chats will appear at top due to their age)
    displayChats.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    chatList.innerHTML = displayChats.map(chat => `
        <div class="chat-preview p-2 mb-2 border rounded">
            <div class="d-flex justify-content-between align-items-center">
                <div class="chat-preview-content" onclick="loadChat('${chat.session_id}')">
                    <div class="chat-header d-flex align-items-center">
                        ${chat.pinned ? '<i class="bi bi-star-fill text-warning me-2"></i>' : ''}
                        <div class="small text-muted">
                            ${getRelativeDateDescription(chat.created_at)}
                        </div>
                    </div>
                    <div class="chat-text">
                        ${chat.preview || 'Empty chat'}
                    </div>
                </div>
                <div class="chat-actions">
                    <button class="btn btn-link p-1" onclick="togglePin('${chat.session_id}', ${chat.pinned})">
                        <i class="bi ${chat.pinned ? 'bi-star-fill text-warning' : 'bi-star'}"></i>
                    </button>
                    <button class="btn btn-link text-danger p-1" onclick="confirmDeleteChat('${chat.session_id}')">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
    
    // Add a note if we're limiting the display
    if (allChats.length > displayChats.length) {
        const hiddenCount = allChats.length - displayChats.length;
        chatList.innerHTML += `
            <div class="text-muted small text-center mt-2 p-2 border-top">
                Showing ${displayChats.length} of ${allChats.length} chats (${hiddenCount} older chats hidden)
            </div>
        `;
    }
}

// Function to search chats
async function searchChats(searchTerm) {
    if (!searchTerm.trim()) {
        // If search is empty, show all chats with normal limit
        renderChatList(allChats);
        return;
    }
    
    const searchLower = searchTerm.toLowerCase();
    const matchingChats = [];
    
    // Search through all chats
    for (const chat of allChats) {
        // Check if search term matches preview (visible content)
        if (chat.preview && chat.preview.toLowerCase().includes(searchLower)) {
            matchingChats.push(chat);
            continue;
        }
        
        // If not found in preview, fetch full chat content to search
        try {
            const response = await fetch(`${baseUrl}/api/chats/${chat.session_id}`);
            if (response.ok) {
                const chatData = await response.json();
                const chatHistory = chatData.chat_history || [];
                
                // Search through all messages in the chat
                const hasMatch = chatHistory.some(message => 
                    message.content && message.content.toLowerCase().includes(searchLower)
                );
                
                if (hasMatch) {
                    matchingChats.push(chat);
                }
            }
        } catch (error) {
            console.error(`Error fetching chat ${chat.session_id} for search:`, error);
        }
    }
    
    // Render matching chats
    renderChatList(matchingChats);
}

async function togglePin(sessionId, currentPinned) {
    event.stopPropagation();
    try {
        const response = await fetch(`${baseUrl}/api/chats/${sessionId}/toggle-pin`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        if (!response.ok) throw new Error('Failed to toggle pin');
        await loadChatList();
    } catch (error) {
        console.error('Error toggling pin:', error);
    }
}

function confirmDeleteChat(sessionId) {
    event.stopPropagation();
    deleteModal = deleteModal || new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
    chatToDelete = sessionId;
    deleteModal.show();

    document.getElementById('confirmDeleteBtn').onclick = () => {
        deleteModal.hide();
        deleteChat(chatToDelete);
    };
}

async function deleteChat(sessionId) {
    try {
        const response = await fetch(`${baseUrl}/api/chats/${sessionId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        if (!response.ok) throw new Error('Failed to delete chat');

        const data = await response.json();
        if (data.was_current_chat) {
            document.getElementById('chatHistory').innerHTML = '';
        }

        await loadChatList();
    } catch (error) {
        console.error('Error deleting chat:', error);
    }
}

function clearChatHistoryMessages() {
    const chatMessages = document.querySelector('#chatHistory .chat-history-messages');
    if (chatMessages) chatMessages.innerHTML = '';
}

// Enhance chat history loading to insert research results for research requests
async function enhanceChatHistoryWithResearch(chatHistory, projectId) {
    // Fetch research history for this project
    let researchMap = {};
    try {
        const response = await fetch(`${baseUrl}/api/research/history?project_id=${projectId}`);
        if (response.ok) {
            const data = await response.json();
            for (const item of data.research_history) {
                // Use topic as key for quick lookup
                researchMap[item.topic.trim().toLowerCase()] = item.research_content;
            }
        }
    } catch (e) {
        // Ignore errors, just don't enhance
    }
    // Build new chat history with research results inserted
    let enhanced = [];
    for (let i = 0; i < chatHistory.length; ++i) {
        const msg = chatHistory[i];
        enhanced.push(msg);
        if (msg.role === 'user' && msg.content.includes('[RESEARCH_REQUEST]')) {
            // Try to extract topic
            const match = msg.content.match(/topic:\s*(.*?)(?:\n|$)/);
            if (match) {
                const topic = match[1].replace(/['"\n]/g, '').trim().toLowerCase();
                if (researchMap[topic]) {
                    enhanced.push({
                        role: 'assistant',
                        content: researchMap[topic]
                    });
                }
            }
        }
    }
    return enhanced;
}

// Patch chat loading to use enhanced history
async function loadChat(sessionId) {
    try {
        const response = await fetch(`${baseUrl}/api/chats/${sessionId}`);
        if (!response.ok) throw new Error('Failed to load chat');
        const data = await response.json();
        let chatHistory = data.chat_history || [];
        // Enhance with research results if needed
        chatHistory = await enhanceChatHistoryWithResearch(chatHistory, currentProject);
        // Now render as before
        const chatHistoryDiv = document.querySelector('#chatHistory .chat-history-messages');
        chatHistoryDiv.innerHTML = '';
        for (const msg of chatHistory) {
            addMessageToChatHistory(msg.role === 'user' ? 'User' : 'AI', msg.content);
        }
        scrollToBottom();
    } catch (error) {
        addMessageToChatHistory('System', 'Error loading chat: ' + error.message);
    }
}

// Event Handlers
function handleFileUpload(event) {
    const fileInput = event.target;
    const files = Array.from(fileInput.files);

    if (!currentProject) {
        addMessageToChatHistory('System', 'Please select a project first.');
        fileInput.value = '';
        return;
    }

    files.forEach(file => documentStore.uploadDocument(file, currentProject));
    fileInput.value = '';
}

// Add this new helper function to load chat session
async function loadChatSession(sessionId) {
    try {
        const response = await fetch(`${baseUrl}/api/chats/${sessionId}`);
        if (!response.ok) throw new Error('Failed to load chat session');
        return await response.json();
    } catch (error) {
        console.error('Error loading chat session:', error);
        return null;
    }
}

// Utility Functions
function getCsrfToken() {
    return window.CSRF_TOKEN;
}

function createCopyIcon() {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
}

function createCheckIcon() {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
}

function createProcessingIndicator(message) {
    const indicator = document.createElement('div');
    indicator.className = 'processing-indicator';
    indicator.innerHTML = `
        <div class="processing-spinner"></div>
        <div class="processing-text">${message}</div>
    `;
    return indicator;
}

function scrollToBottom() {
    const chatHistory = document.querySelector('#chatHistory .chat-history-messages');
    if (chatHistory) {
        chatHistory.scrollTop = chatHistory.scrollHeight;
        setTimeout(() => chatHistory.scrollTop = chatHistory.scrollHeight, 100);
    }
}

// Initialize Event Listeners
function initializeEventListeners() {
    const promptInput = document.getElementById('prompt');
    if (promptInput) {
        promptInput.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (e.target.value.trim() && !isProcessing) {
                    sendMessage();
                }
            }
        });
    }

    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileUpload);
    }

    // Add Files button triggers file input
    const addFilesBtn = document.getElementById('addFilesBtn');
    if (addFilesBtn && fileInput) {
        addFilesBtn.addEventListener('click', function (e) {
            e.preventDefault();
            fileInput.click();
        });
    }

    const clearButton = document.getElementById('clearButton');
    if (clearButton) {
        clearButton.addEventListener('click', clearChatAndUploads);
    } else {
        console.log("Clear button not found"); // Debug log
    }
}

// Single Initialization
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize Bootstrap modals
    const projectModalEl = document.getElementById('projectModal');
    if (projectModalEl) {
        projectModal = new bootstrap.Modal(projectModalEl);
    }

    const deleteModalEl = document.getElementById('confirmDeleteModal');
    if (deleteModalEl) {
        deleteModal = new bootstrap.Modal(deleteModalEl);
    }

    // Initialize event listeners
    initializeEventListeners();

    // Load saved project from localStorage
    const savedProject = localStorage.getItem('currentProject');
    if (savedProject) {
        currentProject = savedProject;
    }

    // Update edit button state
    const editButton = document.getElementById('editProjectBtn');
    if (editButton) {
        editButton.disabled = !currentProject;
    }

    // Load projects first
    await loadProjects();
    
    // If we have a current project, initialize it
    if (currentProject) {
        try {
            // Create initial chat
            const response = await fetch(`${baseUrl}/api/new_chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify({ project_id: currentProject })
            });

            if (response.ok) {
                const data = await response.json();
                // Always display welcome message
                addMessageToChatHistory('AI', data.welcome_message);
            }

            // Load documents and chat list
            await Promise.all([
                documentStore.refreshDocumentList(currentProject),
                loadChatList()
            ]);
        } catch (error) {
            console.error('Error initializing project:', error);
            addMessageToChatHistory('System', 'Error initializing project');
        }
    } else {
        // Fallback: if no project is selected, try to find and switch to General Chat
        try {
            const response = await fetch(`${baseUrl}/api/projects`);
            if (response.ok) {
                const data = await response.json();
                const generalChatProject = data.projects.find(project => project.name === 'General Chat');
                if (generalChatProject) {
                    console.log('No project selected, switching to General Chat as fallback');
                    await switchProject(String(generalChatProject.id));
                } else if (data.projects.length > 0) {
                    console.log('No General Chat found, switching to first available project');
                    await switchProject(String(data.projects[0].id));
                } else {
                    addMessageToChatHistory('System', 'No projects available. Please create a project first.');
                }
            }
        } catch (error) {
            console.error('Error in fallback project initialization:', error);
            addMessageToChatHistory('System', 'Error initializing fallback project');
        }
    }

    // Quick Upload Button Handler
    const quickUploadBtn = document.querySelector('.quick-upload-btn');
    const quickFileInput = document.getElementById('quickFileInput');

    if (quickUploadBtn && quickFileInput) {
        quickUploadBtn.addEventListener('click', function (e) {
            e.preventDefault();
            quickFileInput.click();
        });
    }

    // Optional: handle file selection
    if (quickFileInput) {
        quickFileInput.addEventListener('change', handleFileUpload);
    }

    // Show/hide edit pencil icon based on selected project
    const projectSelect = document.getElementById('projectSelect');
    const editProjectIcon = document.getElementById('editProjectIcon');
    function updateEditIconVisibility() {
        if (!projectSelect || !editProjectIcon) return;
        const val = projectSelect.value;
        if (val && val !== '__add__') {
            editProjectIcon.style.display = 'flex';
        } else {
            editProjectIcon.style.display = 'none';
        }
    }
    if (projectSelect && editProjectIcon) {
        projectSelect.addEventListener('change', updateEditIconVisibility);
        updateEditIconVisibility();
    }
});

async function editCurrentProject() {
    if (!currentProject) {
        addMessageToChatHistory('System', 'Please select a project first.');
        return;
    }

    try {
        const response = await fetch(`${baseUrl}/api/projects/${currentProject}`);
        if (!response.ok) throw new Error('Failed to load project');

        const project = await response.json();
        editingProjectId = currentProject;

        // Load project data into modal
        document.getElementById('projectName').value = project.name;
        document.getElementById('projectDescription').value = project.description || '';
        document.getElementById('systemInstructions').value = project.system_instructions || '';

        // Update modal title
        document.querySelector('#projectModal .modal-title').textContent = 'Edit Project';
        projectModal.show();
    } catch (error) {
        console.error('Error loading project:', error);
        addMessageToChatHistory('System', 'Error loading project details');
    }
}

async function clearChatAndUploads() {
    if (!currentProject) {
        addMessageToChatHistory('System', 'Please select a project first.');
        return;
    }

    // Clear document store and update UI
    documentStore.documents.clear();
    documentStore.activeDocuments.clear();
    documentStore.updateDocumentCountDisplay();
    const uploadedFileList = document.getElementById('uploadedFileList');
    if (uploadedFileList) uploadedFileList.innerHTML = '';

    try {
        const response = await fetch(`${baseUrl}/api/new_chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({ project_id: currentProject })
        });

        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const data = await response.json();
        if (data.status === 'success') {
            clearChatHistoryMessages();
            document.getElementById('prompt').value = '';

            isFirstAIMessage = true;
            currentAIMessage = '';

            addMessageToChatHistory('AI', data.welcome_message);
            setTimeout(scrollToBottom, 100);
        }
    } catch (error) {
        console.error('Error:', error);
        addMessageToChatHistory('System', `Error starting new chat: ${error.message}`);
    }
}

function createMessageElement(message) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${message.role}-message`;
    
    if (message.role === 'assistant') {
        try {
            messageDiv.innerHTML = marked(message.content);
            
            // Add copy button only if it's not the first AI message
            if (!isFirstAIMessage) {
                const copyButton = document.createElement('button');
                copyButton.className = 'copy-button';
                copyButton.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
                copyButton.onclick = () => copyMessage(message.content, copyButton);
                messageDiv.appendChild(copyButton);
            }
        } catch (error) {
            console.error('Markdown parsing error:', error);
            messageDiv.textContent = message.content;
        }
    } else {
        messageDiv.textContent = message.content;
    }
    
    return messageDiv;
}

function renderImageFileLinks(message) {
    // 1. Find all ImageFileDeltaBlocks and map file paths to file_ids
    const fileIdMap = {};
    const imageBlockRegex = /ImageFileDeltaBlock\([^)]*file_id=['\"](file-[^'\"]+)['\"][^)]*\)/g;
    let match;
    while ((match = imageBlockRegex.exec(message)) !== null) {
        fileIdMap['last'] = match[1];
    }

    // 2. Replace markdown sandbox links
    message = message.replace(/\[([^\]]+)\]\(sandbox:[^)]+\)/g, (m, text) => {
        if (fileIdMap['last']) {
            const url = `/api/download/openai/${fileIdMap['last']}`;
            return `<a href="${url}" target="_blank" download>${text}</a><br><img src="${url}" alt="Generated Chart" style="max-width: 100%; margin-top: 8px;" />`;
        }
        return m;
    });

    // 3. Replace raw sandbox URLs
    message = message.replace(/sandbox:[^\s)]+/g, (m) => {
        if (fileIdMap['last']) {
            const url = `/api/download/openai/${fileIdMap['last']}`;
            return `<img src="${url}" alt="Generated Chart" style="max-width: 100%; margin-top: 8px;" />`;
        }
        return m;
    });

    // 4. Also replace any remaining ImageFileDeltaBlock with a download link and image (for redundancy)
    message = message.replace(imageBlockRegex, (match, fileId) => {
        const url = `/api/download/openai/${fileId}`;
        return `<a href="${url}" target="_blank" download>Download Chart Image</a><br><img src="${url}" alt="Generated Chart" style="max-width: 100%; margin-top: 8px;" />`;
    });

    return message;
}

document.getElementById('projectSelect').addEventListener('change', function() {
    const selectedOption = this.options[this.selectedIndex];
    if (this.value) { // Only update if a real project is selected
        document.getElementById('currentProjectName').textContent = selectedOption.text;
    }
    // ... your existing logic for switching projects ...
});

// Add this function near the top of the file with other utility functions
function submitSuggestedQuestion(question) {
    document.getElementById('prompt').value = question;
    sendMessage();
}

