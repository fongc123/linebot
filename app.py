from flask import Flask, request, abort
import json
from argparse import ArgumentParser
import os
import openai
from copy import deepcopy

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
)

from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

CHANNEL_ACCESS_TOKEN = "QQiVYpwcXYAhYrQ0mCDNU8y+iv18MS7PDHoYs4WexlDQ4ZUFtiop0BTVqiWpL+bun9fJfOMgGfdxbeS3oaPzRa7j+zmb6kNcrSBFLkentJ4QPdBjv96OgOPoSUxvRWnetva7nOHqFsRk9am/s2k0kwdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "c722da9d4e41022ae6906b14b82b9545"
OPENAPI_KEY = "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"
OPENAI_MESSAGES = {
    {
        "role" : "system",
        "content" : "You are a professional Japanese otaku."
    },
    {
        "role" : "user",
        "content" : None
    }
}

app = Flask(__name__)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

def generate_response(text):
    openai.api_key = OPENAPI_KEY

    messages = deepcopy(OPENAI_MESSAGES)
    messages[1]["content"] = text

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.3,
        max_tokens=1000,
    )

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

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=generate_response(event.message.text)['choices'][0]['message']['content'])]
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