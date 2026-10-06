# Verto: Multi-purpose Media & Security Processing Suite

> Processamento 100% local. Dados sensíveis nunca saem da máquina do usuário.

Suíte de 27 ferramentas integradas cobrindo IA, criptografia, manipulação de binários e automação de mídia. Arquitetura local-first por design — não por limitação.

---

## Por que local-first?

Ferramentas que lidam com **esteganografia, remoção de metadados e separação de áudio com IA** não devem depender de servidores externos. Cada operação acontece inteiramente na máquina do usuário:

- Nenhum arquivo é transmitido para terceiros
- Nenhuma API key necessária
- Funciona offline após instalação
- Cleanup automático de arquivos temporários em todos os fluxos

---

## Stack Técnico

| Camada                      | Tecnologia                                    |
| --------------------------- | --------------------------------------------- |
| Backend                     | Python 3 + Flask                              |
| IA — Separação de Áudio | Demucs (Meta Research) via subprocess isolado |
| IA — Remoção de Fundo    | rembg + ONNX Runtime (CPU)                    |
| IA — Transcrição         | faster-whisper (Editor de Vídeo, palavra por palavra) · Google Speech (Transcrever, Subtitle Lab) |
| Criptografia                | AES-256 (esteganografia)                      |
| Download de Mídia          | yt-dlp                                        |
| Manipulação de PDF        | PyPDF2 + img2pdf                              |
| Office (Word/Excel/PPT)     | LibreOffice headless + python-docx/pptx/openpyxl |
| Vetorização / CAD           | potrace (potracer) + scikit-image + ezdxf     |
| Detecção de Objetos       | YOLOv8 (Censor)                               |
| Detecção de Rostos        | YuNet via OpenCV (Efeitos)                    |
| Web Scraping                | BeautifulSoup4 + requests                     |
| Frontend                    | HTML/CSS/JS puro (zero frameworks)            |

---

## Apps da Suíte

| App                         | Categoria      | Detalhe Técnico                                                   |
| --------------------------- | -------------- | ------------------------------------------------------------------ |
| 🎬**Verto**           | Mídia         | Download MP4/MP3/Thumbnail com estimativa de tamanho em tempo real |
| 🕵️**Stealth**       | Security       | Esteganografia LSB com criptografia AES-256 — anti-forensics      |
| 👻**Ghost Tool**      | Anti-forensics | Remoção de metadados EXIF/ID3/XMP em 150+ formatos               |
| 🔒**Censor**          | Privacy AI     | Detecção e censura de 9 tipos de dados sensíveis com YOLOv8     |
| 🎤**Isolador de Voz** | AI Audio       | Separação vocal/instrumental com Demucs (htdemucs model)         |
| 🎨**Transparência**  | AI Vision      | Remoção de fundo com rembg + ONNX Runtime                        |
| 🎤**Transcrever**     | AI NLP         | Áudio para texto com Whisper                                      |
| 📁**Arquivos**        | Conversão     | Conversor universal 150+ formatos                                  |
| 🪄**Efeitos**         | Mídia         | 43 efeitos em fotos e vídeos: clássicos (Sépia, P&B, Vintage, Glitch, Pop Art...), engraçados com detecção de rosto (Thug Life, Olhos de Desenho, Nariz de Palhaço, Cabeção), deformações, câmeras (VHS, CCTV, Visão Noturna, Matrix) e estilos (Quadrinhos, Lápis, Neon...); o arquivo sai no mesmo formato, como `foto (Sépia).jpg` |
| 🔁**Conversor**       | Conversão / CAD | Estilo Convertio: fila de arquivos, 1.700+ rotas diretas, imagem → DXF com potrace (contorno, linha central ou por cor) e PDF/SVG/AI/EPS → DXF sem rasterizar |
| 📄**PDFs**            | Documentos     | Dividir, comprimir, girar, converter, mesclar                      |
| 🗃️**Office**          | Documentos     | Converte e repara Word/Excel/PowerPoint — recuperação em 5 níveis, incluindo extensão trocada |
| 🔲**QR Code**         | Utilitário    | Gerador estático (URLs, Wi-Fi, vCard, PIX) sem rastreamento       |
| 🔗**Encurtador**      | Utilitário    | Links curtos GBM (`gbm.pages.dev/x7k2pq`, `gbmlinks.pages.dev/x7k2pq` ou `gbm.gbm.workers.dev/x7k2pq`) que funcionam no mundo todo com o PC desligado: Cloudflare Pages + Workers + D1 na conta grátis do usuário, estatísticas sem IP, validade, senha, QR e UTM |
| 🗜️**Compressor**    | Utilitário    | Redução de tamanho com controle de qualidade                     |
| 📱**Social Preview**  | Design         | Simulação de posts em 24 formatos Mobile/Desktop/Tablet          |
| 🧹**Clean Reader**    | Produtividade  | Extração de conteúdo + modo leitura                             |
| 🎮**PurpleFlix**      | Streaming      | Player integrado                                                   |
| ⏰**Tempo**           | Utilitário    | Relógio + calendário com feriados brasileiros                    |
| 🧰**Dev/Data**        | Desenvolvimento | Beautifier/minifier, gerador de dados mock, conversor JSON/CSV/YAML/XML e encode/decode — tudo no navegador |
| 🖌️**Image Studio**   | Mídia         | Editor individual (corte manual com arrasto, antes/depois, sem ZIP), crop & resize em massa, filtros/marca d'água em lote e gerador de favicon via Canvas |
| 🔀**Text Clean & Diff** | Produtividade | Diff lado a lado/inline, sanitizador de texto (dedupe, ordenação, case) e contador estatístico |
| 🔍**Capture & OCR**   | Captura        | OCR local via Tesseract.js e gravador de tela com exportação em WEBM/GIF |
| 🛡️**AI Guard & Diff** | IA (heurística) | Detector heurístico de conteúdo de IA (sem limite de tamanho, upload de TXT/PDF/DOCX), reescritor com tom e diff, e verificador de plágio interno |
| 🗂️**Automações**     | Automação      | Organizador do InstaSaver: a cada download, leva o que o InstaSaver/VscoSaver baixaram para `Documentos/Instagram/<Perfil>/<Stories\|Destaques\|Posts\|Reels\|VSCO>`, abrindo ZIPs com segurança, sem duplicar (SHA-256) e com nomes de pasta editáveis em `perfis.txt` |
| ✂️**Editor de Vídeo** | AI Video     | Transcrição palavra por palavra (faster-whisper), corte de pausas e retomadas, legenda animada em .ass, enquadramento pelo rosto (YuNet) em 9:16/4:5/1:1/16:9, zoom alternado e áudio em -14 LUFS, numa única codificação |
| 📖**Instruções**    | Docs           | Documentação inline de todos os apps                             |

---

## Destaques de Implementação

**Isolador de Voz (Demucs)**

- Execução via `subprocess.Popen` com `communicate()` — bloqueante sem timeout
- Variável `TORCHAUDIO_BACKEND=soundfile` injetada no ambiente do subprocess
- Diretórios temporários com timestamp para evitar race conditions
- Cleanup garantido em todos os caminhos de exceção via `try/finally`

**Stealth (Esteganografia)**

- Payload cifrado com AES-256 antes da inserção nos bits LSB
- Suporta imagens PNG/BMP como carrier
- Extração requer chave correta — sem chave, arquivo parece imagem normal

**Office (Conversão e Reparo)**

- Conversão via LibreOffice headless (`soffice --convert-to`) — o mesmo motor de renderização do LibreOffice desenha o texto, então acentuação e fontes nunca quebram
- Exportação para imagem (ex: PPTX → PNG) faz um passo intermediário por PDF e rasteriza cada página com PyMuPDF, evitando redesenhar texto manualmente
- Reparo em cascata de 5 níveis: detecção do formato real pelo conteúdo (corrige extensão trocada, ex: um `.xlsx` que na verdade é um `.docx`), reconstrução tolerante do contêiner ZIP, validação com biblioteca nativa, reparo via LibreOffice e, por último, recuperação bruta de texto
- Cada chamada ao LibreOffice roda em um perfil de usuário isolado (`-env:UserInstallation`) com timeout, evitando travamentos por lock entre conversões

**Conversor (Imagem → DXF e conversão universal)**

- Cada conversão é uma rota "entrada → saída" resolvida por um motor local: Pillow, potrace, ezdxf, PyMuPDF, Ghostscript, LibreOffice, FFmpeg, 7-Zip, fontTools e trimesh. Rotas que dependem de ferramenta ausente somem da interface em vez de falhar
- Imagem → DXF/SVG/EPS com o algoritmo potrace (o mesmo dos conversores online), em 3 modos: contorno preenchido, linha central (esqueleto do traço, com poda de "esporões" nos cruzamentos, para CNC/laser/plotter) e colorido (camada por cor; a paleta sai só de regiões lisas e visíveis, então bordas antisserrilhadas e fundo transparente não viram camadas falsas)
- DXF em mm pelo DPI da imagem (ou largura informada), polilinhas ou splines, hachura opcional e versões R12–R2018. Validado rasterizando o DXF de volta: IoU de 0,988 com a imagem original
- PDF, SVG, AI, EPS, CorelDRAW e Visio → DXF extraindo os vetores reais (linhas, Béziers, cores e textos) em vez de rasterizar
- DWG é formato fechado: é suportado automaticamente se o ODA File Converter ou o LibreDWG estiverem instalados

**Efeitos (fotos e vídeos)**

- Cada efeito é uma função numpy sobre um quadro RGB(A): prévia, foto, GIF animado e vídeo usam o mesmo código, então a prévia mostra exatamente o resultado final
- A saída mantém o formato do original (lido pelo conteúdo, não pela extensão), EXIF, perfil de cor, DPI, transparência e animação; o nome ganha o efeito entre parênteses (`praia (Vintage + Vinheta).jpg`) e nunca sobrescreve nada
- Combinações são aplicadas por camada (composição → cor → tom → filme → lente → textura), não na ordem do clique, para um efeito não apagar o outro; P&B vira a base dos tons e Sépia/Ciano/Duotone juntos se dividem entre sombras e luzes (split toning) pela distribuição de luz da própria imagem
- Efeitos de rosto com o detector YuNet do OpenCV (`FaceDetectorYN`, modelo ONNX de 230 KB, licença MIT, incluído em `Efeitos/modelos/`): caixa do rosto + olhos, nariz e boca, detectados a cada quadro para acompanhar o rosto no vídeo
- Efeitos animados no vídeo usam o tempo de cada quadro: óculos do Thug Life descendo, pupilas balançando, derretimento progressivo, relógio do VHS/CCTV contando
- Fotos acima de 8 MP são processadas em faixas horizontais com coordenadas globais (vinheta e grão sem emendas): uma foto de 45 MP usa ~1 GB de RAM em vez de mais de 3,5 GB
- Vídeos: FFmpeg decodifica em quadros crus a taxa constante, os quadros passam pelo efeito em paralelo (limitado pela RAM livre) e voltam no mesmo contêiner, com o áudio original copiado sem recodificar

**Encurtador (links curtos globais)**

- Exceção consciente ao local-first: um link curto só serve se abrir para qualquer pessoa com o PC desligado. Por isso o redirecionamento roda na Cloudflare Pages (plano grátis: 100 mil acessos/dia; D1: 100 mil gravações/dia) e o Verto só administra pela API da Cloudflare
- Na conexão, o Verto cria o banco D1, aplica o schema e publica `cloudflare/worker.js` como `_worker.js` de um projeto Cloudflare Pages, tudo pela API, sem wrangler nem Node. O envio é idêntico ao do `wrangler pages deploy` (conferido campo a campo)
- Endereço de uma parte só (`<projeto>.pages.dev`), coisa que o workers.dev não permite (lá é sempre `<worker>.<conta>.workers.dev`)
- Até três endereços redundantes, ligados ao mesmo banco (todo link abre em todos). Na ordem de preferência: `gbm.pages.dev`, `gbmlinks.pages.dev` e o reserva no Workers, `gbm.gbm.workers.dev` (ou `gbm.gbmlinks.workers.dev`, se o subdomínio `gbm` tiver dono). O principal é o primeiro da lista que está no ar
- O subdomínio workers.dev é um só por conta: o Verto só o cria ou troca se a conta não tiver outros Workers (senão usaria `gbm.<subdomínio-atual>.workers.dev`, para não quebrar nada), e depois de escolhido nunca o troca, para não quebrar links já enviados. Um Worker "gbm" de outro uso nunca é sobrescrito
- O envio do Worker é o mesmo do `wrangler deploy` (metadata, ligação D1 e a chamada que liga o workers.dev, conferidos campo a campo)
- Falta de permissão para um tipo (Pages ou Workers) não impede o outro
- Nome ocupado: o DNS dá a pista (nome sem dono não resolve) e a Cloudflare dá a palavra final. Se ela devolver um endereço com sufixo aleatório, o projeto é apagado (ou fica pendente e é apagado na próxima verificação). Projetos do usuário com o mesmo nome e outro uso nunca são tocados: só conta como do encurtador o projeto ligado ao banco dele
- Saúde a cada 5 minutos com o app aberto: publica a versão nova do `worker.js` onde estiver desatualizada, tenta de novo a cada 6 h reservar o endereço que estava ocupado, recria e republica um endereço apagado ou fora do ar (só quando o outro responde, para não confundir com falta de internet, e respeitando 15 min de propagação) e, se o principal cair, os links novos passam a usar o reserva
- Chamadas à API repetem sozinhas em 429, 5xx e quedas de conexão, mas só quando repetir é seguro: criar link nunca é repetido às cegas, para não duplicar. A publicação é acompanhada até a Cloudflare confirmar, e uma falha num endereço não impede o outro
- No `worker.js`, uma falha do banco ganha uma segunda tentativa e, se persistir, quem clicou vê uma página "volte em instantes" (503 com Retry-After), nunca o erro genérico da Cloudflare
- Código de 6 caracteres de um alfabeto de 31 sem letras ambíguas (887 milhões de combinações), gerado com `secrets` e com `INSERT OR IGNORE ... RETURNING` para resolver colisões sem corrida
- Redirecionamento 302 com `no-store` por padrão: trocar o destino vale na hora e todo clique é contado
- O clique é gravado em `ctx.waitUntil`, sem atrasar o redirecionamento. Robôs de prévia (WhatsApp, Telegram, Facebook...) são marcados e não contam. Visitantes únicos saem de um hash diário de IP+navegador com sal secreto, e o IP nunca é guardado
- Senha com PBKDF2-SHA256, verificada no Worker via WebCrypto, com limite de 5 tentativas a cada 15 minutos por IP

**Automações (Organizador do InstaSaver)**

- O InstaSaver e o VscoSaver continuam salvando em Downloads; com o Verto ligado, a automação leva cada arquivo para `Documentos/Instagram/<Perfil>/<Stories|Destaques|Posts|Reels|Fotos de Perfil|VSCO>` (a pasta Documentos do sistema: `user-dirs.dirs` no Linux, API do shell no Windows)
- Base comum em `Automacoes/core/`, feita para servir às próximas automações: vigia de pasta sob demanda, fila com um único worker em thread (40 arquivos de uma vez são processados em ordem) e registro em JSONL com o motivo de cada falha
- Vigia sob demanda, sem varredura periódica: a thread fica parada num `threading.Event` (CPU zero medida em repouso) e só confere a pasta quando o código pede. As rotas de download do InstaSaver/VscoSaver avisam com `response.call_on_close` (o navegador grava o arquivo logo depois), o "Salvar quadro atual", que acontece só no navegador, avisa por `/automacoes/avisar`, e há uma conferência ao ligar o Verto (o que chegou com ele desligado) e outra no botão "Organizar agora". Depois do aviso, a pasta é conferida em intervalos crescentes (1 s até 10 s, no máximo 5 min) só até o arquivo esperado aparecer completo: tamanho e data iguais entre duas conferências e nenhum `.crdownload`/`.part` ao lado
- Só mexe no que segue o padrão de nome dos dois apps (`usuario_story_20261003_224902_<id>[_2][_capa].mp4`, `usuario_perfil.jpg`, `usuario_destaque_<título>.zip`...), e reconhece o ZIP de um carrossel (`usuario_<código>.zip`) pelo conteúdo. O regex não guloso acerta @ que terminam em `_` (`isaturny__story_...` é do @isaturny_)
- ZIP: `testzip()`, limite de 5 GB e de espaço livre, extração achatada (bloqueia `../` e caminhos absolutos), ZIP dentro de ZIP até 2 níveis, título do destaque vira subpasta. Extrai numa pasta temporária no próprio destino (mover é só renomear) e só manda o ZIP para a lixeira (Send2Trash) depois de conferir que o número de arquivos movidos é igual ao do ZIP; se algo falhar, o ZIP fica intacto e o erro aparece no registro
- Sem duplicar: mesmo nome + mesmo SHA-256 é cópia e é descartada (o ` (1)` do navegador é tirado antes de comparar); conteúdo diferente vira `nome (2).ext`
- `perfis.txt` (`@perfil = Nome da pasta`) no destino, editável na tela ou à mão; @ novo ganha nome limpo (`@gbm.clicks` → Gbm Clicks, nomes reservados do Windows tratados). Cada pasta tem um `.verto_perfil` (oculto no Windows) com os @ dela e o último nome sincronizado: renomear a pasta no gerenciador de arquivos atualiza o `perfis.txt`, mudar o nome no `perfis.txt` renomeia (ou junta) a pasta, e separar um @ de uma pasta compartilhada leva os arquivos dele junto
- Importação de pastas já separadas à mão: o nome próprio da pasta vira o nome do perfil, subpastas do usuário continuam, @ de outra rede guardados junto (o VSCO da mesma pessoa) apontam para a mesma pasta e arquivos sem @ vão para `Outros`
- Com `debug=True`, o vigia liga só no processo filho do Werkzeug (`WERKZEUG_RUN_MAIN`), para não organizar a mesma pasta em dobro

**Editor de Vídeo (Automações)**

- Análise: `ffprobe` lê duração, rotação do celular (side data `displaymatrix`) e fps; fps variável vira fps constante comum (24/25/30/50/60) dentro do próprio render. O áudio de análise sai em 16 kHz mono e, opcionalmente, passa pelo Demucs (voz isolada) antes de transcrever
- Transcrição com faster-whisper (CTranslate2, int8 no CPU, VAD, `word_timestamps`). O áudio entra como numpy (decodificado pelo FFmpeg), então o PyAV não é usado. Segmentos de alucinação conhecidos ("Legendas por…", "Obrigado por assistir") são descartados
- Mapa de cortes: intervalo entre palavras acima do limite do preset (Natural 0,7 s, Dinâmico 0,4 s, Agressivo 0,25 s) vira corte, com folga de 0,15/0,10/0,08 s. Antes, o começo e o fim de cada palavra são puxados para fora dos silêncios do `silencedetect` (limiar adaptativo, entre o ruído de fundo e a fala do próprio áudio), porque o Whisper estica palavras por cima do silêncio
- Retomadas: frases seguidas comparadas com `difflib` (semelhança ≥ 0,6, ou começo interrompido que a seguinte refaz); fica só a última
- Toda borda de trecho cai num quadro exato. O vídeo é cortado com `select` por número de quadro num único fluxo (com `split`+`trim`, cada corte seguraria quadros decodificados na memória) e o áudio é cortado por amostra no Python, em fluxo, com microfade de 10 ms em cada borda. As durações batem amostra por amostra; o AAC só completa o último pacote de 1024 amostras com silêncio
- Enquadramento: o YuNet olha 3 quadros por segundo e cada trecho ganha uma posição fixa de corte (mediana do rosto, a 38% do topo), aplicada com expressões `gte(n,a)*lt(n,b)` no `crop`, sem tremer. Fundo desfocado: o vídeo inteiro sobre uma cópia ampliada com `boxblur`. Zoom alternado de 108% com `overlay` habilitado nos trechos ímpares, mirando no rosto
- Legenda `.ass` (libass) em blocos de 2 a 4 palavras, um evento por palavra com ela em destaque, fonte Montserrat ExtraBold (OFL, em `Automacoes/reels/fontes/`) e margem acima da faixa de UI do Instagram (30% da altura no 9:16); `.srt` separado
- Áudio final: passa-alta 80 Hz, compressão leve e `loudnorm` em duas passadas (medição + `linear=true`) para -14 LUFS. Saída H.264 CRF 19 `yuv420p` + AAC 192k + `+faststart` numa única codificação, conferida em -14,1 LUFS no teste
- Revisão na tela: linha do tempo com cada corte, prévia que pula os cortes, transcrição editável (texto, remover trecho, manter pausa); cada mudança recalcula o mapa no servidor sem FFmpeg. O `.cortes.json` exportado reabre a edição. A pasta de entrada (`Documentos/Verto Editor/Entrada`) é processada sem revisão com o preset marcado, só quando o Verto liga ou no botão

**Ghost Tool (Anti-forensics)**

- Remove metadados de 150+ formatos sem recodificar o conteúdo
- Preserva integridade do arquivo — apenas headers/chunks de metadados são zerados

**Censor (Privacy AI)**

- YOLOv8 para detecção de rostos, placas, documentos e 6 outros tipos
- Aplica blur ou pixelização configurável sobre as regiões detectadas

**Dev/Data, Image Studio, Text Clean & Diff, Capture & OCR, AI Guard & Diff**

- Diferente das ferramentas de IA/binários acima, esses 5 apps rodam inteiramente no navegador (JavaScript puro) — o Flask apenas serve o HTML, sem rota de upload/processamento no backend
- Image Studio usa Canvas para crop/resize/filtros em lote e monta o `.ico` multi-resolução manualmente (container ICO com PNGs embutidos), empacotando lotes em ZIP via JSZip
- O **Editor Individual** do Image Studio (`/imagestudio/solo`) é o modo focado para uma imagem (ou algumas) por vez: seleção de corte arrastável com âncoras e trava de proporção, prévia com filtro CSS ao vivo, comparação antes/depois via canvas + slider, e download direto do arquivo único — sem gerar ZIP, diferente dos modos em lote
- Capture & OCR roda o reconhecimento de texto via Tesseract.js (WebAssembly) e a gravação de tela via `getDisplayMedia`/`MediaRecorder`, convertendo para GIF com gif.js por amostragem de quadros
- AI Guard é heurístico por design: o "detector de IA" combina burstiness (variação do tamanho das frases e das palavras), repetição de bigramas, repetição de aberturas de frase, diversidade de vocabulário e conectores típicos de LLM — não usa nenhum modelo de IA online e é rotulado como estimativa, não prova
- O detector, o reescritor e o verificador de plágio do AI Guard não têm limite de tamanho de texto: aceitam upload de TXT/PDF/DOCX (via pdf.js/mammoth.js) além de colar texto, e processam em lotes assíncronos (`setTimeout`/progress bar) para não travar a aba em documentos grandes
- O reescritor do AI Guard é baseado em dicionários de sinônimos por tom + variação de estrutura de frase, com um "picker" que roda as opções de sinônimo em vez de sortear sempre a mesma, reduzindo repetição em textos longos — não é um modelo de linguagem completo
- O verificador de plágio interno usa shingling de n-gramas (Jaccard) para achar trechos duplicados entre o texto atual e documentos TXT/PDF/DOCX carregados localmente

---

## Instalação

```bash
# Primeira vez
python executaveis/INSTALAR.py

# Iniciar
python executaveis/INICIAR.py

# Acessar
http://localhost:5000
```

**Windows:** `INSTALAR_DEPENDENCIAS.bat` → `INICIAR.bat`
**Linux:** `./INSTALAR_DEPENDENCIAS.sh` → `./INICIAR.sh`

---

## Estrutura

```
├── app.py                        # Flask app — 70+ rotas, 27 apps
├── Office/                       # Conversor e reparador de Word/Excel/PowerPoint
├── Efeitos/                     # Efeitos em fotos e vídeos, saída no mesmo formato do original
├── Conversor/                    # Conversor universal estilo Convertio (imagem → DXF, CAD, documentos, mídia...)
├── Encurtador/                   # Encurtador de links: painel no Verto + Worker/D1 da Cloudflare (cloudflare/)
├── static/localtools/            # Design system da suíte: base.css (tokens --lt-*) e app.css (componentes), fonte Geist,
│                                 # ícones 3D dos apps renderizados por scripts/icones_3d.py (apps/) e símbolos Phosphor (MIT), tudo local
├── Automacoes/                   # Automações em segundo plano
│   ├── core/                     # vigia.py · fila.py · registro.py · pastas.py (base comum)
│   ├── instasaver/               # organizador.py · nomes.py (Organizador do InstaSaver)
│   ├── reels/                    # analise · transcricao · cortes · enquadramento · legendas · render · editor (Editor de Vídeo)
│   └── dados/                    # configuração e registro locais (gitignored)
├── DevData/                      # Beautifier/minifier, dados mock, conversor de formatos, encode/decode
├── ImageStudio/                  # Crop & resize em massa, filtros/marca d'água, gerador de favicon
├── TextClean/                    # Text diff, sanitizador e contador estatístico
├── CaptureOCR/                   # OCR local (Tesseract.js) e gravador de tela/GIF
├── AIGuard/                      # Detector heurístico de IA, reescritor/diff e plágio interno
├── executaveis/
│   ├── INSTALAR.py               # Setup universal (Windows + Linux)
│   ├── INICIAR.py                # Launcher universal
│   └── ATUALIZAR.py              # Atualiza yt-dlp e dependências
├── web/                          # Versão estática (Netlify)
├── docs/                         # Documentação detalhada por app
├── downloads/                    # Output local (gitignored)
└── requirements.txt              # 22 dependências
```

---

## Segurança e Privacidade

- Sem coleta de dados — zero telemetria
- Sem dependência de APIs externas
- Arquivos temporários removidos automaticamente após cada operação
- `downloads/` e `venv/` excluídos do controle de versão via `.gitignore`
