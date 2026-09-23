"""Motor de transcrição do Subtitle Lab.

Reaproveita o mesmo mecanismo do app de transcrição (SpeechRecognition +
Google Speech + ffmpeg para normalizar o áudio), mas em vez de juntar tudo em
um texto único, devolve cada bloco de alguns segundos com o intervalo de
tempo correspondente - pronto para virar legendas (.srt/.vtt) sincronizadas.
"""

import os
import subprocess
import time
from pathlib import Path


class SubtitleLabError(Exception):
    pass


CHUNK_DURATION = 8  # segundos por bloco de legenda
LANGUAGES = ['pt-BR', 'en-US', 'pt-PT', 'es-ES']


def transcribe_to_segments(file_storage):
    import speech_recognition as sr

    if not file_storage or not file_storage.filename:
        raise SubtitleLabError("Selecione um arquivo de áudio ou vídeo.")

    downloads_dir = str(Path.home() / "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    ts = int(time.time() * 1000)
    ext = os.path.splitext(file_storage.filename)[1] or '.dat'
    temp_input = os.path.join(downloads_dir, f"subtitlelab_input_{ts}{ext}")
    temp_audio = os.path.join(downloads_dir, f"subtitlelab_audio_{ts}.wav")

    try:
        file_storage.save(temp_input)

        result = subprocess.run([
            'ffmpeg', '-i', temp_input,
            '-vn', '-ar', '48000', '-ac', '1', '-acodec', 'pcm_s16le',
            '-af', 'highpass=f=80,lowpass=f=8000,afftdn=nf=-25,volume=3,speechnorm',
            '-y', temp_audio
        ], capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise SubtitleLabError("Erro ao processar o áudio/vídeo com ffmpeg.")

        recognizer = sr.Recognizer()
        segments = []

        with sr.AudioFile(temp_audio) as source:
            audio_length = int(source.DURATION)
            for i in range(0, audio_length, CHUNK_DURATION):
                duration = min(CHUNK_DURATION, audio_length - i)
                try:
                    chunk = recognizer.record(source, duration=duration)
                except Exception:
                    continue

                text = None
                for lang in LANGUAGES:
                    try:
                        text = recognizer.recognize_google(chunk, language=lang)
                        if text:
                            break
                    except Exception:
                        continue

                if text:
                    segments.append({'start': i, 'end': i + duration, 'text': text.strip()})

        if not segments:
            raise SubtitleLabError("Não foi possível transcrever. Tente um áudio com voz mais clara.")

        return segments
    except subprocess.TimeoutExpired:
        raise SubtitleLabError("Arquivo muito grande. Tente um arquivo menor.")
    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
