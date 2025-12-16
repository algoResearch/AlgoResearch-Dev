
    const savedScale = localStorage.getItem('messageFontScale') || '1.0';
    document.documentElement.style.setProperty('--message-font-scale', savedScale);
    // Utility Function to Get CSRF Token

    const CHUNK = Number("{{ FILE_CHUNK_SIZE|default:2097152 }}");  // 2MB default
    const CHUNK_THRESHOLD = CHUNK;                                   // switch to chunked at >= 1 chunk

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let c of cookies) {
            c = c.trim();
            if (c.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(c.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
    }

    function buildFormData(obj) {
        const fd = new FormData();
        Object.entries(obj).forEach(([k,v]) => fd.append(k, v));
        return fd;
    }

    async function uploadInChunks(file, orgId, conversationId, onProgress) {
        // INIT
        const initRes = await fetch(`/${orgId}/conversation/${conversationId}/upload/init/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: buildFormData({
        filename: file.name,
        total_size: String(file.size),
        mime_type: file.type || "application/octet-stream",
        }),
        credentials: "same-origin",
    });
    if (!initRes.ok) throw new Error("init failed");
    const { upload_id, part_size, total_parts } = await initRes.json();

    const size = part_size || CHUNK;
    let partNo = 0;
    for (let offset = 0; offset < file.size; offset += size) {
        const slice = file.slice(offset, Math.min(offset + size, file.size));
        const fd = new FormData();
        fd.append("upload_id", upload_id);
        fd.append("part_no", String(partNo));
        fd.append("blob", slice, `${file.name}.part${partNo}`);

        const partRes = await fetch(`/${orgId}/conversation/${conversationId}/upload/part/`, {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken") },
            body: fd,
            credentials: "same-origin",
        });
        if (!partRes.ok) throw new Error(`part ${partNo} failed`);
        partNo++;
        if (typeof onProgress === "function") onProgress(Math.min(100, Math.round((partNo / total_parts) * 100)));
    }

    // COMPLETE
    const doneRes = await fetch(`/${orgId}/conversation/${conversationId}/upload/complete/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: buildFormData({ upload_id }),
        credentials: "same-origin",
    });
    if (!doneRes.ok) throw new Error("complete failed");
    return await doneRes.json(); // { ok, attachment_id, attachment_url, mime_type }
    }

    /** Small utility—normalizes mime key names across server variants */
    function pickMime(data) {
        // can be: mime_type (uploads) | attachment_type (WS) | attachment_mime_type (model)
        return data.mime_type || data.attachment_type || data.attachment_mime_type || "";
    }
    function unsendMessage(orgId, messageId) {
        fetch(`/${orgId}/messages/${messageId}/unsend/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    document.querySelector(`[data-message-id="${messageId}"]`).remove();
                } else {
                    console.error('Error unsending message:', data.error);
                }
            })
            .catch(error => console.error('Error:', error));
    }
    function startEditingMessage(messageId, currentContent) {
        const messageInput = document.querySelector('textarea[name="content"]');
        const sendMessageForm = document.getElementById('sendMessageForm');

        console.log(`Starting edit for message ID: ${messageId}, content: ${currentContent}`);

        // Populate the text area with the current content
        messageInput.value = currentContent;
        messageInput.focus();

        // Add or update a hidden input for the message ID
        let editMessageIdInput = document.getElementById('editMessageId');
        if (!editMessageIdInput) {
            editMessageIdInput = document.createElement('input');
            editMessageIdInput.type = 'hidden';
            editMessageIdInput.id = 'editMessageId';
            editMessageIdInput.name = 'edit_message_id';
            sendMessageForm.appendChild(editMessageIdInput);
        }
        editMessageIdInput.value = messageId;
    }



    function editMessage(orgId, messageId, messageContent) {
        const messageInput = document.querySelector('textarea[name="content"]');
        const editMessageIdInput = document.getElementById('editMessageId');

        messageInput.value = messageContent;

        if (!editMessageIdInput) {
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.id = 'editMessageId';
            hiddenInput.name = 'edit_message_id';
            hiddenInput.value = messageId;
            document.getElementById('sendMessageForm').appendChild(hiddenInput);
        } else {
            editMessageIdInput.value = messageId;
        }

        messageInput.focus();
    }




    function deleteMessage(orgId, messageId) {
        fetch(`/${orgId}/messages/${messageId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to delete message.');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    // Remove the message from the UI for the current user
                    const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                    if (messageElement) {
                        messageElement.remove();
                    }
                } else {
                    console.error('Error deleting message:', data.error);
                }
            })
            .catch(error => console.error('Error:', error));
    }
    function getAttachmentHTML(messageData) {
        const url = new URL(messageData.attachment_url, window.location.origin).href;
        const mime = (pickMime(messageData) || "").toLowerCase();

        if (mime.startsWith('video/')) {
            if (messageData.thumbnail_url) {
            return `
                <img 
                    src="${messageData.thumbnail_url}" 
                    alt="Video Thumbnail" 
                    class="chat-video-thumbnail" 
                    data-video-src="${url}" 
                    data-bs-toggle="modal" 
                    data-bs-target="#videoPreviewModal"
                >
            `;
        }
            return `<a href="${url}" target="_blank">View Video</a>`;
        }
        if (mime.startsWith('image/')) {
            return `<img src="${url}" alt="Attached Image" class="chat-image">`;
        } 
        if (mime === 'application/pdf') {
            return `<a href="${url}" target="_blank">View PDF</a>`;
        }
        return `<a href="${url}" target="_blank">Download File</a>`;
    }
    function deleteSelectedConversation(orgId, conversationId) {
        if (!confirm("Are you sure you want to delete this conversation?")) return;

        const url = `/${orgId}/conversation/${conversationId}/delete/`;

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.status === 'success') {
                    alert("Conversation deleted successfully!");
                    // Redirect to fetch messages
                    window.location.href = data.redirect_url;
                } else {
                    alert(data.error || "Failed to delete conversation.");
                }
            })
            .catch((error) => {
                console.error("Error deleting conversation:", error);
                alert("An error occurred. Please try again.");
            });
        }
        
        document.addEventListener("DOMContentLoaded", function () {
            const searchToggle = document.getElementById("searchToggle");
            const searchBarContainer = document.getElementById("searchBarContainer");
            const searchInput = document.getElementById("searchInput");
            const conversationList = document.getElementById("conversationList");
            const defaultConversationList = conversationList.innerHTML; // Store the original conversation list

            // Toggle the search bar
            searchToggle.addEventListener("click", () => {
                searchBarContainer.classList.toggle("d-none");
                searchInput.focus();
            });

            // Perform search when typing
            searchInput.addEventListener("input", () => {
                const query = searchInput.value.trim();

                if (query.length > 2) {
                    fetch(`/{{ org_id }}/search/?query=${encodeURIComponent(query)}&is_admin={{ is_admin|yesno:"true,false" }}`)
                    
                        .then((response) => {
                            if (!response.ok) {
                                throw new Error("Failed to fetch search results.");
                            }
                            return response.json();
                        })
                        .then((data) => {
                            const isAdminFromResponse = data.is_admin;
                            const dynamicUrlPrefix = isAdminView ? `/${pageOrgId}/admin` : `/${pageOrgId}`;
                            // Clear the conversation list
                            conversationList.innerHTML = "";

                            // Display conversations matching the search query
                            if (data.conversations.length > 0) {
                                data.conversations.forEach((convo) => {
                                    const convoItem = document.createElement("a");
                                    convoItem.href = `${dynamicUrlPrefix}/conversation/${convo.id}/`;
                                
                                    convoItem.innerHTML = `
                                        <img src="${
                                            convo.profile_picture || "/static/img/default-group.jpg"
                                        }" alt="Profile Picture" class="profile-pic-small me-2">
                                        <div>
                                            <span class="fw-bold">${
                                                convo.name || `${convo.user1__username} & ${convo.user2__username}`
                                            }</span><br>
                                        </div>
                                    `;
                                    conversationList.appendChild(convoItem);
                                });
                            }
                            // Display messages matching the search query
                            if (data.messages.length > 0) {
                                data.messages.forEach((msg) => {
                                    const msgItem = document.createElement("a");
                                    msgItem.href = `${dynamicUrlPrefix}/conversation/${msg.conversation.id}/#message-${msg.id}`;
                                    msgItem.className =
                                        "list-group-item list-group-item-action d-flex align-items-start";

                                    msgItem.innerHTML = `
                                        <div>
                                            <strong style="font-size: ${savedScale}rem">"${msg.plain_content}"</strong><br>
                                            <span class="text-muted" style="font-size: ${savedScale}rem">
                                                in ${msg.conversation_name || "Unnamed Group"}
                                            </span>
                                        </div>
                                    `;
                                    conversationList.appendChild(msgItem);
                                });
                            }

                            // Handle no results
                            if (data.conversations.length === 0 && data.messages.length === 0) {
                                conversationList.innerHTML = `<p class="text-center text-muted">No results found.</p>`;
                            }
                        })
                        .catch((error) => {
                            console.error("Error fetching search results:", error);
                            conversationList.innerHTML = `<p class="text-center text-danger">An error occurred while fetching results.</p>`;
                        });
                } else if (query.length === 0) {
                    // Reset to the default conversation list when search input is empty
                    conversationList.innerHTML = defaultConversationList;
                }
            });
        });
    document.addEventListener('DOMContentLoaded', () => {
        function setupMentionClickHandlers() {
            document.querySelectorAll('.mention').forEach(mention => {
                mention.addEventListener('click', function (event) {
                    event.preventDefault();
                    const username = this.dataset.username;
                    console.log(`Navigating to user: ${username}`);
                    if (pageOrgId) {
                        window.location.href = `/${pageOrgId}/friend-info/${username}/`;
                    } else {
                        console.error("Organization ID is missing.");
                    }
                });
            });
        }
        function fetchUserInfo(username) {
            if (!pageOrgId || pageOrgId === "{{ org_id }}") {
                console.error("org_id is not defined or is not properly rendered.");
            }

            fetch(`/api/get-user-id/?username=${encodeURIComponent(username)}`, {
                method: 'GET',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error('Failed to fetch user ID');
                    }
                    return response.json();
                })
                .then((data) => {
                    if (data.status === 'success') {
                        const friendId = data.friend_id;
                        window.location.href = `/${pageOrgId}/friend-info/${friendId}/`;
                    } else {
                        console.error('Error fetching user ID:', data.message);
                        alert('User not found: ' + data.message);
                    }
                })
                .catch((error) => console.error('Error fetching user ID:', error));
        }
        document.addEventListener('click', (e) => {
            const mentionElement = e.target.closest('.mention');
            if (mentionElement) {
                const username = mentionElement.dataset.username;

                if (pageOrgId && username) {
                    // Fetch the friend's info using the correct org_id
                    fetch(`/api/get-user-id/?username=${encodeURIComponent(username)}`)
                        .then((response) => response.json())
                        .then((data) => {
                            if (data.status === 'success') {
                                const friendId = data.friend_id;
                                window.location.href = `/${pageOrgId}/friend-info/${friendId}/`;
                            } else {
                                console.error("Error fetching user info:", data.message);
                                alert("User not found");
                            }
                        })
                        .catch((error) => console.error("Error fetching user ID:", error));
                } else {
                    console.error("Invalid orgId or username for mention.");
                }
            }
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        const attachmentsModal = document.getElementById('attachmentsModal');
        const selector = document.getElementById('textSizeSelector');
        const messageContainer = document.querySelectorAll('.message-content');
        const messageInput = document.querySelector('textarea[name="content"]');
        const mentionSuggestions = document.getElementById('mentionSuggestions');
        document.addEventListener('click', function (e) {
            const clickedImage = e.target.closest('.chat-image');
            if (clickedImage) {
                const imageSrc = clickedImage.getAttribute('src');
                const previewImage = document.getElementById('previewImage');
                previewImage.setAttribute('src', imageSrc);

                // ✅ Show modal here
                const modal = new bootstrap.Modal(document.getElementById('imagePreviewModal'));
                modal.show();
            }
        });

        attachmentsModal.addEventListener('show.bs.modal', function () {
            const gallery = document.getElementById('attachmentsGallery');
            
            gallery.innerHTML = ''; // Clear previous items
            document.querySelectorAll('.message-content').forEach(message => {
                const img = message.querySelector('img.chat-image');
                const video = message.querySelector('img.chat-video-thumbnail');
                const link = message.querySelector('a');

                if (img) {
                    const col = document.createElement('div');
                    col.className = 'col-md-3 mb-3';
                    col.innerHTML = `<img src="${img.src}" class="img-fluid rounded shadow-sm" alt="Image Attachment">`;
                    gallery.appendChild(col);
                }

                if (video) {
                    const col = document.createElement('div');
                    col.className = 'col-md-3 mb-3';
                    col.innerHTML = `
                        <img src="${video.src}" class="img-fluid rounded shadow-sm" 
                             data-video-src="${video.dataset.videoSrc}" 
                             alt="Video Thumbnail" 
                            style="cursor:pointer;" 
                            onclick="previewVideoInModal(this.dataset.videoSrc)">
                    `;
                    gallery.appendChild(col);
                }

                if (link && link.href && link.href.endsWith('.pdf')) {
                    const col = document.createElement('div');
                    col.className = 'col-md-6 mb-3';
                    col.innerHTML = `<a href="${link.href}" target="_blank" class="btn btn-outline-secondary w-100">View PDF</a>`;
                    gallery.appendChild(col);
                }
            });
        });
        attachmentsModal.addEventListener('click', function (e) {
            const clickedImage = e.target.closest('img');
            if (clickedImage && clickedImage.src) {
                const previewImage = document.getElementById('previewImage');
                if (previewImage) {
                    previewImage.setAttribute('src', clickedImage.src);
                    const modal = new bootstrap.Modal(document.getElementById('imagePreviewModal'));
                    modal.show();
                }
            }
        });
        function previewVideoInModal(videoSrc) {
            const previewVideo = document.querySelector('#previewVideo');
            previewVideo.querySelector('source').src = videoSrc;
            previewVideo.load();
            const modal = new bootstrap.Modal(document.getElementById('videoPreviewModal'));
            modal.show();
        }
        // Set color input values
        

        // Event listeners for changes
        document.getElementById('sentColor').addEventListener('input', function () {
            localStorage.setItem('sentColor', this.value);
            document.documentElement.style.setProperty('--sent-message-color', this.value);
        });
        document.getElementById('receivedColor').addEventListener('input', function () {
            localStorage.setItem('receivedColor', this.value);
            document.documentElement.style.setProperty('--received-message-color', this.value);
        });

        let mentionStartIndex = -1;
        const savedScale = localStorage.getItem('messageFontScale') || '1.0';
        
        selector.value = savedScale;
        applyFontScale(savedScale);

        selector.addEventListener('change', function () {
            const scale = this.value;
            localStorage.setItem('messageFontScale', scale);
            document.documentElement.style.setProperty('--message-font-scale', scale);

            // Apply font size to textarea
            const textarea = document.querySelector('textarea[name="content"]');
            if (textarea) {
                textarea.style.fontSize = `${scale}rem`;
            }

            // Apply font size to existing messages
            document.querySelectorAll('.message-content, .message-text').forEach(el => {
                el.style.fontSize = `${scale}rem`;
            });
        });
        function applyFontScale(scale) {
            document.querySelectorAll('.message-content').forEach(el => {
                el.style.fontSize = `${scale}rem`;
            });
            document.querySelectorAll('.message-text').forEach(el => {
                el.style.fontSize = `${scale}rem`;
            });
        }
        if (!mentionSuggestions) {
            console.error('#mentionSuggestions element not found in the DOM');
            return;
        }

        function fetchMentionSuggestions(query) {
            console.log('Fetching suggestions for query:', query);
            fetch(`/search-users/?query=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    console.log('Suggestions fetched:', data);
                    if (data.users && data.users.length > 0) {
                        displayMentionSuggestions(data.users);
                    } else {
                        mentionSuggestions.style.display = 'none';
                    }
                })
                .catch(error => console.error('Error fetching mention suggestions:', error));
        }

        function displayMentionSuggestions(users) {
            // Get the suggestions element
            const mentionSuggestions = document.getElementById('mentionSuggestions');

            // Apply debug styles to ensure it is visible
            mentionSuggestions.style.position = 'absolute';
            mentionSuggestions.style.top = '50px'; // Adjust dynamically in your logic
            mentionSuggestions.style.left = '50px'; // Adjust dynamically in your logic
            mentionSuggestions.style.background = 'white';
            mentionSuggestions.style.border = '1px solid black';
            mentionSuggestions.style.zIndex = '99999';
            mentionSuggestions.style.display = 'block'; // Ensure it is displayed
            mentionSuggestions.style.visibility = 'visible';
            mentionSuggestions.style.opacity = '1';
            mentionSuggestions.style.outline = '2px solid red'; // Highlight for debugging

            // Add suggestions to the dropdown
            mentionSuggestions.innerHTML = ''; // Clear previous suggestions
            users.forEach(user => {
                const suggestionItem = document.createElement('div');
                suggestionItem.classList.add('list-group-item');
                suggestionItem.textContent = user.username;

                // Handle click on suggestion
                suggestionItem.addEventListener('click', function () {
                    const textBeforeMention = messageInput.value.substring(0, mentionStartIndex);
                    const textAfterMention = messageInput.value.substring(messageInput.selectionStart);
                    messageInput.value = `${textBeforeMention}@${user.username} ${textAfterMention}`;
                    mentionSuggestions.style.display = 'none';
                    mentionStartIndex = -1;
                });

                mentionSuggestions.appendChild(suggestionItem);
            });
        }
        function positionMentionSuggestions(inputElement, mentionSuggestions) {
            const rect = inputElement.getBoundingClientRect(); // Get the textarea's position and dimensions
            mentionSuggestions.style.position = 'absolute';
            mentionSuggestions.style.top = `${rect.bottom + window.scrollY}px`; // Position below the textarea
            mentionSuggestions.style.left = `${rect.left + window.scrollX}px`; // Align with the textarea's left
            mentionSuggestions.style.width = `${rect.width}px`; // Match the textarea's width
            mentionSuggestions.style.zIndex = '9999';
            mentionSuggestions.style.display = 'block';
        }
        messageInput.addEventListener('input', function () {
            const cursorPosition = messageInput.selectionStart;
            const textBeforeCursor = messageInput.value.substring(0, cursorPosition);

            // Detect if the user is typing a mention
            const mentionMatch = textBeforeCursor.match(/@[\w]*$/);

            if (mentionMatch) {
                const query = mentionMatch[0].substring(1); // Extract the query after "@"

                // Fetch suggestions based on the query
                fetch(`/search-users/?query=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.users && data.users.length > 0) {
                            displayMentionSuggestions(data.users); // Call the function with fetched users
                        } else {
                            mentionSuggestions.style.display = 'none'; // Hide if no suggestions
                        }
                    })
                    .catch(error => console.error('Error fetching mention suggestions:', error));
            } else {
                mentionSuggestions.style.display = 'none'; // Hide if no "@" detected
            }
        });

        document.addEventListener('click', function (event) {
            if (!mentionSuggestions.contains(event.target) && event.target !== messageInput) {
                mentionSuggestions.style.display = 'none';
            }
        });

        console.log('Mention suggestion script initialized');
    });
    
    document.addEventListener('DOMContentLoaded', function () {
        const textareas = document.querySelectorAll('.auto-expand');
        const conversationId = "{{ selected_conversation_id }}";
        const videoThumbnails = document.querySelectorAll('.chat-video-thumbnail');
        const previewVideo = document.querySelector('#previewVideo');
        const messagesContainer = document.getElementById('messages-container');
        const sendMessageForm = document.getElementById('sendMessageForm');
        const sendMessageButton = document.getElementById('sendMessageButton');
        const formAction = sendMessageForm ? sendMessageForm.getAttribute('action') : null;
        const spinner = document.getElementById('top-loading-spinner');
        if (!sendMessageForm) {
            console.error("sendMessageForm not found");
            return;
        }
        let currentPage = 1;
        let loading = false;
        let allLoaded = false;
        messagesContainer.addEventListener('scroll', async () => {
            if (loading || allLoaded) return;

            if (messagesContainer.scrollTop < 100) {
                loading = true;
                if (spinner) spinner.style.display = 'block'; // Show spinner
                currentPage++;

                const response = await fetch(`?page=${currentPage}`);
                const data = await response.json();

                const tempDiv = document.createElement("div");
                tempDiv.innerHTML = data.messages;

                const firstVisible = messagesContainer.scrollTop;
                messagesContainer.querySelector('.messages-list').prepend(...tempDiv.children);

                messagesContainer.scrollTop = tempDiv.scrollHeight + firstVisible;

                if (!data.has_previous) {
                    allLoaded = true;
                }

                loading = false;
                if (spinner) spinner.style.display = 'none'; // Hide spinner
            }
        });
        if (!conversationId) {
            console.error("Invalid conversation ID");
            return;
        }

        const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
        const wsUrl = `${wsScheme}://${window.location.host}/ws/chat/${conversationId}/`;
        const chatSocket = new WebSocket(wsUrl);
        window.chatSocket = chatSocket;

        function safeSend(socket, payload) {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(payload));
            } else {
                console.error("WebSocket not open; cannot send payload.", payload);
            }
        }

        function sendEditedMessage(messageId, newContent) {
            const parsedMessageId = parseInt(messageId, 10);

            if (isNaN(parsedMessageId) || parsedMessageId <= 0) {
                console.error(`Invalid message ID: ${messageId}`);
                return;
            }

            const payload = {
                type: 'edit_message',
                content: newContent.trim(),
                message_id: parsedMessageId,
            };
            console.log(`Payload to be sent via WebSocket: ${JSON.stringify(payload)}`);
            safeSend(chatSocket, payload);
        }

        const messageInput = sendMessageForm.querySelector('textarea[name="content"]');
        textareas.forEach(textarea => {
            textarea.addEventListener('input', function () {
                this.style.height = 'auto'; // Reset height
                if (this.scrollHeight <= 200) {
                    this.style.height = `${this.scrollHeight}px`; // Dynamically grow
                } else {
                    this.style.height = '200px'; // Limit height
                    this.style.overflowY = 'auto'; // Enable scrolling
                }
            });
        });
        const attachmentInput = sendMessageForm.querySelector('input[name="attachment"]');
        const filePreviewContainer = document.getElementById('file-preview-container');
        let isSubmitting = false; // Prevent duplicate submissions
        function ensureProgressBar() {
            let wrap = document.getElementById("upload-progress-wrap");
            if (!wrap) {
                wrap = document.createElement("div");
                wrap.id = "upload-progress-wrap";
                wrap.innerHTML = `
                    <div class="progress mt-2" style="height: 6px;">
                    <div class="progress-bar" id="upload-progress-bar" role="progressbar" style="width:0%"></div>
                    </div>
                `;
                if (filePreviewContainer) {
                    filePreviewContainer.appendChild(wrap);
                }
                }
                return document.getElementById("upload-progress-bar");
            }

            function removeProgressBar() {
                const existingWrap = document.getElementById("upload-progress-wrap");
                if (existingWrap) {
                    existingWrap.remove();
                }
            }

        async function sendViaHttp(file, text, editMessageId) {
            if (!formAction) return;
            const formData = new FormData();
            if (text) formData.append('content', text);
            if (file) formData.append('attachment', file);
            if (editMessageId) formData.append('edit_message_id', editMessageId);

            const response = await fetch(formAction, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: formData,
            });
            if (!response.ok) throw new Error('Failed to send message via HTTP.');
            const data = await response.json();
            const senderUsername = data.sender_username || data.sender || '';
            appendMessageToChat(data, senderUsername === '{{ request.user.username }}');
        }

        const generateClientId = () => {
            if (window.crypto && typeof window.crypto.randomUUID === "function") {
                return window.crypto.randomUUID();
            }
            return String(Date.now());
        };

        async function handleSendMessage(event) {
            if (isSubmitting) return;
            isSubmitting = true;

            const file = (attachmentInput && attachmentInput.files) ? attachmentInput.files[0] : null;
            const text = (messageInput ? messageInput.value : "").trim();
            const editMessageElement = document.getElementById('editMessageId');
            const editMessageId = editMessageElement ? editMessageElement.value : null;

            if (!file && !text) {
                alert("You cannot send an empty message.");
                isSubmitting = false;
                return;
            }

            if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
                try {
                    await sendViaHttp(file, text, editMessageId);
                    finishReset();
                } catch (httpError) {
                    console.error("HTTP send failed:", httpError);
                    alert("Unable to send message right now. Please try again.");
                    isSubmitting = false;
                }
                return;
            }

            try {
                if (file && file.size >= CHUNK_THRESHOLD) {
                    const bar = ensureProgressBar();
                    const onProgress = (pct) => { if (bar) bar.style.width = `${pct}%`; };
                    await uploadInChunks(file, pageOrgId, conversationId, onProgress);

                    if (text) {
                        chatSocket.send(JSON.stringify({
                            type: editMessageId ? 'edit_message' : 'message',
                            ...(editMessageId ? { message_id: parseInt(editMessageId, 10) } : {}),
                            message: text,
                            message_client_id: generateClientId(),
                        }));
                    }

                    finishReset();
                    removeProgressBar();
                    return;
                }

                if (file) {
                    const reader = new FileReader();
                    reader.onload = function () {
                        const payload = editMessageId
                            ? { type: 'edit_message', message_id: parseInt(editMessageId, 10), content: text }
                            : { type: 'message', message: text, message_client_id: generateClientId() };

                        payload.attachment = {
                            name: file.name,
                            type: file.type,
                            content: reader.result.split(',')[1],
                        };
                        chatSocket.send(JSON.stringify(payload));
                        finishReset();
                    };
                    reader.readAsDataURL(file);
                } else {
                    const payload = editMessageId
                        ? { type: 'edit_message', message_id: parseInt(editMessageId, 10), content: text }
                        : { type: 'message', message: text, message_client_id: generateClientId() };
                    chatSocket.send(JSON.stringify(payload));
                    finishReset();
                }
            } catch (err) {
                console.error("Send failed:", err);
                alert("Upload failed. Please try again.");
                isSubmitting = false;
            }
        }

        function finishReset() {
            messageInput.value = '';
            messageInput.style.height = '';
            messageInput.setAttribute('rows', 2);
            attachmentInput.value = '';
            if (filePreviewContainer) {
                filePreviewContainer.innerHTML = '';
            }
            const editInput = document.getElementById('editMessageId');
            if (editInput) {
                editInput.remove();
            }
            isSubmitting = false;
        }

        sendMessageForm.addEventListener('submit', function (e) {
            e.preventDefault();
            handleSendMessage(e);
        });
        if (sendMessageButton) {
            sendMessageButton.addEventListener('click', handleSendMessage);
        }
        if (messageInput) {
            messageInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    handleSendMessage();
                }
            });
        }
        chatSocket.onopen = function () {
            console.log("WebSocket connection established");
        };

        chatSocket.onclose = function () {
            console.error("WebSocket connection closed:", event.reason || "Unknown reason");
        };

        chatSocket.onerror = function (error) {
            console.error("WebSocket error:", error);
        };
        function formatTimestamp(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
        }
        // WebSocket message handling
        chatSocket.onmessage = function (e) {
            const data = JSON.parse(e.data);
            console.log('WebSocket received data:', data);
            if (data.type === 'chat_message' && data.event === 'attachment_pending') {
                // Optional: show “uploading…” toast/spinner
                console.log("Attachment incoming:", data.filename);
                return;
            }

            if (data.type === 'chat_message' && data.event === 'attachment_uploaded') {
                // Server has created the Message + broadcasted a lightweight event.
                // Show the file immediately (thumbnail may arrive later).
                appendMessageToChat({
                    attachment_url: data.attachment_url,
                    attachment_type: data.mime_type,
                    sender_username: data.uploaded_by,
                    timestamp: data.timestamp
                }, data.uploaded_by === '{{ request.user.username }}');
                return;
            }

            if (data.type === 'chat_message' && data.event === 'attachment_ready') {
                // Thumbnail ready—update any matching elements
                // (You can also just append a fresh message UI if you prefer)
                const thumbUrl = data.thumb_url;
                if (!thumbUrl) return;
                // naive: find last video anchor without thumbnail and replace
                const list = document.querySelector('.messages-list');
                if (list) {
                    const last = list.querySelector('a[target="_blank"][href*=".mp4"], a[target="_blank"][href*=".mov"]');
                    if (last) {
                        const li = last.closest('li');
                        if (li) {
                            const container = li.querySelector('.message-content');
                            if (container) {
                                container.innerHTML = `
                                <img 
                                    src="${thumbUrl}" 
                                    alt="Video Thumbnail" 
                                    class="chat-video-thumbnail" 
                                    data-video-src="${new URL(data.attachment_url, window.location.origin).href}" 
                                    data-bs-toggle="modal" 
                                    data-bs-target="#videoPreviewModal"
                                >
                            `;
                            }
                        }
                    }
                }
                return;
            }
            if (data.type === 'chat_message') {
                // Append new message to the chat
                appendMessageToChat(data, data.sender_username === '{{ request.user.username }}');
                // Reinitialize mention handlers for new messages
                //setupMentionClickHandlers();

            if (data.type === 'chat_message' && data.event === 'attachment_ready') {
                // Thumbnail ready—update any matching elements
                // (You can also just append a fresh message UI if you prefer)
                const thumbUrl = data.thumb_url;
                if (!thumbUrl) return;
                // naive: find last video anchor without thumbnail and replace
                const list = document.querySelector('.messages-list');
                if (list) {
                    const last = list.querySelector('a[target="_blank"][href*=".mp4"], a[target="_blank"][href*=".mov"]');
                    if (last) {
                        const li = last.closest('li');
                        if (li) {
                            const container = li.querySelector('.message-content');
                            if (container) {
                                container.innerHTML = `
                                <img 
                                    src="${thumbUrl}" 
                                    alt="Video Thumbnail" 
                                    class="chat-video-thumbnail" 
                                    data-video-src="${new URL(data.attachment_url, window.location.origin).href}" 
                                    data-bs-toggle="modal" 
                                    data-bs-target="#videoPreviewModal"
                                >
                            `;
                            }
                        }
                    }
                }
                return;
            }
            if (data.type === 'chat_message') {
                const currentUser = '{{ request.user.username }}';
                const senderUsername = data.sender_username || data.sender;
                appendMessageToChat(data, senderUsername === currentUser);
            }else if (data.type === 'edit_message') {
                console.log(`Editing message with ID: ${data.message_id}`);
                const messageElement = document.querySelector(`[data-message-id="${data.message_id}"] .message-content`);

                if (messageElement) {
                    // Update the message content
                    const messageTextElement = messageElement.querySelector('.message-text');
                    if (messageTextElement) {
                        messageTextElement.innerHTML = highlightMentions(data.content); // Apply mention highlighting
                    } else {
                        const newTextElement = document.createElement('p');
                        newTextElement.classList.add('message-text');
                        newTextElement.innerHTML = highlightMentions(data.content); // Apply mention highlighting
                        messageElement.prepend(newTextElement);
                    }

                    // Add "Edited" label if it doesn't exist
                    let editedLabel = messageElement.querySelector('.edited-label');
                    if (!editedLabel) {
                        editedLabel = document.createElement('small');
                        editedLabel.classList.add('text-muted', 'd-block', 'mt-1', 'edited-label');
                        editedLabel.textContent = '(Edited)';
                        messageElement.appendChild(editedLabel);
                    }

                    // Reinitialize mention handlers for edited messages
                    //setupMentionClickHandlers();
                } else {
                    console.error(`Message element with ID ${data.message_id} not found.`);
                }
            } else if (data.type === 'notification_message') {
                console.log("Notification message received:", data); // Debugging notifications
                displayNotification(data); // Ensure this function processes mentions correctly
            } else if (data.type === 'conversation_update') {
                const convoId = data.conversation_id;
                const preview = data.last_message_preview;
                const time = new Date(data.last_message_time);
                const formattedTime = time.toLocaleString(); // Match your UI format

                const convoElement = document.querySelector(`[data-conversation-id="${convoId}"]`);
                if (convoElement) {
                    const nameElement = convoElement.querySelector(".sidebar-conversation-name");
                    const timeElement = convoElement.querySelector("small");

                    if (nameElement) nameElement.innerText = preview;
                    if (timeElement) timeElement.innerText = formattedTime;

                    // Reorder conversation to top
                    const parent = convoElement.parentNode;
                    parent.removeChild(convoElement);
                    parent.prepend(convoElement);
                }
            }else if (data.type === 'calendar_prompt') {
                showCalendarPrompt(data.message, data.event_data);
            } else if (data.type === 'error') {
                console.error(`Error received: ${data.message}`);
            } else if (data.type === 'error') {
                console.error(`Error received: ${data.message}`);
            }
        };
        function showCalendarPrompt(message, eventData) {
            const container = document.getElementById("notifications") || document.body;
            const wrapper = document.createElement("div");
            wrapper.className = "alert alert-info d-flex justify-content-between align-items-center shadow-sm p-3 mb-2 rounded";
            wrapper.innerHTML = `
                <div>
                    <strong>📅 ${message}</strong>
                </div>
                <div>
                    <button class="btn btn-sm btn-success me-2">Yes</button>
                    <button class="btn btn-sm btn-outline-secondary">No</button>
                </div>
            `;

            const [yesBtn, noBtn] = wrapper.querySelectorAll("button");

            yesBtn.onclick = () => {
                fetch(`/${pageOrgId}/add-event/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie("csrftoken")
                    },
                    body: JSON.stringify({
                        title: eventData.title,
                        description: "Auto-created from chat message",
                        start: eventData.start,
                        end: eventData.end,
                        color: "#1E90FF",
                        all_day: false,
                        invite_users: [],
                        recurrence: {}
                    })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {
                        wrapper.innerHTML = `
                            ✅ Event added: <strong>${eventData.title}</strong><br>
                            <a class="btn btn-sm btn-primary mt-2" href="/agenda/${pageOrgId}/">View Event</a>
                        `;
                        setTimeout(() => wrapper.remove(), 8000);
                    } else {
                        alert("Failed to add event.");
                    }
                })
                .catch(err => {
                    console.error("Error adding event:", err);
                    alert("Error adding event.");
                });
            };

            noBtn.onclick = () => wrapper.remove();

            container.appendChild(wrapper);
        }

        function highlightMentions(content) {
            const mentionPattern = /@(\w+)/g;
            const currentUsername = "{{ request.user.username }}"; // From backend context

            return content.replace(mentionPattern, (match, username) => {
                if (username === currentUsername) {
                    return `<span class="mention bg-warning" data-username="${username}">@${username}</span>`;
                }
                return `<span class="mention" data-username="${username}">@${username}</span>`;
            });
        }
        function updateMessageInChat(data) {
            console.log("Updating message in chat:", data); // Log for debugging

            const messageElement = document.querySelector(`[data-message-id="${data.message_id}"]`);
            if (messageElement) {
                const messageContent = messageElement.querySelector('.message-content');
                if (messageContent) {
                    messageContent.innerHTML = `
                        <p>${data.content}</p>
                        ${data.is_edited ? '<small class="text-muted">(Edited)</small>' : ''}
                    `;
                }
            } else {
                console.error(`Message with ID ${data.message_id} not found.`);
            }
        }

        function resetEditState() {
            const editMessageIdInput = document.getElementById('editMessageId');
            if (editMessageIdInput) {
                editMessageIdInput.remove();
            }
            const messageInput = document.querySelector('textarea[name="content"]');
            messageInput.value = '';
        }
        videoThumbnails.forEach(thumbnail => {
            thumbnail.addEventListener('click', function () {
                const videoSrc = this.getAttribute('data-video-src');
                previewVideo.querySelector('source').src = videoSrc;
                previewVideo.load(); // Reload video in the modal
            });
        });

        function appendMessageToChat(messageData, isSender) {
            const messagesList = document.querySelector('.messages-list');
            const newMessage = document.createElement('li');
            newMessage.classList.add(
                'd-flex',
                isSender ? 'justify-content-end' : 'justify-content-start',
                'mb-4'
            );
            const textContent =
                messageData.message ||
                messageData.message_content ||
                '';

            const senderUsername =
                messageData.sender_username ||
                messageData.sender ||
                'Unknown';

            let attachmentContent = '';

            if (messageData.attachment_url) {
                const attachmentUrl = new URL(messageData.attachment_url, window.location.origin).href;

                // Handle video attachments with thumbnails
                if (messageData.attachment_type && messageData.attachment_type.startsWith('video/')) {
                    if (messageData.thumbnail_url) {
                        attachmentContent = `
                            <img 
                                src="${messageData.thumbnail_url}" 
                                alt="Video Thumbnail" 
                                class="chat-video-thumbnail" 
                                data-video-src="${attachmentUrl}" 
                                data-bs-toggle="modal" 
                                data-bs-target="#videoPreviewModal"
                            >
                        `;
                    } else {
                        attachmentContent = `<a href="${attachmentUrl}" target="_blank">View Video</a>`;
                    }
                }
                // Handle image attachments
                else if (messageData.attachment_type && messageData.attachment_type.startsWith('image/')) {
                    attachmentContent = `
                        <img 
                            src="${attachmentUrl}" 
                            alt="Attached Image" 
                            style="max-width: 100%; max-height: 300px;"
                        >
                    `;
                }
                // Handle PDF attachments
                else if (messageData.attachment_type === 'application/pdf') {
                    attachmentContent = `<a href="${attachmentUrl}" target="_blank">View PDF</a>`;
                }
                // Handle other file attachments
                else {
                    attachmentContent = `<a href="${attachmentUrl}" target="_blank">Download File</a>`;
                }
            }

            // Construct the message HTML
            newMessage.innerHTML = `
                <div class="message-wrapper ${isSender ? 'justify-content-end' : 'justify-content-start'}">
                    ${!isSender ? `
                        <img src="${messageData.sender_profile_picture}" 
                            alt="${senderUsername}'s Profile Picture" 
                            class="profile-pic-small me-3">
                    ` : ''}
                    <div class="message-body-container">
                        ${!isSender ? `
                            <div class="message-meta mb-1">
                                <strong class="message-sender">${senderUsername}</strong><br>
                                <small class="message-timestamp">${formatTimestamp(messageData.timestamp)}</small>
                            </div>
                        ` : `
                            <div class="message-meta text-end mb-1">
                                <small class="message-timestamp">${formatTimestamp(messageData.timestamp)}</small>
                            </div>
                        `}
                        <div class="message-content">
                            ${messageData.attachment_url ? getAttachmentHTML(messageData) : `
                                <p class="message-text">${highlightMentions(textContent)}</p>
                            `}
                        </div>
                    </div>
                    ${isSender ? `
                        <img src="${messageData.sender_profile_picture}" 
                            alt="Your Profile Picture" 
                            class="profile-pic-small ms-3">
                    ` : ''}
                </div>
            `;
            messagesList.appendChild(newMessage);

            
            const savedScale = localStorage.getItem('messageFontScale') || '1.0';
            newMessage.querySelectorAll('.message-content, .message-text').forEach(el => {
                el.style.fontSize = `${savedScale}rem`;
            });
            requestAnimationFrame(() => {
                newMessage.style.display = 'none';
                void newMessage.offsetHeight; // trigger reflow
                newMessage.style.display = '';
            });
            scrollToBottom();
            // setupMentionClickHandlers(); // re-bind mention clicks
            // Attach click event to video thumbnails for modal preview
            if (messageData.attachment_type && messageData.attachment_type.startsWith('video/')) {
                const videoThumbnail = newMessage.querySelector('.chat-video-thumbnail');
                if (videoThumbnail) {
                    videoThumbnail.addEventListener('click', function () {
                        const videoSrc = this.getAttribute('data-video-src');
                        const previewVideo = document.querySelector('#previewVideo');
                        previewVideo.querySelector('source').src = videoSrc;
                        previewVideo.load();
                    });
                }
            }
        }

        function scrollToBottom() {
            const messagesContainer = document.querySelector('.conversation-content');
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }
        const addMembersForm = document.getElementById('addMembersForm');
            const addMembersInput = document.getElementById('addMembersInput');
            const addMembersSuggestions = document.getElementById('addMembersSuggestions');
            const selectedAddMembersBox = document.getElementById('selectedAddMembers');
            let selectedUsers = [];

            // Handle input in the Add Members field
            addMembersInput.addEventListener('input', function () {
                const query = this.value;

                if (query.length > 0) {
                    fetch(`/search-users/?query=${encodeURIComponent(query)}`, {
                        method: 'GET',
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    })
                        .then((response) => response.json())
                        .then((data) => {
                            addMembersSuggestions.innerHTML = '';
                            if (data.users.length > 0) {
                                data.users.forEach((user) => {
                                    const suggestionItem = document.createElement('a');
                                    suggestionItem.href = '#';
                                    suggestionItem.className = 'list-group-item list-group-item-action';
                                    suggestionItem.textContent = user.username;

                                    suggestionItem.addEventListener('click', function (e) {
                                        e.preventDefault();
                                        if (!selectedUsers.includes(user.username)) {
                                            selectedUsers.push(user.username);

                                            addMembersInput.value = '';
                                            addMembersSuggestions.innerHTML = '';

                                            const userBadge = document.createElement('span');
                                            userBadge.className = 'xperiment-badge bg-secondary m-1';
                                            userBadge.textContent = user.username;

                                            const removeBtn = document.createElement('span');
                                            removeBtn.className = 'ms-1 text-danger';
                                            removeBtn.innerHTML = '&times;';
                                            removeBtn.style.cursor = 'pointer';
                                            removeBtn.addEventListener('click', () => {
                                                selectedUsers = selectedUsers.filter((u) => u !== user.username);
                                                selectedAddMembersBox.removeChild(userBadge);
                                            });

                                            userBadge.appendChild(removeBtn);
                                            selectedAddMembersBox.appendChild(userBadge);
                                        }
                                    });

                                    addMembersSuggestions.appendChild(suggestionItem);
                                });
                            } else {
                                addMembersSuggestions.innerHTML = '<li class="list-group-item">No users found</li>';
                            }
                        })
                        .catch((error) => console.error('Error fetching users:', error));
                } else {
                    addMembersSuggestions.innerHTML = '';
                }
            });

            // Handle form submission for adding members
            addMembersForm.addEventListener('submit', function (e) {
                e.preventDefault();

                if (selectedUsers.length === 0) {
                    alert('Please select at least one user to add.');
                    return;
                }

                const conversationId = "{{ conversation.id }}";
                const url = `/${pageOrgId}/conversation/${conversationId}/add-members/`;

                fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({ members: selectedUsers }),
                })
                    .then((response) => response.json())
                    .then((data) => {
                        if (data.status === 'success') {
                            alert('Members added successfully!');
                            window.location.reload();
                        } else {
                            alert(`Error: ${data.message}`);
                        }
                    })
                    .catch((error) => console.error('Error:', error));
            });
            const dropdownContainer = document.querySelector('.conversation-box');
                if (dropdownContainer) {
                    dropdownContainer.addEventListener('click', function (event) {
                        const toggleButton = event.target.closest('.dropdown-item[data-conversation-id]');
                        if (toggleButton) {
                            const conversationId = toggleButton.getAttribute('data-conversation-id');
                            const orgId = toggleButton.getAttribute('data-org-id');

                            if (!conversationId || !orgId) {
                                console.error("Conversation ID or Organization ID is missing. Cannot toggle mute.");
                                return;
                            }

                            const url = `/${orgId}/conversation/${conversationId}/toggle-mute/`;

                            fetch(url, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': getCookie('csrftoken'),
                                },
                            })
                                .then((response) => response.json())
                                .then((data) => {
                                    if (data.status === 'muted' || data.status === 'unmuted') {
                                        console.log('Mute toggle response:', data);

                                        // Update the dropdown button UI
                                        toggleButton.setAttribute('data-muted', data.status === 'muted');
                                        toggleButton.innerHTML = `
                                            <i class="fas ${data.status === 'muted' ? 'fa-bell-slash' : 'fa-bell'}"></i>
                                            ${data.status === 'muted' ? 'Unmute Notifications' : 'Mute Notifications'}
                                        `;

                                        // Update the sidebar icon dynamically
                                        const sidebarIcon = document.querySelector(
                                            `.conversation-item[data-conversation-id="${conversationId}"] .fas.fa-bell, .fas.fa-bell-slash`
                                        );
                                        if (sidebarIcon) {
                                            sidebarIcon.className = `fas ${data.status === 'muted' ? 'fa-bell-slash' : 'fa-bell'} text-muted`;
                                            sidebarIcon.setAttribute('title', data.status === 'muted' ? 'Muted' : 'Unmuted');
                                        }
                                    } else {
                                        console.error('Failed to toggle mute. Server response:', data);
                                    }
                                })
                                .catch((error) => console.error('Error while toggling mute:', error));
                        }
                    });
                }
                const toggleMuteButton = document.getElementById('toggleMuteButton');
                if (toggleMuteButton) {
                    toggleMuteButton.addEventListener('click', function () {
                        const conversationId = this.getAttribute('data-conversation-id');
                        const orgId = this.getAttribute('data-org-id');

                        console.log(`Toggle mute for conversation ID: ${conversationId}, Org ID: ${orgId}`);

                        if (!conversationId || !orgId) {
                            console.error("Conversation ID or Organization ID is missing. Cannot toggle mute.");
                            return;
                        }

                        const url = `/${orgId}/conversation/${conversationId}/toggle-mute/`;

                        fetch(url, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCookie('csrftoken'),
                            },
                        })
                            .then((response) => response.json())
                            .then((data) => {
                                if (data.status === 'muted' || data.status === 'unmuted') {
                                    console.log('Mute toggle response:', data);

                                    // Update the button UI
                                    this.setAttribute('data-muted', data.status === 'muted');
                                    this.innerHTML = `
                                        <i class="fas ${data.status === 'muted' ? 'fa-bell-slash' : 'fa-bell'}"></i>
                                        ${data.status === 'muted' ? 'Unmute Notifications' : 'Mute Notifications'}
                                    `;

                                    // Update the sidebar icon dynamically
                                    const sidebarIcon = document.querySelector(
                                        `.conversation-item[data-conversation-id="${conversationId}"] .fas.fa-bell, .fas.fa-bell-slash`
                                    );
                                    if (sidebarIcon) {
                                        sidebarIcon.className = `fas ${data.status === 'muted' ? 'fa-bell-slash' : 'fa-bell'} text-muted`;
                                        sidebarIcon.setAttribute(
                                            'title',
                                            data.status === 'muted' ? 'Muted' : 'Unmuted'
                                        );
                                    }
                                } else {
                                    console.error('Failed to toggle mute. Server response:', data);
                                }
                            })
                            .catch((error) => console.error('Error while toggling mute:', error));
                    });
                }
            
                const sidebar = document.querySelector('.list-group');

                if (sidebar) {
                    sidebar.addEventListener('click', function (event) {
                    const target = event.target.closest('.conversation-item');

                    // 🔒 Ignore if target has an href (search results already do)
                    if (target && !target.hasAttribute('href')) {
                        const conversationId = target.getAttribute('data-conversation-id');
                        const isAdmin = {{ is_admin|yesno:"true,false" }};

                        const pathPrefix = isAdmin ? 'admin/conversation' : 'conversation';
                        window.location.href = `/${pageOrgId}/${pathPrefix}/${conversationId}/`;
                    }
                });
            }
            // Initialize mute buttons for dropdown options only
            const muteButtons = document.querySelectorAll('.mute-button');
            muteButtons.forEach((button) => {
                button.addEventListener('click', function (e) {
                    e.preventDefault(); // Prevent default button behavior

                    const conversationId = parseInt(this.getAttribute('data-conversation-id'), 10);
                    const orgId = this.getAttribute('data-org-id');
                    const isMuted = this.getAttribute('data-muted') === 'true';

                    if (!conversationId || !orgId) {
                        console.error("Missing conversation or organization ID.");
                        return;
                    }

                    const url = `/${orgId}/conversation/${conversationId}/toggle-mute/`;

                    fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                        },
                    })
                        .then((response) => response.json())
                        .then((data) => {
                            if (data.status === 'muted' || data.status === 'unmuted') {
                                const newStatus = data.status === 'muted';

                                // Update the button text and icon
                                this.setAttribute('data-muted', newStatus);
                                this.innerHTML = `
                                    <i class="fas ${newStatus ? 'fa-bell-slash' : 'fa-bell'}"></i>
                                    ${newStatus ? 'Unmute Notifications' : 'Mute Notifications'}
                                `;

                                // Update the sidebar icon dynamically
                                const sidebarItem = document.querySelector(
                                    `.conversation-item[data-conversation-id="${conversationId}"]`
                                );
                                if (sidebarItem) {
                                    const icon = sidebarItem.querySelector('.fas.fa-bell, .fas.fa-bell-slash');
                                    if (icon) {
                                        icon.className = `fas ${newStatus ? 'fa-bell-slash' : 'fa-bell'} text-muted`;
                                        icon.setAttribute('title', newStatus ? 'Muted' : 'Unmuted');
                                    }
                                }

                                // Update localStorage for muted conversations
                                const mutedConversations = JSON.parse(localStorage.getItem('mutedConversations')) || [];
                                if (newStatus) {
                                    // Add to muted conversations if not already present
                                    if (!mutedConversations.includes(conversationId)) {
                                        mutedConversations.push(conversationId);
                                    }
                                } else {
                                    // Remove from muted conversations
                                    const index = mutedConversations.indexOf(conversationId);
                                    if (index !== -1) {
                                        mutedConversations.splice(index, 1);
                                    }
                                }
                                localStorage.setItem('mutedConversations', JSON.stringify(mutedConversations));
                            } else {
                                console.error("Failed to toggle mute:", data);
                            }
                        })
                        .catch((error) => console.error("Error toggling mute:", error));
                });
            });
            
            
            // Notification Links Setup
            function setupNotificationLinks() {
                const notificationLinks = document.querySelectorAll('.notification-link');
                const conversationContent = document.querySelector('.conversation-content');

                notificationLinks.forEach((link) => {
                    link.addEventListener('click', function (e) {
                        e.preventDefault(); // Stop default navigation
                        const notificationUrl = this.href;

                        fetch(notificationUrl, {
                            method: 'GET',
                            headers: {
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                        })
                            .then((response) => {
                                if (!response.ok) {
                                    throw new Error('Network response was not ok');
                                }
                                return response.json();
                            })
                            .then((data) => {
                                console.log('Notification JSON:', data); // Debugging

                                // Inject content into the conversationContent area
                                conversationContent.innerHTML = `
                                    <div class="notification-detail-container">
                                        <div class="notification-header d-flex align-items-center mb-4">
                                            <img src="/static/img/notification-icon.png" 
                                                alt="Notification Icon" 
                                                class="profile-pic-extra-large me-3">
                                            <h3 class="mb-0">Notification Details</h3>
                                        </div>
                                        <div class="notification-body bg-light p-4 rounded shadow-sm">
                                            <h4 class="notification-title mb-3">${data.title || 'Notification'}</h4>
                                            <p class="text-muted mb-2"><strong>From:</strong> ${data.sender_name || 'Unknown'}</p>
                                            <p class="text-muted mb-4"><strong>Date:</strong> ${data.timestamp || ''}</p>
                                            <div class="notification-message">
                                                <p>${data.message || ''}</p>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            })
                            .catch((error) => {
                                console.error('Error fetching notification:', error);
                                conversationContent.innerHTML = `
                                    <div class="alert alert-danger" role="alert">
                                        Failed to load notification. Please try again.
                                    </div>
                                `;
                            });
                    });
                });
            }

            setupNotificationLinks();

            document.querySelectorAll('.chat-video').forEach(video => {
                video.addEventListener('click', function () {
                    const previewVideo = document.querySelector('#previewVideo');
                    previewVideo.querySelector('source').src = this.querySelector('source').src;
                    previewVideo.load(); // Reload video in modal
                    const modal = new bootstrap.Modal(document.querySelector('#videoPreviewModal'));
                    modal.show();
                });
            });
            document.querySelectorAll('.chat-video-thumbnail').forEach(thumbnail => {
                thumbnail.addEventListener('click', function () {
                    const videoSrc = this.getAttribute('data-video-src');
                    const previewVideo = document.querySelector('#previewVideo');
                    previewVideo.querySelector('source').src = videoSrc;
                    previewVideo.load(); // Load video in the modal
                });
            });

            const attachmentInputEl = document.querySelector('#attachment');
            if (attachmentInputEl) {
                attachmentInputEl.addEventListener('change', function () {
                    const file = this.files[0];
                    const previewContainer = document.getElementById('file-preview-container');
                    if (!previewContainer) return;
                    previewContainer.innerHTML = '';

                    if (!file) return;

                    if (file.type.startsWith('image/')) {
                        const reader = new FileReader();
                        reader.onload = function (e) {
                            const imgUrl = e.target.result;
                            const img = document.createElement('img');
                            img.src = imgUrl;
                            img.style.maxWidth = '200px';
                            img.style.marginTop = '10px';
                            img.alt = 'Preview';
                            img.className = 'img-thumbnail';
                            img.style.cursor = 'pointer';
                            img.addEventListener('click', function () {
                                const previewImage = document.getElementById('previewImage');
                                if (previewImage) {
                                    previewImage.setAttribute('src', imgUrl);
                                    const modal = new bootstrap.Modal(document.getElementById('imagePreviewModal'));
                                    modal.show();
                                }
                            });
                            previewContainer.appendChild(img);
                        };
                        reader.readAsDataURL(file);
                    } else if (file.type === 'application/pdf') {
                        const link = document.createElement('a');
                        link.href = URL.createObjectURL(file);
                        link.textContent = 'Preview PDF';
                        link.target = '_blank';
                        link.style.display = 'block';
                        link.style.marginTop = '10px';
                        previewContainer.appendChild(link);
                    } else {
                        const fileName = document.createElement('p');
                        fileName.textContent = `Selected file: ${file.name}`;
                        fileName.className = 'text-muted';
                        fileName.style.marginTop = '10px';
                        previewContainer.appendChild(fileName);
                    }
                });
            }
        });
    });
