document.addEventListener('DOMContentLoaded', function () {
    const tg = window.Telegram.WebApp;

    const messageTextarea = document.getElementById('message');
    const groupsContainer = document.getElementById('groups-container');
    const addGroupBtn = document.getElementById('add-group-btn');

    // Initialize the Web App
    tg.ready();
    tg.expand();

    // Configure the Main Button to save and send data
    tg.MainButton.text = "Save Configuration";
    tg.MainButton.show();

    // Function to add a new group input row
    const addGroupRow = (id = '', interval = '') => {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'group-entry';
        groupDiv.innerHTML = `
            <input type="text" class="group-id" placeholder="Group ID or @username" value="${id}">
            <input type="number" class="group-interval" placeholder="Interval (hours)" value="${interval}">
            <button class="remove-btn">X</button>
        `;
        groupsContainer.appendChild(groupDiv);

        // Add event listener to the new remove button
        groupDiv.querySelector('.remove-btn').addEventListener('click', () => {
            groupDiv.remove();
        });
    };

    // Add a group when the button is clicked
    addGroupBtn.addEventListener('click', () => {
        addGroupRow();
    });

    // --- Main Logic: Send data back to the bot ---
    tg.MainButton.onClick(() => {
        const message = messageTextarea.value;
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
            groups: groups
        };

        // Use the Telegram Web App API to send data to the bot
        tg.sendData(JSON.stringify(dataToSend));

        // Optionally, close the web app after sending
        // tg.close();
    });

    // For simplicity, we start with one empty group row
    addGroupRow();
});