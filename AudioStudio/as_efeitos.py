"""Áudio Studio · efeitos: catálogo, validação e filtro do FFmpeg de cada um.

A cadeia do master é uma lista [{id, ef, ativo, p: {param: valor}}]. O arquivo
final sempre passa pelo FFmpeg (filtros testados nesta máquina: afftdn,
anlmdn, arnndn, deesser, adeclick, adeclip, agate, acompressor, alimiter,
equalizer, rubberband, loudnorm, speechnorm, dynaudnorm...). No navegador, os
que têm "previa" tocam em tempo real com Web Audio; os outros dá para ouvir
pela "Prévia fiel" (10 s renderizados aqui com a cadeia inteira).
"""
import math
import os

MODELO_RNNOISE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modelos', 'rnnoise.rnnn')


def _lin(db):
    return 10 ** (db / 20)


EQ_PRESETS = {
    'voz': ('Voz clara', 'highpass=f=80:poles=2,equalizer=f=250:t=q:w=1.1:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=3,'
                         'treble=g=2:f=10000'),
    'radio': ('Voz de rádio', 'highpass=f=110:poles=2,bass=g=3:f=140,equalizer=f=2500:t=q:w=1:g=4,treble=g=1.5:f=9000'),
    'telefone': ('Telefone', 'highpass=f=320:poles=2,lowpass=f=3300:poles=2,equalizer=f=1500:t=q:w=1:g=4'),
    'graves': ('Mais graves', 'bass=g=6:f=110'),
    'brilho': ('Mais brilho', 'treble=g=5:f=7000'),
    'abafado': ('Tirar o abafado', 'equalizer=f=400:t=q:w=1:g=-4,equalizer=f=4000:t=q:w=1.4:g=2.5'),
    'zumbido60': ('Tirar zumbido 60 Hz', ','.join(f'bandreject=f={f}:width_type=q:w=30' for f in (60, 120, 180, 240, 300))),
    'zumbido50': ('Tirar zumbido 50 Hz', ','.join(f'bandreject=f={f}:width_type=q:w=30' for f in (50, 100, 150, 200, 250))),
}

RUIDO = {
    'leve': ('Leve', 'afftdn=nr=10:nf=-45:tn=1'),
    'medio': ('Médio', 'afftdn=nr=16:nf=-42:tn=1,anlmdn=s=0.00008:p=0.002:r=0.006'),
    'forte': ('Forte (voz)', None),   # RNNoise quando o modelo está instalado
}


def _ruido(p):
    nivel = p.get('nivel', 'medio')
    if nivel == 'forte':
        if os.path.exists(MODELO_RNNOISE):
            m = MODELO_RNNOISE.replace('\\', '/').replace(':', '\\:')
            return f"arnndn=m='{m}':mix=0.9"
        return 'afftdn=nr=24:nf=-40:tn=1,anlmdn=s=0.00015:p=0.002:r=0.008'
    return RUIDO.get(nivel, RUIDO['medio'])[1]


CATALOGO = [
    # id, nome, grupo, parâmetros, prévia no navegador, construtor do filtro
    {'id': 'ganho', 'nome': 'Ganho', 'grupo': 'Volume', 'previa': True,
     'p': [{'id': 'db', 'nome': 'Ganho', 'min': -24, 'max': 24, 'passo': 0.5, 'padrao': 0, 'un': 'dB'}],
     'f': lambda p: f"volume={p['db']}dB"},
    {'id': 'normalizar', 'nome': 'Normalizar pico', 'grupo': 'Volume', 'previa': False,
     'p': [{'id': 'pico', 'nome': 'Pico', 'min': -12, 'max': 0, 'passo': 0.5, 'padrao': -1, 'un': 'dBFS'}],
     'f': None},   # duas passadas: mede o pico e aplica o ganho (no render)
    {'id': 'nivelar', 'nome': 'Nivelar volume da fala', 'grupo': 'Volume', 'previa': False,
     'p': [{'id': 'forca', 'nome': 'Força', 'min': 1, 'max': 10, 'passo': 1, 'padrao': 5, 'un': ''}],
     'f': lambda p: f"speechnorm=e={2 + p['forca'] * 1.2:.1f}:r=0.00012:l=1"},
    {'id': 'nivelar_musica', 'nome': 'Nivelar volume (música)', 'grupo': 'Volume', 'previa': False,
     'p': [{'id': 'janela', 'nome': 'Janela', 'min': 3, 'max': 30, 'passo': 1, 'padrao': 10, 'un': 's'}],
     'f': lambda p: f"dynaudnorm=f={int(p['janela'] * 1000 / 20)}:g=15:p=0.9"},
    {'id': 'compressor', 'nome': 'Compressor', 'grupo': 'Dinâmica', 'previa': True,
     'p': [{'id': 'limiar', 'nome': 'Limiar', 'min': -50, 'max': 0, 'passo': 1, 'padrao': -20, 'un': 'dB'},
           {'id': 'razao', 'nome': 'Razão', 'min': 1, 'max': 20, 'passo': 0.5, 'padrao': 3, 'un': ':1'},
           {'id': 'ataque', 'nome': 'Ataque', 'min': 1, 'max': 200, 'passo': 1, 'padrao': 15, 'un': 'ms'},
           {'id': 'liberacao', 'nome': 'Liberação', 'min': 20, 'max': 1000, 'passo': 10, 'padrao': 200, 'un': 'ms'},
           {'id': 'ganho', 'nome': 'Ganho de saída', 'min': 0, 'max': 18, 'passo': 0.5, 'padrao': 3, 'un': 'dB'}],
     'f': lambda p: (f"acompressor=threshold={_lin(p['limiar']):.6f}:ratio={p['razao']}:attack={p['ataque']}:"
                     f"release={p['liberacao']}:makeup={_lin(p['ganho']):.4f}")},
    {'id': 'limitador', 'nome': 'Limitador', 'grupo': 'Dinâmica', 'previa': True,
     'p': [{'id': 'teto', 'nome': 'Teto', 'min': -12, 'max': 0, 'passo': 0.1, 'padrao': -1, 'un': 'dBFS'}],
     'f': lambda p: f"alimiter=limit={_lin(p['teto']):.5f}:attack=5:release=50:level=disabled"},
    {'id': 'gate', 'nome': 'Gate (corta o ruído nas pausas)', 'grupo': 'Dinâmica', 'previa': False,
     'p': [{'id': 'limiar', 'nome': 'Limiar', 'min': -80, 'max': -20, 'passo': 1, 'padrao': -50, 'un': 'dB'}],
     'f': lambda p: f"agate=threshold={_lin(p['limiar']):.6f}:range=0.05:attack=5:release=180"},
    {'id': 'ruido', 'nome': 'Redução de ruído', 'grupo': 'Limpeza', 'previa': False,
     'p': [{'id': 'nivel', 'nome': 'Nível', 'opcoes': [[k, v[0]] for k, v in RUIDO.items()], 'padrao': 'medio'}],
     'f': _ruido},
    {'id': 'deesser', 'nome': 'De-esser (chiado do S)', 'grupo': 'Limpeza', 'previa': False,
     'p': [{'id': 'intensidade', 'nome': 'Intensidade', 'min': 0.05, 'max': 1, 'passo': 0.05, 'padrao': 0.4, 'un': ''}],
     'f': lambda p: f"deesser=i={p['intensidade']}:m=0.5:f=0.5:s=o"},
    {'id': 'declick', 'nome': 'Tirar cliques e estalos', 'grupo': 'Limpeza', 'previa': False, 'p': [],
     'f': lambda p: 'adeclick=w=55:o=75:a=2:t=2:b=2'},
    {'id': 'declip', 'nome': 'Recuperar estouro (clipping)', 'grupo': 'Limpeza', 'previa': False, 'p': [],
     'f': lambda p: 'adeclip=w=55:o=75:a=8:t=10:n=1000'},
    {'id': 'passa_alta', 'nome': 'Corte de graves', 'grupo': 'Equalização', 'previa': True,
     'p': [{'id': 'freq', 'nome': 'Abaixo de', 'min': 20, 'max': 400, 'passo': 5, 'padrao': 80, 'un': 'Hz'}],
     'f': lambda p: f"highpass=f={p['freq']}:poles=2"},
    {'id': 'passa_baixa', 'nome': 'Corte de agudos', 'grupo': 'Equalização', 'previa': True,
     'p': [{'id': 'freq', 'nome': 'Acima de', 'min': 1000, 'max': 20000, 'passo': 100, 'padrao': 12000, 'un': 'Hz'}],
     'f': lambda p: f"lowpass=f={p['freq']}:poles=2"},
    {'id': 'eq', 'nome': 'Equalizador', 'grupo': 'Equalização', 'previa': True,
     'p': [{'id': 'graves', 'nome': 'Graves (100 Hz)', 'min': -15, 'max': 15, 'passo': 0.5, 'padrao': 0, 'un': 'dB'},
           {'id': 'medios', 'nome': 'Médios (1 kHz)', 'min': -15, 'max': 15, 'passo': 0.5, 'padrao': 0, 'un': 'dB'},
           {'id': 'presenca', 'nome': 'Presença (3,5 kHz)', 'min': -15, 'max': 15, 'passo': 0.5, 'padrao': 0, 'un': 'dB'},
           {'id': 'agudos', 'nome': 'Agudos (10 kHz)', 'min': -15, 'max': 15, 'passo': 0.5, 'padrao': 0, 'un': 'dB'}],
     'f': lambda p: (f"bass=g={p['graves']}:f=100,equalizer=f=1000:t=q:w=1:g={p['medios']},"
                     f"equalizer=f=3500:t=q:w=1.2:g={p['presenca']},treble=g={p['agudos']}:f=10000")},
    {'id': 'eq_preset', 'nome': 'Equalização pronta', 'grupo': 'Equalização', 'previa': True,
     'p': [{'id': 'preset', 'nome': 'Tipo', 'opcoes': [[k, v[0]] for k, v in EQ_PRESETS.items()], 'padrao': 'voz'}],
     'f': lambda p: EQ_PRESETS.get(p['preset'], EQ_PRESETS['voz'])[1]},
    {'id': 'velocidade', 'nome': 'Velocidade (sem mudar o tom)', 'grupo': 'Tempo e tom', 'previa': False,
     'p': [{'id': 'fator', 'nome': 'Velocidade', 'min': 0.5, 'max': 2, 'passo': 0.05, 'padrao': 1.1, 'un': '×'}],
     'f': lambda p: f"rubberband=tempo={p['fator']}:pitchq=quality"},
    {'id': 'tom', 'nome': 'Tom (sem mudar a velocidade)', 'grupo': 'Tempo e tom', 'previa': False,
     'p': [{'id': 'semitons', 'nome': 'Semitons', 'min': -12, 'max': 12, 'passo': 1, 'padrao': 2, 'un': 'st'}],
     'f': lambda p: f"rubberband=pitch={2 ** (p['semitons'] / 12):.6f}:pitchq=quality:formant=preserved"},
    {'id': 'reverb', 'nome': 'Reverb (sala)', 'grupo': 'Espaço', 'previa': False,
     'p': [{'id': 'quantidade', 'nome': 'Quantidade', 'min': 0.05, 'max': 0.8, 'passo': 0.05, 'padrao': 0.25, 'un': ''},
           {'id': 'tamanho', 'nome': 'Tamanho', 'opcoes': [['pequena', 'Sala pequena'], ['media', 'Sala média'], ['grande', 'Salão']],
            'padrao': 'media'}],
     'f': lambda p: (lambda d: f"aecho=0.85:{1 - p['quantidade'] * 0.6:.2f}:{d[0]}:{d[1]}")(
         {'pequena': ('23|37|51', '0.35|0.25|0.18'), 'media': ('40|67|103', '0.4|0.3|0.2'),
          'grande': ('70|121|187|263', '0.45|0.35|0.27|0.2')}[p['tamanho']])},
    {'id': 'eco', 'nome': 'Eco', 'grupo': 'Espaço', 'previa': False,
     'p': [{'id': 'atraso', 'nome': 'Atraso', 'min': 80, 'max': 1500, 'passo': 10, 'padrao': 350, 'un': 'ms'},
           {'id': 'volume', 'nome': 'Volume do eco', 'min': 0.05, 'max': 0.8, 'passo': 0.05, 'padrao': 0.35, 'un': ''}],
     'f': lambda p: f"aecho=0.9:0.9:{p['atraso']}|{p['atraso'] * 2}:{p['volume']}|{p['volume'] * 0.5:.3f}"},
    {'id': 'mono', 'nome': 'Mono (as duas caixas iguais)', 'grupo': 'Espaço', 'previa': True, 'p': [],
     'f': lambda p: 'pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1'},
    {'id': 'largura', 'nome': 'Largura estéreo', 'grupo': 'Espaço', 'previa': False,
     'p': [{'id': 'fator', 'nome': 'Largura', 'min': 0, 'max': 3, 'passo': 0.1, 'padrao': 1.5, 'un': '×'}],
     'f': lambda p: f"extrastereo=m={p['fator']}:c=1"},
    {'id': 'inverter', 'nome': 'Tocar ao contrário', 'grupo': 'Espaço', 'previa': False, 'p': [],
     'f': lambda p: 'areverse'},
]
POR_ID = {e['id']: e for e in CATALOGO}
MUDA_DURACAO = {'velocidade'}


def catalogo():
    return [{k: v for k, v in e.items() if k != 'f'} for e in CATALOGO]


def _param(spec, valor):
    if 'opcoes' in spec:
        validos = [o[0] for o in spec['opcoes']]
        return valor if valor in validos else spec['padrao']
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return spec['padrao']
    if math.isnan(v):
        return spec['padrao']
    return max(spec['min'], min(spec['max'], v))


def validar_cadeia(cadeia):
    out = []
    for item in (cadeia or [])[:40]:
        e = POR_ID.get((item or {}).get('ef'))
        if not e:
            continue
        p = {s['id']: _param(s, (item.get('p') or {}).get(s['id'], s['padrao'])) for s in e['p']}
        out.append({'id': str(item.get('id') or os.urandom(4).hex())[:16], 'ef': e['id'], 'ativo': item.get('ativo', True) is not False, 'p': p})
    return out


def filtros(cadeia, duracao=None):
    """Cadeia -> lista de filtros do FFmpeg (o 'normalizar' é tratado no render)."""
    partes = []
    for item in validar_cadeia(cadeia):
        if not item['ativo']:
            continue
        e = POR_ID[item['ef']]
        if e['f'] is None:
            continue
        if item['ef'] == 'inverter' and duracao and duracao > 1500:
            raise ValueError('"Tocar ao contrário" funciona até 25 min (ele precisa do áudio inteiro na memória).')
        partes.append(e['f'](item['p']))
    return partes


def pico_alvo(cadeia):
    """Se houver 'Normalizar pico' ativo, o alvo em dBFS (aplicado no fim)."""
    for item in validar_cadeia(cadeia):
        if item['ativo'] and item['ef'] == 'normalizar':
            return item['p']['pico']
    return None
