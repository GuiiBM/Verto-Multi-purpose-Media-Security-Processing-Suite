"""Áudio Studio · liga cada tipo de tarefa da fila à função que a executa."""
from AudioStudio import as_fila as F
from AudioStudio import as_midia as M
from AudioStudio import as_projeto as P


def _preparar(t, ctx):
    return M.preparar(P.pasta_fonte(t['projeto'], t['args']['fonte']), ctx)


def _transcrever(t, ctx):
    from AudioStudio import as_transcrever
    return as_transcrever.tarefa(t, ctx)


def _analisar(t, ctx):
    from AudioStudio import as_analise
    return as_analise.tarefa(t, ctx)


def _exportar(t, ctx):
    from AudioStudio import as_render
    return as_render.exportar(t['projeto'], t['args'], ctx)


def _medir(t, ctx):
    from AudioStudio import as_render
    return as_render.medir(t['projeto'], ctx)


def _receita(t, ctx):
    from AudioStudio import as_receitas
    return as_receitas.tarefa(t, ctx)


def _separar(t, ctx):
    from AudioStudio import as_receitas
    return as_receitas.separar(t, ctx)


def registrar():
    for nome, f in (('preparar', _preparar), ('transcrever', _transcrever), ('analisar', _analisar),
                    ('exportar', _exportar), ('medir', _medir), ('receita', _receita), ('separar', _separar)):
        F.registrar(nome, f)
    F.iniciar()
