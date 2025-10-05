document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    // --- DOM Elements ---
    const messageTextarea = document.getElementById('message');
    const imageUrlInput = document.getElementById('image-url');
    const chatSelectionContainer = document.getElementById('chat-selection-container');
    const groupsConfigContainer = document.getElementById('groups-config-container');
    const loadingChatsP = document.getElementById('loading-chats');
    const noChatsSelectedP = document.getElementById('no-chats-selected');

    // --- Initialize the Web App ---
    tg.ready();
    tg.expand();
    tg.MainButton.text = "Save Configuration";
    tg.MainButton.show();
    tg.MainButton.disable(); // Disabled until chats are loaded

    // --- 1. Signal to Bot that the Web App is ready ---
    tg.sendData(JSON.stringify({ type: "ready" }));

    // --- 2. Listen for the Bot's response with the chat list ---
    tg.onEvent('web_app_data_recieved', function(data) {
        try {
            const chatData = JSON.parse(data.data);
            populateChatList(chatData.chats);
        } catch (e) {
            loadingChatsP.innerText = 'Error loading chats. Please try again.';
            console.error(e);
        }
    });

    function populateChatList(chats) {
        loadingChatsP.style.display = 'none'; // Hide loading message
        tg.MainButton.enable(); // Enable save button

        if (!chats || chats.length === 0) {
            chatSelectionContainer.innerHTML = '<p>No groups or channels found.</p>';
            return;
        }

        chats.forEach(chat => {
            const div = document.createElement('div');
            div.className = 'chat-item';
            div.innerHTML = `
                <input type="checkbox" id="chat-${chat.id}" value="${chat.id}" data-title="${chat.title}">
                <label for="chat-${chat.id}">${chat.title}</label>
            `;
            chatSelectionContainer.appendChild(div);

            // Add event listener to the new checkbox
            div.querySelector('input').addEventListener('change', handleCheckboxChange);
        });
    }

    function handleCheckboxChange(event) {
        const checkbox = event.target;
        const chatId = checkbox.value;
        const chatTitle = checkbox.getAttribute('data-title');
        const existingConfigRow = document.getElementById(`config-${chatId}`);

        noChatsSelectedP.style.display = 'none';

        if (checkbox.checked && !existingConfigRow) {
            // Add a configuration row
            const configDiv = document.createElement('div');
            configDiv.className = 'group-entry';
            configDiv.id = `config-${chatId}`;
            configDiv.innerHTML = `
                <label>${chatTitle}</label>
                <input type="number" class="group-interval" placeholder="Interval (hours)" data-id="${chatId}">
            `;
            groupsConfigContainer.appendChild(configDiv);
        } else if (!checkbox.checked && existingConfigRow) {
            // Remove the configuration row
            existingConfigRow.remove();
        }
    }

    // --- 3. Send final configuration back to the Bot ---
    tg.MainButton.onClick(() => {
        const message = messageTextarea.value;
        const imageUrl = imageUrlInput.value.trim();
        const groups = {};

        document.querySelectorAll('.group-interval').forEach(input => {
            const id = input.getAttribute('data-id');
            const interval = parseFloat(input.value);

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
```**Remember to deploy these changes** to your GitHub Pages repository.
