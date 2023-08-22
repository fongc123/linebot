import os
from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)

from argparse import ArgumentParser

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = "QQiVYpwcXYAhYrQ0mCDNU8y+iv18MS7PDHoYs4WexlDQ4ZUFtiop0BTVqiWpL+bun9fJfOMgGfdxbeS3oaPzRa7j+zmb6kNcrSBFLkentJ4QPdBjv96OgOPoSUxvRWnetva7nOHqFsRk9am/s2k0kwdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "c722da9d4e41022ae6906b14b82b9545"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    print("yo1")
    # Get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # Get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    print("yo2")
    """ Here's all the messages will be handled and processed by the program """
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))

if __name__ == "__main__":
    print("yo3")
    parser = ArgumentParser(
        usage="Usage: python " + __file__ + " [--port <port>] [--help]"
    )
    parser.add_argument("--host", default="0.0.0.0", help="host")
    parser.add_argument("--port", type=int, default=5000, help="port")
    args = parser.parse_args()

    # deploy to Heroku port
    port = int(os.environ.get('PORT', 8000))
    
    print("yo4")
    app.run(debug=True, host=args.host, port=port)