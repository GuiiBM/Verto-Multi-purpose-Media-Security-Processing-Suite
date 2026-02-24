# 🚀 Deploy no Render (GRATUITO)

## 📋 Passo a passo:

### 1. Criar conta no Render
- Acesse: https://render.com
- Clique em "Get Started for Free"
- Faça login com GitHub

### 2. Criar repositório GitHub
```bash
# Criar novo repositório no GitHub
# Nome: youtube-downloader-web
# Público ou privado
```

### 3. Upload dos arquivos
- Faça upload de TODOS os arquivos da pasta `deploy/`
- Ou use git:
```bash
git init
git add .
git commit -m "YouTube Downloader Flask App"
git remote add origin https://github.com/SEU-USUARIO/youtube-downloader-web.git
git push -u origin main
```

### 4. Deploy no Render
1. No Render, clique "New +"
2. Selecione "Web Service"
3. Conecte seu repositório GitHub
4. Configure:
   - **Name:** youtube-downloader
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free

### 5. Variáveis de ambiente (opcional)
- PORT: 10000 (automático)

## ✅ Resultado:
- URL: https://youtube-downloader-XXXX.onrender.com
- **100% GRATUITO**
- Seu Flask + yt-dlp funcionando!

## ⚠️ Limitações do plano gratuito:
- 750 horas/mês
- Dorme após 15min inativo
- 512MB RAM