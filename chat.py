import requests

URL = "https://api.openai.com/v1/chat/completions"
KEY = "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"

prompts = [
    {
        "role" : "system",
        "content" : "You are a helpful assistant."
    }
]

params = {
    "model" : "gpt-3.5-turbo",
    "messages" : prompts,
    "max_tokens" : 100,
}

headers = {
    "Authorization" : "Bearer " + KEY,
    "Content-Type" : "application/json"
}

response = requests.post(URL, json=params, headers=headers)

data = response.json()
print(data)