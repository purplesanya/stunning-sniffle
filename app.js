document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    const messageTextarea = document.getElementById('message');
    const imageUrlInput = document.getElementById('image-url'); // NEW: Get the image input
    const groupsContainer = document.getElementById('groups-container');
    const addGroupBtn = document.getElementById('add-group-btn');

    tg.ready();
    tg.expand();
    tg.MainButton.text = "Save Configuration";
    tg.MainButton.show();

    const addGroupRow = (id = '', interval = '') => {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'group-entry';
        groupDiv.innerHTML = `
            <input type="text" class="group-id" placeholder="Group ID or @username" value="${id}">
            <input type="number" class="group-interval" placeholder="Interval (hours)" value="${interval}">
            <button class="remove-btn">X</button>
        `;
        groupsContainer.appendChild(groupDiv);
        groupDiv.querySelector('.remove-btn').addEventListener('click', () => {
            groupDiv.remove();
        });
    };
    
    addGroupBtn.addEventListener('click', () => {
        addGroupRow();
    });

    // --- Main Logic: Send data back to the bot ---
    tg.MainButton.onClick(() => {
        const message = messageTextarea.value;
        const imageUrl = imageUrlInput.value.trim(); // NEW: Get the image URL
        const groups = {};

        document.querySelectorAll('.group-entry').forEach(entry => {
            const id = entry.querySelector('.group-id').value.trim();
            const interval = parseFloat(entry.querySelector('.group-interval').value);

            if (id && !isNaN(interval) && interval > 0) {
                groups[id] = { interval_hours: interval };
            }
        });

        // Construct the final data object
        const dataToSend = {
            message: message,
            image_url: imageUrl, // NEW: Add image_url to the data
            groups: groups
        };

        // Use the Telegram Web App API to send data to the bot
        tg.sendData(JSON.stringify(dataToSend));
    });

    addGroupRow();
});
