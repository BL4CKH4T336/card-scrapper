from telethon import TelegramClient
import asyncio
import logging
import re
import time
from collections import defaultdict
from flask import Flask, jsonify
import threading

# Configuration
API_ID = 29612794
API_HASH = '6edc1a58a202c9f6e62dc98466932bad'
PHONE_NUMBER = '+918528234488'
API_KEY = 'waslost'

# Global variables
client = None
telegram_ready = False
telegram_loop = None

# Configure logging
logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# CC pattern
CC_PATTERN = re.compile(r'\b\d{15,16}\|\d{2}\|\d{4}\|\d{3,4}\b')

# Flask app
app = Flask(__name__)

async def initialize_telegram():
    """Initialize Telegram client"""
    global client, telegram_ready
    try:
        client = TelegramClient('session_name', API_ID, API_HASH)
        await client.start(PHONE_NUMBER)
        me = await client.get_me()
        logger.info(f"Logged in as {me.first_name} (username: @{me.username})")
        telegram_ready = True
        return client
    except Exception as e:
        logger.error(f"Telegram initialization failed: {e}")
        raise

async def process_cc_info(cc_list):
    """Process CC information"""
    unique_ccs = set()
    cc_counts = defaultdict(int)

    for cc in cc_list:
        cc_number = cc.split('|')[0]
        cc_counts[cc_number] += 1
        unique_ccs.add(cc)

    return {
        'unique_ccs': sorted(list(unique_ccs)),
        'duplicates': sum(1 for count in cc_counts.values() if count > 1),
        'total_found': len(cc_list)
    }

async def scrape_channel(channel_identifier, num_messages):
    """Scrape messages from a channel"""
    try:
        channel = await client.get_entity(channel_identifier)
        cc_list = []

        async for message in client.iter_messages(channel, limit=num_messages):
            if message.text:
                matches = CC_PATTERN.findall(message.text)
                cc_list.extend(matches)

        return await process_cc_info(cc_list) if cc_list else None
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return None

@app.route('/key=<key>/uname/<username>/<int:count>')
def scrape_endpoint(key, username, count):
    """API endpoint"""
    if key != API_KEY:
        return jsonify({'error': 'Invalid API key'}), 401
    
    if count <= 0:
        return jsonify({'error': 'Count must be positive'}), 400
    
    if not telegram_ready or not client:
        return jsonify({'error': 'Telegram client not ready'}), 503
    
    try:
        future = asyncio.run_coroutine_threadsafe(scrape_channel(username, count), telegram_loop)
        result = future.result(timeout=300)
        
        if not result:
            return jsonify({'error': 'No CCs found or channel not accessible'}), 404
        
        return jsonify({
            'status': 'success',
            'channel': username,
            'messages_scraped': count,
            'unique_ccs': len(result['unique_ccs']),
            'duplicates_found': result['duplicates'],
            'total_found': result['total_found'],
            'cc_list': result['unique_ccs']
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

def telegram_thread_func():
    """Run Telegram client in its own event loop"""
    global telegram_loop, client
    telegram_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(telegram_loop)
    
    try:
        client = telegram_loop.run_until_complete(initialize_telegram())
        telegram_loop.run_forever()
    except Exception as e:
        logger.error(f"Telegram thread failed: {e}")
    finally:
        telegram_loop.close()

def run_flask():
    """Run Flask app"""
    app.run(host='0.0.0.0', port=2233)

if __name__ == '__main__':
    # Start Telegram client in a separate thread
    telegram_thread = threading.Thread(target=telegram_thread_func, daemon=True)
    telegram_thread.start()

    # Wait for initialization
    while not telegram_ready:
        logger.info("Waiting for Telegram client to initialize...")
        time.sleep(1)

    # Start Flask
    run_flask()
