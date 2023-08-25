from flask import Flask, request, abort
import json
from argparse import ArgumentParser
import os
import openai
from copy import deepcopy
import json
import os

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

def generate_response(userId, text):
    openai.api_key = OPENAPI_KEY

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

    return json.dumps({"status" : "OK"}), 200

@app.route("/admin/send/message", methods=['POST'])
def send_message():
    if request.headers.get("Authorization").split()[1] != AUTHORIZATION_BEARER_KEYWORD:
        return json.dumps({"status" : "Incorrect authorization"}), 401

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
            raise Exception("Missing userId or message")
    except Exception as e:
        return json.dumps({"status" : str(e)}), 500

    return json.dumps({"status" : "OK"}), 200

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