import requests
import json

def speech_to_text(audio_file_path):
    API_KEY = "AQVN0OwWQzhdGyu2Gso6sB1bw0uONmFszI0OSQF6"
    FOLDER_ID = "b1g3hllubkfvvm07f9o8"
    
    with open(audio_file_path, "rb") as f:
        audio_data = f.read()

    headers = {
        "Authorization": f"Api-Key {API_KEY}",
    }

    params = {
        "folderId": FOLDER_ID,
        "lang": "ru-RU",
    }

    response = requests.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        headers=headers,
        params=params,
        data=audio_data,
    )

    if response.status_code == 200:
        return response.json().get("result")
    else:
        raise Exception(f"Ошибка: {response.text}")

# Пример использования
# text = speech_to_text("test.ogg")
text = speech_to_text("speech.wav")
print(text)  # "Создай встречу на завтра в 15:00"