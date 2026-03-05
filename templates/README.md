# Templates - Estrutura de Arquivos

Esta pasta contém templates HTML, arquivos de configuração e listas de formatos suportados.

## 📁 Estrutura

### Templates HTML
- `compress.html` - Interface do compressor de arquivos
- `qrcode.html` - Gerador de QR Code
- `tempo.html` - Relógio e calendário
- `tempo_base.html` - Template base do Tempo
- `tempo_part1.txt` - Parte 1 do template Tempo

### Configurações
- `tempo_holidays.py` - Lista de feriados brasileiros
- `update_tempo.py` - Script de atualização do Tempo

### Formatos Suportados
- `file_formats.json` - Lista completa de 150+ formatos de arquivo

## 📋 file_formats.json

Contém categorias de formatos:

### Categorias Disponíveis:
- **images** (50+ formatos) - JPG, PNG, WEBP, TIFF, BMP, GIF, HEIC, RAW, etc.
- **raw_images** (20+ formatos) - CR2, NEF, ARW, DNG, ORF, etc.
- **videos** (35+ formatos) - MP4, MOV, AVI, MKV, WEBM, FLV, etc.
- **audio** (40+ formatos) - MP3, WAV, FLAC, AAC, OGG, OPUS, etc.
- **documents** (35+ formatos) - PDF, DOCX, TXT, RTF, ODT, etc.
- **presentations** (13+ formatos) - PPTX, ODP, KEY, etc.
- **ebooks** (20+ formatos) - EPUB, MOBI, AZW, FB2, etc.
- **archives** (25+ formatos) - ZIP, RAR, 7Z, TAR, ISO, etc.
- **fonts** (20+ formatos) - TTF, OTF, WOFF, WOFF2, etc.
- **cad** (20+ formatos) - DWG, DXF, STL, STEP, etc.
- **3d_models** (25+ formatos) - OBJ, FBX, GLTF, BLEND, etc.
- **code** (40+ formatos) - PY, JS, HTML, CSS, JSON, etc.
- **executables** (8+ formatos) - EXE, DLL, SO, APP, etc.
- **databases** (5+ formatos) - DB, SQLITE, SQL, etc.
- **design** (7+ formatos) - PSD, AI, SKETCH, FIGMA, etc.

## 🔧 Como Usar

### Python
```python
import json

with open('templates/file_formats.json', 'r') as f:
    formats = json.load(f)

# Obter formatos de imagem
image_formats = formats['images']['formats']

# Verificar se arquivo é suportado
ext = '.jpg'
is_image = ext in formats['images']['formats']
```

### JavaScript
```javascript
fetch('/templates/file_formats.json')
  .then(response => response.json())
  .then(formats => {
    const imageFormats = formats.images.formats;
    console.log(imageFormats);
  });
```

## 📝 Adicionar Novos Formatos

Edite `file_formats.json` e adicione na categoria apropriada:

```json
{
  "nova_categoria": {
    "formats": [".ext1", ".ext2"],
    "description": "Descrição da categoria"
  }
}
```

## 🎯 Apps que Usam file_formats.json

- **Ghost Tool** - Remoção de metadados
- **Arquivos** - Conversor de formatos
- **Compressor** - Compressão de arquivos
- (Futuros apps podem importar facilmente)

## 📌 Notas

- Todos os formatos estão em lowercase
- Incluem o ponto (.) no início
- Total: 150+ formatos suportados
- Atualizado regularmente
