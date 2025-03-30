from argparse import ArgumentParser
from speechkit import model_repository, configure_credentials, creds
from speechkit.stt import AudioProcessingType
import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)
ya_api = os.getenv('YANDEX_API_KEY')

# Аутентификация через API-ключ.
configure_credentials(
   yandex_credentials=creds.YandexCredentials(
      api_key = ya_api
   )
)

def recognize(audio):
   model = model_repository.recognition_model()

   # Задайте настройки распознавания.
   model.model = 'general'
   model.language = 'ru-RU'
   model.audio_processing_type = AudioProcessingType.Full

   # Распознавание речи в указанном аудиофайле и вывод результатов в консоль.
   result = model.transcribe_file(audio)
   for c, res in enumerate(result):
      print('=' * 80)
      print(f'channel: {c}\n\nraw_text:\n{res.raw_text}\n\nnorm_text:\n{res.normalized_text}\n')
      if res.has_utterances():
         print('utterances:')
         for utterance in res.utterances:
            print(utterance)

if __name__ == '__main__':
   parser = ArgumentParser()
   parser.add_argument('--audio', type=str, help='audio path', required=True)

   args = parser.parse_args()

   recognize(args.audio)
