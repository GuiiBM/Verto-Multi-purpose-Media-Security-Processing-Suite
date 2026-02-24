# 🚀 Deploy no Netlify - Guia Completo

## 📋 Pré-requisitos

1. Conta no [GitHub](https://github.com)
2. Conta no [Netlify](https://netlify.app)
3. Repositório com o código

## 🔧 Passos para Deploy

### 1. Preparar Repositório
```bash
# Adicionar arquivos ao git
git add web/
git commit -m "Add web version for Netlify"
git push origin main
```

### 2. Conectar ao Netlify
1. Acesse [netlify.app](https://netlify.app)
2. Clique em "New site from Git"
3. Conecte sua conta GitHub
4. Selecione o repositório

### 3. Configurar Build
- **Build command:** (deixe vazio)
- **Publish directory:** `web`
- **Branch:** `main`

### 4. Deploy Automático
- ✅ Deploy será feito automaticamente
- ✅ URL será gerada (ex: `https://seu-site.netlify.app`)
- ✅ SSL automático ativado

## 🌐 Funcionalidades da Versão Web

### ✅ O que funciona:
- Interface responsiva idêntica ao Flask
- Validação de URLs do YouTube
- Geração de links para serviços de download
- Múltiplas opções de qualidade
- Headers de segurança

### ❌ Diferenças da versão local:
- Não baixa diretamente (gera links)
- Usa serviços externos (Y2mate, SaveFrom, etc.)
- Sem processamento server-side

## 🔧 Customização

### Adicionar novos serviços:
Edite `web/app.js` na função `getDownloadUrls()`:

```javascript
const downloadServices = [
    {
        name: 'NovoServico',
        url: `https://exemplo.com/download?v=${videoId}`,
        description: 'Baixar via NovoServico'
    }
];
```

### Alterar aparência:
Edite o CSS em `web/index.html`

## 🛡️ Segurança

- CSP configurado em `_headers`
- Validação de URLs no frontend
- Headers de segurança automáticos
- HTTPS forçado pelo Netlify

## 📱 Responsividade

A interface se adapta automaticamente a:
- 📱 Smartphones
- 📱 Tablets  
- 💻 Desktops
- 🖥️ Monitores grandes