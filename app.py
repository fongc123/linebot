from flask import Flask, request, abort, send_from_directory
import json
from argparse import ArgumentParser
import os
import openai
from copy import deepcopy
from PIL import Image
import base64
import json
import uuid
import os
import io
import requests

from linebot.v3 import (
    WebhookHandler
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
    ImageMessageContent
)

IMAGE_ORIGINAL_SIZE = 10*1024*1024
IMAGE_PREVIEW_SIZE = 1024*1024
IMAGES_PATH = "./images"
CHANNEL_ACCESS_TOKEN = "CHANNEL_ACCESS_TOKEN"
CHANNEL_SECRET = "CHANNEL_SECRET"
AUTHORIZATION_BEARER_KEYWORD = os.getenv("AUTHORIZATION_BEARER_KEYWORD")
OPENAPI_KEY = os.getenv("OPENAPI_KEY")
OPENAI_MESSAGES = [
    {
        "role" : "system",
        "content" : "You are an unhelpful assistant. You are relecutant to reply to the user's questions. However, you may reply if they mention the keyword 'suipiss'."
    }
]

app = Flask(__name__)

configuration = Configuration(access_token=os.getenv(CHANNEL_ACCESS_TOKEN))
handler = WebhookHandler(os.getenv(CHANNEL_SECRET))

def save_file(filename, content):
    with open(filename, "w") as f:
        f.write(content)

def insert_record(data):
    print(data)

def generate_response(userId, text):
    openai.api_key = OPENAPI_KEY

    if text.startswith("!reg"):
        # initialize register: !reg <LINE_ID> <PHONE_NUMBER> <EMAIL>
        insert_record(text.split()[1:])
    else:
        # check if conversations folder exists
        if not os.path.exists("./conversations/"):
            os.mkdir("./conversations/")

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

def save_image(path, data, target_size):
    # save and compress image from base64
    image_data = io.BytesIO(base64.b64decode(data))
    image = Image.open(image_data)

    # resize image
    quality = 100
    current_size = len(image_data)
    while current_size > target_size and quality > 0:
        image.save(path, optimize=True, quality=quality)
        with open(path, "rb") as f:
            current_size = len(f.read())
        quality -= 5
    
    if quality > 0:
        image.save(path, optimize=True, quality=quality)
        return True
    else:
        return False

@app.route("/", methods=["GET"])
def hello():
    print(requests.get("https://api.ipify.org?format=json"))
    return json.dumps({"status" : "OK."}), 200

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return json.dumps({"status" : "OK."}), 200

@app.route("/admin/send/message", methods=['POST'])
def send_message():
    if request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401

    body = request.get_json()
    try:
        if "userId" in body.keys() and "message" in body.keys():
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                push_message_request = PushMessageRequest(
                    to=body["userId"],
                    messages=[TextMessage(text=body["message"])]
                )

                line_bot_api.push_message(push_message_request)
        else:
            raise Exception("Missing userId or message.")
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK."}), 200

@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_PATH, filename)

@app.route("/admin/send/image", methods=['POST'])
def send_image():
    if request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    try:
        # save image
        body = request.get_json()
        file_id = uuid.uuid4()
        path_ori = f"{IMAGES_PATH}/{file_id}-original.png"
        path_pre = f"{IMAGES_PATH}/{file_id}-preview.png"
        if not save_image(f"{path_ori}.png", body["image"], IMAGE_ORIGINAL_SIZE) or not save_image(f"{path_pre}.png", body["image"], IMAGE_PREVIEW_SIZE):
            raise Exception("Image too large. Please send an image less than 10MB.")
        

    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK."}), 200

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=generate_response(event.source.user_id, event.message.text))]
            )
        )

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="I can't see images yet.")]
            )
        )

if __name__ == "__main__":
    parser = ArgumentParser(
        usage="Usage: python " + __file__ + " [--host <host>] [--help]"
    )
    parser.add_argument("--host", default="0.0.0.0", help="host")
    opts = parser.parse_args()
    port = int(os.environ.get("PORT", 8000)) # deploy to Heroku port

    app.run(debug=True, host=opts.host, port=port)