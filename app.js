// Initialize Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand();

// State management
let groups = [];
let currentStatus = [];

// DOM Elements
const setupCheck = document.getElementById('setupCheck');
const mainInterface = document.getElementById('mainInterface');
const errorContainer = document.getElementById('errorContainer');
const groupSelect = document.getElementById('groupSelect');
const messageText = document.getElementById('messageText');
const intervalInput = document.getElementById('intervalInput');
const scheduleBtn = document.getElementById('scheduleBtn');
const refreshGroups = document.getElementById('refreshGroups');
const refreshStatus = document.getElementById('refreshStatus');
const statusContainer = document.getElementById('statusContainer');
const closeApp = document.getElementById('closeApp');
const notification = document.getElementById('notification');

// Utility Functions
function showNotification(message, isError = false) {
    notification.textContent = message;
    notification.className = 'notification show' + (isError ? ' error' : '');
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

function sendData(data) {
    tg.sendData(JSON.stringify(data));
}

// Check setup status on load
async function checkSetup() {
    // Simulate checking if user has completed setup
    // In real implementation, this would query the bot
    setTimeout(() => {
        // For demo purposes, showing main interface
        // In production, you'd check actual setup status
        setupCheck.style.display = 'none';
        mainInterface.style.display = 'block';
        loadGroups();
    }, 1000);
}

// Load user's groups
function loadGroups() {
    // Send request to bot to get groups
    sendData({
        action: 'get_groups'
    });
    
    // Simulate loading groups (in production, this comes from bot response)
    setTimeout(() => {
        groups = [
            { id: '-1001234567890', name: 'My First Group' },
            { id: '-1009876543210', name: 'Another Group' },
            { id: '-1001111111111', name: 'Test Group' }
        ];
        
        populateGroupSelect();
    }, 500);
}

function populateGroupSelect() {
    groupSelect.innerHTML = '<option value="">Select a group...</option>';
    
    groups.forEach(group => {
        const option = document.createElement('option');
        option.value = group.id;
        option.textContent = group.name;
        groupSelect.appendChild(option);
    });
}

// Schedule message
function scheduleMessage() {
    const groupId = groupSelect.value;
    const message = messageText.value.trim();
    const interval = parseInt(intervalInput.value);
    
    // Validation
    if (!groupId) {
        showNotification('Please select a group', true);
        return;
    }
    
    if (!message) {
        showNotification('Please enter a message', true);
        return;
    }
    
    if (interval < 60) {
        showNotification('Interval must be at least 60 seconds', true);
        return;
    }
    
    // Get group name
    const selectedGroup = groups.find(g => g.id === groupId);
    
    // Send data to bot
    sendData({
        action: 'schedule',
        group_id: groupId,
        group_name: selectedGroup.name,
        message: message,
        interval: interval
    });
    
    // Show success notification
    showNotification('Message scheduled successfully!');
    
    // Clear form
    messageText.value = '';
    groupSelect.value = '';
    intervalInput.value = '3600';
    
    // Close web app after scheduling
    setTimeout(() => {
        tg.close();
    }, 1500);
}

// Load status
function loadStatus() {
    sendData({
        action: 'get_status'
    });
    
    // Simulate status (in production, this comes from bot response)
    setTimeout(() => {
        currentStatus = [
            {
                group: 'My First Group',
                message: 'Hello everyone! This is a scheduled message.',
                interval: 3600
            },
            {
                group: 'Test Group',
                message: 'Reminder: Meeting at 3 PM',
                interval: 7200
            }
        ];
        
        displayStatus();
    }, 500);
}

function displayStatus() {
    if (currentStatus.length === 0) {
        statusContainer.innerHTML = '<p class="text-muted">No active scheduled messages</p>';
        return;
    }
    
    statusContainer.innerHTML = '';
    
    currentStatus.forEach((status, index) => {
        const statusItem = document.createElement('div');
        statusItem.className = 'status-item';
        statusItem.innerHTML = `
            <strong>Schedule ${index + 1}</strong>
            <p><strong>Group:</strong> ${status.group}</p>
            <p><strong>Message:</strong> ${status.message.substring(0, 50)}${status.message.length > 50 ? '...' : ''}</p>
            <p><strong>Interval:</strong> ${formatInterval(status.interval)}</p>
        `;
        statusContainer.appendChild(statusItem);
    });
}

function formatInterval(seconds) {
    if (seconds < 60) {
        return `${seconds} seconds`;
    } else if (seconds < 3600) {
        return `${Math.floor(seconds / 60)} minutes`;
    } else if (seconds < 86400) {
        return `${Math.floor(seconds / 3600)} hours`;
    } else {
        return `${Math.floor(seconds / 86400)} days`;
    }
}

// Event Listeners
scheduleBtn.addEventListener('click', scheduleMessage);

refreshGroups.addEventListener('click', () => {
    groupSelect.innerHTML = '<option value="">Loading groups...</option>';
    showNotification('Refreshing groups...');
    loadGroups();
});

refreshStatus.addEventListener('click', () => {
    showNotification('Refreshing status...');
    loadStatus();
});

closeApp.addEventListener('click', () => {
    tg.close();
});

// Handle Enter key in message textarea
messageText.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
        scheduleMessage();
    }
});

// Set theme colors from Telegram
if (tg.themeParams) {
    document.documentElement.style.setProperty('--primary-color', tg.themeParams.button_color || '#0088cc');
    document.documentElement.style.setProperty('--bg-color', tg.themeParams.bg_color || '#ffffff');
    document.documentElement.style.setProperty('--text-color', tg.themeParams.text_color || '#333333');
}

// Initialize
checkSetup();

// Listen for messages from Telegram Bot (when running in Telegram)
window.addEventListener('message', (event) => {
    if (event.data.type === 'groups_loaded') {
        groups = event.data.groups;
        populateGroupSelect();
        showNotification('Groups loaded successfully!');
    } else if (event.data.type === 'status_loaded') {
        currentStatus = event.data.status;
        displayStatus();
    }
});
