# Verto: Multi-purpose Media & Security Processing Suite

> Processamento 100% local. Dados sensíveis nunca saem da máquina do usuário.

Suíte de 17 ferramentas integradas cobrindo IA, criptografia, manipulação de binários e automação de mídia. Arquitetura local-first por design — não por limitação.

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
| 📄**PDFs**            | Documentos     | Dividir, comprimir, girar, converter, mesclar                      |
| 🗃️**Office**          | Documentos     | Converte e repara Word/Excel/PowerPoint — recuperação em 5 níveis, incluindo extensão trocada |
| 🔲**QR Code**         | Utilitário    | Gerador estático (URLs, Wi-Fi, vCard, PIX) sem rastreamento       |
| 🗜️**Compressor**    | Utilitário    | Redução de tamanho com controle de qualidade                     |
| 📱**Social Preview**  | Design         | Simulação de posts em 24 formatos Mobile/Desktop/Tablet          |
| 🧹**Clean Reader**    | Produtividade  | Extração de conteúdo + modo leitura                             |
| 🎮**PurpleFlix**      | Streaming      | Player integrado                                                   |
| ⏰**Tempo**           | Utilitário    | Relógio + calendário com feriados brasileiros                    |
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

**Ghost Tool (Anti-forensics)**

- Remove metadados de 150+ formatos sem recodificar o conteúdo
- Preserva integridade do arquivo — apenas headers/chunks de metadados são zerados

**Censor (Privacy AI)**

- YOLOv8 para detecção de rostos, placas, documentos e 6 outros tipos
- Aplica blur ou pixelização configurável sobre as regiões detectadas

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
├── app.py                        # Flask app — 50+ rotas, 17 apps
├── Office/                       # Conversor e reparador de Word/Excel/PowerPoint
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
