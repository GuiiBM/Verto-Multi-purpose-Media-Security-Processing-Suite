from flask import Flask, request, render_template_string, jsonify
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <title>YouTube MP4 Downloader</title>
  <style>
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0, #020617 45%, #000 100%);
      color: #e5e7eb;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: rgba(15, 23, 42, 0.95);
      border-radius: 18px;
      padding: 24px 26px 22px;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.6);
      width: 420px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      backdrop-filter: blur(16px);
    }
    h1 {
      margin: 0 0 4px;
      font-size: 22px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    h1 span.emoji {
      font-size: 24px;
    }
    p.subtitle {
      margin: 0 0 18px;
      font-size: 13px;
      color: #9ca3af;
    }
    label {
      display: block;
      font-size: 13px;
      margin-bottom: 6px;
      color: #cbd5f5;
    }
    input[type="text"] {
      width: 100%;
      padding: 9px 11px;
      border-radius: 10px;
      border: 1px solid #1f2937;
      background: #020617;
      color: #e5e7eb;
      font-size: 13px;
      outline: none;
      box-sizing: border-box;
    }
    input[type="text"]:focus {
      border-color: #22c55e;
      box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.6);
    }
    button {
      margin-top: 14px;
      width: 100%;
      border: none;
      border-radius: 999px;
      padding: 10px 12px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      background: linear-gradient(135deg, #22c55e, #16a34a);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    button:disabled {
      opacity: 0.6;
      cursor: default;
    }
    .status {
      margin-top: 10px;
      font-size: 12px;
      color: #9ca3af;
      min-height: 18px;
    }
    .status.ok {
      color: #4ade80;
    }
    .status.err {
      color: #f97373;
    }
    .spinner {
      width: 14px;
      height: 14px;
      border-radius: 999px;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      animation: spin 0.7s linear infinite;
      display: none;
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  </style>
</head>
<body>
  <div class="card">
    <h1><span class="emoji">🎬</span> YouTube MP4 Downloader</h1>
    <p class="subtitle">Cole a URL do vídeo do YouTube e ele será baixado em MP4 na sua pasta Downloads.</p>

    <form method="POST" id="download-form">
      <label for="url">URL do vídeo</label>
      <input type="text" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required>
      
      <label for="quality" style="margin-top: 12px;">Qualidade</label>
      <select id="quality" name="quality" style="width: 100%; padding: 9px 11px; border-radius: 10px; border: 1px solid #1f2937; background: #020617; color: #e5e7eb; font-size: 13px; outline: none; box-sizing: border-box;">
        <option value="best">🔥 Melhor qualidade disponível</option>
        <option value="8k">🌟 8K (7680p) - Ultra HD</option>
        <option value="4k">💎 4K (2160p) - Ultra HD</option>
        <option value="2k">🎯 2K (1440p) - Quad HD</option>
        <option value="1080p">📺 1080p (Full HD)</option>
        <option value="720p">📱 720p (HD)</option>
        <option value="480p">💻 480p (SD)</option>
        <option value="360p">📞 360p (Baixa)</option>
        <option value="worst">⚡ Menor arquivo (pior qualidade)</option>
      </select>

      <button type="submit" id="download-button">
        <span class="btn-text">⬇️ Baixar MP4</span>
        <span class="spinner" id="btn-spinner"></span>
      </button>
    </form>

    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% else %}
      <div class="status">Pronto para baixar.</div>
    {% endif %}
  </div>

  <script>
    const form = document.getElementById('download-form');
    const button = document.getElementById('download-button');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.getElementById('btn-spinner');

    form.addEventListener('submit', () => {
      // desabilita botao e mostra loading
      button.disabled = true;
      if (btnText) btnText.textContent = 'Baixando...';
      if (spinner) spinner.style.display = 'inline-block';
    });
  </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    status = None
    error = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        quality = request.form.get("quality", "best")
        if not url:
            error = "Insira uma URL válida."
        else:
            try:
                # Usar a pasta Downloads do usuário
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                # Formatos priorizando MP4 e suportando altas resoluções
                format_map = {
                    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
                    "8k": "bestvideo[height<=7680][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=7680]+bestaudio/best[height<=7680][ext=mp4]/best[height<=7680]",
                    "4k": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160][ext=mp4]/best[height<=2160]",
                    "2k": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440][ext=mp4]/best[height<=1440]",
                    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080][ext=mp4]/best[height<=1080]",
                    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720][ext=mp4]/best[height<=720]", 
                    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]",
                    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360][ext=mp4]/best[height<=360]",
                    "worst": "worst[ext=mp4]/worst"
                }
                
                ydl_opts = {
                    "format": format_map.get(quality, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"),
                    "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                    "noplaylist": True,
                    "merge_output_format": "mp4",
                    "prefer_free_formats": False,
                    "format_sort": ["res", "ext:mp4", "codec:h264"],
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Verificar se a URL é válida primeiro
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Video')
                    
                    # Fazer o download
                    ydl.download([url])
                    
                quality_text = {
                    "best": "melhor qualidade",
                    "8k": "8K (7680p)",
                    "4k": "4K (2160p)",
                    "2k": "2K (1440p)",
                    "1080p": "1080p", 
                    "720p": "720p",
                    "480p": "480p",
                    "360p": "360p",
                    "worst": "menor arquivo"
                }.get(quality, quality)
                
                status = f"✅ '{title}' baixado em {quality_text} na pasta Downloads!"
                
            except yt_dlp.DownloadError as e:
                error = f"Erro no download: {str(e)}"
            except Exception as e:
                error = f"Erro inesperado: {str(e)}"

    return render_template_string(HTML, status=status, error=error)


if __name__ == "__main__":
    # host=0.0.0.0 se quiser abrir em outros devices da rede
    app.run(debug=True)
