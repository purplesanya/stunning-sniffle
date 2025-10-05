document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    // --- DOM Elements ---
    const messageTextarea = document.getElementById('message');
    const imageUrlInput = document.getElementById('image-url');
    const chatListContainer = document.getElementById('chat-list-container');
    const loadingChatsP = document.getElementById('loading-chats');

    // --- Initialize the Web App ---
    tg.ready();
    tg.expand();
    tg.MainButton.text = "Save Configuration";

    // --- Tell the bot we are ready for data ---
    // The bot will receive this and reply with the combined config
    tg.sendData(JSON.stringify({ type: "get_data" }));
    
    // --- Listen for the bot's data response ---
    tg.onEvent('web_app_data_recieved', function(event) {
        try {
            const data = JSON.parse(event.data);
            populateForm(data);
        } catch (e) {
            loadingChatsP.innerText = 'Error loading initial data.';
            console.error(e);
        }
    });

    function populateForm(data) {
        loadingChatsP.style.display = 'none';
        tg.MainButton.show();

        // Populate the message and image URL from saved config
        messageTextarea.value = data.config.message || '';
        imageUrlInput.value = data.config.image_url || '';

        // Populate the chat list
        if (!data.chats || data.chats.length === 0) {
            chatListContainer.innerHTML = '<p>Could not find any groups or channels.</p>';
            return;
        }

        data.chats.forEach(chat => {
            // Check if this chat was previously saved in the user's config
            const savedGroup = data.config.groups ? data.config.groups[chat.id] : null;
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
                </div>
            `;
            chatListContainer.appendChild(div);
        });
    }

    // --- Send final configuration back to the Bot ---
    tg.MainButton.onClick(() => {
        const message = messageTextarea.value;
        const imageUrl = imageUrlInput.value.trim();
        const groups = {};

        document.querySelectorAll('.chat-selector input[type="checkbox"]:checked').forEach(checkbox => {
            const id = checkbox.value;
            const intervalInput = document.querySelector(`.group-interval[data-id="${id}"]`);
            const interval = parseFloat(intervalInput.value);

            if (id && !isNaN(interval) && interval > 0) {
                groups[id] = { interval_hours: interval };
            }
        });

        const dataToSend = {
            type: "save",
            message: message,
            image_url: imageUrl,
            groups: groups
        };

        tg.sendData(JSON.stringify(dataToSend));
    });
});
