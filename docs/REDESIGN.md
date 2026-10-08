# Redesign LocalTools — estado e próximos passos

Leia isto antes de continuar o redesign. Marca: **LocalTools** (título); projeto: **Verto**.

## Regras que o usuário já definiu
- Menu inicial (`MENU_HTML` em `app.py`): **não mexer** no topo (título LOCALTOOLS 3D, relógio grande com dígitos que rolam, barra de segundos, data, frase com bolinha verde dos dois lados, busca, legenda de grupos). Sem o "V" no menu.
- `<title>` do menu deve continuar **"Menu de Apps"** (o atalho `~/.local/bin/verto-toggle.sh` acha a aba por ele).
- Ícones: **peças 3D próprias** (`static/localtools/apps/<id>.webp`), geradas por `scripts/icones_3d.py`. Nada de emoji, néon, ícones prontos de pacote ou fundo branco.
- Cor = grupo do app (tokens `--lt-cat-*` em `static/localtools/base.css`).
- Nunca deixar servidor rodando: testar na porta 5055 e encerrar (o usuário usa a 5000 via `executaveis/INICIAR.py`).
- **Social Preview no teste**: `/social/contas*` e `/social/publicar` chamam as APIs reais das redes com as contas salvas em `SocialPreview/dados/contas.json`. Para testar a publicação, apontar o conector para uma API falsa (ex.: trocar `publicador.GRAPH_IG`) e usar uma pasta de dados temporária (`publicador.CONTAS_PATH`).
- **WhatsSaver no teste**: as chamadas `/whatssaver/*` ligam a ponte do WhatsApp (`node bridge.mjs`) com a sessão real em `WhatsSaver/dados/auth`. Só abrir a página com **todas** as `/whatssaver/*` interceptadas no Playwright (`page.route`, como faz o `foto.py`); a rota `/whatssaver` sozinha só desenha o HTML. O mesmo para `/encurtador/*` (token real da Cloudflare).
- Sem commit, a não ser que o usuário peça.

## Identidade de cada app (pedido do usuário, 2026-10-05) — feito
- **Não padronizar tudo.** O comum é só a base: fundo grafite (`lt-body`), fonte Geist, `lt-back`, marca `LOCALTOOLS` (sem o V) e o ícone 3D do app no topo.
- Cada app tem um **modo visual próprio** ligado ao que ele faz (metáfora, material, detalhe-assinatura), sem néon. Os 34 já têm (coluna "Modo" abaixo).

## Onde ficam os modos
- `static/localtools/modos/<modo>.css`: um arquivo por modo. Todo seletor começa com `body.modo-X` (ou `body.tema-X`), porque a classe fica no próprio `<body>` e precisa vencer a base `body[class*="modo-"]` do `app.css` (especificidade 0,2,1).
- **`modo-X`** (23 modos, 53 páginas): páginas migradas por `scripts/visual_modos.py`. Recebem também a base neutra do `app.css` (`body[class*="modo-"] .card`, campos, `.tools-grid`, `.btn-secondary`…). O botão principal de cada modo cobre `.btn-primary`, `button[type=submit]`, `.action-btn`, `.process-btn` e `button.action` (menos `.btn-danger`, `.btn-secondary`, `.btn-flag`).
- **`tema-X`** (9 páginas feitas à mão sobre os componentes `lt-*`): só somam o CSS do tema no fim do `<head>`; "tema-" de propósito não casa com `body[class*="modo-"]`, para a base neutra não mexer nos `.card` e campos delas.
- PDFs: modo papel em `static/localtools/pdfs-papel.css` (classe `pdf-papel`) e o hub em `PDFS_HTML`.

## Scripts (`venv/bin/python scripts/visual_modos.py …`)
- sem opção: migra as páginas da lista `P` (idempotente: pula quem já tem `lt-body`).
- `--cores`: troca os destaques antigos pela cor de cada modo (mapa `RECOR`).
- `--emojis [modo…]`: tira emoji do começo de textos da marcação e de strings do JS; elemento que era só um emoji vira ícone de traço (`ICONE_EMOJI` → `static/localtools/traco/`). Mantém setas, ✓/✕ e strings que são só o emoji (ex.: o estilo "emoji" do Censor). Idempotente; vale para `P`, `TEMAS` e `PDFS`. **Revisar o diff**: emoji que carrega informação (♥ curtidas, 👥 grupo, ⏸ legenda da timeline) tem de voltar.
- `--temas`: aplica `tema-X` nas 9 páginas de `TEMAS`.
- Ícones de traço novos: Phosphor *light* em `https://unpkg.com/@phosphor-icons/core@2.1.1/assets/light/<nome>-light.svg`, salvos com `fill="currentColor"` e sem o `<rect>` de fundo.

## Os 34 apps
"Fonte" = onde está o HTML. "Modo" = arquivo em `static/localtools/modos/` (`tema …` = `tema-<nome>.css`).

| # | App | Rota | Grupo (cor) | Ícone 3D (`apps/`) | Fonte | Modo |
|---|-----|------|-------------|--------------------|-------|--------|
| 1 | Verto (YouTube) | `/verto` | downloads (verde) | verto | `VERTO_HTML` em `app.py` | ✅ tema player |
| 2 | InstaSaver | `/instasaver` | downloads | instasaver | `InstaSaver/instasaver.html` + `static/localtools/instasaver/vitrine.js` (layout de app em 3 colunas: perfil · celular 3D realista mostrando a mídia escolhida com a interface do Instagram, vídeos tocando · grade estilo perfil; clique escolhe, duplo clique abre o visualizador; a página emite `insta:*` e expõe `window.InstaSaver`; sem WebGL volta ao layout clássico) | ✅ tema stories |
| 3 | VscoSaver | `/vscosaver` | downloads | vscosaver | `VscoSaver/vscosaver.html` | ✅ tema filme |
| 4 | WhatsSaver | `/whatssaver` | downloads | whatssaver | `WhatsSaver/whatssaver.html` | ✅ tema conversa |
| 5 | Automações | `/automacoes` (mini menu) + `/automacoes/organizador` | downloads | automacoes | `Automacoes/automacoes.html` (mini menu) e `Automacoes/organizador.html` | ✅ tema fluxo |
| 6 | PurpleFlix | `/purpleflix` | downloads | purpleflix | `PURPLEFLIX_HTML` em `app.py` + `static/localtools/purpleflix/sala.js` (sala de cinema 3D: Three.js + CSS3DRenderer com o site real na tela, GSAP na câmera; bibliotecas em `static/localtools/vendor/`) | ✅ cinema |
| 7 | Efeitos | `/efeitos` | imagem (rosa) | efeitos | `Efeitos/efeitos.html` | ✅ tema laboratorio |
| 8 | Editor de Vídeo | `/automacoes/editor` (entra pelo mini menu de Automações) | imagem | editor | `Automacoes/editor.html` | ✅ tema timeline |
| 9 | Image Studio | `/imagestudio` (+ /solo, /resize, /filters, /favicon) | imagem | imagestudio | `ImageStudio/` (hub + páginas) | ✅ mesa-de-luz |
| 10 | Transparência | `/transparent` | imagem | transparent | HTML embutido em `app.py` | ✅ recorte |
| 11 | Matcha Effect | `/matchaeffect` (+ subpáginas) | imagem | matchaeffect | `MatchaEffect/` | ✅ matcha |
| 12 | Capture & OCR | `/captureocr` | imagem | captureocr | `CaptureOCR/` (hub) | ✅ visor |
| 13 | Social Preview | `/social` (+ `/social/*` API) | imagem | social | `templates/social.html` + `static/localtools/social/` (estudio.js/css, marcas.js); backend em `SocialPreview/` (redes.py = catálogo de formatos e limites; publicador.py = contas e publicação pelas APIs oficiais; hospedagem.py = endereço público temporário para Instagram/Threads; midia.py = recorte, preenchimento e vídeo com música no ffmpeg + foco automático com o YuNet do Efeitos). Enquadramento por rede (chave `rede:formato:proporção`), automático na primeira foto e editável no diálogo "Editar". Credenciais em `SocialPreview/dados/` (fora do git). Vai virar um app separado do Verto: manter o SocialPreview/ sem depender de outras partes do app.py | ✅ feed |
| 14 | Transcrever | `/transcribe` | audio (amarelo) | transcribe | HTML embutido em `app.py` | ✅ fita |
| 15 | Isolador de Voz | `/isolate` | audio | isolate | HTML embutido em `app.py` | ✅ mesa-de-som |
| 16 | Smart Studio | `/smartstudio` (+ editor/studio) | audio | smartstudio | `SmartStudio/` | ✅ no-ar |
| 17 | Subtitle Lab | `/subtitlelab` (+ editor/burn) | audio | subtitlelab | `SubtitleLab/` | ✅ legenda |
| 18 | PDFs | `/pdfs` (+ ferramentas) | documentos (coral) | pdfs | `PDFS_HTML` + 12 ferramentas (`PDFs/`, `PDFS_MERGE_HTML`) | ✅ papel (`pdfs-papel.css`) |
| 19 | Office | `/office` | documentos | office | `Office/` (hub) | ✅ pastas |
| 20 | Arquivos | `/files` | conversao (azul) | files | HTML embutido em `app.py` | ✅ fichario |
| 21 | Conversor | `/conversor` | conversao | conversor | `Conversor/conversor.html` | ✅ tema planta |
| 22 | Compressor | `/compress` | conversao | compress | HTML embutido em `app.py` | ✅ prensa |
| 23 | Ghost Tool | `/ghost` | privacidade (lilás) | ghost | `GHOST_HTML` em `app.py` | ✅ nevoa |
| 24 | Stealth | `/stealth` | privacidade | stealth | `STEALTH_HTML` em `app.py` | ✅ esteganografia |
| 25 | Censor | `/censor` | privacidade | censor | HTML embutido em `app.py` | ✅ tarja |
| 26 | Text Clean & Diff | `/textclean` | texto (turquesa) | textclean | `TextClean/` (hub) | ✅ diff |
| 27 | AI Guard & Diff | `/aiguard` | texto | aiguard | `AIGuard/` (hub) | ✅ analise |
| 28 | Clean Reader | `/clean` | texto | clean | `templates/clean.html` (leitor: tons sépia/papel/noite, tamanho da letra, modo foco) | ✅ leitura |
| 29 | Dev/Data | `/devdata` | dev (laranja) | devdata | `DevData/` (hub) | ✅ terminal |
| 30 | QR Code | `/qrcode` | dev | qrcode | HTML embutido em `app.py` | ✅ modulos |
| 31 | Encurtador | `/encurtador` | dev | encurtador | `Encurtador/encurtador.html` | ✅ bilhete |
| 32 | Tempo | `/tempo` | dev | tempo | HTML embutido em `app.py` | ✅ calendario |
| 33 | Instruções | `/instructions` | ajuda (cinza) | instructions | `templates/instructions.html` | ✅ tema manual |
| 34 | Vetor3D | `/vetor3d` | conversao | vetor3d (cube) | `Vetor3D/vetor3d.html` (viewer em `static/localtools/vetor3d/`) | ✅ tema maquete (base de corte quadriculada, folhas de papel-cartão empilhadas, título em camadas de extrusão) |

"HTML embutido em `app.py`": procurar a rota com `grep -n '@app.route("/<rota>"' app.py` e seguir até a constante/`render_template_string`. Apps com várias páginas (hub + ferramentas) precisam de todas as páginas migradas.

## Ideias de animação e 3D para os outros apps (viabilidade, 2026-10-06)
Regra: em ferramenta de uso diário, o movimento fica na entrada, no estado vazio e no momento do resultado. Nada de loop durante o trabalho; sempre com `prefers-reduced-motion` e pausando quando a aba some. Three.js e GSAP já estão em `static/localtools/vendor/` (só carregam na página que usa).

| Esforço | App | Ideia |
|---|---|---|
| CSS 3D | Tempo | Relógio de virar plaquinhas (flip clock) nos contadores |
| CSS 3D | Encurtador | Ingresso que inclina com o mouse e destaca o canhoto ao criar o link |
| CSS 3D | PDFs / Office | Folhas e pastas que abrem em 3D no hover; folha "saindo da impressora" no resultado |
| CSS 3D | Instruções | Virar página de livro entre categorias |
| SVG/canvas com dado real (meio dia) | Transcrever | Fita cassete com os carretéis girando no ritmo do progresso real |
| SVG/canvas | Compressor | Prensa descendo sobre o arquivo, com o tamanho antes/depois |
| SVG/canvas | Smart Studio / Isolador | Medidores VU e faders reagindo ao áudio de verdade (Web Audio) |
| SVG/canvas | Dev/Data | Brilho de tubo CRT e linhas de varredura no terminal |
| Three.js (1–2 dias) | QR Code | O código se montando a partir de cubos 3D quando é gerado |
| Three.js | Matcha Effect | Tigela de matcha com o líquido em shader "fluid art" no hub |
| Three.js | Stealth | Imagem "raio-X" revelando os bits escondidos em partículas |
| Three.js | VscoSaver | Cópias de foto caindo sobre a mesa ao carregar a galeria |


- Efeitos: os emojis de cada efeito (`fx-img`) continuam como marcador enquanto a miniatura real não carrega; vêm de `Efeitos/efeitos_engine.py`.
- Instruções: os ícones das funções continuam emoji nos dados (o tema manual mostra números 01, 02… no lugar).
- Arquivos (`/files`): os formatos que esta máquina não converte ficam apagados de propósito (acendem pelo `/formats`).
- CSS antigo sem uso (`.logo`, `.tagline`, `.back-button`) ficou nas páginas migradas: pode limpar.
- App novo: adicionar em `APPS` de `scripts/icones_3d.py` (símbolo + grupo) e rodar `venv/bin/python scripts/icones_3d.py <id>` (precisa `pip install playwright` para rasterizar o SVG); depois dar a ele um modo próprio em `static/localtools/modos/`.
