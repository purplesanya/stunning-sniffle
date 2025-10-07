// script.js

// Telegram Web App integration
const tg = window.Telegram.WebApp;
tg.ready();

// On init
tg.expand();
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('scheduleForm');
    const status = document.getElementById('status');
    
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const group = document.getElementById('group').value;
        const message = document.getElementById('message').value;
        const interval = parseInt(document.getElementById('interval').value);
        const startTime = document.getElementById('startTime').value;
        
        const task = {
            group: group,
            message: message,
            interval: interval,
            start_time: startTime
        };
        
        try {
            // Send to bot via Telegram WebApp MainButton or API
            // For simplicity, use tg.sendData(JSON.stringify(task))
            tg.sendData(JSON.stringify(task));
            
            status.textContent = 'Task scheduled! Check bot for confirmation.';
            status.className = 'success';
        } catch (error) {
            status.textContent = 'Error scheduling task.';
            status.className = 'error';
        }
    });
});

// Handle data received from bot if needed
tg.onEvent('mainButtonClicked', function() {
    // Optional: Trigger something
});
