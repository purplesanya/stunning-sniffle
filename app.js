// script.js

// Initialize the Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand();

// Function to populate the group list
function populateGroupList() {
    const groupListContainer = document.getElementById("group-list");

    try {
        const urlParams = new URLSearchParams(window.location.search);
        const groupsParam = urlParams.get('groups');

        if (!groupsParam) {
            groupListContainer.innerHTML = "<p>No group data found. Please use the /config command in the bot.</p>";
            return;
        }

        const decodedGroups = decodeURIComponent(groupsParam);
        const groups = JSON.parse(decodedGroups);

        if (groups && groups.length > 0) {
            groupListContainer.innerHTML = ""; // Clear loading message
            groups.forEach(group => {
                const item = document.createElement("div");
                item.className = "group-item";
                
                // Telegram group IDs are large negative numbers. The ID in Telethon is just the number part.
                // We must reconstruct the full group ID (-100... + ID) for it to work.
                const fullGroupId = -1000000000000 - group.id > -1000000000000 ? group.id : -1000000000000 - group.id;

                item.innerHTML = `
                    <input type="checkbox" id="group-${group.id}" value="${fullGroupId}" class="group-checkbox">
                    <label for="group-${group.id}">${group.title}</label>
                `;
                groupListContainer.appendChild(item);
            });
        } else {
            groupListContainer.innerHTML = "<p>Could not find any available groups.</p>";
        }

    } catch (e) {
        groupListContainer.innerHTML = `<p>Error parsing group data: ${e.message}</p>`;
        console.error(e);
    }
}

// Function to send data back to the bot
function sendDataToBot() {
    const selectedGroups = [];
    document.querySelectorAll(".group-checkbox:checked").forEach(checkbox => {
        selectedGroups.push(checkbox.value);
    });

    if (selectedGroups.length === 0) {
        tg.showAlert("Please select at least one group.");
        return;
    }

    const data = {
        message: document.getElementById("message").value,
        groups: selectedGroups.join(','), // Send as comma-separated string of IDs
        interval: document.getElementById("interval").value
    };

    if (!data.message.trim()) {
        tg.showAlert("Please enter a message.");
        return;
    }

    // Use Telegram's sendData method
    tg.sendData(JSON.stringify(data));
}

// Add event listeners once the DOM is fully loaded
window.addEventListener("load", populateGroupList);
document.getElementById("send-data").addEventListener("click", sendDataToBot);
