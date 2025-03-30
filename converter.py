from pydub import AudioSegment
import os

def convert_ogg_to_wav(input_ogg_path, output_wav_path=None, sample_rate=16000):
    """
    Конвертирует OGG в WAV с заданной частотой дискретизации.
    
    :param input_ogg_path: Путь к исходному OGG-файлу
    :param output_wav_path: Путь для сохранения WAV (если None, сохраняет рядом с исходным файлом)
    :param sample_rate: Частота дискретизации (Гц)
    :return: Путь к созданному WAV-файлу
    """
    try:
        # Загружаем OGG-файл
        audio = AudioSegment.from_ogg(input_ogg_path)
        
        # Устанавливаем параметры
        audio = audio.set_frame_rate(sample_rate).set_channels(1)  # моно
        
        # Определяем путь для сохранения
        if output_wav_path is None:
            base = os.path.splitext(input_ogg_path)[0]
            output_wav_path = f"{base}.wav"
        
        # Экспортируем в WAV
        audio.export(output_wav_path, format="wav")
        print(f"Файл успешно конвертирован: {output_wav_path}")
        return output_wav_path
        
    except Exception as e:
        print(f"Ошибка конвертации: {str(e)}")
        return None

# Пример использования
if __name__ == "__main__":
    input_file = "test.ogg"  # Укажите ваш файл
    output_file = "test.wav"  # Можно оставить None для автоимени
    
    convert_ogg_to_wav(input_file, output_file)