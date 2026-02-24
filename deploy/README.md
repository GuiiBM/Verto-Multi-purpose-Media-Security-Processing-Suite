# 🚀 Deploy no Heroku

## Arquivos para deploy:
- `app.py` - Flask app original
- `requirements.txt` - Python dependencies
- `Procfile` - Heroku config
- `runtime.txt` - Python version

## Como fazer deploy:

### 1. Heroku (Recomendado)
```bash
# Instalar Heroku CLI
# Fazer login: heroku login
heroku create seu-app-name
git init
git add .
git commit -m "Deploy Flask app"
git push heroku main
```

### 2. Railway
```bash
# Conectar no railway.app
# Fazer upload desta pasta
# Deploy automático
```

### 3. Render
```bash
# Conectar no render.com
# Fazer upload desta pasta  
# Deploy automático
```

## ✅ Funciona 100%:
- Flask original
- yt-dlp completo
- Download real de vídeos
- Todas as qualidades