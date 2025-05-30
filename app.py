from flask import Flask, Response
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
import asyncio
import re
import json
import time
from functools import wraps

# Telegram credentials
api_id = 29612794
api_hash = '6edc1a58a202c9f6e62dc98466932bad'
phone_number = '+918528234488'

# Bot & auth config
bot_username = 'dopayu_bot'
message_prefix = '/bt'
authorized_key = 'never'
max_retries = 15  # Increased from 10 to 15
retry_delay = 3   # Seconds between retries
response_timeout = 45  # Total timeout in seconds

app = Flask(__name__)

def async_route(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(f(*args, **kwargs))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}, status=500, mimetype='application/json'))
        finally:
            loop.close()
    return wrapper


def parse_bot_reply(text):
    """Extract info from bot reply and return dict."""
    if not text or not isinstance(text, str):
        return {"error": "Invalid bot response format"}
    
    cc_match = re.search(r'CC:\s*(.*)', text)
    status_match = re.search(r'Status:\s*(.*)', text)
    response_match = re.search(r'Response:\s*(.*)', text)

    result = {
        "cc": cc_match.group(1).strip() if cc_match else "",
        "status": status_match.group(1).strip() if status_match else "",
        "response": response_match.group(1).strip() if response_match else "",
        "raw_response": text  # Include full response for debugging
    }
    
    # Validate we got at least status and response
    if not result["status"] or not result["response"]:
        result["error"] = "Incomplete bot response"
    
    return result

    
    async with TelegramClient('anon', api_id, api_hash) as client:
        try:
            await client.start(phone=phone_number)
            entity = await client.get_entity(f'@{bot_username}')
            
            # Send the message with timestamp
            message = f"{message_prefix} {cc_data}"
            await client.send_message(entity, message)
            send_time = time.time()
            
            # Track seen messages to avoid duplicates
            seen_messages = set()
            
            # Poll for bot reply with timeout
            while time.time() - send_time < response_timeout:
                await asyncio.sleep(retry_delay)
                
                history = await client(GetHistoryRequest(
                    peer=entity,
                    limit=5,  # Check last 5 messages for more reliability
                    offset_date=None,
                    offset_id=0,
                    max_id=0,
                    min_id=0,
                    add_offset=0,
                    hash=0
                ))
                
                if history.messages:
                    for msg in history.messages:
                        # Skip if we've already processed this message
                        if msg.id in seen_messages:
                            continue
                            
                        seen_messages.add(msg.id)
                        current_text = msg.message
                        
                        # Check if this is a response to our request
                        if (cc_data in current_text and 
                            "Status:" in current_text and 
                            "Response:" in current_text):
                            return parse_bot_reply(current_text)
            
            return {"error": f"No valid reply from bot within {response_timeout} seconds"}
            
        except Exception as e:
            return {"error": f"Telegram communication error: {str(e)}"}
        finally:
            await client.disconnect()

@app.route('/key=<key>/cc=<cc>', methods=['GET'])
@async_route
async def check_card(key, cc):
    if key != authorized_key:
        return Response(
            json.dumps({"error": "Unauthorized key"}, ensure_ascii=False),
            status=403,
            mimetype='application/json'
        )
    
    # Introduce 10-second delay before processing as requested
    await asyncio.sleep(10)
    
    result = await send_and_get_result(cc)
    
    # Add timestamp to response
    result["timestamp"] = int(time.time())
    
    status_code = 200 if "error" not in result else 400
    return Response(
        json.dumps(result, ensure_ascii=False),
        status=status_code,
        mimetype='application/json'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3333, threaded=True)
