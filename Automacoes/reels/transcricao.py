"""Transcrição palavra por palavra com o faster-whisper (CTranslate2).

No CPU ele é bem mais rápido que o Whisper original e já tem filtro de voz
(VAD). O modelo é baixado na primeira vez (base ~145 MB, small ~460 MB,
medium ~1,5 GB) e fica no cache do Hugging Face.

O áudio entra já decodificado (numpy, 16 kHz), então o PyAV do
faster-whisper não é usado.
"""
import os
import re
import threading

MODELOS = {
    'base': 'Rápido (base)',
    'small': 'Equilibrado (small)',
    'medium': 'Preciso (medium, lento no CPU)',
}

# Frases que o Whisper "ouve" em música ou silêncio (vêm das legendas dos
# vídeos em que ele foi treinado).
_ALUCINACOES = re.compile(
    r'legendas? (por|pela|de)|amara\.org|obrigad[oa]s? por assistir|inscreva-se|'
    r'subt[ií]tulos? (por|realizados)|transcri[çc][ãa]o (por|de)|♪', re.I)

_cache = {}
_lock = threading.Lock()


class TranscricaoError(Exception):
    pass


def _modelo(nome):
    with _lock:
        if nome not in _cache:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise TranscricaoError('Falta o pacote faster-whisper: rode o INSTALAR.py ou pip install faster-whisper.')
            threads = max(1, (os.cpu_count() or 2) - 1)
            _cache.clear()   # um modelo por vez na memória
            _cache[nome] = WhisperModel(nome, device='cpu', compute_type='int8', cpu_threads=threads)
        return _cache[nome]


def transcrever(audio, modelo='small', idioma='pt', progresso=None):
    """Lista de palavras {'w', 'ini', 'fim', 'p'} no tempo do vídeo original."""
    if modelo not in MODELOS:
        modelo = 'small'
    m = _modelo(modelo)
    duracao = len(audio) / 16000 or 1
    segmentos, _ = m.transcribe(
        audio, language=idioma or None, word_timestamps=True, vad_filter=True,
        vad_parameters={'min_silence_duration_ms': 300}, condition_on_previous_text=False, beam_size=5)
    palavras = []
    for seg in segmentos:
        if progresso:
            progresso(min(1.0, seg.end / duracao))
        texto = (seg.text or '').strip()
        if _ALUCINACOES.search(texto) or (seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0):
            continue
        for w in seg.words or []:
            t = w.word.strip()
            if t and w.end > w.start:
                palavras.append({'w': t, 'ini': round(float(w.start), 3), 'fim': round(float(w.end), 3),
                                 'p': round(float(w.probability), 3)})
    return palavras
