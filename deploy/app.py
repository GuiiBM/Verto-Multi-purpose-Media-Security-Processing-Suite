from flask import Flask, request, render_template_string, jsonify
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube MP4 Downloader</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🎬%3C/text%3E%3C/svg%3E">
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
        select {
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
        <p class="subtitle">Cole a URL do vídeo do YouTube e ele será baixado em MP4.</p>

        <form method="POST" id="download-form">
            <label for="url">URL do vídeo</label>
            <input type="text" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required>
            
            <label for="quality" style="margin-top: 12px;">Qualidade</label>
            <select id="quality" name="quality">
                <option value="best">🔥 Melhor qualidade disponível</option>
                <option value="1080p">📺 1080p (Full HD)</option>
                <option value="720p">📱 720p (HD)</option>
                <option value="480p">💻 480p (SD)</option>
                <option value="360p">📞 360p (Baixa)</option>
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
                downloads_dir = "/tmp/downloads"
                os.makedirs(downloads_dir, exist_ok=True)
                
                format_map = {
                    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
                    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]", 
                    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
                    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]"
                }
                
                ydl_opts = {
                    "format": format_map.get(quality, "best[ext=mp4]/best"),
                    "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                    "noplaylist": True,
                    "merge_output_format": "mp4"
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Video')
                    ydl.download([url])
                    
                quality_text = {"best": "melhor qualidade", "1080p": "1080p", "720p": "720p", "480p": "480p", "360p": "360p"}.get(quality, quality)
                status = f"✅ '{title}' baixado em {quality_text} na pasta Downloads!"
                
            except Exception as e:
                error = f"Erro no download: {str(e)}"

    return render_template_string(HTML, status=status, error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))