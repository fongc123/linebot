from flask import Flask, request, abort, send_from_directory
import json
from argparse import ArgumentParser
import os
import openai
from copy import deepcopy
from PIL import Image
import threading
import requests
import schedule
import datetime
import base64
import time
import json
import uuid
import os
import io
import pymssql

from linebot.v3 import (
    WebhookHandler,
    WebhookParser
)

from linebot.v3.exceptions import (
    InvalidSignatureError
)

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    PushMessageRequest,
    ImageMessage
)

from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    FollowEvent,
    UnfollowEvent
)

IMAGE_ORIGINAL_SIZE = 10*1024*1024
IMAGE_PREVIEW_SIZE = 1024*1024
IMAGES_PATH = "./images"
IMAGE_EXPIRY = 3 # 3 days
BOT_NAMES = os.getenv("BOT_NAMES").split(",")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN").split(",")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET").split(",")
AUTHORIZATION_BEARER_KEYWORD = os.getenv("AUTHORIZATION_BEARER_KEYWORD")
MSSQL_HOST = os.getenv("MSSQL_HOST")
MSSQL_USER = os.getenv("MSSQL_USER")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE")
MSSQL_TABLE = os.getenv("MSSQL_TABLE")
OPENAPI_KEY = os.getenv("OPENAPI_KEY")
OPENAI_MESSAGES = [
    {
        "role" : "system",
        "content" : "You are an unhelpful assistant. You are relecutant to reply to the user's questions. However, you may reply only if they mention the keyword 'apple'."
    }
]

app = Flask(__name__)

handler = WebhookHandler(CHANNEL_SECRET[0])
message_destinations = {}
use_openai = False

def save_file(filename, content):
    with open(filename, "w") as f:
        f.write(content)

def insert_record(userId, data):
    cursor = pymssql.connect(MSSQL_HOST, MSSQL_USER, MSSQL_PASSWORD, MSSQL_DATABASE).cursor()
    _sql_create_table = f"""
    IF OBJECT_ID('{MSSQL_TABLE}', 'U') IS NULL
        CREATE TABLE {MSSQL_TABLE} (
            userId VARCHAR(200) NOT NULL,
            display_name VARCHAR(100),
            picture_url VARCHAR(200),
            language VARCHAR(10),
            bot VARCHAR(200),
            PRIMARY KEY (userId, bot)
        )
    """
    cursor.execute(_sql_create_table)
    cursor.connection.commit()  

    _sql_insert = f"""
    INSERT INTO {MSSQL_TABLE} (userId, display_name, picture_url, language, bot) VALUES (%s, %s, %s, %s, %s)
    """
    values = [(userId, data['display_name'], data['picture_url'], data['language'], data['bot'])]
    cursor.executemany(_sql_insert, values)
    cursor.connection.commit()

    cursor.connection.close()

def generate_response(userId, text):
    global use_openai
    openai.api_key = OPENAPI_KEY

    # check if conversations folder exists
    if not os.path.exists("./conversations/"):
        os.mkdir("./conversations/")

    response = "Sorry, but I cannot process your message."
    if use_openai:
        # check if user.json exists, if not load default, else load user.json
        messages = None
        if not os.path.exists(f"./conversations/{userId}.json"):
            messages = deepcopy(OPENAI_MESSAGES)    
        else:
            with open(f"./conversations/{userId}.json", "r") as f:
                messages = json.load(f)
        messages.append({ "role" : "user", "content" : text })

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
            max_tokens=1000,
        )['choices'][0]['message']['content']

        # save user.json
        messages.append({ "role" : "system", "content" : response })
        with open(f"./conversations/{userId}.json", "w") as f:
            json.dump(messages, f)

    return response

def get_user_info(userId, access_token):
    with ApiClient(Configuration(access_token=access_token)) as api_client:
        line_bot_api = MessagingApi(api_client)
        return line_bot_api.get_profile(userId).dict()
    
def get_bot_info(access_token):
    with ApiClient(Configuration(access_token=access_token)) as api_client:
        line_bot_api = MessagingApi(api_client)
        return line_bot_api.get_bot_info().dict()

def compress_image(data, target_size):
    # save and compress image from base64
    image = Image.open(io.BytesIO(base64.b64decode(data)))
    if image.mode != "RGB":
        image = image.convert("RGB")
    output = io.BytesIO()

    quality = 100
    while True:
        image.save(output, format="JPEG", optimize=True, quality=quality)
        if len(output.getvalue()) <= target_size:
            break
        if quality <= 0:
            raise Exception("Image too large. Max size: 10MB.")
        
        quality -= 5
        output.seek(0)
        output.truncate()

    return Image.open(io.BytesIO(output.getvalue()))

def delete_images():
    current_time = datetime.datetime.now()
    if os.path.exists(IMAGES_PATH):
        for filename in os.listdir(IMAGES_PATH):
            if not filename.endswith(".png"):
                continue
            file_time = datetime.datetime.fromtimestamp(os.path.getmtime(f"{IMAGES_PATH}/{filename}"))
            if (current_time - file_time).days >= IMAGE_EXPIRY:
                os.remove(f"{IMAGES_PATH}/{filename}")
                print("Deleted:", filename)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route("/<bot_name>/callback", methods=['POST'])
def callback(bot_name):
    global handler
    global message_destinations

    try:
        if bot_name not in BOT_NAMES:
            raise Exception("Incorrect bot name.")
        
        # get header information
        signature = request.headers['X-Line-Signature']
        body = request.get_data(as_text=True)
        app.logger.info("Request body: " + body)

        # store incoming messages by webhookEventId
        events = json.loads(body)["events"]
        for event in events:
            if event["type"] == "message" or event["type"] == "follow":
                message_destinations[event["webhookEventId"]] = bot_name

        # handle webhook body
        handler.parser = WebhookParser(CHANNEL_SECRET[BOT_NAMES.index(bot_name)])
        handler.handle(body, signature)

        return json.dumps({"status" : "OK."}), 200
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

@app.route("/<bot_name>/admin/send/text", methods=['POST'])
def send_text(bot_name):
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    if bot_name not in BOT_NAMES:
        return json.dumps({"status" : "Incorrect bot name."}), 401

    body = request.get_json()
    try:
        if "userId" in body.keys() and "text" in body.keys():
            with ApiClient(Configuration(access_token=CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])) as api_client:
                line_bot_api = MessagingApi(api_client)
                push_message_request = PushMessageRequest(
                    to=body["userId"],
                    messages=[TextMessage(text=body["text"])]
                )

                line_bot_api.push_message(push_message_request)
        else:
            raise Exception("Missing userId or text.")
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK."}), 200

@app.route(f"{IMAGES_PATH.replace('.', '')}/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_PATH, filename)

@app.route("/<bot_name>/admin/send/image", methods=['POST'])
def send_image(bot_name):
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    if bot_name not in BOT_NAMES:
        return json.dumps({"status" : "Incorrect bot name."}), 401
    
    if not os.path.exists(IMAGES_PATH):
        os.mkdir(IMAGES_PATH)
    file_id = uuid.uuid4()
    domain = request.host_url.replace("http://", "https://")
    body = request.get_json()
    print("File ID:", file_id)
    try:
        if "userId" in body.keys() and ("image_data" in body.keys() or "image_url" in body.keys()):
            if "image_data" in body.keys():
                # original and preview images
                original = compress_image(body["image_data"], IMAGE_ORIGINAL_SIZE)
                preview = compress_image(body["image_data"], IMAGE_PREVIEW_SIZE)

                # save images
                original.save(f"{IMAGES_PATH}/{file_id}-original.png", format="PNG")
                preview.save(f"{IMAGES_PATH}/{file_id}-preview.png", format="PNG")
                
                original_content_url = f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-original.png"
                preview_image_url = f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-preview.png"
            elif "image_url" in body.keys():
                image_response = requests.get(body["image_url"])
                if image_response.status_code != 200:
                    raise Exception(f"Failed to get image ({image_response.status_code}).")
                
                original = compress_image(base64.b64encode(image_response.content), IMAGE_ORIGINAL_SIZE)
                preview = compress_image(base64.b64encode(image_response.content), IMAGE_PREVIEW_SIZE)
                
                # save images
                original.save(f"{IMAGES_PATH}/{file_id}-original.png", format="PNG")
                preview.save(f"{IMAGES_PATH}/{file_id}-preview.png", format="PNG")

                original_content_url = f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-original.png"
                preview_image_url = f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-preview.png"

            # send image
            with ApiClient(Configuration(access_token=CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])) as api_client:
                line_bot_api = MessagingApi(api_client)
                push_message_request = PushMessageRequest(
                    to=body["userId"],
                    messages=[ImageMessage(
                        original_content_url=original_content_url,
                        preview_image_url=preview_image_url
                    )]
                )

                line_bot_api.push_message(push_message_request)
        else:
            raise Exception("Missing userId or image.")
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK."}), 200

@app.route("/<bot_name>/admin/get/user", methods=['GET'])
def get_user(bot_name):
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    if bot_name not in BOT_NAMES:
        return json.dumps({"status" : "Incorrect bot name."}), 401
    
    response = None
    body = request.get_json()
    try:
        if "userId" in body.keys():
            response = get_user_info(body["userId"], CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])
            print("User Info:", response)
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK.", "data" : response}), 200

@app.route("/<bot_name>/admin/get/botinfo", methods=['GET'])
def get_bot(bot_name):
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    if bot_name not in BOT_NAMES:
        return json.dumps({"status" : "Incorrect bot name."}), 401

    response = None
    try:
        response = get_bot_info(CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500
    
    return json.dumps({"status" : "OK.", "data" : response}), 200

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    bot_name = message_destinations[event.webhook_event_id]
    del message_destinations[event.webhook_event_id]
    with ApiClient(Configuration(access_token=CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=generate_response(event.source.user_id, event.message.text))]
            )
        )

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    bot_name = message_destinations[event.webhook_event_id]
    del message_destinations[event.webhook_event_id]
    with ApiClient(Configuration(access_token=CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="I can't see images yet.")]
            )
        )

@handler.add(FollowEvent)
def handle_follow(event):
    try:
        bot_name = message_destinations[event.webhook_event_id]
        del message_destinations[event.webhook_event_id]

        userId = event.source.user_id
        user_info = get_user_info(userId, CHANNEL_ACCESS_TOKEN[BOT_NAMES.index(bot_name)])
        user_info['userId'] = userId
        user_info['bot'] = bot_name

        insert_record(userId, user_info)
        print("Follow event received:", user_info)
    except Exception as e:
        print("Error:", str(e))

if __name__ == "__main__":
    parser = ArgumentParser(
        usage="Usage: python " + __file__ + " [--host <host>] [--help]"
    )
    parser.add_argument("--host", default="0.0.0.0", help="host")
    parser.add_argument("--chat", type=bool, default=False, help="Use OpenAI API to respond to non-system messages.")
    opts = parser.parse_args()
    port = int(os.environ.get("PORT", 8000)) # deploy to Heroku port

    # schedule to delete images
    schedule.every().day.at("00:00").do(delete_images)
    schedule_thread = threading.Thread(target=run_schedule)
    schedule_thread.start()

    # run app
    use_openai = opts.chat
    app.run(debug=True, host=opts.host, port=port)