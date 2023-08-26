# LINE Messaging Bot

A LINE messaging bot. 

## Description

This LINE messaging bot primarily sends messages on the administrator's behalf through HTTP requests. These messages are limited to contain either a text or an image. Optionally, the bot can be connected to OpenAI's chatbot by passing the `--chat` argument when running the application. This would allow the bot to chat with users on LINE.

**NOTE:** It should be noted that the LINE bot can only send to and receive from users who added the bot as a friend.

## Installation
The application uses Python to run.

```bash
git clone https://github.com/fongc123/linebot.git
```

## Usage
Ensure that all required packages are installed. Then, run the Flask application.

```bash
pip install -r requirements.txt
python app.py
```

Ensure that a `.env` file is present to store secrets and access tokens. It should contain the following variables:
- `AUTHORIZATION_BEARER_KEYWORD`: keyword for access to the API (*currently set as a static phrase*)
- `CHANNEL_ACCESS_TOKEN`: channel access token from LINE
- `CHANNEL_SECRET`: channel secret from LINE
- `OPENAPI_KEY`: (OPTIONAL) OpenAPI key for chat bot

A sample `POST` request to the `/admin/send/text` endpoint is shown below. Ensure that the Bearer authorization token is the same as that of in the `.env` file.

```json
{
    "userId" : "abc123",
    "text" : "Hello, world!"
}
```

It should be noted that the `userId` is a unique identifier number for the LINE Messaging API. It is not the same as a LINE ID or name.