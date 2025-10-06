document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    // --- DOM Elements ---
    const messageTextarea = document.getElementById('message');
    const imageUrlInput = document.getElementById('image-url');
    const chatListContainer = document.getElementById('chat-list-container');
    const loadingChatsP = document.getElementById('loading-chats');

    // --- Setup ---
    tg.ready();
    tg.expand();
    tg.MainButton.text = "Save Configuration";

    // --- Robust URL-safe Base64 decoder ---
    function urlBase64Decode(str) {
        let output = str.replace(/-/g, '+').replace(/_/g, '/');
        switch (output.length % 4) {
            case 0: break;
            case 2: output += '=='; break;
            case 3: output += '='; break;
            default: throw 'Illegal base64url string!';
        }
        try {
            return decodeURIComponent(atob(output).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
        } catch (e) {
            console.error("Base64 decoding failed:", e);
            throw e;
        }
    }

    setTimeout(loadInitialData, 100);

    function loadInitialData() {
        let rawHash = window.location.hash.substring(1);
        const tgDataIndex = rawHash.indexOf('?');
        if (tgDataIndex !== -1) {
            rawHash = rawHash.substring(0, tgDataIndex);
        }
        if (rawHash) {
            try {
                const decodedJsonString = urlBase64Decode(rawHash);
                const initialData = JSON.parse(decodedJsonString);
                populateForm(initialData);
            } catch (e) {
                loadingChatsP.innerHTML = `<p><strong>Fatal Error:</strong> Could not parse initial data.</p><p><strong>Error:</strong> ${e.message}</p>`;
                console.error('URL/Base64/JSON parsing failed:', e);
            }
        } else {
            loadingChatsP.innerText = 'Error: No initial data in URL. Please try again.';
        }
    }

    function populateForm(data) {
        loadingChatsP.style.display = 'none';
        tg.MainButton.show();
        messageTextarea.value = data.config.message || '';
        imageUrlInput.value = data.config.image_url || '';

        if (!data.chats || data.chats.length === 0) {
            chatListContainer.innerHTML = '<p>Could not find any groups or channels in your account.</p>';
            return;
        }

        data.chats.forEach(chat => {
            const savedGroup = data.config.groups ? data.config.groups[String(chat.id)] : null;
            const isChecked = savedGroup ? 'checked' : '';
            const intervalValue = savedGroup ? savedGroup.interval_hours : '';

            const div = document.createElement('div');
            div.className = 'chat-item';
            div.innerHTML = `
                <div class="chat-selector">
                    <input type="checkbox" id="chat-${chat.id}" value="${chat.id}" data-title="${chat.title}" ${isChecked}>
                    <label for="chat-${chat.id}">${chat.title}</label>
                </div>
                <div class="interval-input">
                    <input type="number" class="group-interval" placeholder="Hours" value="${intervalValue}" data-id="${chat.id}">
                    <!-- NEW: Test Send Button -->
                    <button class="test-btn" data-id="${chat.id}">Test</button>
                </div>
            `;
            chatListContainer.appendChild(div);
        });

        // Add event listeners to all new test buttons
        document.querySelectorAll('.test-btn').forEach(button => {
            button.addEventListener('click', handleTestSend);
        });
    }

    function handleTestSend(event) {
        const testButton = event.target;
        const chatId = testButton.getAttribute('data-id');
        
        // Temporarily disable button to prevent multiple clicks
        testButton.innerText = '...';
        testButton.disabled = true;

        const dataToSend = {
            type: "test_send",
            message: messageTextarea.value,
            image_url: imageUrlInput.value.trim(),
            test_chat_id: chatId
        };

        tg.sendData(JSON.stringify(dataToSend));
        
        // Re-enable the button after a short delay
        setTimeout(() => {
            testButton.innerText = 'Test';
            testButton.disabled = false;
        }, 2000); // 2-second cooldown
    }

   tg.MainButton.onClick(() => {
        const message = messageTextarea.value;
        const imageUrl = imageUrlInput.value.trim();
        const groups = {};
        let hasValidGroups = false;

        document.querySelectorAll('.chat-selector input[type="checkbox"]:checked').forEach(checkbox => {
            const id = checkbox.value;
            const intervalInput = document.querySelector(`.group-interval[data-id="${id}"]`);
            const interval = parseFloat(intervalInput.value);

            if (id && !isNaN(interval) && interval > 0) {
                groups[id] = { interval_hours: interval };
                hasValidGroups = true;
            }
        });
        
        // --- CRITICAL FIX: Prevent saving if no valid groups are configured ---
        if (!hasValidGroups) {
            tg.showAlert("No chats selected or no valid intervals provided. Please check a chat and enter a positive number for the hours.");
            return; // Stop the save process
        }
        
        const dataToSend = { type: "save", message: message, image_url: imageUrl, groups: groups };
        tg.sendData(JSON.stringify(dataToSend));
    });
});
