# 🎬 YouTube MP4 Downloader

Aplicação web para baixar vídeos do YouTube com seleção de qualidade.

## 🌐 Versão Web (Netlify)

**🚀 Deploy Instantâneo:** [Guia Completo](deploy-netlify.md)

1. **Faça upload da pasta `web/` para seu repositório**
2. **Conecte ao Netlify**
3. **Configure: Publish directory = `web`**
4. **Deploy automático ativo!**

## 💻 Versão Local

### Instalação Universal (Windows e Linux)
1. **Execute `python executaveis/INSTALAR.py`** (primeira vez)
2. **Execute `python executaveis/INICIAR.py`**
3. **Acesse `http://localhost:5000`**

### Método Alternativo
**Windows:** Execute `INSTALAR_DEPENDENCIAS.bat` e depois `INICIAR.bat`
**Linux:** Execute `./INSTALAR_DEPENDENCIAS.sh` e depois `./INICIAR.sh`

## 📁 Estrutura

```
├── app.py                    # Aplicação principal (local)
├── web/                     # ← Versão Web (Netlify)
│   ├── index.html          # Interface web
│   ├── app.js              # Lógica JavaScript
│   ├── netlify.toml        # Config Netlify
│   └── _headers            # Headers segurança
├── executaveis/              # Scripts prontos para usar
│   ├── INSTALAR.py          # ← Universal (Windows + Linux)
│   ├── INICIAR.py           # ← Universal (Windows + Linux)
│   ├── ATUALIZAR.py         # ← Universal (Windows + Linux)
│   ├── INICIAR.bat          # Windows - Clique aqui
│   ├── INICIAR.sh           # Linux - Execute aqui
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