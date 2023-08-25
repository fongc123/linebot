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

def insert_record(userId, data):
    print(userId, data)

def generate_response(userId, text):
    openai.api_key = OPENAPI_KEY

    if text.startswith("!reg"):
        # initialize register: !reg <LINE_ID> <PHONE_NUMBER> <EMAIL>
        insert_record(userId, text.split()[1:])

        response = "You have been registered."
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

@app.route("/admin/send/text", methods=['POST'])
def send_text():
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401

    body = request.get_json()
    try:
        if "userId" in body.keys() and "text" in body.keys():
            with ApiClient(configuration) as api_client:
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

@app.route("/admin/send/image", methods=['POST'])
def send_image():
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    file_id = uuid.uuid4()
    domain = request.host_url.replace("http://", "https://")
    body = request.get_json()
    try:
        if "userId" in body.keys() and "image" in body.keys():
            # original and preview images
            original = compress_image(body["image"], IMAGE_ORIGINAL_SIZE)
            preview = compress_image(body["image"], IMAGE_PREVIEW_SIZE)

            # save images
            if not os.path.exists(IMAGES_PATH):
                os.mkdir(IMAGES_PATH)
            original.save(f"{IMAGES_PATH}/{file_id}-original.png", format="PNG")
            preview.save(f"{IMAGES_PATH}/{file_id}-preview.png", format="PNG")
            
            print(file_id)
            # send image
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                push_message_request = PushMessageRequest(
                    to=body["userId"],
                    messages=[ImageMessage(
                        original_content_url=f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-original.png",
                        preview_image_url=f"{domain}{IMAGES_PATH.replace('.', '')}/{file_id}-preview.png"
                    )]
                )

                line_bot_api.push_message(push_message_request)
        else:
            raise Exception("Missing userId or image.")
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK."}), 200

@app.route("/admin/get/user", methods=['GET'])
def get_user():
    if request.headers.get("Authorization") is None or request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization."}), 401
    
    response = None
    body = request.get_json()
    try:
        if "userId" in body.keys():
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                response = line_bot_api.get_profile(body["userId"]).dict()
                print(response)
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK.", "message" : response}), 200

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