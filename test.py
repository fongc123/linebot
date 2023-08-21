import os
import sys
from argparse import ArgumentParser

import asyncio
from aiohttp import web

import logging

from aiohttp.web_runner import TCPSite

from linebot.v3 import (
    WebhookParser
)
from linebot.v3.messaging import (
    Configuration,
    AsyncApiClient,
    AsyncMessagingApi,
    TextMessage,
    ReplyMessageRequest
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

# get channel_secret and channel_access_token from your environment variable
channel_secret = "c722da9d4e41022ae6906b14b82b9545"
channel_access_token = "QQiVYpwcXYAhYrQ0mCDNU8y"

configuration = Configuration(
    access_token=channel_access_token
)


class Handler:
    def __init__(self, line_bot_api: AsyncMessagingApi, parser: WebhookParser):
        self.line_bot_api = line_bot_api
        self.parser = parser

    async def echo(self, request):
        signature = request.headers['X-Line-Signature']
        body = await request.text()

        try:
            events = self.parser.parse(body, signature)
        except InvalidSignatureError:
            return web.Response(status=400, text='Invalid signature')

        for event in events:
            if not isinstance(event, MessageEvent):
                continue
            if not isinstance(event.message, TextMessageContent):
                continue
            await self.line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=event.message.text)]
                )
            )

        return web.Response(text="OK\n")


async def main(port=8000):
    async_api_client = AsyncApiClient(configuration)
    line_bot_api = AsyncMessagingApi(async_api_client)
    parser = WebhookParser(channel_secret)

    handler = Handler(line_bot_api, parser)

    app = web.Application()
    app.add_routes([web.post('/callback', handler.echo)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = TCPSite(runner=runner, port=port)
    await site.start()
    while True:
        await asyncio.sleep(3600)  # sleep forever


if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

    arg_parser = ArgumentParser(
        usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    )
    arg_parser.add_argument('-p', '--port', type=int, default=8000, help='port')
    options = arg_parser.parse_args()

    asyncio.run(main(options.port))