# Verto: Multi-purpose Media & Security Processing Suite

> Processamento 100% local. Dados sensíveis nunca saem da máquina do usuário.

Suíte de 34 ferramentas integradas cobrindo IA, criptografia, manipulação de binários e automação de mídia. Arquitetura local-first por design — não por limitação.

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
| Geometria 3D (Vetor3D)      | shapely + mapbox-earcut + trimesh + manifold3d; visualizador three.js (local) |
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
| 🧊**Vetor3D**         | Conversão / 3D | SVG, DXF, PDF/AI, EPS ou imagem → modelo 3D em alta definição: chanfro ou inflado por peça, cores no DXF preto e branco, fila em etapas que acompanha o hardware (CPU, RAM, temperatura) e exporta GLB/STL/3MF/OBJ/PLY ou código copia-e-cola (HTML, Netlify, React, PHP, Python, Node) com giro 360° e zoom |
| 📄**PDFs**            | Documentos     | Dividir, comprimir, girar, converter, mesclar                      |
| 🗃️**Office**          | Documentos     | Converte e repara Word/Excel/PowerPoint — recuperação em 5 níveis, incluindo extensão trocada |
| 🔲**QR Code**         | Utilitário    | Gerador estático (URLs, Wi-Fi, vCard, PIX) sem rastreamento       |
| 🔗**Encurtador**      | Utilitário    | Links curtos GBM (`gbm.pages.dev/x7k2pq`, `gbmlinks.pages.dev/x7k2pq` ou `gbm.gbm.workers.dev/x7k2pq`) que funcionam no mundo todo com o PC desligado: Cloudflare Pages + Workers + D1 na conta grátis do usuário, estatísticas sem IP, validade, senha, QR e UTM |
| 🗜️**Compressor**    | Utilitário    | Redução de tamanho com controle de qualidade                     |
| 📱**Social Preview**  | Redes sociais  | Um post adaptado a 14 destinos (Instagram, Facebook, Threads, X, LinkedIn, Bluesky, Mastodon, Telegram, Discord, Pinterest, YouTube, TikTok, Status do WhatsApp, prévia de link): configuração automática na primeira foto (enquadramento pelo rosto com YuNet), edição individual por rede (cortar, encaixar ou preenchimento automático), prévia fiel de cada app, fotos com música virando vídeo e publicação direta pelas APIs oficiais com os tokens do próprio usuário |
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

**Vetor3D (vetor → 3D em alta definição)**
- Importação para um modelo comum de peças 2D em mm: SVG (svgelements, transformações e `fill-rule` nonzero/evenodd calculados por número de voltas), DXF (ezdxf: linhas, arcos, polilinhas com bulge, splines, hachuras, blocos explodidos e textos em curvas), PDF/AI (PyMuPDF), EPS (Ghostscript → PDF) e imagens (vetorização por cor do Conversor)
- Imagens (PNG/JPG/WEBP/HEIC): fundo removido pela transparência existente, pela cor das bordas (preenchimento a partir das bordas) ou por IA (rembg); PNG sem fundo para baixar. Modo desenho: tinta (limiar de Otsu, frestas fechadas) + áreas fechadas como regiões pintáveis com a cor original, vãos de hachura somados à tinta, contornos de subpixel (marching squares sobre máscara suavizada); modo cores: vetorização por cor do Conversor
- Personagem 3D, dois motores de IA (`Vetor3D/v3d_modelos.py` decide e baixa): **Máxima qualidade** = Hunyuan3D-2 mini turbo (Tencent, código de geração de forma adaptado em `Vetor3D/hy3dgen/` com a licença Tencent Hunyuan 3D 2.0 Community, que vale fora da UE, Reino Unido e Coreia do Sul; ~4,3 GB), rodando no processador com pesos fp16 mapeados do disco (redes montadas sem alocar memória, camadas lineares convertidas para fp32 só no cálculo), leitura da imagem pelo DINOv2-giant a 1022 px, 5 passos de difusão e volume pelo decodificador FlashVDM: ~7 min por imagem na primeira vez (depois em cache), ~1,2 GB de memória real; o volume é alinhado ao desenho por uma câmera em PERSPECTIVA ajustada (distância, escala e posição otimizadas pela sobreposição das silhuetas: desenhos usam perspectiva, a IA reconstrói sem ela). **Leve** = TripoSR (~1,7 GB, ~1 min), usado em máquinas com menos de 6 GB de RAM, sem espaço em disco ou se o máximo falhar. Opção **Ajuste** (padrão: *Desenho adaptado ao 3D*): a forma 3D da IA fica limpa e o desenho se adapta a ela por um registro elástico ("demons" em várias escalas) entre a silhueta do modelo vista da câmera e a do desenho, que leva cada traço ao lugar certo do corpo (~97–98% de coincidência), sem distorcer nem perder partes; *Contorno exato* deforma o 3D até o contorno do desenho. Todo corpo passa por fechamento morfológico (fendas, furos e cavidades), espessura mínima em placas finas e fechamento de furos que atravessam o corpo onde o desenho é sólido; a cor das costas só herda a da frente perto de onde ela é vista (sem manchas que parecem buracos).
- Personagem 3D (imagens), método padrão "Reconstrução 360°" (`Vetor3D/v3d_reconstrucao.py`): forma fiel ao desenho + volume reconstruído por IA (qualquer um dos dois motores). O DESENHO manda na vista de frente (um "cone" que sai da câmera e passa pelo contorno da imagem limita o volume: silhueta 99%+ igual à do desenho, medida a cada geração) e a imagem original vira a textura da frente; a REDE TripoSR (Stability AI + Tripo AI, MIT, código adaptado em `Vetor3D/triposr/`, ~1,7 GB baixados uma vez, roda num processo filho que devolve toda a memória ao terminar) dá o volume que a imagem não mostra (costas, lados, embaixo). O corpo da rede vira distância assinada (256³, em cache por imagem) e é DEFORMADO para a silhueta do desenho (correspondência pelas distâncias 2D, sem paredes de recorte); partes que a rede perdeu viram tubos redondos; nada fica muito mais fundo do que largo no desenho. Campo final numa grade de até 1000 voxels no lado maior, em fatias com orçamento de memória (colunas fora da silhueta são puladas), amostragem por B-spline cúbica aproximante (sem dobras nem oscilações), marching cubes com costura exata pelos índices, Taubin proporcional à resolução. Preview ~400 mil triângulos e textura 2048; HD ~2,5 milhões e textura 4096 (qualidade fixa por nível; máquina fraca só demora mais). Textura assada em blocos: frente projetada da imagem onde é visível da câmera, costas/lados com a cor de base da frente levada ao ponto escondido mais próximo e a cor da rede ajustada à paleta. Atlas UV próprio por projeção em ilhas (~1 s para 2,5 milhões de triângulos).
- Personagem 3D, método "Inflado": volume fechado de 360° em vez de extrusão — inflação da silhueta pela equação de Poisson (sqrt(2u): partes finas com seção redonda, partes largas limitadas pela profundidade), deslocamento e relevo pela profundidade estimada localmente (Depth Anything V2 Small via transformers, ~100 MB no primeiro uso, liberado da RAM após o uso e guardado em cache por projeto), traço como sulco, superfície por marching cubes (estanque) suavizada por Taubin e reduzida conforme o perfil; textura em atlas (frente com a imagem, costas lisas) com UV por lado
- Fila: limite de quantas etapas aparecem (lembrado no navegador), "Limpar concluídas" e "Cancelar tudo"
- DXF preto e branco: as linhas soltas são unidas num arranjo plano (pontas soldadas por tolerância, inclusive junções em "T") e cada face fechada vira uma região pintável; o nível de aninhamento decide sólido/furo
- Geometria por "curvas de nível": a forma encolhe em degraus (buffer negativo) e cada faixa é costurada anel a anel (ou triangulada com earcut quando a topologia muda), então chanfro e inflado funcionam em qualquer forma, sem auto-interseção, e a malha sai fechada; normais com vinco calculadas por componentes conexos
- Painel de hardware com valores reais lidos a cada 1,5 s: RAM em uso, cache que o sistema libera e livre; swap usado e troca com o disco em MB/s; temperaturas de CPU, GPU e SSD; uso e VRAM da GPU. Cada etapa rodando mostra a RAM real que está usando (sem os pesos mapeados do disco), o teto dela e o uso de CPU
- Fila de IA (personagem 3D): na ordem do pedido (duas ao mesmo tempo só com memória e núcleos para as duas), cada etapa num processo novo com TETO RÍGIDO de memória, limite macio um pouco abaixo e PRIORIDADE BAIXA de CPU e disco (cgroup via `systemd-run --user --scope`: MemoryMax, MemoryHigh, CPUWeight=20, IOWeight=20; a IA usa os núcleos que estão livres no momento), para o computador continuar livre para outros programas: se a etapa passar do teto só ela é encerrada, o computador não trava, e ela recomeça sozinha em modo de pouca memória (mesma qualidade, fatias menores, até 3 tentativas); vigia da RAM do sistema como segunda proteção; cada item da fila mostra quando começa e quando fica pronto (custo por etapa calibrado a cada execução em `~/.cache/verto/vetor3d_ritmo.json`)
- Fila em processos separados (`python -m Vetor3D.v3d_trabalho`): leitura/preview num processo sempre pronto, alta definição em processos dedicados que dividem as peças entre núcleos; perfil pelo hardware (núcleos, RAM), admissão por memória livre, menos processos com CPU quente ou ocupada, pausar (processo congelado), cancelar (árvore de processos encerrada) e aviso claro se o sistema matar um processo por falta de memória
- Código copia-e-cola gerado de um único visualizador (`static/localtools/vetor3d/viewer.js`), empacotado com esbuild em duas versões: three.js via jsDelivr (13 KB) ou embutido (650 KB, offline); qualidade adaptada ao aparelho do visitante, desenho só quando algo muda e só enquanto visível

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

## Social Preview: versão web por assinatura (planejada)

O Social Preview vai ganhar uma versão própria, fora da suíte. **Por enquanto nada mudou:** o Social Preview do Verto (`/social`) continua e segue os padrões do Verto. Os dois só viram sistemas separados quando o app novo for criado.

- **Mesmo backend** (`SocialPreview/`) nas duas versões, para uma correção valer nas duas; o que muda é o front.
- **Aplicação web multiusuário**, com login simples e segurança completa. Cada pessoa conecta as próprias contas com os próprios tokens, guardados criptografados e isolados por usuário.
- **Website por assinatura, quase autônomo e de custo mínimo:**
  - planos mensal e anual, com "você economiza 10% no plano anual" exato: anual = 13 × valor base (para o cliente aparece só "1 ano"); mensal = anual ÷ 12 ÷ 0,9, arredondado para cima; valor, multiplicador e percentual editáveis no menu do administrador;
  - teste grátis de 1 semana, só por convite do administrador;
  - limites tirados das cotas dos provedores compartilhados (servidor, Gmail, nota, pagamento), com teto diário por pessoa;
  - nota fiscal automática e e-mails por código próprio, pelo Gmail pessoal;
  - 2FA obrigatório para todos, com app autenticador (gratuito) e códigos de recuperação;
  - quem não paga: 3 dias de carência, bloqueio, dados apagados 1 mês depois;
  - quem cancela: 1 mês para renovar, com 3 e-mails de aviso, e depois os dados são apagados;
  - nos dois casos, um aviso curto com o motivo fica no sistema por 6 meses.
- **Conta de administrador:** vê as contas criadas e a situação de cada uma; cria, bloqueia, desbloqueia e remove contas; e acompanha cobranças e o painel do negócio. Nunca vê os tokens dos usuários.
- **A versão do Verto não terá** login, administrador nem cobrança.
- **Leve e focada:** leva do Verto só o que o Social Preview usa, sem as dependências da suíte.
- **Sem os nomes Verto e LocalTools.** Nome provisório: Social Preview. Identidade visual definida na criação.

Plano completo, com a lista do que o app faz hoje, o contrato das rotas, a segurança, a administração, a assinatura e as decisões em aberto (listadas no topo): [`docs/SOCIAL-APP-NOVO.md`](docs/SOCIAL-APP-NOVO.md).

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

Modelos de IA do Vetor3D: o instalador confere o espaço livre e o que já está baixado no cache do Hugging Face (não baixa de novo o que está completo, continua downloads interrompidos, atualiza o que mudou no servidor) e mostra velocidade e tempo estimado. Com espaço, ficam os dois motores (~6 GB); sem espaço para o de máxima qualidade, só o leve; sem espaço nenhum, o app baixa na primeira vez. Para conferir a qualquer hora: `venv/bin/python -m Vetor3D.v3d_modelos --servidor` (ou `--instalar` para baixar o que falta).

**Windows:** `INSTALAR_DEPENDENCIAS.bat` → `INICIAR.bat`
**Linux:** `./INSTALAR_DEPENDENCIAS.sh` → `./INICIAR.sh`

---

## Estrutura

```
├── app.py                        # Flask app — 70+ rotas, 34 apps
├── Office/                       # Conversor e reparador de Word/Excel/PowerPoint
├── Efeitos/                     # Efeitos em fotos e vídeos, saída no mesmo formato do original
├── Conversor/                    # Conversor universal estilo Convertio (imagem → DXF, CAD, documentos, mídia...)
├── Vetor3D/                      # Vetor/DXF → 3D: importação, geometria (chanfro/inflado), fila por hardware, exportação e código
├── Encurtador/                   # Encurtador de links: painel no Verto + Worker/D1 da Cloudflare (cloudflare/)
├── SocialPreview/                # Social Preview: catálogo das redes, publicação pelas APIs, mídia (ffmpeg/YuNet) e hospedagem temporária;
│                                 # tokens em dados/ (gitignored). Backend que será compartilhado com a futura versão web
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
- Sem dependência de APIs externas. Exceções opcionais, que só falam com a internet quando o usuário conecta a própria conta: Encurtador (Cloudflare) e Social Preview (APIs das redes sociais)
- Arquivos temporários removidos automaticamente após cada operação
- `downloads/` e `venv/` excluídos do controle de versão via `.gitignore`
