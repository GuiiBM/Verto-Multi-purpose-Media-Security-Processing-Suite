"""Áudio Studio · transcrição em blocos (tarefa da fila).

Cada bloco de 10 min (+2 s de sobra) roda num processo próprio, com teto de
memória, e o resultado do bloco fica salvo: se o Verto fechar, a transcrição
volta do bloco seguinte. No fim os blocos viram uma lista só de palavras com
o tempo de cada uma (em tempo da fonte).

Medido nesta máquina (10 min de fala real, LibriVox em português):
base 105 s (850 MB), small 299 s (1 GB). Padrão: base; "precisa": small.
O contexto inicial com hesitações ("hã, é... tipo, né") faz o Whisper
escrever os vícios em vez de limpá-los, que é o que as sugestões precisam.
"""
import json
import os
import sys
import time

import numpy as np

from AudioStudio import as_fila as F
from AudioStudio import as_midia as M
from AudioStudio import as_projeto as P

TETO_MB = {'base': 1300, 'small': 1600}
PRECISA_MB = {'base': 1000, 'small': 1300}
CONTEXTO = {
    'pt': 'Hã, é... então, tipo, né? Ahn, hum, bom. Eu, eu acho que...',
    'en': 'Um, uh, so, like, you know? Uh, hmm, well. I, I think that...',
    'es': 'Eh, este... o sea, pues, ¿no? Ehm, bueno. Yo, yo creo que...',
}


def tarefa(t, ctx):
    pid, fid = t['projeto'], t['args']['fonte']
    modelo = t['args'].get('modelo', 'base')
    pf = P.pasta_fonte(pid, fid)
    info = M.ler_fonte(pf)
    if info.get('estado') != 'pronta':
        raise F.FilaError('O arquivo ainda está sendo preparado. A transcrição entra na fila logo depois.')
    dur = info['duracao']
    n = max(1, int(np.ceil(dur / F.BLOCO_S)))
    ctx.blocos(n)
    pasta_tr = os.path.join(P.pasta(pid), 'transcricao')
    os.makedirs(pasta_tr, exist_ok=True)
    idioma = t['args'].get('idioma') or P.ler(pid).get('idioma') or 'auto'
    idioma = ctx.t['dados'].get('idioma_detectado') or (None if idioma == 'auto' else idioma)
    for b in range(ctx.t['feitos'], n):
        t0 = time.time()
        ini = b * F.BLOCO_S
        fim = min(dur, ini + F.BLOCO_S + F.SOBRA_S)
        saida = os.path.join(pasta_tr, f'{fid}_b{b:04d}.json')
        ctx.etapa(f'Transcrevendo: bloco {b + 1} de {n}', b / n)
        livre = F.ram_livre_mb() - F.MARGEM_MB
        mod = modelo if livre >= PRECISA_MB[modelo] else 'base'
        if livre < PRECISA_MB['base']:
            raise MemoryError()
        inicio_bloco = time.time()

        def ler(linha, b=b):
            if linha.startswith('PROGRESSO '):
                try:
                    ctx.etapa(f'Transcrevendo: bloco {b + 1} de {n}', (b + float(linha.split()[1])) / n)
                except ValueError:
                    pass
            elif linha.startswith('IDIOMA '):
                ctx.t['dados']['idioma_detectado'] = linha.split()[1]
        ctx.rodar([sys.executable, '-m', 'AudioStudio.as_transcrever', os.path.join(pf, 'a16.raw'), str(ini), str(fim),
                   saida, mod, idioma or 'auto'], teto_mb=TETO_MB[mod], ao_ler=ler)
        idioma = ctx.t['dados'].get('idioma_detectado') or idioma
        ctx.bloco_feito({'idioma_detectado': idioma}, seg=time.time() - inicio_bloco)
    # junta os blocos: no limite B, fica o que começa antes de B no bloco de
    # cima e o que começa depois de B no bloco de baixo
    palavras = []
    for b in range(n):
        with open(os.path.join(pasta_tr, f'{fid}_b{b:04d}.json'), encoding='utf-8') as f:
            ws = json.load(f)
        lim_ini = b * F.BLOCO_S
        lim_fim = (b + 1) * F.BLOCO_S if b < n - 1 else 1e12
        palavras += [w for w in ws if lim_ini <= w['ini'] < lim_fim]
    palavras.sort(key=lambda w: w['ini'])
    final = {'fonte': fid, 'idioma': idioma or 'pt', 'modelo': modelo, 'palavras': palavras,
             'criada': time.strftime('%Y-%m-%d %H:%M')}
    with open(P.caminho_transcricao(pid, fid), 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False)
    for b in range(n):
        try:
            os.remove(os.path.join(pasta_tr, f'{fid}_b{b:04d}.json'))
        except OSError:
            pass
    return {'palavras': len(palavras), 'idioma': final['idioma']}


def _worker(a16_path, ini, fim, saida, modelo, idioma):
    from faster_whisper import WhisperModel
    a = np.memmap(a16_path, dtype=np.int16, mode='r')
    i0, i1 = int(float(ini) * M.SR_ANALISE), int(float(fim) * M.SR_ANALISE)
    sinal = np.asarray(a[i0:i1], dtype=np.float32) / 32768.0
    threads = max(1, (os.cpu_count() or 2) - 1)
    m = WhisperModel(modelo, device='cpu', compute_type='int8', cpu_threads=threads)
    lang = None if idioma in ('auto', '', None) else idioma
    segs, info = m.transcribe(sinal, language=lang, word_timestamps=True, vad_filter=True,
                              vad_parameters={'min_silence_duration_ms': 400}, beam_size=5,
                              condition_on_previous_text=False,
                              initial_prompt=CONTEXTO.get(lang or 'pt'))
    print(f'IDIOMA {info.language}', flush=True)
    dur = max(1e-6, len(sinal) / M.SR_ANALISE)
    palavras = []
    for s in segs:
        print(f'PROGRESSO {min(1.0, s.end / dur):.3f}', flush=True)
        if s.no_speech_prob > 0.7 and s.avg_logprob < -1.0:
            continue
        for w in s.words or []:
            texto = w.word.strip()
            if texto and w.end > w.start:
                palavras.append({'w': texto, 'ini': round(float(ini) + float(w.start), 3),
                                 'fim': round(float(ini) + float(w.end), 3), 'p': round(float(w.probability), 3)})
    with open(saida + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(palavras, f, ensure_ascii=False)
    os.replace(saida + '.tmp', saida)


if __name__ == '__main__':
    _worker(*sys.argv[1:7])
