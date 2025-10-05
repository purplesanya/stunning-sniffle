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

---

### Step 2: Update the Backend (`main.py`)

The backend needs to handle the new "ready" signal and use Telethon to fetch and return the chat list.

```python
# --- Step 1: Import nest_asyncio and apply it FIRST ---
import nest_asyncio
nest_asyncio.apply()

import asyncio
import configparser
import json
import logging
import os
import uuid

from apscheduler.schedulers.asyncio import AsyncScheduler
from telethon import TelegramClient
from telethon.tl.types import InputPeerChannel, InputPeerChat
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

# Import specific types for answerWebAppQuery
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ... (Setup Logging, Config, Dirs, Per-User Data Handling - ALL UNCHANGED) ...
logging.basicConfig(format='%(asctime)s - %(name)s [%(levelname)s] - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
CONFIG_FILE = 'config.ini'
STORAGE_DIR = 'storage'
SESSION_DIR = 'sessions'
os.makedirs(STORAGE_DIR, exist_ok=True); os.makedirs(SESSION_DIR, exist_ok=True)
config = configparser.ConfigParser(); config.read(CONFIG_FILE); BOT_TOKEN = config['telegram']['bot_token']
(GET_API_ID, GET_API_HASH, GET_PHONE, GET_CODE_FILE, GET_PASSWORD_FILE) = range(5)
def get_user_storage_path(user_id: int) -> str: return os.path.join(STORAGE_DIR, f"storage_{user_id}.json")
def get_user_session_path(user_id: int) -> str: return os.path.join(SESSION_DIR, f"session_{user_id}.session")
def load_data(user_id: int):
    path = get_user_storage_path(user_id)
    try:
