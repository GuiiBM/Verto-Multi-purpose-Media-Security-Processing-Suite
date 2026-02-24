# 🎬 YouTube MP4 Downloader

Aplicação web simples para baixar vídeos do YouTube em formato MP4.

## 📋 Pré-requisitos

- Python 3.7 ou superior
- pip (gerenciador de pacotes do Python)

## 🚀 Instalação

### Método 1: Automático (Windows)
```bash
# Execute o arquivo de instalação
install.bat
```

### Método 2: Manual
```bash
# Instale as dependências
pip install -r requirements.txt
```

### Método 3: Instalação individual
```bash
pip install Flask==2.3.3
pip install yt-dlp==2023.12.30
```

## ▶️ Como usar

### Método Fácil (Recomendado)
1. **Vá para a pasta `executaveis/`**
2. **Execute `INSTALAR_DEPENDENCIAS.bat`** (apenas na primeira vez)
3. **Execute `INICIAR.bat`** para iniciar
4. **Acesse `http://localhost:5000`** no navegador

### Método Manual
1. **Inicie o servidor:**
   ```bash
   python app.py
   ```
2. **Acesse no navegador:**
   ```
   http://localhost:5000
   ```
3. **Cole a URL do YouTube, escolha a qualidade e clique em "Baixar MP4"**

## 📁 Estrutura de arquivos

```
baixar video youtube python/
├── app.py                        # Aplicação principal
├── requirements.txt              # Dependências
├── PASSO_A_PASSO.md             # Guia completo
├── README.md                    # Este arquivo
├── executaveis/                 # Scripts para executar
│   ├── INICIAR.bat              # ← CLIQUE AQUI PARA INICIAR
│   ├── INSTALAR_DEPENDENCIAS.bat
│   ├── ATUALIZAR_YT-DLP.bat
│   └── LEIA-ME.txt
└── downloads/                   # Vídeos baixados
```

## 🔧 Solução de problemas

### Erro 403 Forbidden
Se aparecer erro "HTTP Error 403: Forbidden", tente:
1. Atualizar o yt-dlp: `pip install --upgrade yt-dlp`
2. Usar URLs diferentes do mesmo vídeo
3. Aguardar alguns minutos e tentar novamente

### Dependências não encontradas
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## ✨ Novidades

- **Seleção de qualidade**: Escolha entre 1080p, 720p, 480p, 360p ou melhor disponível
- **Scripts automáticos**: Pasta `executaveis/` com tudo pronto para usar
- **Instalação fácil**: Um clique para instalar e outro para iniciar

## 📝 Notas

- Os vídeos são salvos na pasta `downloads/`
- Funciona apenas com vídeos públicos do YouTube
- Respeite os direitos autorais dos conteúdos
- **Leia o `PASSO_A_PASSO.md` para instruções detalhadas**