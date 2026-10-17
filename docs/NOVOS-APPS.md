# Novos apps: Áudio Studio, Vetorizar 4K e SunoSaver

> Planejamento de três apps novos para o Verto (35, 36 e 37). Nada aqui foi implementado.
> Os nomes são provisórios. Pontos marcados **[verificado 2026-10-12]** foram testados
> nesta máquina ou contra o serviço real; **[a verificar]** é suposição que a fase 0 de
> cada app confirma antes de construir em cima.

| # | App (provisório) | Rota | Grupo (cor) | Pasta | Referência |
|---|---|---|---|---|---|
| 35 | **Áudio Studio** | `/audiostudio` | audio (amarelo) | `AudioStudio/` | clideo.com/editor, Descript, Audacity |
| 36 | **Vetorizar 4K** | `/vetorizar` | conversao (azul) | `Vetorizar/` | Vectorizer.AI, Inkscape Trace Bitmap |
| 37 | **SunoSaver** | `/sunosaver` | downloads (verde) | `SunoSaver/` | usesuno.com/pt-br/tools/downloader |

**Ordem sugerida:** SunoSaver (menor, 1 a 2 dias) → Vetorizar 4K (médio) → Áudio Studio
(o maior; ganha com o SunoSaver pronto, que já entrega música para editar).

---

## 0. Restrições que valem para os três

- **Máquina:** APU AMD de 8 threads, 7,2 GB de RAM, sem CUDA. Faltar memória **trava o
  computador** (ver memória do Vetor3D). Toda etapa pesada (IA, render longo) roda pela
  fila com teto de memória do Vetor3D (`Vetor3D/v3d_fila.py` + `v3d_hardware.py`:
  processo novo por tarefa, `systemd-run` com `MemoryMax`, `CPUWeight=20`, nova tentativa
  em modo de pouca memória). Antes de copiar, avaliar extrair a fila para um módulo comum
  (`comum/fila.py`?) que os quatro apps importem.
- **Offline:** Áudio Studio e Vetorizar funcionam sem internet depois do `INSTALAR.py`
  (modelos baixados na instalação, não no primeiro uso). O SunoSaver é downloader e
  depende da internet por natureza.
- **Padrão do projeto:** pasta própria com `__init__.py`, `<app>_templates.py` (lê o HTML
  do disco a cada chamada), `<app>_engine.py`; rotas finas em `app.py`; dados em
  `<App>/dados/` (gitignored); front em HTML/CSS/JS puro; bibliotecas JS locais em
  `static/localtools/vendor/`, nunca CDN.
- **Testes:** porta 5055 e encerrar o servidor; o usuário usa a 5000.

### Checklist de integração (igual para cada app)
1. `app.py`: import do engine/templates, rotas `/<rota>/*`, entrada no `MENU_HTML`
   (`data-cat`, `--hue`, `--i`) e palavras de busca (lista perto da linha 780).
2. Ícone 3D: `scripts/icones_3d.py` → `static/localtools/apps/<id>.webp`.
3. Modo visual próprio (`static/localtools/modos/tema-<x>.css`), sem néon, seguindo
   `docs/REDESIGN.md`. Propostas na seção de cada app.
4. Linhas novas na tabela "Os 34 apps" do `REDESIGN.md` (vira "Os 37 apps"), README
   (tabela de apps e stack) e `templates/instructions.html`.
5. `requirements.txt` + `executaveis/INSTALAR.py` (pacotes e download dos modelos).
6. `.gitignore` para `<App>/dados/`.

---

## 1. Áudio Studio (app 35)

> **Implementado em 2026-10-12** (app 37 do menu): backend em `AudioStudio/` (as_fila,
> as_midia, as_projeto, as_edicao, as_analise, as_transcrever, as_efeitos, as_render,
> as_receitas, audiostudio_engine), front em `AudioStudio/audiostudio.html` +
> `static/localtools/audiostudio/` (estudio.js, estudio.css), tema `tema-ilha.css`.
> Fases 1 a 4 feitas; o editor do Smart Studio saiu (`/smartstudio/editor` redireciona) e o
> gravador ganhou "Editar no Áudio Studio" (leva os marcadores). Medido nesta máquina:
> - **Whisper** (10 min de fala real, LibriVox): `base` 105 s / 850 MB; `small` 299 s / 1 GB.
>   **Padrão: base**; `small` é a opção "Preciso". O espeak não serve para medir (voz robótica
>   detectada como latim, Whisper em laço).
> - **Preparo de 2 h** (vídeo MP4): extrair o áudio + 12 blocos de a16/picos em ~45 s. A prévia
>   em Opus do plano foi trocada por **janelas de 20 s** decodificadas do original na hora (o
>   navegador toca sem cópia nenhuma; a prévia Opus levaria 69 s por 2 h).
> - **Loudness:** `loudnorm` em duas passadas era o gargalo (10 s por 2,5 min, ele roda a
>   192 kHz). Troquei por medição com `ebur128` + ganho linear + limitador: exportar 2,5 min
>   caiu de 40 s para 11,6 s, com −16,0 LUFS medidos no resultado.
> - **Retomada:** servidor derrubado no bloco 4 de 12; ao voltar, continuou do bloco 5 e o
>   arquivo final ficou com o tamanho exato.
> - **Música × fala sem transcrição:** a regra do plano (poucas palavras + pouco silêncio)
>   tratava audiolivro como música. Agora: variação de energia em 200 ms (fala ~15 dB,
>   música 6–10 dB) e quedas abaixo do nível da fala (fala ~40%, música ~18%).
> - **Vícios:** "a" e "e" (artigo e conjunção) não contam; "não, não" e "Morte! Morte!"
>   (ênfase) não são gaguejo. Num audiolivro profissional, zero vícios (certo).
> - Receitas de fala só mexem nas pistas de voz (a primeira versão cortou as pausas da
>   música de fundo).
> - Redução de ruído "Forte" usa FFT reforçada; o RNNoise (`arnndn`) entra sozinho se o
>   modelo for posto em `AudioStudio/modelos/rnnoise.rnnn` (não baixado).
> - **Exportar MP4 (vídeo com o áudio novo)** (2026-10-17): o primeiro vídeo importado é
>   guardado em `<projeto>/video.mkv` (imagem + áudio original, sem recodificar); para
>   projetos antigos, a aba Exportar pede o MP4. A exportação troca o som do vídeo pela
>   mixagem, copia a imagem (H.264 só se o codec não couber em MP4) e sincroniza sozinha
>   por correlação dos ataques de energia (10 ms, ±30 s). Medido: o áudio extraído para o
>   `.mka` ao importar fica 46,5 ms atrasado (perde o ajuste de início do AAC); o
>   automático corrige (resíduo 3,5 ms). Vídeo de 4 min 53 s: 13 s para exportar.
> - MP3/M4A/OGG só aceitam até 48 kHz (MP3 a 96 kHz dava "Nothing was written"): o
>   servidor usa a taxa válida mais próxima e a tela desabilita as que não servem.

### 1.1 Objetivo
Editor de áudio completo e offline: edição livre multipista, **sugestões de onde cortar**
que a pessoa aceita uma a uma ou todas, e **receitas automáticas** que fazem a edição
inteira com um clique (podcast, música para Reels, gravação de celular…).

### 1.2 O que já existe no Verto para reaproveitar
| Peça | Onde | Uso no Áudio Studio |
|---|---|---|
| Forma de onda, marcadores, desfazer, corte de silêncio | `SmartStudio/smartstudio_editor.html` | ponto de partida do canvas (o Smart Studio decodifica tudo no navegador, o que não serve para arquivo longo; ver 1.4) |
| Transcrição palavra por palavra | `Automacoes/reels/transcricao.py` (faster-whisper, int8, filtro de alucinações) | vícios de linguagem, repetições, edição pelo texto |
| Separação de voz | Isolador de Voz (Demucs) | "isolar voz", "tirar voz" (karaokê), limpar fundo |
| Legendas | Subtitle Lab | exportar a transcrição como .srt/.vtt |
| Gravação | Smart Studio | botão "abrir no Áudio Studio" depois de gravar |
| Fila com teto de memória | Vetor3D | Demucs, Whisper e render longo |

**FFmpeg desta máquina [verificado 2026-10-12]:** tem `afftdn`, `anlmdn`, `arnndn`
(RNNoise), `deesser`, `adeclick`, `adeclip`, `agate`, `acompressor`, `alimiter`,
`equalizer`/`anequalizer`, `afir` (reverb por resposta ao impulso), `rubberband`
(tempo e tom com qualidade), `atempo`, `loudnorm`, `ebur128`, `speechnorm`,
`dynaudnorm`, `silencedetect` e `showspectrumpic`. Nenhuma biblioteca de DSP nova é
necessária para os efeitos.

### 1.3 Funcionalidades

**Edição livre**
- Multipista (voz, música, efeitos) com volume, pan, mudo e solo por pista.
- Clipes não destrutivos: cortar, dividir (S), apagar com ou sem fechar o buraco
  (ripple), mover, duplicar, colar, juntar arquivos.
- Fade de entrada/saída e **crossfade automático em cada corte** (5 a 10 ms, no cruzamento
  por zero) para nunca dar estalo.
- Envelope de volume desenhado na pista (automação), ducking automático da música
  quando há voz.
- Zoom até a amostra, rolagem suave, imã (encaixa em marcadores, batidas, palavras).
- Marcadores e regiões com nome; exportar cada região como arquivo separado.
- Vista de espectrograma (para achar ruído, estalo e assobio a olho) além da onda.
- Desfazer/refazer ilimitado (histórico do projeto), atalhos de teclado no padrão
  Audacity/DAW, projeto salvo em `dados/projetos/<id>.json` com autosave.
- **Edição pelo texto** (estilo Descript): a transcrição aparece ao lado; apagar uma
  palavra ou frase apaga o áudio dela.

**Efeitos** (prévia em tempo real com Web Audio quando dá; render final no FFmpeg)
- Ganho, normalizar pico, **loudness por alvo** (Spotify/YouTube −14 LUFS, podcast
  −16, Apple −16, broadcast −23, audiobook ACX), medidor LUFS/True Peak (`ebur128`).
- EQ paramétrico + predefinições (voz, telefone, rádio, graves, tirar zumbido 50/60 Hz).
- Compressor, limitador, gate, de-esser, redução de ruído (três níveis: `afftdn` leve,
  `anlmdn` médio, `arnndn` RNNoise para voz), de-click, de-clip.
- Velocidade sem mudar o tom e tom sem mudar a velocidade (`rubberband`), inverter,
  reverb/eco, estéreo↔mono, largura estéreo.
- IA (pela fila): isolar voz, tirar voz (instrumental), separar 4 stems (Demucs).

**Sugestões de corte** (botão "Analisar"; cada sugestão mostra motivo, confiança, prévia
de antes/depois e aceitar/recusar; "aceitar todas desta categoria")
| Sugestão | Como detectar |
|---|---|
| Silêncios longos → encurtar para N ms (não apagar) | RMS com limiar adaptado ao ruído de fundo do próprio arquivo |
| Vícios de linguagem ("é…", "tipo", "né", "hã", "ahn") | palavras do Whisper + lista por idioma; palavras curtas de baixa confiança |
| Frase repetida / tomada refeita → manter a última | similaridade entre trechos da transcrição |
| Respiração alta, estalo de boca, clique | energia em banda + duração curta entre palavras |
| Começo e fim mortos | ruído antes da primeira palavra/nota e depois da última |
| Trecho estourado (clipping) ou com volume muito diferente | pico ≥ −0,1 dBFS; LUFS curto por janela |
| Música: corte no tempo | detecção de batidas (fluxo espectral em numpy) → imã nas batidas/compassos |
| Música: melhor trecho de 15/30/60 s (Reels, TikTok, Status) | refrão = trecho que mais se repete (autossimilaridade de croma) |

**Receitas automáticas** (cada uma é uma lista de passos editável e salvável; dá para
rodar em lote numa pasta de arquivos)
- **Podcast/voz:** reduzir ruído → tirar vícios → encurtar silêncios → EQ de voz →
  compressor → −16 LUFS.
- **Gravação de celular:** tirar zumbido, ruído e eco leve, nivelar volume.
- **Aula/palestra:** encurtar silêncios agressivamente, nivelar, mono, MP3 leve.
- **Audiobook (ACX):** RMS −18 a −23, pico −3 dB, piso de ruído −60 dB, com relatório.
- **Música para Reels:** melhor trecho de 30/60 s com fade, −14 LUFS.
- **Karaokê:** tirar voz e exportar o instrumental.

**Entrada e saída**
- Importa tudo que o FFmpeg lê, inclusive vídeo (extrai o áudio).
- Exporta WAV, FLAC, MP3, OGG, Opus, M4A/AAC (taxa, bits e bitrate), com tags e capa
  embutidas pelo FFmpeg; transcrição em TXT/SRT/VTT; projeto .json.

### 1.4 Arquitetura
- **A lista de edição é a fonte da verdade.** O projeto é um JSON (pistas → clipes com
  arquivo de origem, início na origem, duração, posição, ganho, fades, efeitos). A prévia
  no navegador e o render final leem a mesma lista; o render vira um `filter_complex` do
  FFmpeg no servidor.
- **Arquivo longo não é decodificado inteiro no navegador.** 1 h de WAV estéreo vira
  ~1,3 GB de `AudioBuffer` float32, inviável com 7 GB. O servidor gera, ao importar:
  (a) uma pirâmide de picos (min/max por bloco em várias escalas) para desenhar a onda
  em qualquer zoom, e (b) uma cópia de prévia em Opus/AAC. O navegador toca pela prévia
  e só decodifica em memória o trecho visível quando o zoom chega perto da amostra.
- **Análises em segundo plano** pela fila, com progresso: Whisper e Demucs no lane `ia`
  (um por vez, com teto), análise de silêncio/batidas no lane leve.
- **Modo fila para áudios longos (> 1 h)** (pedido do usuário, 2026-10-12): arquivo
  acima de 1 h (ou vários arquivos) não abre direto no editor; entra numa fila própria
  que processa em blocos de ~10 min com sobreposição (picos, prévia, transcrição,
  análise de sugestões, efeitos e render), um bloco por vez, com teto de memória,
  pausar/retomar/cancelar/reordenar, tempo estimado e retomada do ponto em que parou
  se o Verto fechar. A pessoa pode começar a editar os blocos já prontos enquanto o
  resto processa; as receitas automáticas rodam na fila inteira sem abrir o editor.
- Módulos: `as_projeto.py` (lista de edição, desfazer), `as_picos.py`, `as_analise.py`
  (sugestões), `as_efeitos.py` (efeito → filtro FFmpeg), `as_render.py`,
  `as_receitas.py`; front em `AudioStudio/audiostudio.html` +
  `static/localtools/audiostudio/` (timeline em canvas).

### 1.5 Fases
- **Fase 0:** medir o tempo do faster-whisper `small` em 10 min de voz nesta máquina e a
  memória com a fila; decidir o modelo padrão. Medir pirâmide de picos e prévia em 1 h.
- **Fase 1 (MVP):** modo fila para > 1 h, uma pista, importar, onda com zoom, cortar/apagar/fade com crossfade
  automático, desfazer, ganho/normalizar/loudness, exportar. Sugestões de silêncio e
  começo/fim.
- **Fase 2:** transcrição, vícios, repetições, edição pelo texto, redução de ruído, EQ,
  compressor, receitas Podcast/Celular/Aula.
- **Fase 3:** multipista, envelope, ducking, espectrograma, Demucs, batidas, melhor
  trecho, Reels, Karaokê, lote, Audiobook.
- **Fase 4:** integração com Smart Studio, Subtitle Lab e SunoSaver; modo visual.

### 1.6 Modo visual (proposta)
**"Ilha de edição"**: régua de tempo com marcações de fita, pistas como faixas de
mesa de corte, cursor tipo agulha de leitura; sugestões aparecem como etiquetas de
papel coladas sobre a onda (cor por categoria). Diferente do "no-ar" (Smart Studio) e
da "mesa-de-som" (Isolador).

### 1.7 Decisões
- **Decidido (2026-10-12):** o Áudio Studio substitui o editor do Smart Studio, que
  vira só gravador com o botão "editar no Áudio Studio".
- **Decidido (2026-10-12):** nomes Áudio Studio, Vetorizar 4K e SunoSaver.
- **Decidido pela medição (2026-10-12):** Whisper padrão `base` (3× mais rápido que o `small`).

---

## 2. Vetorizar 4K (app 36)

> **Implementado em 2026-10-12** (app 36 do menu): `Vetorizar/vz_nucleo.py` (análise,
> pixel art, paleta, traçado, render, fidelidade), `Vetorizar/vetorizar_engine.py`
> (projetos em `Vetorizar/dados/`, automático, fundo por IA, exportação),
> `Vetorizar/vetorizar.html`, tema `tema-milimetrado.css`. O que mudou em relação ao plano,
> medido aqui:
> - Grade da pixel art: pela **intensidade** das bordas depois de uma mediana, não pela
>   contagem. Contando, os blocos 8×8 do JPEG puxavam a grade 12 para 4 (mdc com 8).
>   Acerta 5×, 6× com deslocamento (3,5), 7×, 9×, 12× e 16×, em PNG e em JPEG q50–75.
> - Pixel art limpa (PNG): cores exatas, fidelidade 100 e ΔE 0. Suja (JPEG): junta cores a
>   menos de 20 ΔE e funde a "sangria" (cor rara que encosta numa vizinha maior e parecida).
> - Tipo logo × foto: cores que cobrem 95% em caixas de 3 bits depois de um bilateral
>   (logos 4–20, foto 56; corte em 28).
> - Pixel suave: EPX (Scale2x) + arredondamento das manchas na resolução final, em vez do
>   Kopf–Lischinski.
> - O fundo que encosta na borda vira um retângulo exato (o traçado em curvas arredondava
>   os cantos da imagem). O vtracer faz média de cor ao juntar manchinhas: cada forma volta
>   para a cor da paleta (senão saíam 63 tons para uma paleta de 6).
> - Pixels de borda só viram uma cor que existe em área lisa por perto (some o filete
>   branco entre amarelo e azul).
> - Foto "detalhado": paleta de 32 cores (o modo livre do vtracer achatava o rosto).
> - **Não feito:** ampliação por IA (Real-ESRGAN). A ampliação bicúbica + bilateral +
>   paleta já tira o serrilhado dos testes; fica para quando aparecer um caso que precise.

### 2.1 Objetivo
Transformar qualquer imagem (pixel art, logo pequeno e serrilhado, print, desenho
escaneado, foto) em **vetor limpo**, com pré-visualização e entrega em **4K ou mais**.

O que "4K" significa aqui: o vetor não tem resolução (escala infinita). O app entrega
o **vetor** (SVG, PDF, EPS, AI, DXF) e também **renderiza o vetor em PNG** no tamanho
pedido (3840 px, 4096 px, 8K ou personalizado), com fundo transparente opcional.

### 2.2 O que já existe para reaproveitar
| Peça | Onde | Uso |
|---|---|---|
| potrace por máscara, linha central, vetorização por cor, escrita de DXF/EPS | `Conversor/conversor_engine.py` (`_potrace_curves`, `_centerline`, `trace_to_dxf`…) | modo "traço" e exportação DXF |
| Remoção de fundo | rembg (Transparência) | "tirar o fundo antes de vetorizar" |
| Renderização de SVG/PDF | PyMuPDF (já instalado) | PNG 4K/8K do resultado sem dependência nova [a verificar: fidelidade do render de SVG no PyMuPDF; alternativa: `resvg`] |
| Fila com teto | Vetor3D | ampliação por IA e lote |
| Consumidor do resultado | Vetor3D, Conversor | botões "abrir no Vetor3D" (SVG → 3D) |

**Novas dependências**
- `vtracer` (MIT, Rust): vetorização colorida empilhada, muito melhor que potrace por
  cor para ilustração e foto. **Wheel para Python 3.12 existe [verificado 2026-10-12].**
- Ampliação por IA para entradas pequenas: Real-ESRGAN *compact* (`realesr-general-x4v3`,
  ~5 MB, BSD-3) em ONNX Runtime CPU (o onnxruntime já vem com o rembg), por blocos com
  teto de memória. [a verificar: tempo por imagem de 512 px nesta CPU]

### 2.3 Funcionalidades
**Detecção automática do tipo** (a pessoa pode trocar):
| Tipo | Como reconhecer | Caminho |
|---|---|---|
| Pixel art | poucas cores, bordas alinhadas a uma grade regular | detectar o tamanho do "pixel" (corridas de cor/autocorrelação) → reduzir à grade real → modo **Pixel exato** (cada pixel vira quadrado, quadrados da mesma cor viram um polígono só: SVG mínimo e perfeito) ou modo **Pixel suavizado** (contornos curvos no estilo *Depixelizing Pixel Art*, Kopf & Lischinski; implementação própria: grafo de similaridade → contornos → splines) |
| Logo, ícone, ilustração | paleta pequena após limpar ruído de JPEG | limpar (filtro que preserva bordas) → ampliar ×4 se pequeno → quantizar cores em Lab → vtracer (ou potrace por camada) → ajustar cantos e retas |
| Desenho a traço, escaneado | quase P&B | binarizar adaptativo → potrace (contorno) ou linha central do Conversor |
| Foto | muitas cores | vtracer com N cores ("pôster", "ilustração", "detalhado") |

**Editor do resultado**
- Comparar original × vetor com divisória arrastável e zoom até 1600 % para conferir as
  curvas; alternar contorno dos caminhos e nós.
- **Paleta editável:** juntar cores (conta-gotas), trocar cor, apagar cor, limitar a N
  cores, travar cores da marca (hex).
- Controles: suavidade de curva × fidelidade, cantos, remover manchas menores que X,
  simplificar nós, fundo transparente/remover fundo, camadas por cor visíveis ou não.
- **Fidelidade medida:** o app renderiza o vetor de volta e compara com a imagem
  (SSIM/ΔE), mostrando "fidelidade 97 %, 1.240 nós". **Modo automático** testa algumas
  combinações de parâmetros e escolhe a de melhor fidelidade com menos nós.
- Lote: fila de arquivos com a mesma predefinição.

**Exportar:** SVG (otimizado, com `viewBox`), PDF vetorial, EPS, AI (PDF compatível),
DXF (pelo Conversor), PNG/WebP em 4K/8K/tamanho livre, paleta em .txt/.ase.

### 2.4 Arquitetura
- `vz_tipo.py` (detecção), `vz_pixelart.py` (grade + pixel exato + suavizado),
  `vz_limpeza.py` (limpar, quantizar), `vz_ampliar.py` (Real-ESRGAN ONNX por blocos),
  `vz_tracar.py` (vtracer/potrace), `vz_fidelidade.py`, `vz_exportar.py`; front em
  `Vetorizar/vetorizar.html` + `static/localtools/vetorizar/`.
- Prévia rápida em resolução reduzida a cada ajuste; o traço final só ao soltar o
  controle.

### 2.5 Fases
- **Fase 0:** reunir 15 imagens de teste (pixel art 16/32/64 px, logo JPEG pequeno,
  print, escaneado, foto) e comparar potrace × vtracer × vtracer com ampliação; medir
  Real-ESRGAN na CPU. Conferir o render de SVG no PyMuPDF.
- **Fase 1:** logo/ilustração e traço com vtracer/potrace, paleta, comparação, SVG/PDF/PNG 4K.
- **Fase 2:** pixel art (grade + pixel exato), detecção automática, fidelidade e modo
  automático.
- **Fase 3:** pixel suavizado, ampliação por IA, foto, lote, EPS/AI/DXF, integração com
  Vetor3D.

### 2.6 Modo visual (proposta)
**"Prancheta de plotter"**: base de corte verde com grade milimetrada, o vetor desenhado
com as alças dos nós visíveis como numa mesa de vinil, régua lateral em px/mm.

---

## 3. SunoSaver (app 37)

> **Implementado em 2026-10-12** (virou o app 35 do menu): `SunoSaver/sunosaver_engine.py`,
> `SunoSaver/sunosaver_letra.py`, `SunoSaver/sunosaver.html`, tema `tema-disco.css`.
> Fases 1, 2 e 3 prontas e testadas (link de compartilhamento, música, playlist, perfil,
> lote, ZIP, M4A/MP3/WAV/FLAC/MP4/capa/letra/JSON, LRC/SRT/VTT). Fase 4 (login) **não**
> foi feita, por decisão do usuário: tudo sem login. Hook: implementado sem teste real
> (não achei um link de hook público). Diferenças em relação ao plano abaixo, medidas aqui:
> - `GET /api/clip/<id>` (sem login) é o endpoint de uma música; playlist em
>   `/api/playlist/<id>/?page=N`; perfil em `/api/profiles/<handle>?page=N&clips_sort_by=created_at&playlists_sort_by=created_at`
>   (sem `playlists_sort_by` dá 422). `suno.com/s/<código>` responde 307 para `/song/<id>?sh=<código>`.
> - Letra no MP3: o FFmpeg 6 grava "lyrics" como TXXX (nenhum player lê); o motor escreve o
>   quadro ID3 `USLT` direto. No M4A sai `©lyr` e no FLAC `LYRICS` pelo próprio FFmpeg.
> - Letra sincronizada: o filtro de voz (VAD) da transcrição de vídeos jogava fora o canto
>   suave (26 % de cobertura numa música); sem VAD e com a letra como contexto: 92 a 95 %.
>   Por isso o modo **rápido** (sem Demucs, ~1 min) é o padrão. O **preciso** roda o Demucs
>   em pedaços de 45 s num processo só: a música inteira passa de 1,7 GB; em pedaços, pico
>   de ~1,5 GB e 4 a 5 min. Linhas de crédito antes do primeiro `[Verse]` ficam de fora.

### 3.1 Objetivo
Releitura do downloader do usesuno: colar o link de uma música do Suno e baixar áudio,
vídeo, capa, letra e metadados; ir além com **letra sincronizada gerada localmente** e
envio direto para o Áudio Studio e o Subtitle Lab.

### 3.2 Como o Suno entrega os arquivos hoje [verificado 2026-10-12]
Testado com músicas públicas do "Trending" pela API pública
(`POST studio-api.prod.suno.com/api/discover/`):
| Item | Situação sem login |
|---|---|
| `audio_url` | vem como `…/api/forbidden` |
| `cdn1.suno.ai/<id>.mp3` e `.wav` | **403** (o caminho que os downloaders antigos usavam fechou) |
| `media_urls` (`…cloudfront.net/1/clip/<id>.m4a`, `content_type: m4a-opus`, `encoding: 1.0.0`) | baixa, mas **cifrado** (não é M4A válido); é o que o usesuno "descriptografa" |
| `video_url` (`cdn1.suno.ai/<id>.mp4`) | **aberto**: H.264 + **AAC estéreo 48 kHz, ~194 kbps**; 35 de 35 músicas testadas tinham |
| `image_large_url` (JPEG) | aberto |
| Letra (`metadata.prompt`), estilo (`metadata.tags`), título, autor, duração, modelo | abertos no JSON |
| Stems | `has_stem: false` em todas as testadas |
| Letra sincronizada (`/api/gen/<id>/aligned_lyrics/v2/`) | relatos de que passou a exigir login [a verificar] |

**Decisão de projeto: não quebrar a cifra do áudio.** Contornar a proteção que o Suno
colocou é burlar uma medida técnica dele (o tipo de coisa que tira o app de qualquer
caminho de produto, ver triagem ⛔1 de `APPS-PROPRIOS.md`) e quebra a cada mudança da
chave. Em vez disso, o áudio sai do **MP4 público**, que o próprio Suno publica aberto:
`ffmpeg -i video.mp4 -vn -c:a copy musica.m4a` dá o AAC de ~194 kbps **sem perda
nenhuma** em relação ao que foi publicado.

### 3.3 Funcionalidades
**Fase 1, música pública por link** (`suno.com/song/…`, `suno.com/s/…`, `suno.com/hook/…`)
- Cartão da música: capa, título, autor, estilo, duração, letra, player de prévia.
- Baixar: **áudio original** (.m4a, cópia sem recodificar, recomendado), MP3 (320 kbps
  VBR, recodificado, avisando), WAV/FLAC (para editar; avisando que não ganha qualidade),
  **MP4**, capa JPEG (original e quadrados 1000/3000 px), letra .txt, metadados .json.
- Tags e capa embutidas no MP3/M4A pelo FFmpeg (título, artista = autor no Suno,
  estilo como gênero, letra no campo de letra, link de origem no comentário).
- "Baixar tudo" em ZIP, com nome de pasta `Autor - Título`.
- Abrir direto no **Áudio Studio** e no **Isolador de Voz**.

**Fase 2, letra sincronizada sem login (local)**
- Temos a letra exata (`metadata.prompt`); falta só o tempo. Pipeline: Demucs isola a voz
  (melhora muito o reconhecimento em música) → faster-whisper com marcação por palavra →
  **alinhar as palavras reconhecidas à letra conhecida** (alinhamento de sequências;
  partes como `[Chorus]` e `[Verse]` viram marcadores) → exportar **LRC** (linha e
  palavra a palavra), **SRT** e **VTT**; abrir no Subtitle Lab para ajuste fino ou para
  queimar no vídeo.
- Roda pela fila `ia` (Demucs + Whisper juntos passam do que cabe com folga em 7 GB se
  rodarem ao mesmo tempo: um depois do outro, com teto).

**Fase 3, em lote**
- Vários links colados de uma vez; playlist e perfil público (`suno.com/playlist/…`,
  `suno.com/@handle`) [a verificar: endpoints públicos de playlist e perfil e paginação].
- Fila com progresso, pular repetidos (id), salvar em
  `Documentos/Suno/<Autor>/` e, opcional, uma regra nova no Automações.

**Fase 4, a conta da própria pessoa (opcional)** [a verificar inteira; precisa de uma
conta para testar]
- A pessoa cola o token da sessão dela (guardado em `SunoSaver/dados/`, fora do git,
  nunca devolvido ao front, como as contas do Social Preview).
- Com login, o `audio_url` das **músicas dela** volta a ser o MP3 do Suno; WAV oficial e
  stems quando o plano dela tiver; letra sincronizada oficial; músicas privadas dela;
  baixar a biblioteca inteira.

### 3.4 Arquitetura
- `ss_link.py` (normalizar link → id; `suno.com/s/…` segue o redirecionamento),
  `ss_suno.py` (busca do JSON do clipe; isolar aqui tudo que depende do Suno, porque é o
  que vai quebrar), `ss_baixar.py` (MP4 → áudio, capa, tags, ZIP), `ss_letra.py`
  (alinhamento → LRC/SRT/VTT), `ss_lote.py`; front em `SunoSaver/sunosaver.html`.
- User-Agent de navegador, intervalo entre pedidos no lote, nada de paralelismo agressivo.
- Mensagens claras quando algo muda no Suno: "o Suno mudou o formato; o vídeo/a capa
  ainda funcionam" em vez de erro genérico.

### 3.5 Fase 0
- Achar o endpoint público que devolve **um clipe por id** (a página `suno.com/song/<id>`
  e o JSON embutido nela; ou a API de clipe) e confirmar que traz `video_url` e
  `metadata.prompt` sem login. O `discover` já confirmou os campos.
- Testar uma música **sem vídeo** (se existir) para definir a mensagem nesse caso.
- Testar o alinhamento de letra em 3 músicas (pt, en, instrumental com voz curta).

### 3.6 Modo visual (proposta)
**"Disco"**: a capa vira o selo de um vinil que gira só ao tocar a prévia, letra em
encarte de papel ao lado, botões de formato como etiquetas de lado A/B. Grupo downloads
(verde), irmão visual de InstaSaver/VscoSaver.

### 3.7 Uso e limites
- Para uso pessoal, como os outros downloaders: as músicas são dos autores, e os termos
  do Suno definem o que cada plano pode fazer com elas. O app mostra autor e link de
  origem em todo arquivo e não oferece "remover autoria".
- Pela triagem de `APPS-PROPRIOS.md`, o SunoSaver **não** vira produto vendido (⛔1);
  o Áudio Studio e o Vetorizar 4K são bons candidatos.

---

## 4. Riscos principais
| Risco | App | Mitigação |
|---|---|---|
| Faltar memória e travar o PC | Áudio Studio, Vetorizar | fila com teto (Vetor3D), prévias leves, picos no servidor |
| Suno mudar a API ou fechar o MP4 | SunoSaver | tudo do Suno isolado em `ss_suno.py`; mensagens claras; fase 4 com login como plano B |
| Whisper lento em arquivo longo | Áudio Studio, SunoSaver | medir na fase 0; modelo `base` como opção rápida; análise em segundo plano |
| Pixel suavizado ficar abaixo do esperado | Vetorizar | entregar "pixel exato" primeiro (sempre perfeito); suavizado só na fase 3 |
| Escopo do Áudio Studio crescer sem fim | Áudio Studio | fases fechadas; MVP de uma pista entregue antes de multipista |
