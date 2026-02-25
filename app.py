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
  <title>Verto - Conversor de Mídia Profissional</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: 
        radial-gradient(at 0% 0%, rgba(34, 197, 94, 0.08) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(59, 130, 246, 0.06) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.05) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 60px 20px;
      position: relative;
      overflow-x: hidden;
    }
    body::before {
      content: '';
      position: fixed;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(148, 163, 184, 0.03) 2px,
        rgba(148, 163, 184, 0.03) 4px
      );
      animation: grid-move 20s linear infinite;
      pointer-events: none;
    }
    @keyframes grid-move {
      0% { transform: translateY(0); }
      100% { transform: translateY(50px); }
    }
    .logo-container {
      position: relative;
      margin-bottom: 20px;
      padding: 10px 0;
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #22c55e 0%, #16a34a 50%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 18px;
      text-transform: uppercase;
      position: relative;
      filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4));
      animation: glow-pulse 3s ease-in-out infinite;
    }
    @keyframes glow-pulse {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4)); }
      50% { filter: drop-shadow(0 0 35px rgba(34, 197, 94, 0.9)) drop-shadow(0 0 70px rgba(59, 130, 246, 0.6)); }
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      font-weight: 500;
      letter-spacing: 0.5px;
      position: relative;
      z-index: 1;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 20px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(34, 197, 94, 0.05);
      width: 90vw;
      max-width: 520px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      z-index: 1;
    }
    .card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.5px;
    }
    p.subtitle {
      margin: 0 0 32px;
      font-size: 14px;
      color: #94a3b8;
      font-weight: 400;
      line-height: 1.6;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #cbd5e1;
      letter-spacing: 0.3px;
    }
    input[type="text"] {
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.8);
      color: #f1f5f9;
      font-size: 14px;
      outline: none;
      transition: all 0.2s;
    }
    input[type="text"]:focus {
      border-color: #22c55e;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
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
    .preview {
      margin-top: 16px;
      padding: 12px;
      background: rgba(30, 41, 59, 0.6);
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      display: none;
    }
    .preview.show {
      display: block;
    }
    .preview img {
      width: 100%;
      border-radius: 8px;
      margin-bottom: 8px;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .preview img:hover {
      opacity: 0.8;
    }
    .preview img.image-format {
      cursor: zoom-in;
    }
    .preview img.image-format:hover {
      opacity: 1;
      transform: scale(1.02);
    }
    .preview iframe {
      width: 100%;
      height: 220px;
      border-radius: 8px;
      margin-bottom: 8px;
      border: none;
    }
    .preview h3 {
      margin: 0 0 6px;
      font-size: 14px;
      color: #e5e7eb;
    }
    .preview p {
      margin: 0;
      font-size: 12px;
      color: #9ca3af;
    }
    .preview-loading {
      text-align: center;
      padding: 20px;
      color: #9ca3af;
      font-size: 12px;
    }
    .format-selector {
      display: flex;
      gap: 12px;
      margin-bottom: 40px;
      justify-content: center;
      flex-wrap: wrap;
      position: relative;
      z-index: 1;
    }
    .format-btn {
      padding: 14px 28px;
      border-radius: 14px;
      border: 1.5px solid rgba(148, 163, 184, 0.12);
      background: rgba(15, 23, 42, 0.4);
      color: #94a3b8;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      backdrop-filter: blur(20px);
      position: relative;
      overflow: hidden;
    }
    .format-btn::after {
      content: '';
      position: absolute;
      top: 50%;
      left: 50%;
      width: 0;
      height: 0;
      border-radius: 50%;
      background: rgba(34, 197, 94, 0.1);
      transform: translate(-50%, -50%);
      transition: width 0.6s, height 0.6s;
    }
    .format-btn:hover::after {
      width: 300px;
      height: 300px;
    }
    .format-btn:hover {
      border-color: rgba(34, 197, 94, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      transform: translateY(-2px);
      box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
    }
    .format-btn.active {
      border-color: #22c55e;
      background: rgba(34, 197, 94, 0.12);
      color: #22c55e;
      box-shadow: 0 0 24px rgba(34, 197, 94, 0.2), 0 4px 12px rgba(0, 0, 0, 0.3);
    }
    .format-btn span {
      position: relative;
      z-index: 1;
    }
    .image-modal {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.9);
      z-index: 2000;
      justify-content: center;
      align-items: center;
      cursor: zoom-out;
    }
    .image-modal img {
      max-width: 90%;
      max-height: 90%;
      border-radius: 8px;
    }
    @media (max-width: 640px) {
      body { padding: 30px 15px; }
      .logo { font-size: 48px; letter-spacing: 12px; }
      .tagline { font-size: 13px; margin-bottom: 32px; }
      .format-selector { gap: 8px; margin-bottom: 32px; }
      .format-btn { padding: 12px 20px; font-size: 13px; }
      .card { padding: 28px 20px; border-radius: 20px; width: 95vw; }
      h1 { font-size: 24px; }
      p.subtitle { font-size: 13px; margin-bottom: 24px; }
    }
    @media (min-width: 641px) and (max-width: 1024px) {
      .card { width: 85vw; max-width: 600px; }
    }
    @media (min-width: 1025px) {
      .card { width: 80vw; max-width: 700px; padding: 48px; }
      .logo { font-size: 80px; letter-spacing: 20px; }
    }
    @media (max-width: 480px) {
      .logo { font-size: 40px; letter-spacing: 8px; }
      .format-btn { padding: 10px 16px; font-size: 12px; }
      .card { padding: 24px 16px; width: 96vw; }
      h1 { font-size: 22px; }
      input[type="text"], select { padding: 12px 14px; font-size: 13px; }
      button { padding: 14px; font-size: 14px; }
    }
    @media (min-width: 768px) and (max-width: 1024px) {
      .logo { font-size: 64px; letter-spacing: 16px; }
      .card { padding: 36px; }
    }
  </style>
</head>
<body>
  <div class="logo-container">
    <div class="logo">VERTO</div>
  </div>
  <div class="tagline">Conversor de Vídeos do Youtube Profissional</div>
  
  <div class="format-selector">
    <div class="format-btn active" data-format="mp4"><span>🎬 MP4</span></div>
    <div class="format-btn" data-format="mp3"><span>🎵 MP3</span></div>
    <div class="format-btn" data-format="thumbnail"><span>🖼️ PNG</span></div>
    <div class="format-btn" data-format="jpg"><span>🖼️ JPG</span></div>
  </div>

  <div class="card">
    <h1>Convert Media</h1>
    <p class="subtitle">Paste YouTube URL and select your preferred format</p>

    <form method="POST" id="download-form">
      <label for="url">URL do vídeo</label>
      <input type="text" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required>
      
      <input type="hidden" id="format" name="format" value="mp4">
      
      <label for="quality" id="quality-label" style="margin-top: 12px;">Qualidade</label>
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
        <span class="btn-text">⬇️ Baixar</span>
        <span class="spinner" id="btn-spinner"></span>
      </button>
    </form>

    <div class="preview" id="preview">
      <div class="preview-loading" id="preview-loading">Carregando preview...</div>
      <div id="preview-content" style="display: none;">
        <img id="preview-thumb" src="" alt="Thumbnail" onclick="playVideo()">
        <div id="preview-player" style="display: none;"></div>
        <h3 id="preview-title"></h3>
        <p id="preview-duration"></p>
      </div>
    </div>

    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% else %}
      <div class="status">Pronto para baixar.</div>
    {% endif %}
  </div>

  <div class="image-modal" id="image-modal" onclick="closeImageModal()">
    <img id="modal-image" src="" alt="">
  </div>

  <script>
    const form = document.getElementById('download-form');
    const button = document.getElementById('download-button');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.getElementById('btn-spinner');
    const urlInput = document.getElementById('url');
    const preview = document.getElementById('preview');
    const previewLoading = document.getElementById('preview-loading');
    const previewContent = document.getElementById('preview-content');
    const previewThumb = document.getElementById('preview-thumb');
    const previewTitle = document.getElementById('preview-title');
    const previewDuration = document.getElementById('preview-duration');
    const previewPlayer = document.getElementById('preview-player');

    let debounceTimer;
    let currentVideoId = '';

    const qualitySelect = document.getElementById('quality');
    let currentFormat = 'mp4';
    const formatInput = document.getElementById('format');

    const formatBtns = document.querySelectorAll('.format-btn');

    formatBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        formatBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFormat = btn.dataset.format;
        formatInput.value = currentFormat;
        updateQualityOptions();
      });
    });

    function updateQualityOptions() {
      let options;
      if (currentFormat === 'mp3') {
        options = mp3Options;
      } else if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
        options = thumbnailOptions;
      } else {
        options = mp4Options;
      }
      qualitySelect.innerHTML = options.map(opt => `<option value="${opt.value}">${opt.text}</option>`).join('');
    }

    const mp4Options = [
      { value: 'best', text: '🔥 Melhor qualidade disponível' },
      { value: '8k', text: '🌟 8K (7680p) - Ultra HD' },
      { value: '4k', text: '💎 4K (2160p) - Ultra HD' },
      { value: '2k', text: '🎯 2K (1440p) - Quad HD' },
      { value: '1080p', text: '📺 1080p (Full HD)' },
      { value: '720p', text: '📱 720p (HD)' },
      { value: '480p', text: '💻 480p (SD)' },
      { value: '360p', text: '📞 360p (Baixa)' },
      { value: 'worst', text: '⚡ Menor arquivo (pior qualidade)' }
    ];

    const mp3Options = [
      { value: 'best', text: '🔥 Melhor qualidade disponível' },
      { value: '320', text: '📺 320 kbps (Alta)' },
      { value: '256', text: '📱 256 kbps' },
      { value: '192', text: '💻 192 kbps (Média)' },
      { value: '128', text: '📞 128 kbps (Baixa)' },
      { value: 'worst', text: '⚡ Menor arquivo (pior qualidade)' }
    ];

    const thumbnailOptions = [
      { value: 'maxres', text: '🔥 Máxima resolução' },
      { value: 'high', text: '📺 Alta qualidade' },
      { value: 'medium', text: '📱 Média qualidade' },
      { value: 'default', text: '📞 Padrão' }
    ];

    function playVideo() {
      if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
        const modal = document.getElementById('image-modal');
        const modalImage = document.getElementById('modal-image');
        modalImage.src = previewThumb.src;
        modal.style.display = 'flex';
      } else {
        previewThumb.style.display = 'none';
        previewPlayer.style.display = 'block';
        previewPlayer.innerHTML = `<iframe src="https://www.youtube.com/embed/${currentVideoId}?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`;
      }
    }

    function closeImageModal() {
      document.getElementById('image-modal').style.display = 'none';
    }

    urlInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      const url = e.target.value.trim();
      
      if (!url || !isYouTubeUrl(url)) {
        preview.classList.remove('show');
        return;
      }
      
      debounceTimer = setTimeout(() => loadPreview(url), 800);
    });

    function isYouTubeUrl(url) {
      return /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/.test(url);
    }

    async function loadPreview(url) {
      preview.classList.add('show');
      previewLoading.style.display = 'block';
      previewContent.style.display = 'none';
      
      try {
        const response = await fetch('/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        
        const result = await response.json();
        
        if (result.success) {
          currentVideoId = result.video_id;
          previewThumb.src = result.thumbnail;
          previewThumb.style.display = 'block';
          if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
            previewThumb.className = 'image-format';
          } else {
            previewThumb.className = '';
          }
          previewPlayer.style.display = 'none';
          previewPlayer.innerHTML = '';
          previewTitle.textContent = result.title;
          previewDuration.textContent = `Duração: ${result.duration}`;
          previewLoading.style.display = 'none';
          previewContent.style.display = 'block';
        } else {
          preview.classList.remove('show');
        }
      } catch (error) {
        preview.classList.remove('show');
      }
    }

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

@app.route("/preview", methods=["POST"])
def preview():
    data = request.get_json()
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"success": False})
    
    try:
        ydl_opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60
            return jsonify({
                "success": True,
                "title": info.get('title', 'Sem título'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": f"{minutes}:{seconds:02d}",
                "video_id": info.get('id', '')
            })
    except:
        return jsonify({"success": False})

@app.route("/", methods=["GET", "POST"])
def index():
    status = None
    error = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        format_type = request.form.get("format", "mp4")
        quality = request.form.get("quality", "best")
        if not url:
            error = "Insira uma URL válida."
        else:
            try:
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                if format_type == "mp3":
                    if quality in ['best', 'worst']:
                        audio_quality = '0' if quality == 'best' else '9'
                    else:
                        audio_quality = quality
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": audio_quality,
                        }]
                    }
                elif format_type == "thumbnail":
                    ydl_opts = {
                        "skip_download": True,
                        "writethumbnail": True,
                        "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegThumbnailsConvertor",
                            "format": "png"
                        }]
                    }
                elif format_type == "jpg":
                    ydl_opts = {
                        "skip_download": True,
                        "writethumbnail": True,
                        "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegThumbnailsConvertor",
                            "format": "jpg"
                        }]
                    }
                else:
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
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Video')
                    ydl.download([url])
                    
                if format_type == "mp3":
                    quality_text = {'best': 'melhor qualidade', 'worst': 'menor arquivo'}.get(quality, f"{quality}kbps")
                    status = f"✅ '{title}' baixado em MP3 {quality_text} na pasta Downloads!"
                elif format_type == "thumbnail":
                    status = f"✅ Thumbnail de '{title}' salva em PNG na pasta Downloads!"
                elif format_type == "jpg":
                    status = f"✅ Thumbnail de '{title}' salva em JPG na pasta Downloads!"
                else:
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
