# 📱 Apps Disponíveis - LocalTools

## 🎬 Verto (Conversor YouTube)
**Rota:** `/verto`
**Dependências:**
- `yt-dlp` - Download de vídeos
- `ffmpeg` - Conversão de formatos

**Funcionalidades:**
- Download de vídeos MP4 (múltiplas resoluções)
- Extração de áudio MP3 (múltiplos bitrates)
- Download de thumbnails (PNG/JPG)
- Cálculo automático de tamanho

---

## 📄 PDFs (Ferramentas PDF)
**Rota:** `/pdfs`
**Dependências:**
- `PyPDF2` - Manipulação de PDFs
- `pikepdf` - Desbloqueio avançado
- `qpdf` - Reparação de PDFs
- `reportlab` - Criação de PDFs
- `PyMuPDF (fitz)` - Conversão PDF→Imagem
- `Pillow` - Processamento de imagens
- `weasyprint` - HTML→PDF

**Ferramentas disponíveis:**
1. **Juntar PDFs** (`/pdfs/merge`) - Mesclar múltiplos PDFs
2. **Dividir PDF** (`/pdfs/split`) - Separar páginas
3. **Converter PDF** (`/pdfs/convert`) - PDF↔Imagem
4. **Comprimir PDF** (`/pdfs/compress`) - Reduzir tamanho
5. **Girar PDF** (`/pdfs/rotate`) - Rotacionar páginas
6. **Comparar PDFs** (`/pdfs/compare`) - Encontrar diferenças
7. **Reparar PDF** (`/pdfs/repair`) - Recuperar arquivos corrompidos
8. **Proteger PDF** (`/pdfs/protect`) - Adicionar senha
9. **Desbloquear PDF** (`/pdfs/unlock`) - Remover senha (força bruta)
10. **Editar PDF** (`/pdfs/edit`) - Editar texto
11. **Marca d'água** (`/pdfs/watermark`) - Adicionar marca d'água
12. **Corromper PDF** (`/pdfs/corrupt`) - Corromper para testes

---

## 📁 Arquivos (Conversor Universal)
**Rota:** `/files`
**Dependências:**
- `Pillow` - Conversão de imagens

**Funcionalidades:**
- Conversão entre 100+ formatos de imagem
- Suporte a RAW de câmeras
- Estimativa de tamanho em tempo real

---

## 🎨 Transparência (Remoção de Fundo)
**Rota:** `/transparent`
**Dependências:**
- `Pillow` - Processamento de imagens
- `rembg` - Remoção automática de fundo (opcional)

**Funcionalidades:**
- Remoção de fundo por cor
- Remoção automática de fundo (IA)
- Seletor de cor interativo

---

## ⏰ Tempo (Relógio e Calendário)
**Rota:** `/tempo`
**Dependências:** Nenhuma (apenas HTML/CSS/JS)

**Funcionalidades:**
- Relógio digital e analógico
- Calendário interativo
- Lista de feriados brasileiros

---

## 🎬 PurpleFlix (Em desenvolvimento)
**Rota:** `/purpleflix`
**Status:** Interface criada, funcionalidades em desenvolvimento

---

## ⚙️ Configurações
**Rota:** `/config`
**Status:** Em desenvolvimento

---

## 📦 Instalação de Dependências

### Básico (obrigatório):
```bash
pip install flask yt-dlp Pillow PyPDF2
```

### Completo (todas as funcionalidades):
```bash
pip install flask yt-dlp Pillow PyPDF2 pikepdf reportlab PyMuPDF weasyprint rembg
```

### Sistema (ffmpeg e qpdf):
```bash
# Ubuntu/Debian
sudo apt install ffmpeg qpdf

# macOS
brew install ffmpeg qpdf

# Windows
# Baixar de: https://ffmpeg.org e https://qpdf.sourceforge.io
```

---

## 🚀 Executar

```bash
python executaveis/INICIAR.py
```

Acesse: `http://localhost:5000`
