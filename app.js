document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    const messageTextarea = document.getElementById('message');
    const imageUrlInput = document.getElementById('image-url');
    const chatListContainer = document.getElementById('chat-list-container');
    const loadingChatsP = document.getElementById('loading-chats');

    tg.ready();
    tg.expand();
    tg.MainButton.text = "Save Configuration";

    // --- CRITICAL FIX: ---
    // Use a short timeout to ensure the window.location.hash has been
    // populated by the browser before we try to read it. This solves the race condition.
    setTimeout(loadInitialData, 100); // 100 millisecond delay is plenty.

    function loadInitialData() {
        const hash = window.location.hash.substring(1);
        if (hash) {
            try {
                const decodedData = decodeURIComponent(hash);
                const initialData = JSON.parse(decodedData);
                populateForm(initialData);
            } catch (e) {
                loadingChatsP.innerText = 'Error: Could not parse initial data from URL.';
                console.error(e);
            }
        } else {
            loadingChatsP.innerText = 'Error: No initial data found in URL. Please try launching from Telegram again.';
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
                </div>
            `;
            chatListContainer.appendChild(div);
        });
    }

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
