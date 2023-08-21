from flask import Flask, request, abort

from linebot import (
    WebhookParser
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)

CHANNEL_ACCESS_TOKEN = "QQiVYpwcXYAhYrQ0mCDNU8y+iv18MS7PDHoYs4WexlDQ4ZUFtiop0BTVqiWpL+bun9fJfOMgGfdxbeS3oaPzRa7j+zmb6kNcrSBFLkentJ4QPdBjv96OgOPoSUxvRWnetva7nOHqFsRk9am/s2k0kwdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "c722da9d4e41022ae6906b14b82b9545"

app = Flask(__name__)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    # if event is MessageEvent and message is TextMessage, then echo text
    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=event.message.text)]
                )
            )

    return 'OK'

if __name__ == "__main__":  
    app.run()