"""Áudio Studio · operações na lista de edição (as mesmas do editor, em Python).

As receitas e as sugestões aceitas no servidor usam estas funções; o editor no
navegador tem as mesmas regras em JavaScript (estudio.js), então o resultado
é igual dos dois lados.

- cortar_fonte: tira trechos (em tempo da FONTE) de todo clipe que usa aquela
  fonte; com "fechar o buraco" (ripple), o que vem depois na pista anda para trás.
- encurtar: corta o miolo de um trecho e deixa `manter` segundos (pausa natural).
- recortar: fica só com [a, b] do tempo do projeto (melhor trecho, Reels).
"""
import secrets


def _id():
    return secrets.token_hex(5)


def _subtrair(ini, fim, cortes):
    """[ini, fim) menos os cortes -> pedaços que sobram."""
    pedacos = [(ini, fim)]
    for a, b in cortes:
        novo = []
        for x, y in pedacos:
            if b <= x or a >= y:
                novo.append((x, y))
                continue
            if a > x:
                novo.append((x, a))
            if b < y:
                novo.append((b, y))
        pedacos = novo
    return [(x, y) for x, y in pedacos if y - x > 0.004]


def _normalizar(cortes):
    cs = sorted((float(a), float(b)) for a, b in cortes if b - a > 0.004)
    out = []
    for a, b in cs:
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def cortar_fonte(proj, fid, cortes, ripple=True):
    """-> segundos removidos da linha do tempo (por pista)."""
    cortes = _normalizar(cortes)
    removido = {}
    for pista in proj['pistas']:
        novos, buracos = [], []
        for c in sorted(pista['clipes'], key=lambda c: c['pos']):
            if c['fonte'] != fid:
                novos.append(dict(c))
                continue
            ini, fim = c['ini'], c['ini'] + c['dur']
            sobra = _subtrair(ini, fim, cortes)
            for a, b in cortes:   # buracos em tempo do projeto
                x, y = max(a, ini), min(b, fim)
                if y > x:
                    buracos.append((c['pos'] + x - ini, c['pos'] + y - ini))
            for k, (x, y) in enumerate(sobra):
                n = dict(c)
                n.update(id=c['id'] if k == 0 else _id(), ini=x, dur=y - x, pos=c['pos'] + (x - ini))
                if x > ini:
                    n['fi'] = 0.0   # o fade de entrada era do começo original
                if y < fim:
                    n['fo'] = 0.0
                novos.append(n)
        if ripple and buracos:
            buracos = _normalizar(buracos)
            for n in novos:
                antes = sum(b - a for a, b in buracos if b <= n['pos'] + 1e-6)
                n['pos'] = max(0.0, n['pos'] - antes)
            pista['envelope'] = _mover_envelope(pista.get('envelope') or [], buracos)
        pista['clipes'] = sorted(novos, key=lambda c: c['pos'])
        removido[pista['id']] = sum(b - a for a, b in buracos)
    return removido


def _mover_envelope(env, buracos):
    out = []
    for t, db in env:
        if any(a < t < b for a, b in buracos):
            continue
        antes = sum(b - a for a, b in buracos if b <= t)
        out.append([max(0.0, t - antes), db])
    return out


def encurtar_trechos(trechos, manter):
    """Pausas longas viram pausas de `manter` s: corta o miolo, deixa metade de cada lado."""
    cortes = []
    for a, b in trechos:
        if b - a > manter + 0.05:
            meio = manter / 2
            cortes.append((a + meio, b - meio))
    return cortes


def recortar(proj, a, b, fade_in=0.3, fade_out=1.5):
    """Fica só com [a, b] do tempo do projeto, começando em 0, com fades."""
    for pista in proj['pistas']:
        novos = []
        for c in pista['clipes']:
            x, y = max(a, c['pos']), min(b, c['pos'] + c['dur'])
            if y - x <= 0.004:
                continue
            n = dict(c)
            n.update(ini=c['ini'] + (x - c['pos']), dur=y - x, pos=x - a, fi=0.0, fo=0.0)
            novos.append(n)
        if novos:
            novos.sort(key=lambda c: c['pos'])
            novos[0]['fi'] = fade_in if novos[0]['pos'] < 0.01 else novos[0]['fi']
            fim = max(c['pos'] + c['dur'] for c in novos)
            for c in novos:
                if abs(c['pos'] + c['dur'] - fim) < 0.01:
                    c['fo'] = min(fade_out, c['dur'] / 2)
        pista['clipes'] = novos
        pista['envelope'] = [[t - a, db] for t, db in (pista.get('envelope') or []) if a <= t <= b]
    proj['marcadores'] = [dict(m, t=m['t'] - a) for m in proj.get('marcadores', []) if a <= m['t'] <= b]
    proj['regioes'] = []


def duracao(proj):
    return max([c['pos'] + c['dur'] for p in proj['pistas'] for c in p['clipes']] or [0.0])


def fonte_para_projeto(proj, fid, t):
    """Instante t da fonte -> instante no projeto (primeiro clipe que o contém), ou None."""
    for p in proj['pistas']:
        for c in p['clipes']:
            if c['fonte'] == fid and c['ini'] - 1e-6 <= t <= c['ini'] + c['dur'] + 1e-6:
                return c['pos'] + (t - c['ini'])
    return None


def reduzir_trechos(proj, fid, trechos):
    """Abaixa trechos da fonte (respirações): divide os clipes nas bordas e
    soma `db` ao ganho dos pedaços de dentro. Não muda nenhum tempo."""
    for pista in proj['pistas']:
        novos = []
        for c in pista['clipes']:
            if c['fonte'] != fid:
                novos.append(c)
                continue
            ini, fim = c['ini'], c['ini'] + c['dur']
            cortes = sorted({x for a, b, _ in trechos for x in (a, b) if ini < x < fim})
            limites = [ini] + cortes + [fim]
            for k, (x, y) in enumerate(zip(limites, limites[1:])):
                if y - x <= 0.004:
                    continue
                n = dict(c)
                n.update(id=c['id'] if k == 0 else _id(), ini=x, dur=y - x, pos=c['pos'] + (x - ini),
                         fi=c['fi'] if x == ini else 0.0, fo=c['fo'] if y == fim else 0.0)
                meio = (x + y) / 2
                for a, b, db in trechos:
                    if a <= meio <= b:
                        n['ganho'] = max(-60.0, (c.get('ganho') or 0.0) + db)
                        break
                novos.append(n)
        pista['clipes'] = sorted(novos, key=lambda c: c['pos'])
