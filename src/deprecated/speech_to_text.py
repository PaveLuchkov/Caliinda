from argparse import ArgumentParser
from speechkit import model_repository, configure_credentials, creds
from speechkit.stt import AudioProcessingType
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

def recognize_speech(audio_path):
    """Распознает речь из аудиофайла и возвращает текст"""
    configure_credentials(
        yandex_credentials=creds.YandexCredentials(
            api_key=os.getenv('YANDEX_API_KEY')
        )
    )

    model = model_repository.recognition_model()
    model.model = 'general'
    model.language = 'ru-RU'
    model.audio_processing_type = AudioProcessingType.Full

    result = model.transcribe_file(audio_path)
    return result[0].raw_text if result else None


