# Verto: Multi-purpose Media & Security Processing Suite

> Processamento 100% local. Dados sensíveis nunca saem da máquina do usuário.

Suíte de 23 ferramentas integradas cobrindo IA, criptografia, manipulação de binários e automação de mídia. Arquitetura local-first por design — não por limitação.

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
| IA — Transcrição         | Whisper (OpenAI)                              |
| Criptografia                | AES-256 (esteganografia)                      |
| Download de Mídia          | yt-dlp                                        |
| Manipulação de PDF        | PyPDF2 + img2pdf                              |
| Office (Word/Excel/PPT)     | LibreOffice headless + python-docx/pptx/openpyxl |
| Vetorização / CAD           | potrace (potracer) + scikit-image + ezdxf     |
| Detecção de Objetos       | YOLOv8 (Censor)                               |
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
| 🔁**Conversor**       | Conversão / CAD | Estilo Convertio: fila de arquivos, 1.700+ rotas diretas, imagem → DXF com potrace (contorno, linha central ou por cor) e PDF/SVG/AI/EPS → DXF sem rasterizar |
| 📄**PDFs**            | Documentos     | Dividir, comprimir, girar, converter, mesclar                      |
| 🗃️**Office**          | Documentos     | Converte e repara Word/Excel/PowerPoint — recuperação em 5 níveis, incluindo extensão trocada |
| 🔲**QR Code**         | Utilitário    | Gerador estático (URLs, Wi-Fi, vCard, PIX) sem rastreamento       |
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
├── app.py                        # Flask app — 70+ rotas, 23 apps
├── Office/                       # Conversor e reparador de Word/Excel/PowerPoint
├── Conversor/                    # Conversor universal estilo Convertio (imagem → DXF, CAD, documentos, mídia...)
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
