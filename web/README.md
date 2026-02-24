# 🌐 YouTube Downloader - Versão Web

Versão web do YouTube MP4 Downloader otimizada para hospedagem no Netlify.

## 🚀 Deploy no Netlify

1. **Conecte seu repositório GitHub ao Netlify**
2. **Configure o build:**
   - Build command: (deixe vazio)
   - Publish directory: `web`
3. **Deploy automático ativado**

## 📁 Estrutura Web

```
web/
├── index.html          # Interface principal
├── app.js             # Lógica da aplicação
├── netlify.toml       # Configuração do Netlify
├── _headers           # Headers de segurança
└── README.md          # Este arquivo
```

## ⚡ Funcionalidades

- ✅ Interface responsiva
- ✅ Validação de URLs do YouTube
- ✅ Múltiplos serviços de download
- ✅ Sem dependências de servidor
- ✅ Deploy automático no Netlify

## 🔗 Como Usar

1. Cole a URL do vídeo do YouTube
2. Selecione a qualidade desejada
3. Clique em "Gerar Link"
4. Escolha um dos serviços de download

## 🛡️ Segurança

- Headers de segurança configurados
- CSP (Content Security Policy) ativo
- Validação de URLs no frontend