# 🎬 YouTube MP4 Downloader

Aplicação web para baixar vídeos do YouTube com seleção de qualidade.

## 📱 Menu de Apps Integrado

**Interface estilo smartphone com navegação entre aplicativos!**

### Como usar:
1. **Execute `python executaveis/INICIAR.py`** (ou `./executaveis/INSTALAR.py` na primeira vez)
2. **Acesse `http://localhost:5000`**
3. **Clique no app Verto** para acessar o conversor
4. **Use a seta ← no canto superior esquerdo** para voltar ao menu

### Recursos do Menu:
- 🎬 **Verto** - Conversor de vídeos do YouTube (MP4/MP3/Thumbnails)
- 📖 **Instruções** - Documentação completa de todos os apps
- 📁 **Arquivos** - Conversor universal (150+ formatos)
- 🎮 **PurpleFlix** - Streaming integrado
- ⏰ **Tempo** - Relógio e calendário com feriados brasileiros
- 📄 **PDFs** - Suite completa (dividir, converter, comprimir, girar, etc)
- 🎨 **Transparência** - Remover fundo de imagens com IA
- 🔲 **QR Code** - Gerador gratuito e permanente
- 🗜️ **Compressor** - Redução de tamanho de arquivos
- 🎤 **Transcrever** - Áudio para texto com IA
- 👻 **Ghost Tool** - Removedor de metadados (150+ formatos)
- 🕵️ **Stealth** - Esteganografia com criptografia AES-256
- 🔒 **Censor** - Proteção de privacidade com IA (9 tipos de detecção)

## ✨ Novidade: Cálculo Automático de Tamanho

**Agora você vê o tamanho estimado de cada arquivo em tempo real!**

- 📊 Tamanho exibido para cada resolução (MP4)
- 🎵 Tamanho para cada bitrate (MP3)
- 🖼️ Tamanho das thumbnails (PNG/JPG)
- ⚡ Atualização automática ao colar URL

*Disponível apenas na versão local*

## 🌐 Versão Web (Netlify)

**🚀 Deploy Instantâneo:** [Guia Completo](deploy-netlify.md)

1. **Faça upload da pasta `web/` para seu repositório**
2. **Conecte ao Netlify**
3. **Configure: Publish directory = `web`**
4. **Deploy automático ativo!**

## 💻 Versão Local

### Início Rápido (Recomendado)
1. **Execute `python executaveis/INSTALAR.py`** (primeira vez)
2. **Execute `python executaveis/INICIAR.py`**
3. **Acesse `http://localhost:5000`**
4. **Navegue entre os apps!**

### Método Alternativo
**Windows:** Execute `INSTALAR_DEPENDENCIAS.bat` e depois `INICIAR.bat`
**Linux:** Execute `./INSTALAR_DEPENDENCIAS.sh` e depois `./INICIAR.sh`

## 📁 Estrutura

```
├── app.py                   # Aplicação principal com menu integrado
├── web/                     # Versão Web (Netlify)
│   ├── index.html          # Interface web
│   ├── app.js              # Lógica JavaScript
│   ├── netlify.toml        # Config Netlify
│   └── _headers            # Headers segurança
├── executaveis/             # Scripts prontos para usar
│   ├── INSTALAR.py         # Universal (Windows + Linux)
│   ├── INICIAR.py          # Universal (Windows + Linux)
│   ├── ATUALIZAR.py        # Universal (Windows + Linux)
│   ├── INICIAR.bat         # Windows - Clique aqui
│   ├── INICIAR.sh          # Linux - Execute aqui
│   ├── INSTALAR_DEPENDENCIAS.bat  # Windows
│   ├── INSTALAR_DEPENDENCIAS.sh   # Linux
│   ├── ATUALIZAR_YT-DLP.bat # Windows
│   └── ATUALIZAR_YT-DLP.sh  # Linux
├── docs/                    # Documentação completa
├── scripts/                 # Scripts auxiliares
├── deploy-netlify.md        # Guia deploy Netlify
└── downloads/              # Vídeos baixados
```

## 📖 Documentação

Leia `docs/PASSO_A_PASSO.md` para instruções detalhadas.


## 🔲 Gerador de QR Code

**Contra-ataque aos geradores "gratuitos" que cobram por QR Codes dinâmicos!**

### Funcionalidades:
- ✅ **QR Codes Estáticos** - Nunca expiram
- 🎨 **Customização Total** - Cores, tamanho, bordas
- 🖼️ **Logo Central** - Adicione sua marca
- 🔧 **Correção de Erro** - 4 níveis (7% a 30%)
- 🚫 **Sem Marcas D'água** - 100% limpo

### Tipos Suportados:
1. **🔗 Links/URLs** - Qualquer endereço web
2. **📶 Wi-Fi** - Compartilhe sua rede
3. **👤 vCard** - Cartão de visita digital
4. **💰 PIX** - Pagamentos instantâneos

### Diferencial:
Todos os QR Codes gerados são **estáticos e permanentes**. Não há planos mensais, não há expiração, não há rastreamento. Seu QR Code, suas regras!
