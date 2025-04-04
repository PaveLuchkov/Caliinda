import requests
from urllib.parse import unquote

auth_url = f"https://accounts.google.com/o/oauth2/auth?client_id=835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com&redirect_uri=http://localhost:8000&response_type=code&scope=https://www.googleapis.com/auth/calendar&access_type=offline&prompt=consent"
print("Перейдите по ссылке и авторизуйтесь:", auth_url)

# Декодируем URL-encoded code
code = unquote("4/0AQSTgQFHs2ZsiX6-KsYo9EPKg3OatuNaHOhI6QHDYZszCzAhiAxhpF13ZDIDkFe6VQI9lg")

data = {
    "code": code,
    "client_id": "835523232919-o0ilepmg8ev25bu3ve78kdg0smuqp9i8.apps.googleusercontent.com",
    "client_secret": "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",
    "redirect_uri": "http://localhost:8000",  # Должен совпадать с Cloud Console!
    "grant_type": "authorization_code"
}

response = requests.post("https://oauth2.googleapis.com/token", data=data)

if response.status_code == 200:
    print("Токены получены:", response.json())
else:
    print("Ошибка:", response.text)  # Выведет детали ошибки