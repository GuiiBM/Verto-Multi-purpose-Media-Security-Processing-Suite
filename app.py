from flask import Flask, request, render_template_string, jsonify, Response, send_file
import yt_dlp
import os
import time
import shutil
import io
import zipfile
import tarfile
import gzip
import bz2
import lzma
from pathlib import Path
import json
try:
    from PIL import Image
except:
    pass
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from PDFs.pdfs_templates import PDFS_SPLIT_HTML, PDFS_CONVERT_HTML
from Office.office_templates import OFFICE_HUB_HTML, OFFICE_CONVERT_HTML, OFFICE_REPAIR_HTML
from Office import office_engine
from DevData.devdata_templates import (
    DEVDATA_HUB_HTML, DEVDATA_FORMAT_HTML, DEVDATA_MOCK_HTML,
    DEVDATA_CONVERT_HTML, DEVDATA_ENCODE_HTML,
)
from ImageStudio.imagestudio_templates import (
    IMAGESTUDIO_HUB_HTML, IMAGESTUDIO_SOLO_HTML, IMAGESTUDIO_RESIZE_HTML,
    IMAGESTUDIO_FILTERS_HTML, IMAGESTUDIO_FAVICON_HTML,
)
from TextClean.textclean_templates import (
    TEXTCLEAN_HUB_HTML, TEXTCLEAN_DIFF_HTML, TEXTCLEAN_SANITIZE_HTML, TEXTCLEAN_STATS_HTML,
)
from CaptureOCR.captureocr_templates import (
    CAPTUREOCR_HUB_HTML, CAPTUREOCR_OCR_HTML, CAPTUREOCR_RECORD_HTML,
)
from AIGuard.aiguard_templates import (
    AIGUARD_HUB_HTML, AIGUARD_DETECT_HTML, AIGUARD_HUMANIZE_HTML, AIGUARD_PLAGIARISM_HTML,
)
from SmartStudio.smartstudio_templates import (
    SMARTSTUDIO_HUB_HTML, SMARTSTUDIO_STUDIO_HTML, SMARTSTUDIO_EDITOR_HTML,
)
from SubtitleLab.subtitlelab_templates import (
    SUBTITLELAB_HUB_HTML, SUBTITLELAB_EDITOR_HTML, SUBTITLELAB_BURN_HTML,
)
from SubtitleLab import subtitlelab_engine
from MatchaEffect.matchaeffect_templates import (
    MATCHAEFFECT_HUB_HTML, MATCHAEFFECT_ADD_HTML, MATCHAEFFECT_REMOVE_HTML,
    MATCHAEFFECT_VIDEO_ADD_HTML, MATCHAEFFECT_VIDEO_REMOVE_HTML,
    MATCHAEFFECT_AI_ADD_HTML, MATCHAEFFECT_AI_REMOVE_HTML, MATCHAEFFECT_AI_VIDEO_HTML,
    MATCHAEFFECT_AI_VIDEO_REMOVE_HTML,
)
from MatchaEffect import matchaeffect_ai_engine
from InstaSaver.instasaver_templates import INSTASAVER_HTML
from InstaSaver import instasaver_engine

app = Flask(__name__)

# Desde meados de 2026 o YouTube passou a exigir a resolução de um desafio em
# JavaScript para liberar a maioria dos formatos de vídeo/áudio. Sem um
# runtime JS habilitado, o yt-dlp falha silenciosamente e reporta erros
# genéricos como "This video is not available" mesmo em vídeos perfeitamente
# disponíveis. O pacote yt-dlp-ejs traz o script resolvedor embutido (sem
# precisar baixar nada da internet a cada chamada); só falta um runtime JS
# (deno/node/bun/quickjs) para executá-lo - usamos o que já estiver instalado
# no sistema, ou o Deno baixado pelo INSTALAR.py na pasta do app.
def _detect_js_runtimes():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    runtimes = {}
    for name in ("deno", "node", "bun", "quickjs"):
        bundled = os.path.join(base_dir, f"{name}.exe" if os.name == "nt" else name)
        path = bundled if os.path.isfile(bundled) else shutil.which(name)
        if path:
            runtimes[name] = {"path": path}
    return runtimes


YTDLP_JS_RUNTIMES = _detect_js_runtimes()
# Se nenhum runtime JS local for encontrado, ainda tentamos buscar o script
# resolvedor direto do GitHub como último recurso (precisa de internet).
YTDLP_REMOTE_COMPONENTS = [] if YTDLP_JS_RUNTIMES else ["ejs:github"]


def with_js_runtime(opts):
    """Adiciona o runtime JS (e o fallback remoto) a um dict de opções do yt-dlp."""
    if YTDLP_JS_RUNTIMES:
        opts["js_runtimes"] = YTDLP_JS_RUNTIMES
    if YTDLP_REMOTE_COMPONENTS:
        opts["remote_components"] = YTDLP_REMOTE_COMPONENTS
    return opts


def yt_dlp_opts(**extra):
    """Opções padrão (silenciosas) para consultas rápidas ao YouTube, já com
    o runtime JS habilitado."""
    opts = with_js_runtime({"quiet": True, "no_warnings": True})
    opts.update(extra)
    return opts


def friendly_yt_dlp_error(exc):
    """Traduz os erros mais comuns do yt-dlp para mensagens compreensíveis."""
    msg = str(exc)
    lower = msg.lower()
    if "private video" in lower:
        return "Este vídeo é privado e não pode ser baixado."
    if "sign in to confirm" in lower and "age" in lower:
        return "Este vídeo tem restrição de idade e exige login para ser baixado."
    if "members-only" in lower or "join this channel" in lower:
        return "Este vídeo é exclusivo para membros do canal e não pode ser baixado."
    if "copyright" in lower:
        return "Este vídeo foi removido por motivo de direitos autorais."
    if ("live event" in lower and "start" in lower) or "premiere" in lower:
        return "Esta transmissão ainda não começou."
    if "unavailable" in lower or "not available" in lower or "removed" in lower:
        return "Este vídeo não está disponível (pode ter sido removido, tornado privado ou bloqueado na sua região)."
    return msg

MENU_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Menu de Apps</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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
      justify-content: center;
      padding: 40px 20px;
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
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4));
      animation: glow-pulse 3s ease-in-out infinite;
      margin-bottom: 10px;
      position: relative;
      z-index: 1;
    }
    @keyframes glow-pulse {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4)); }
      50% { filter: drop-shadow(0 0 35px rgba(34, 197, 94, 0.9)) drop-shadow(0 0 70px rgba(59, 130, 246, 0.6)); }
    }
    .time {
      color: white;
      font-size: 48px;
      font-weight: 300;
      margin-bottom: 10px;
      position: relative;
      z-index: 1;
    }
    .date {
      color: rgba(255,255,255,0.9);
      font-size: 20px;
      margin-top: 10px;
      margin-bottom: 8px;
      position: relative;
      z-index: 1;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 60px;
      font-weight: 500;
      letter-spacing: 0.5px;
      position: relative;
      z-index: 1;
    }
    .apps-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 32px;
      max-width: 600px;
      position: relative;
      z-index: 1;
    }
    .app {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      transition: transform 0.2s;
      text-decoration: none;
    }
    .app:active { transform: scale(0.95); }
    .app-icon {
      width: 90px;
      height: 90px;
      background: rgba(15, 23, 42, 0.4);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 44px;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 20px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(34, 197, 94, 0.05);
      border: 1px solid rgba(148, 163, 184, 0.08);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }
    .app-icon::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    }
    .app:hover .app-icon {
      background: rgba(15, 23, 42, 0.6);
      transform: translateY(-4px);
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.2),
        0 24px 70px rgba(0, 0, 0, 0.7),
        0 0 100px rgba(34, 197, 94, 0.1);
      border-color: rgba(34, 197, 94, 0.2);
    }
    .app-name { 
      color: #cbd5e1;
      font-size: 14px;
      font-weight: 600;
      text-align: center;
      letter-spacing: 0.3px;
    }
    .youtube-icon {
      width: 50px;
      height: 50px;
      position: relative;
    }
    .youtube-icon svg {
      width: 100%;
      height: 100%;
    }

    .neon-icon-verto {
      filter: drop-shadow(0 0 8px rgba(34, 197, 94, 0.5));
    }

    .neon-icon-purpleflix {
      filter: drop-shadow(0 0 8px rgba(188, 19, 255, 0.5));
    }

    .neon-icon-tempo {
      filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.5));
    }

    .neon-icon-pdf {
      filter: drop-shadow(0 0 8px rgba(239, 68, 68, 0.5));
    }

    @media (max-width: 640px) {
      .logo { font-size: 48px; letter-spacing: 12px; }
      .time { font-size: 36px; }
      .date { font-size: 14px; margin-bottom: 30px; }
      .tagline { font-size: 13px; margin-bottom: 40px; }
      .apps-grid { grid-template-columns: repeat(3, 1fr); gap: 24px; }
      .app-icon { width: 75px; height: 75px; font-size: 36px; }
    }
    @media (max-width: 480px) {
      .logo { font-size: 40px; letter-spacing: 8px; }
      .time { font-size: 32px; }
      .date { font-size: 13px; }
      .app-icon { width: 70px; height: 70px; font-size: 32px; }
      .apps-grid { grid-template-columns: repeat(2, 1fr); }
    }
  </style>
</head>
<body>
  <div class="logo">LOCALTOOLS</div>
  <div class="date" id="date">Segunda, 1 de Janeiro</div>
  <div class="time" id="time">12:00</div>
  <div class="tagline">Menu de Aplicativos</div>
  <div class="apps-grid">
    <a href="/verto" class="app">
      <div class="app-icon">
        <div class="youtube-icon neon-icon-verto">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" fill="url(#gradient)"/>
            <defs>
              <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:1" />
                <stop offset="25%" style="stop-color:#16a34a;stop-opacity:1" />
                <stop offset="50%" style="stop-color:#22c55e;stop-opacity:1" />
                <stop offset="75%" style="stop-color:#16a34a;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#3b82f6;stop-opacity:1" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      <div class="app-name">Verto</div>
    </a>
    <a href="/instructions" class="app">
      <div class="app-icon">📖</div>
      <div class="app-name">Instruções</div>
    </a>
    <a href="/files" class="app">
      <div class="app-icon">📁</div>
      <div class="app-name">Arquivos</div>
    </a>
    <a href="/purpleflix" class="app">
      <div class="app-icon">
        <div class="youtube-icon neon-icon-purpleflix"">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z" fill="url(#gradient2)"/>
            <defs>
              <linearGradient id="gradient2" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#9333ea;stop-opacity:1" />
                <stop offset="50%" style="stop-color:#a855f7;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#c084fc;stop-opacity:1" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      <div class="app-name">PurpleFlix</div>
    </a>
    <a href="/tempo" class="app">
      <div class="app-icon">
        <div class="youtube-icon neon-icon-tempo">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="9" stroke="url(#gradient3)" stroke-width="2"/>
            <path d="M12 6v6l4 2" stroke="url(#gradient3)" stroke-width="2" stroke-linecap="round"/>
            <defs>
              <linearGradient id="gradient3" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:1" />
                <stop offset="50%" style="stop-color:#60a5fa;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#93c5fd;stop-opacity:1" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      <div class="app-name">Tempo</div>
    </a>
    <a href="/pdfs" class="app">
      <div class="app-icon">
        <div class="youtube-icon neon-icon-pdf">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" fill="url(#gradient4)" stroke="url(#gradient4)" stroke-width="1.5"/>
            <path d="M14 2v6h6" stroke="url(#gradient4)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <text x="12" y="17" font-size="6" font-weight="bold" fill="#fff" text-anchor="middle">PDF</text>
            <defs>
              <linearGradient id="gradient4" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#ef4444;stop-opacity:1" />
                <stop offset="50%" style="stop-color:#dc2626;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#b91c1c;stop-opacity:1" />
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      <div class="app-name">PDFs</div>
    </a>
    <a href="/office" class="app">
      <div class="app-icon">🗃️</div>
      <div class="app-name">Office</div>
    </a>
    <a href="/transparent" class="app">
      <div class="app-icon">🎨</div>
      <div class="app-name">Transparência</div>
    </a>
    <a href="/qrcode" class="app">
      <div class="app-icon">🔲</div>
      <div class="app-name">QR Code</div>
    </a>
    <a href="/compress" class="app">
      <div class="app-icon">🗜️</div>
      <div class="app-name">Compressor</div>
    </a>
    <a href="/transcribe" class="app">
      <div class="app-icon">🎤</div>
      <div class="app-name">Transcrever</div>
    </a>
    <a href="/ghost" class="app">
      <div class="app-icon">👻</div>
      <div class="app-name">Ghost Tool</div>
    </a>
    <a href="/stealth" class="app">
      <div class="app-icon">🕵️</div>
      <div class="app-name">Stealth</div>
    </a>
    <a href="/censor" class="app">
      <div class="app-icon">🔒</div>
      <div class="app-name">Censor</div>
    </a>
    <a href="/social" class="app">
      <div class="app-icon">📱</div>
      <div class="app-name">Social Preview</div>
    </a>
    <a href="/clean" class="app">
      <div class="app-icon">🧹</div>
      <div class="app-name">Clean Reader</div>
    </a>
    <a href="/isolate" class="app">
      <div class="app-icon">🎤</div>
      <div class="app-name">Isolador de Voz</div>
    </a>
    <a href="/devdata" class="app">
      <div class="app-icon">🧰</div>
      <div class="app-name">Dev/Data</div>
    </a>
    <a href="/imagestudio" class="app">
      <div class="app-icon">🖌️</div>
      <div class="app-name">Image Studio</div>
    </a>
    <a href="/textclean" class="app">
      <div class="app-icon">🔀</div>
      <div class="app-name">Text Clean & Diff</div>
    </a>
    <a href="/captureocr" class="app">
      <div class="app-icon">🔍</div>
      <div class="app-name">Capture & OCR</div>
    </a>
    <a href="/aiguard" class="app">
      <div class="app-icon">🛡️</div>
      <div class="app-name">AI Guard & Diff</div>
    </a>
    <a href="/smartstudio" class="app">
      <div class="app-icon">🎙️</div>
      <div class="app-name">Smart Studio</div>
    </a>
    <a href="/subtitlelab" class="app">
      <div class="app-icon">📝</div>
      <div class="app-name">Subtitle Lab</div>
    </a>
    <a href="/matchaeffect" class="app">
      <div class="app-icon">🍵</div>
      <div class="app-name">Matcha Effect</div>
    </a>
    <a href="/instasaver" class="app">
      <div class="app-icon">📸</div>
      <div class="app-name">InstaSaver</div>
    </a>
  </div>
  <script>
    function updateTime() {
      const now = new Date();
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      document.getElementById('time').textContent = `${hours}:${minutes}`;
      const days = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];
      const months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
      document.getElementById('date').textContent = `${days[now.getDay()]}, ${now.getDate()} de ${months[now.getMonth()]}`;
    }
    updateTime();
    setInterval(updateTime, 1000);
  </script>
</body>
</html>
"""

VERTO_HTML = """
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
      padding: 40px 15px;
      position: relative;
      overflow-x: hidden;
    }
    .main-container {
      display: flex;
      flex-direction: row;
      gap: 20px;
      width: 100%;
      max-width: 1200px;
      align-items: flex-start;
      justify-content: center;
      margin: 0 auto;
      flex-wrap: wrap;
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
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
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
      width: 100%;
      max-width: 520px;
      min-width: 320px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      z-index: 1;
      flex: 1 1 520px;
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
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: 100%;
      width: 100%;
    }
    .preview-loading {
      text-align: center;
      padding: 20px;
      color: #9ca3af;
      font-size: 12px;
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #preview-content {
      display: flex;
      flex-direction: column;
      height: 100%;
      justify-content: space-between;
    }
    .preview-info {
      margin-top: 20px;
      padding-top: 15px;
      border-top: 1px solid rgba(255,255,255,0.05);
    }
    .preview-card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 24px;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 20px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(34, 197, 94, 0.05);
      width: 100%;
      max-width: 520px;
      min-width: 320px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      z-index: 1;
      display: none;
      flex-direction: column;
      flex: 1 1 520px;
    }
    .preview-card.show {
      display: flex !important;
    }
    .preview.show {
      display: block;
    }
    .preview img {
      width: 100%;
      border-radius: 8px;
      cursor: pointer;
      transition: opacity 0.2s;
      flex-shrink: 0;
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
      aspect-ratio: 16 / 9;
      height: auto;
      border-radius: 12px;
      border: none;
      flex-shrink: 0;
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
      width: 100%;
      max-width: 520px;
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
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
      font-size: 28px;
      color: #cbd5e1;
      font-weight: 700;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 8px 24px rgba(0, 0, 0, 0.5),
        0 0 40px rgba(34, 197, 94, 0.03);
      line-height: 1;
    }
    .back-button::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
      box-shadow: 
        0 0 0 1px rgba(34, 197, 94, 0.2),
        0 12px 32px rgba(0, 0, 0, 0.6),
        0 0 60px rgba(34, 197, 94, 0.15);
    }
    .back-button:active {
      transform: translateX(-4px) scale(0.96);
    }
    @media (max-width: 640px) {
      body { padding: 30px 10px; padding-top: 100px; }
      .logo { font-size: 48px; letter-spacing: 12px; }
      .tagline { font-size: 13px; margin-bottom: 32px; }
      .main-container { flex-direction: column; align-items: center; }
      .card { padding: 24px 16px; }
      .preview-card { padding: 20px 16px; }
      h1 { font-size: 24px; }
      p.subtitle { font-size: 13px; }
      label { font-size: 13px; }
      input[type="text"] { font-size: 14px; padding: 12px 14px; }
      select { font-size: 13px !important; padding: 10px 12px !important; }
      button { font-size: 14px; padding: 12px 14px; }
      .format-selector { gap: 8px; margin-bottom: 32px; }
      .format-btn { padding: 10px 18px; font-size: 13px; }
      .main-container { gap: 16px; }
    }
    @media (max-width: 480px) {
      body { padding: 20px 8px; padding-top: 90px; }
      .logo { font-size: 40px; letter-spacing: 8px; }
      .tagline { font-size: 12px; margin-bottom: 24px; }
      .card { padding: 20px 12px; border-radius: 20px; }
      .preview-card { padding: 16px 12px; border-radius: 20px; }
      h1 { font-size: 20px; }
      p.subtitle { font-size: 12px; margin-bottom: 24px; }
      .format-btn { padding: 8px 14px; font-size: 12px; border-radius: 10px; }
      .back-button { width: 48px; height: 48px; top: 16px; left: 16px; }
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
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

  <div class="main-container">
    <div class="card">
      <h1>Conversor de Mídia</h1>
      <p class="subtitle">Cole seu URL do Youtube e selecione sua preferência</p>

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

      {% if status %}
        <div class="status ok">{{ status }}</div>
      {% elif error %}
        <div class="status err">{{ error }}</div>
      {% else %}
        <div class="status">Pronto para baixar.</div>
      {% endif %}
    </div>

    <div class="preview-card" id="preview-card">
      <div class="preview" id="preview">
        <div class="preview-loading" id="preview-loading">Carregando preview...</div>
        <div id="preview-content" style="display: none;">
          <img id="preview-thumb" src="" alt="Thumbnail" onclick="playVideo()">
          <div id="preview-player" style="display: none;"></div>
          <div class="preview-info">
            <h3 id="preview-title"></h3>
            <p id="preview-duration"></p>
          </div>
        </div>
      </div>
    </div>
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
        resetPreviewToThumb();
      });
    });

    function resetPreviewToThumb() {
      if (previewPlayer && previewThumb) {
        previewPlayer.style.display = 'none';
        previewPlayer.innerHTML = '';
        previewThumb.style.display = 'block';
        if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
          previewThumb.className = 'image-format';
        } else {
          previewThumb.className = '';
        }
      }
    }

    function updateQualityOptions() {
      let options;
      if (currentFormat === 'mp3') {
        options = mp3Options;
      } else if (currentFormat === 'thumbnail') {
        options = thumbnailOptions;
      } else if (currentFormat === 'jpg') {
        options = thumbnailOptions.map(opt => ({
          value: opt.value,
          text: opt.text
        }));
      } else {
        options = mp4Options;
      }
      qualitySelect.innerHTML = options.map(opt => {
        let sizeKey = opt.value;
        if (currentFormat === 'jpg') {
          sizeKey = opt.value + '_jpg';
        }
        const size = formatSizes[sizeKey] || '';
        return `<option value="${opt.value}">${opt.text}${size}</option>`;
      }).join('');
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

    let formatSizes = {};

    function formatBytes(bytes) {
      if (bytes === 0) return '';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return ' - ' + parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

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
      const previewCard = document.getElementById('preview-card');
      
      if (!url || !isYouTubeUrl(url)) {
        previewCard.classList.remove('show');
        return;
      }
      
      debounceTimer = setTimeout(() => loadPreview(url), 800);
    });

    function isYouTubeUrl(url) {
      return /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/.test(url);
    }

    async function loadPreview(url) {
      const previewCard = document.getElementById('preview-card');
      previewCard.classList.add('show');
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
          
          // Buscar tamanhos dos formatos
          loadFormatSizes(url);
        } else {
          previewCard.classList.remove('show');
        }
      } catch (error) {
        previewCard.classList.remove('show');
      }
    }

    async function loadFormatSizes(url) {
      try {
        const response = await fetch('/formats', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        
        const result = await response.json();
        
        if (result.success && result.sizes) {
          formatSizes = {};
          Object.keys(result.sizes).forEach(key => {
            formatSizes[key] = formatBytes(result.sizes[key]);
          });
          updateQualityOptions();
        }
      } catch (error) {
        console.log('Erro ao carregar tamanhos');
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
        with yt_dlp.YoutubeDL(yt_dlp_opts()) as ydl:
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

@app.route("/formats", methods=["POST"])
def get_formats():
    data = request.get_json()
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"success": False})
    
    try:
        sizes = {}
        duration = 0
        
        # Simular exatamente o que será baixado para cada qualidade
        format_map = {
            "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "8k": "bestvideo[height<=7680][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=7680]+bestaudio/best[height<=7680][ext=mp4]/best[height<=7680]",
            "4k": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160][ext=mp4]/best[height<=2160]",
            "2k": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440][ext=mp4]/best[height<=1440]",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080][ext=mp4]/best[height<=1080]",
            "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720][ext=mp4]/best[height<=720]",
            "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]",
            "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360][ext=mp4]/best[height<=360]",
            "worst": "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worstvideo+worstaudio/worst[ext=mp4]/worst"
        }
        
        for quality, format_str in format_map.items():
            try:
                ydl_opts = yt_dlp_opts(format=format_str, skip_download=True)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    duration = info.get('duration', 0)
                    
                    # Pegar tamanho do formato selecionado
                    if 'requested_formats' in info:
                        # Vídeo + Áudio separados
                        total = sum(f.get('filesize') or f.get('filesize_approx', 0) for f in info['requested_formats'])
                        if total > 0:
                            sizes[quality] = total
                    elif 'filesize' in info or 'filesize_approx' in info:
                        # Formato único
                        size = info.get('filesize') or info.get('filesize_approx', 0)
                        if size > 0:
                            sizes[quality] = size
            except:
                pass
        
        # MP3
        if duration:
            sizes['320'] = int(duration * 320 * 1000 / 8)
            sizes['256'] = int(duration * 256 * 1000 / 8)
            sizes['192'] = int(duration * 192 * 1000 / 8)
            sizes['128'] = int(duration * 128 * 1000 / 8)
        
        # Thumbnails - estimar baseado nas resoluções
        try:
            ydl_opts = yt_dlp_opts(skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                thumbnails = info.get('thumbnails', [])
                
                # Mapear resoluções de thumbnail
                thumb_sizes = {}
                for thumb in thumbnails:
                    if 'width' in thumb and 'height' in thumb:
                        width = thumb.get('width', 0)
                        height = thumb.get('height', 0)
                        
                        # Estimar tamanho baseado em resolução (aproximação)
                        # PNG: ~3 bytes por pixel, JPG: ~0.5 bytes por pixel
                        pixels = width * height
                        
                        if width >= 1920:  # maxres
                            thumb_sizes['maxres_png'] = int(pixels * 3)
                            thumb_sizes['maxres_jpg'] = int(pixels * 0.5)
                        elif width >= 640:  # high
                            thumb_sizes['high_png'] = int(pixels * 3)
                            thumb_sizes['high_jpg'] = int(pixels * 0.5)
                        elif width >= 320:  # medium
                            thumb_sizes['medium_png'] = int(pixels * 3)
                            thumb_sizes['medium_jpg'] = int(pixels * 0.5)
                        else:  # default
                            thumb_sizes['default_png'] = int(pixels * 3)
                            thumb_sizes['default_jpg'] = int(pixels * 0.5)
                
                # Adicionar aos sizes
                sizes['maxres'] = thumb_sizes.get('maxres_png', 0)
                sizes['high'] = thumb_sizes.get('high_png', 0)
                sizes['medium'] = thumb_sizes.get('medium_png', 0)
                sizes['default'] = thumb_sizes.get('default_png', 0)
                
                # JPG
                sizes['maxres_jpg'] = thumb_sizes.get('maxres_jpg', 0)
                sizes['high_jpg'] = thumb_sizes.get('high_jpg', 0)
                sizes['medium_jpg'] = thumb_sizes.get('medium_jpg', 0)
                sizes['default_jpg'] = thumb_sizes.get('default_jpg', 0)
        except:
            pass
        
        return jsonify({"success": True, "sizes": sizes})
    except:
        return jsonify({"success": False})

@app.route("/")
def index():
    return render_template_string(MENU_HTML)

@app.route("/verto", methods=["GET", "POST"], strict_slashes=False)
def verto():
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
                
                # Função para gerar nome único
                def get_unique_filename(base_path, title, ext):
                    filename = f"{title}.{ext}"
                    filepath = os.path.join(base_path, filename)
                    if not os.path.exists(filepath):
                        return filename
                    
                    counter = 1
                    while True:
                        filename = f"{title} - cópia {counter}.{ext}"
                        filepath = os.path.join(base_path, filename)
                        if not os.path.exists(filepath):
                            return filename
                        counter += 1
                
                if format_type == "mp3":
                    if quality in ['best', 'worst']:
                        audio_quality = '0' if quality == 'best' else '9'
                    else:
                        audio_quality = quality
                    ydl_opts = with_js_runtime({
                        "format": "bestaudio/best",
                        "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": audio_quality,
                        }]
                    })
                elif format_type in ("thumbnail", "jpg"):
                    # "writethumbnail" sempre baixa a única miniatura que o yt-dlp
                    # escolhe por padrão, ignorando completamente o seletor de
                    # qualidade (maxres/high/medium/default) da interface. Para
                    # respeitar a escolha do usuário, olhamos a lista real de
                    # miniaturas disponíveis e baixamos a que bate com a faixa de
                    # resolução pedida.
                    import requests as _requests

                    with yt_dlp.YoutubeDL(yt_dlp_opts()) as ydl_probe:
                        info = ydl_probe.extract_info(url, download=False)
                    title = info.get('title', 'Video')

                    thumbnails = [t for t in (info.get('thumbnails') or []) if t.get('url')]
                    if not thumbnails:
                        raise Exception("Nenhuma miniatura disponível para este vídeo.")
                    thumbnails.sort(key=lambda t: t.get('width') or 0)

                    if quality == 'maxres':
                        chosen = thumbnails[-1]
                    elif quality == 'high':
                        candidates = [t for t in thumbnails if (t.get('width') or 0) >= 480]
                        chosen = candidates[0] if candidates else thumbnails[-1]
                    elif quality == 'medium':
                        candidates = [t for t in thumbnails if 180 <= (t.get('width') or 0) < 480]
                        chosen = candidates[-1] if candidates else thumbnails[len(thumbnails) // 2]
                    else:
                        chosen = thumbnails[0]

                    resp = _requests.get(chosen['url'], timeout=30)
                    resp.raise_for_status()

                    ext = "png" if format_type == "thumbnail" else "jpg"
                    from PIL import Image
                    img = Image.open(io.BytesIO(resp.content)).convert('RGB')
                    unique_filename = get_unique_filename(downloads_dir, title, ext)
                    img.save(os.path.join(downloads_dir, unique_filename), format='PNG' if ext == 'png' else 'JPEG')

                    if format_type == "thumbnail":
                        status = f"✅ Thumbnail '{unique_filename}' salva em PNG na pasta Downloads!"
                    else:
                        status = f"✅ Thumbnail '{unique_filename}' salva em JPG na pasta Downloads!"
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
                        "worst": "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worstvideo+worstaudio/worst[ext=mp4]/worst"
                    }
                    ydl_opts = with_js_runtime({
                        "format": format_map.get(quality, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"),
                        "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                        "noplaylist": True,
                        "merge_output_format": "mp4",
                        "prefer_free_formats": False,
                        "format_sort": ["res", "ext:mp4", "codec:h264"],
                    })

                # Obter título e extensão
                if format_type not in ["thumbnail", "jpg"]:
                    with yt_dlp.YoutubeDL(yt_dlp_opts()) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', 'Video')
                
                # Determinar extensão final
                if format_type == "mp3":
                    ext = "mp3"
                elif format_type == "thumbnail":
                    ext = "png"
                elif format_type == "jpg":
                    ext = "jpg"
                else:
                    ext = "mp4"
                
                # Gerar nome único (se não for thumbnail, já foi gerado acima)
                if format_type not in ["thumbnail", "jpg"]:
                    unique_filename = get_unique_filename(downloads_dir, title, ext)
                    ydl_opts["outtmpl"] = os.path.join(downloads_dir, unique_filename.replace(f".{ext}", "") + ".%(ext)s")

                    # Baixar
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])

                # Thumbnail/jpg já foram baixados e salvos acima, com a resolução
                # certa e status já definido - nada mais a fazer aqui para eles.
                if format_type == "mp3":
                    quality_text = {'best': 'melhor qualidade', 'worst': 'menor arquivo'}.get(quality, f"{quality}kbps")
                    status = f"✅ '{unique_filename}' baixado em MP3 {quality_text} na pasta Downloads!"
                elif format_type in ("thumbnail", "jpg"):
                    pass
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
                    status = f"✅ '{unique_filename}' baixado em {quality_text} na pasta Downloads!"
                
            except yt_dlp.DownloadError as e:
                error = f"Erro no download: {friendly_yt_dlp_error(e)}"
            except Exception as e:
                error = f"Erro inesperado: {str(e)}"

    return render_template_string(VERTO_HTML, status=status, error=error)

@app.route("/instructions", strict_slashes=False)
@app.route("/config", strict_slashes=False)
def instructions():
    try:
        with open('templates/instructions.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return render_template_string(CONFIG_HTML)

@app.route("/purpleflix", strict_slashes=False)
def purpleflix():
    return render_template_string(PURPLEFLIX_HTML)

@app.route("/tempo", strict_slashes=False)
def tempo():
    try:
        with open('templates/tempo.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return render_template_string(TEMPO_HTML)

@app.route("/api/holidays/<int:year>", methods=["GET"], strict_slashes=False)
def get_holidays(year):
    """API para buscar feriados de um ano específico"""
    try:
        import json
        from datetime import datetime, timedelta
        
        # Tentar carregar do cache
        try:
            with open('templates/holidays_cache.json', 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if str(year) in cache:
                    return jsonify({'success': True, 'holidays': cache[str(year)]})
        except:
            pass
        
        # Calcular dinamicamente
        holidays = []
        
        # Feriados fixos
        fixed = [
            {'date': f'{year}-01-01', 'name': 'Confraternização Universal'},
            {'date': f'{year}-04-21', 'name': 'Tiradentes'},
            {'date': f'{year}-05-01', 'name': 'Dia do Trabalho'},
            {'date': f'{year}-09-07', 'name': 'Independência do Brasil'},
            {'date': f'{year}-10-12', 'name': 'Nossa Senhora Aparecida'},
            {'date': f'{year}-11-02', 'name': 'Finados'},
            {'date': f'{year}-11-15', 'name': 'Proclamação da República'},
            {'date': f'{year}-11-20', 'name': 'Consciência Negra'},
            {'date': f'{year}-12-25', 'name': 'Natal'}
        ]
        
        # Calcular Páscoa
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        
        easter = datetime(year, month, day)
        # Carnaval é observado na segunda E na terça-feira antes da Quarta de Cinzas
        # (-48 e -47 dias a partir da Páscoa) - faltava a segunda-feira aqui, ao
        # contrário do calendário de referência usado em /tempo.
        carnaval_segunda = easter - timedelta(days=48)
        carnaval_terca = easter - timedelta(days=47)
        sexta_santa = easter - timedelta(days=2)
        corpus = easter + timedelta(days=60)

        mobile = [
            {'date': carnaval_segunda.strftime('%Y-%m-%d'), 'name': 'Carnaval'},
            {'date': carnaval_terca.strftime('%Y-%m-%d'), 'name': 'Carnaval'},
            {'date': sexta_santa.strftime('%Y-%m-%d'), 'name': 'Sexta-feira Santa'},
            {'date': corpus.strftime('%Y-%m-%d'), 'name': 'Corpus Christi'}
        ]
        
        holidays = fixed + mobile
        holidays.sort(key=lambda x: x['date'])
        
        return jsonify({'success': True, 'holidays': holidays})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def _is_pdf_filename(filename):
    """Checa a extensão .pdf sem diferenciar maiúsculas/minúsculas (ex: 'Documento.PDF')."""
    return bool(filename) and filename.lower().endswith('.pdf')


@app.route("/pdfs", strict_slashes=False)
def pdfs():
    return render_template_string(PDFS_HTML)

@app.route("/office", strict_slashes=False)
def office():
    return render_template_string(OFFICE_HUB_HTML)

@app.route("/office/convert", methods=["GET", "POST"], strict_slashes=False)
def office_convert():
    if request.method == "GET":
        return render_template_string(OFFICE_CONVERT_HTML)

    file = request.files.get('file')
    output_format = request.form.get('format', 'pdf')
    try:
        dpi = int(request.form.get('dpi', 200))
    except (TypeError, ValueError):
        dpi = 200

    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Selecione um arquivo.'})

    try:
        saved_files = office_engine.convert_office_file(file, output_format, dpi=dpi)
        if len(saved_files) == 1:
            message = f"'{saved_files[0]}' salvo na pasta Downloads!"
        else:
            message = f"{len(saved_files)} arquivos salvos na pasta Downloads!"
        return jsonify({'success': True, 'message': message, 'files': saved_files})
    except office_engine.OfficeError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao converter: {str(e)}'})

@app.route("/office/repair", methods=["GET", "POST"], strict_slashes=False)
def office_repair():
    if request.method == "GET":
        return render_template_string(OFFICE_REPAIR_HTML)

    file = request.files.get('file')
    cleanup_columns = request.form.get('cleanup_columns') in ('1', 'true', 'on', 'yes')

    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Selecione um arquivo.'})

    try:
        output_filename, notes = office_engine.repair_office_file(file, cleanup_columns=cleanup_columns)
        return jsonify({
            'success': True,
            'message': f"'{output_filename}' recuperado e salvo na pasta Downloads!",
            'filename': output_filename,
            'notes': notes,
        })
    except office_engine.OfficeError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao reparar: {str(e)}'})

# --- Dev/Data: ferramentas de formatação, dados mock, conversão e encode/decode ---
# Todas processadas 100% no navegador (JS) - sem rotas de upload/processamento no backend.

@app.route("/devdata", strict_slashes=False)
def devdata():
    return render_template_string(DEVDATA_HUB_HTML())

@app.route("/devdata/format", strict_slashes=False)
def devdata_format():
    return render_template_string(DEVDATA_FORMAT_HTML())

@app.route("/devdata/mock", strict_slashes=False)
def devdata_mock():
    return render_template_string(DEVDATA_MOCK_HTML())

@app.route("/devdata/convert", strict_slashes=False)
def devdata_convert():
    return render_template_string(DEVDATA_CONVERT_HTML())

@app.route("/devdata/encode", strict_slashes=False)
def devdata_encode():
    return render_template_string(DEVDATA_ENCODE_HTML())

# --- Image Studio: crop/resize, filtros/marca d'água e favicon em lote ---
# Processamento via Canvas no navegador - imagens nunca sobem para o servidor.

@app.route("/imagestudio", strict_slashes=False)
def imagestudio():
    return render_template_string(IMAGESTUDIO_HUB_HTML())

@app.route("/imagestudio/solo", strict_slashes=False)
def imagestudio_solo():
    return render_template_string(IMAGESTUDIO_SOLO_HTML())

@app.route("/imagestudio/resize", strict_slashes=False)
def imagestudio_resize():
    return render_template_string(IMAGESTUDIO_RESIZE_HTML())

@app.route("/imagestudio/filters", strict_slashes=False)
def imagestudio_filters():
    return render_template_string(IMAGESTUDIO_FILTERS_HTML())

@app.route("/imagestudio/favicon", strict_slashes=False)
def imagestudio_favicon():
    return render_template_string(IMAGESTUDIO_FAVICON_HTML())

# --- Text Clean & Diff: diff, sanitizador e contador estatístico ---

@app.route("/textclean", strict_slashes=False)
def textclean():
    return render_template_string(TEXTCLEAN_HUB_HTML())

@app.route("/textclean/diff", strict_slashes=False)
def textclean_diff():
    return render_template_string(TEXTCLEAN_DIFF_HTML())

@app.route("/textclean/sanitize", strict_slashes=False)
def textclean_sanitize():
    return render_template_string(TEXTCLEAN_SANITIZE_HTML())

@app.route("/textclean/stats", strict_slashes=False)
def textclean_stats():
    return render_template_string(TEXTCLEAN_STATS_HTML())

# --- Capture & OCR: OCR local (Tesseract.js) e gravador de tela/GIF ---

@app.route("/captureocr", strict_slashes=False)
def captureocr():
    return render_template_string(CAPTUREOCR_HUB_HTML())

@app.route("/captureocr/ocr", strict_slashes=False)
def captureocr_ocr():
    return render_template_string(CAPTUREOCR_OCR_HTML())

@app.route("/captureocr/record", strict_slashes=False)
def captureocr_record():
    return render_template_string(CAPTUREOCR_RECORD_HTML())

# --- AI Guard & Diff: detector heurístico de IA, reescritor/diff e plágio interno ---

@app.route("/aiguard", strict_slashes=False)
def aiguard():
    return render_template_string(AIGUARD_HUB_HTML())

@app.route("/aiguard/detect", strict_slashes=False)
def aiguard_detect():
    return render_template_string(AIGUARD_DETECT_HTML())

@app.route("/aiguard/humanize", strict_slashes=False)
def aiguard_humanize():
    return render_template_string(AIGUARD_HUMANIZE_HTML())

@app.route("/aiguard/plagiarism", strict_slashes=False)
def aiguard_plagiarism():
    return render_template_string(AIGUARD_PLAGIARISM_HTML())

# --- Smart Studio: gravador, teleprompter e editor de corte/waveform ---
# Câmera, microfone e todo o tratamento de áudio (Web Audio API) rodam no navegador.

@app.route("/smartstudio", strict_slashes=False)
def smartstudio():
    return render_template_string(SMARTSTUDIO_HUB_HTML())

@app.route("/smartstudio/studio", strict_slashes=False)
def smartstudio_studio():
    return render_template_string(SMARTSTUDIO_STUDIO_HTML())

@app.route("/smartstudio/editor", strict_slashes=False)
def smartstudio_editor():
    return render_template_string(SMARTSTUDIO_EDITOR_HTML())

# --- Subtitle Lab: transcrição/timeline e burn-in de legendas (SRT/VTT) ---
# Timeline, sincronizador de delay e burn-in rodam 100% no navegador; a
# transcrição automática reaproveita o motor de reconhecimento de voz do
# servidor local (mesmo mecanismo do app de transcrição).

@app.route("/subtitlelab", strict_slashes=False)
def subtitlelab():
    return render_template_string(SUBTITLELAB_HUB_HTML())

@app.route("/subtitlelab/editor", strict_slashes=False)
def subtitlelab_editor():
    return render_template_string(SUBTITLELAB_EDITOR_HTML())

@app.route("/subtitlelab/burn", strict_slashes=False)
def subtitlelab_burn():
    return render_template_string(SUBTITLELAB_BURN_HTML())

@app.route("/subtitlelab/transcribe", methods=["POST"], strict_slashes=False)
def subtitlelab_transcribe():
    file = request.files.get('file')
    try:
        segments = subtitlelab_engine.transcribe_to_segments(file)
        return jsonify({'success': True, 'segments': segments})
    except subtitlelab_engine.SubtitleLabError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao transcrever: {str(e)}'})

# --- Matcha Effect: aplicar/remover o filtro verde e "hazy" que viralizou ---
# Tudo roda via Canvas no navegador; a remoção é uma correção heurística de
# cor (rebalanceamento de canal), não uma reversão exata de qualquer edição.

@app.route("/matchaeffect", strict_slashes=False)
def matchaeffect():
    return render_template_string(MATCHAEFFECT_HUB_HTML())

@app.route("/matchaeffect/add", strict_slashes=False)
def matchaeffect_add():
    return render_template_string(MATCHAEFFECT_ADD_HTML())

@app.route("/matchaeffect/remove", strict_slashes=False)
def matchaeffect_remove():
    return render_template_string(MATCHAEFFECT_REMOVE_HTML())

@app.route("/matchaeffect/video/add", strict_slashes=False)
def matchaeffect_video_add():
    return render_template_string(MATCHAEFFECT_VIDEO_ADD_HTML())

@app.route("/matchaeffect/video/remove", strict_slashes=False)
def matchaeffect_video_remove():
    return render_template_string(MATCHAEFFECT_VIDEO_REMOVE_HTML())

# --- Matcha Effect por IA: Stable Diffusion (img2img) + ControlNet SoftEdge ---
# Dependências pesadas (torch/diffusers/controlnet_aux) são opcionais e só são
# importadas dentro de matchaeffect_ai_engine quando um job é executado — ver
# MatchaEffect/requirements_ai.txt. A geração roda em thread de fundo e o
# front-end consulta o progresso via polling (mesmo padrão do /isolate/progress).

@app.route("/matchaeffect/ai/add", strict_slashes=False)
def matchaeffect_ai_add():
    return render_template_string(MATCHAEFFECT_AI_ADD_HTML())

@app.route("/matchaeffect/ai/remove", strict_slashes=False)
def matchaeffect_ai_remove():
    return render_template_string(MATCHAEFFECT_AI_REMOVE_HTML())

@app.route("/matchaeffect/ai/video", strict_slashes=False)
def matchaeffect_ai_video():
    return render_template_string(MATCHAEFFECT_AI_VIDEO_HTML())

@app.route("/matchaeffect/ai/video/remove", strict_slashes=False)
def matchaeffect_ai_video_remove():
    return render_template_string(MATCHAEFFECT_AI_VIDEO_REMOVE_HTML())

@app.route("/matchaeffect/ai/capabilities", methods=["GET"], strict_slashes=False)
def matchaeffect_ai_capabilities():
    available = matchaeffect_ai_engine.is_available()
    return jsonify({
        'available': available,
        'gpu': matchaeffect_ai_engine.has_cuda() if available else False,
        'install_message': None if available else matchaeffect_ai_engine.install_instructions(),
    })

@app.route("/matchaeffect/ai/jobs", methods=["POST"], strict_slashes=False)
def matchaeffect_ai_start_job():
    if not matchaeffect_ai_engine.is_available():
        return jsonify({'success': False, 'error': matchaeffect_ai_engine.install_instructions()}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'Nenhuma imagem enviada.'}), 400

    mode = request.form.get('mode', 'add')
    if mode not in ('add', 'remove'):
        return jsonify({'success': False, 'error': 'Modo inválido.'}), 400

    try:
        seed_raw = request.form.get('seed')
        params = {
            'denoising_strength': float(request.form.get('denoising_strength', 0.6)),
            'control_weight': float(request.form.get('control_weight', 0.7)),
            'steps': int(request.form.get('steps', 20)),
            'cfg': float(request.form.get('cfg', 7.0)),
            'seed': int(seed_raw) if seed_raw else None,
            'max_side': int(request.form.get('max_side', 512)),
        }
    except ValueError:
        return jsonify({'success': False, 'error': 'Parâmetros inválidos.'}), 400

    job_id = matchaeffect_ai_engine.start_job(mode, file.read(), params)
    return jsonify({'success': True, 'job_id': job_id})

@app.route("/matchaeffect/ai/jobs/<job_id>", methods=["GET"], strict_slashes=False)
def matchaeffect_ai_job_status(job_id):
    job = matchaeffect_ai_engine.get_job(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job não encontrado.'}), 404
    return jsonify({
        'success': True,
        'status': job['status'],
        'message': job.get('message'),
        'image_b64': job.get('image_b64'),
        'elapsed': job.get('elapsed'),
    })

# --- InstaSaver: cola um link do Instagram e vê/baixa stories, destaques e posts ---
# Usa a sessão do Instagram já logada no navegador local (cookies lidos pelo
# leitor do yt-dlp); as mídias passam por /instasaver/media porque a CDN do
# Instagram bloqueia exibição direta em outras origens.

@app.route("/instasaver", strict_slashes=False)
def instasaver():
    return render_template_string(INSTASAVER_HTML())

@app.route("/instasaver/status", methods=["GET"], strict_slashes=False)
def instasaver_status():
    return jsonify(instasaver_engine.session_status())

@app.route("/instasaver/resolve", methods=["POST"], strict_slashes=False)
def instasaver_resolve():
    link = (request.get_json(silent=True) or {}).get('link', '')
    try:
        return jsonify({'success': True, **instasaver_engine.resolve(link)})
    except instasaver_engine.InstaSaverError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro inesperado: {e}'})

@app.route("/instasaver/posts", methods=["GET"], strict_slashes=False)
def instasaver_posts():
    try:
        page = instasaver_engine.get_posts(
            request.args.get('username', ''), request.args.get('max_id') or None)
        return jsonify({'success': True, **page})
    except instasaver_engine.InstaSaverError as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route("/instasaver/highlight/<highlight_id>", methods=["GET"], strict_slashes=False)
def instasaver_highlight(highlight_id):
    try:
        return jsonify({'success': True, 'highlight': instasaver_engine.get_highlight(highlight_id)})
    except instasaver_engine.InstaSaverError as e:
        return jsonify({'success': False, 'error': str(e)})

def _instasaver_filename(name, fallback):
    import re
    name = re.sub(r'[^\w.-]', '_', name or '')[:150]
    return name or fallback

@app.route("/instasaver/media", methods=["GET"], strict_slashes=False)
def instasaver_media():
    url = request.args.get('url', '')
    try:
        upstream = instasaver_engine.open_media(url, request.headers.get('Range'))
    except instasaver_engine.InstaSaverError as e:
        return Response(str(e), status=400, mimetype='text/plain')
    except Exception:
        return Response('Falha ao buscar a mídia.', status=502, mimetype='text/plain')

    headers = {'Cache-Control': 'private, max-age=3600'}
    for key in ('Content-Length', 'Content-Range', 'Accept-Ranges'):
        if upstream.headers.get(key):
            headers[key] = upstream.headers[key]
    if request.args.get('dl'):
        headers['Content-Disposition'] = (
            f'attachment; filename="{_instasaver_filename(request.args.get("name"), "instagram_media")}"')

    def stream():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                yield chunk
        finally:
            upstream.close()

    return Response(stream(), status=upstream.status_code, headers=headers,
                    mimetype=upstream.headers.get('Content-Type', 'application/octet-stream'))

@app.route("/instasaver/zip", methods=["POST"], strict_slashes=False)
def instasaver_zip():
    import tempfile
    payload = request.get_json(silent=True) or {}
    items = [i for i in (payload.get('items') or [])[:300]
             if instasaver_engine.is_allowed_media_url(i.get('url', ''))]
    if not items:
        return jsonify({'success': False, 'error': 'Nada para baixar.'}), 400

    spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    used = set()
    with zipfile.ZipFile(spool, 'w', zipfile.ZIP_STORED) as zf:
        for n, item in enumerate(items):
            name = _instasaver_filename(item.get('filename'), f'instagram_{n}')
            if name in used:
                name = f'{n}_{name}'
            used.add(name)
            try:
                upstream = instasaver_engine.open_media(item['url'])
                with zf.open(name, 'w') as dest:
                    for chunk in upstream.iter_content(chunk_size=256 * 1024):
                        dest.write(chunk)
                upstream.close()
            except Exception:
                continue  # link expirado: o resto do zip ainda vale
    spool.seek(0)
    return send_file(spool, mimetype='application/zip', as_attachment=True,
                     download_name=_instasaver_filename(payload.get('name'), 'instagram') + '.zip')

@app.route("/musica", strict_slashes=False)
def musica():
    return render_template_string(MUSICA_HTML)

@app.route("/instagram", methods=["GET", "POST"], strict_slashes=False)
def instagram():
    status = None
    error = None
    media_list = []
    
    if request.method == "POST":
        action = request.form.get('action', 'fetch')
        input_value = request.form.get('input', '').strip()
        
        if action == 'fetch' and input_value:
            try:
                import requests
                import re
                
                username = None
                shortcode = None
                
                # Detecta tipo de entrada
                if 'instagram.com/' in input_value:
                    parts = input_value.split('instagram.com/')[-1].split('/')
                    if parts[0] in ['p', 'reel', 'tv']:
                        shortcode = parts[1].split('?')[0]
                    elif parts[0] == 'stories':
                        username = parts[1].split('?')[0]
                    else:
                        username = parts[0].split('?')[0]
                else:
                    # É username direto
                    username = input_value.replace('@', '')
                
                # Busca stories por username
                if username and not shortcode:
                    # Método 1: Scraping da página do perfil
                    profile_url = f"https://www.instagram.com/{username}/"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Connection': 'keep-alive',
                    }
                    
                    try:
                        response = requests.get(profile_url, headers=headers, timeout=15)
                        html = response.text
                        
                        # Extrai dados JSON embutidos
                        import json
                        json_match = re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL)
                        if json_match:
                            try:
                                data = json.loads(json_match.group(1))
                                # Busca por imagens de posts recentes como fallback
                                if 'image' in data:
                                    images = data['image'] if isinstance(data['image'], list) else [data['image']]
                                    for img in images[:6]:
                                        if isinstance(img, str):
                                            media_list.append({'type': 'image', 'url': img, 'shortcode': username})
                            except:
                                pass
                        
                        # Busca URLs de mídia no HTML
                        if not media_list:
                            display_urls = re.findall(r'"display_url":"([^"]+)"', html)
                            for url in display_urls[:6]:
                                media_list.append({'type': 'image', 'url': url.replace('\\u0026', '&'), 'shortcode': username})
                        
                        if not media_list:
                            # O Instagram parou de embutir mídia em HTML estático para
                            # quem não está logado - isso normalmente não é culpa do
                            # perfil/post informado, é a plataforma bloqueando scraping
                            # sem sessão autenticada.
                            error = ("Não foi possível extrair mídia. O Instagram passou a exigir login "
                                     "para acessar a maioria dos perfis/posts sem app oficial, então esta "
                                     "ferramenta pode não funcionar mais para muitos conteúdos.")
                    except Exception as e:
                        error = f"Erro ao buscar perfil: {str(e)}"
                
                # Busca post/reel por shortcode
                elif shortcode:
                    page_url = f"https://www.instagram.com/p/{shortcode}/"
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    response = requests.get(page_url, headers=headers, timeout=15)
                    html = response.text
                    
                    video_urls = re.findall(r'"video_url":"([^"]+)"', html)
                    image_urls = re.findall(r'"display_url":"([^"]+)"', html)
                    
                    for url in video_urls[:1]:
                        media_list.append({'type': 'video', 'url': url.replace('\\u0026', '&'), 'shortcode': shortcode})
                    
                    if not media_list:
                        for url in image_urls[:1]:
                            media_list.append({'type': 'image', 'url': url.replace('\\u0026', '&'), 'shortcode': shortcode})
                    
                    if not media_list:
                        # Mesmo motivo do fetch por perfil: o Instagram exige login
                        # para a maioria dos posts hoje em dia, não é um problema
                        # com esse post/link em particular.
                        error = ("Não foi possível extrair mídia. O Instagram passou a exigir login "
                                 "para acessar a maioria dos posts sem app oficial, então esta "
                                 "ferramenta pode não funcionar mais para muitos conteúdos.")
                else:
                    error = "Entrada inválida."
                    
            except Exception as e:
                error = f"Erro: {str(e)}"
        
        elif action == 'download':
            selected = request.form.getlist('selected')
            if selected:
                try:
                    import requests
                    downloads_dir = str(Path.home() / "Downloads")
                    os.makedirs(downloads_dir, exist_ok=True)
                    
                    downloaded = []
                    for url in selected:
                        try:
                            headers = {'User-Agent': 'Mozilla/5.0'}
                            response = requests.get(url, headers=headers, timeout=30, stream=True)
                            ext = '.mp4' if 'video' in url or '.mp4' in url else '.jpg'
                            filename = f"instagram_{int(time.time())}_{len(downloaded)}{ext}"
                            filepath = os.path.join(downloads_dir, filename)
                            
                            with open(filepath, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            downloaded.append(filename)
                        except:
                            continue
                    
                    if downloaded:
                        status = f"✅ {len(downloaded)} arquivo(s) baixado(s) em Downloads!"
                    else:
                        error = "Erro ao baixar arquivos."
                except Exception as e:
                    error = f"Erro: {str(e)}"
            else:
                error = "Selecione pelo menos uma mídia."
    
    return render_template_string(INSTAGRAM_HTML, status=status, error=error, media_list=media_list)

@app.route("/pdfs/split", methods=["GET", "POST"], strict_slashes=False)
def pdfs_split():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        splits_config = request.form.get('splits_config', '')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                import json
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                reader = PdfReader(file.stream)
                base_name = os.path.splitext(file.filename)[0]
                
                splits = json.loads(splits_config)
                
                for split in splits:
                    writer = PdfWriter()
                    for page_num in range(split['start'] - 1, split['end']):
                        if page_num < len(reader.pages):
                            writer.add_page(reader.pages[page_num])
                    
                    name_base = split['name'] if split['name'] else f"{base_name}_parte"
                    output_name = name_base if _is_pdf_filename(name_base) else f"{name_base}.pdf"

                    output_path = os.path.join(downloads_dir, output_name)
                    counter = 1
                    while os.path.exists(output_path):
                        output_name = f"{name_base}_{counter}.pdf"
                        output_path = os.path.join(downloads_dir, output_name)
                        counter += 1
                    
                    with open(output_path, 'wb') as f:
                        writer.write(f)
                
                status = f"✅ {len(splits)} arquivos criados na pasta Downloads!"
            
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao dividir PDF: {str(e)}"
    
    return render_template_string(PDFS_SPLIT_HTML, status=status, error=error)

@app.route("/pdfs/convert", methods=["GET", "POST"], strict_slashes=False)
def pdfs_convert():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        output_format = request.form.get('format', 'docx')
        
        if not file:
            error = "Selecione um arquivo."
        else:
            try:
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                base_name = os.path.splitext(file.filename)[0]
                
                if _is_pdf_filename(file.filename) and output_format in ['jpg', 'png']:
                    from PyPDF2 import PdfReader
                    from PIL import Image
                    import fitz
                    
                    doc = fitz.open(stream=file.read(), filetype="pdf")
                    for i, page in enumerate(doc, 1):
                        pix = page.get_pixmap(dpi=150)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        output_path = os.path.join(downloads_dir, f"{base_name}_pagina_{i}.{output_format}")
                        img.save(output_path)
                    status = f"✅ {len(doc)} imagens criadas na pasta Downloads!"
                
                elif not _is_pdf_filename(file.filename) and output_format == 'pdf':
                    from PIL import Image
                    
                    img = Image.open(file.stream)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = bg
                    output_path = os.path.join(downloads_dir, f"{base_name}.pdf")
                    img.save(output_path, 'PDF')
                    status = f"✅ '{base_name}.pdf' criado na pasta Downloads!"
                
                else:
                    error = "Conversão não suportada. Use PDF→Imagem ou Imagem→PDF."
            
            except ImportError as e:
                error = f"Biblioteca necessária não instalada: {str(e)}"
            except Exception as e:
                error = f"Erro ao converter: {str(e)}"
    
    return render_template_string(PDFS_CONVERT_HTML, status=status, error=error)

@app.route("/pdfs/compress", methods=["GET", "POST"], strict_slashes=False)
def pdfs_compress():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        quality = request.form.get('quality', 'medium')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                import subprocess

                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)

                gs_setting = {
                    'low': '/screen',
                    'medium': '/ebook',
                    'high': '/printer'
                }.get(quality, '/ebook')

                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_comprimido.pdf"
                output_path = os.path.join(downloads_dir, output_filename)

                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_comprimido_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1

                temp_input = os.path.join(downloads_dir, f"temp_{file.filename}")
                file.save(temp_input)
                original_size = os.path.getsize(temp_input)

                try:
                    result = subprocess.run([
                        'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                        f'-dPDFSETTINGS={gs_setting}', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                        f'-sOutputFile={output_path}', temp_input
                    ], capture_output=True, timeout=120)

                    if result.returncode != 0 or not os.path.exists(output_path):
                        raise RuntimeError(result.stderr.decode('utf-8', errors='ignore').strip() or 'erro desconhecido do Ghostscript')
                except (FileNotFoundError, RuntimeError):
                    # Ghostscript não disponível: recorre à compressão básica de streams do PyPDF2
                    from PyPDF2 import PdfReader, PdfWriter
                    reader = PdfReader(temp_input)
                    writer = PdfWriter()
                    for page in reader.pages:
                        page.compress_content_streams()
                        writer.add_page(page)
                    with open(output_path, 'wb') as f:
                        writer.write(f)
                finally:
                    os.remove(temp_input)

                compressed_size = os.path.getsize(output_path)
                reduction = round((1 - compressed_size / original_size) * 100, 1)

                status = f"✅ '{output_filename}' criado! Redução: {reduction}%"

            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao comprimir PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_compress.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/rotate", methods=["GET", "POST"], strict_slashes=False)
def pdfs_rotate():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        angle = int(request.form.get('angle', 90))
        mode = request.form.get('mode', 'all')
        rotations_str = request.form.get('rotations', '{}')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                import json
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                reader = PdfReader(file.stream)
                writer = PdfWriter()
                
                if mode == 'all':
                    for page in reader.pages:
                        page.rotate(angle)
                        writer.add_page(page)
                else:
                    from PyPDF2.generic import NameObject, NumberObject
                    # A UI de "páginas específicas" mostra botões de orientação final
                    # (0°/90°/180°/270°), mas page.rotate() do PyPDF2 é relativo -
                    # soma ao /Rotate que a página já tiver. Uma página já rotacionada
                    # no PDF original acabava com uma orientação diferente da que o
                    # botão clicado prometia. Setamos o /Rotate final diretamente.
                    rotations = json.loads(rotations_str)
                    for i, page in enumerate(reader.pages):
                        page_num = str(i + 1)
                        if page_num in rotations:
                            page[NameObject("/Rotate")] = NumberObject(int(rotations[page_num]) % 360)
                        writer.add_page(page)
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_girado.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_girado_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                status = f"✅ '{output_filename}' criado com sucesso!"
            
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao girar PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_rotate.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/compare", methods=["GET", "POST"], strict_slashes=False)
def pdfs_compare():
    status = None
    error = None
    
    if request.method == "POST":
        files = request.files.getlist('files')
        
        if not files or len(files) < 2:
            error = "Selecione pelo menos 2 arquivos PDF."
        else:
            try:
                from PyPDF2 import PdfReader
                from difflib import SequenceMatcher
                
                texts = []
                names = []
                for file in files:
                    reader = PdfReader(file.stream)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text()
                    texts.append(text)
                    names.append(file.filename)
                
                comparisons = []
                for i in range(len(texts)):
                    for j in range(i+1, len(texts)):
                        similarity = SequenceMatcher(None, texts[i], texts[j]).ratio() * 100
                        if similarity >= 35:
                            matcher = SequenceMatcher(None, texts[i], texts[j])
                            differences = []
                            similarities = []
                            
                            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                                if tag == 'equal':
                                    similarities.append(texts[i][i1:i2])
                                elif tag in ['replace', 'delete', 'insert']:
                                    if tag == 'replace':
                                        differences.append(f"'{texts[i][i1:i2]}' vs '{texts[j][j1:j2]}'")
                                    elif tag == 'delete':
                                        differences.append(f"Removido: '{texts[i][i1:i2]}'")
                                    else:
                                        differences.append(f"Adicionado: '{texts[j][j1:j2]}'")
                            
                            comparisons.append({
                                'file1': names[i],
                                'file2': names[j],
                                'similarity': round(similarity, 1),
                                'differences': differences,
                                'similarities': similarities
                            })
                
                if comparisons:
                    return render_template_string(
                        open('/opt/lampp/htdocs/Verto/PDFs/pdfs_compare.html', 'r', encoding='utf-8').read(),
                        status=None,
                        error=None,
                        comparisons=comparisons
                    )
                else:
                    error = "Nenhum par de PDFs possui 35% ou mais de similaridade."
            
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao comparar PDFs: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_compare.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/repair", methods=["GET", "POST"], strict_slashes=False)
def pdfs_repair():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                import re
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                temp_path = os.path.join(downloads_dir, f"temp_{file.filename}")
                file.save(temp_path)
                
                # Estratégia 1: Reconstruir estrutura básica do PDF
                try:
                    with open(temp_path, 'rb') as f:
                        data = f.read()
                    
                    # Adiciona header se estiver faltando
                    if not data.startswith(b'%PDF'):
                        data = b'%PDF-1.4\n' + data
                    
                    # Adiciona EOF se estiver faltando (ignorando espaços/quebras de
                    # linha finais - muitos PDFs válidos terminam com "%%EOF\n", e
                    # sem o rstrip() esse header era considerado "faltando" e um
                    # segundo "%%EOF" era duplicado no arquivo, o que quebrava o
                    # parser de xref do PyPDF2 mesmo em PDFs originalmente válidos)
                    if not data.rstrip().endswith(b'%%EOF'):
                        data = data.rstrip() + b'\n%%EOF'
                    
                    # Tenta encontrar e reconstruir xref table
                    if b'xref' not in data:
                        # Adiciona xref básico
                        xref_pos = len(data) - 20
                        data = data[:-5] + b'\nxref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 >>\nstartxref\n' + str(xref_pos).encode() + b'\n%%EOF'
                    
                    with open(temp_path, 'wb') as f:
                        f.write(data)
                except:
                    pass
                
                # Estratégia 2: PyPDF2 com strict=False
                try:
                    reader = PdfReader(temp_path, strict=False)
                    writer = PdfWriter()
                    
                    recovered_pages = 0
                    for page in reader.pages:
                        try:
                            writer.add_page(page)
                            recovered_pages += 1
                        except:
                            continue
                    
                    if recovered_pages > 0:
                        base_name = os.path.splitext(file.filename)[0]
                        output_filename = f"{base_name}_reparado.pdf"
                        output_path = os.path.join(downloads_dir, output_filename)
                        
                        counter = 1
                        while os.path.exists(output_path):
                            output_filename = f"{base_name}_reparado_{counter}.pdf"
                            output_path = os.path.join(downloads_dir, output_filename)
                            counter += 1
                        
                        with open(output_path, 'wb') as f:
                            writer.write(f)
                        
                        os.remove(temp_path)
                        status = f"✅ '{output_filename}' recuperado! {recovered_pages} páginas salvas."
                        return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
                except:
                    pass
                
                # Estratégia 3: pikepdf
                try:
                    import pikepdf
                    pdf = pikepdf.open(temp_path, allow_overwriting_input=True)
                    
                    base_name = os.path.splitext(file.filename)[0]
                    output_filename = f"{base_name}_reparado.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    
                    counter = 1
                    while os.path.exists(output_path):
                        output_filename = f"{base_name}_reparado_{counter}.pdf"
                        output_path = os.path.join(downloads_dir, output_filename)
                        counter += 1
                    
                    pdf.save(output_path)
                    os.remove(temp_path)
                    
                    status = f"✅ '{output_filename}' reparado com pikepdf!"
                    return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
                except:
                    pass
                
                # Estratégia 4: Extração de texto e recriação
                try:
                    import fitz  # PyMuPDF
                    from reportlab.pdfgen import canvas
                    from reportlab.lib.pagesizes import letter
                    
                    doc = fitz.open(temp_path)
                    
                    base_name = os.path.splitext(file.filename)[0]
                    output_filename = f"{base_name}_reparado.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    
                    counter = 1
                    while os.path.exists(output_path):
                        output_filename = f"{base_name}_reparado_{counter}.pdf"
                        output_path = os.path.join(downloads_dir, output_filename)
                        counter += 1
                    
                    c = canvas.Canvas(output_path, pagesize=letter)
                    recovered_pages = 0
                    
                    for page_num in range(len(doc)):
                        try:
                            page = doc[page_num]
                            text = page.get_text()
                            
                            y = 750
                            for line in text.split('\n'):
                                if y > 50:
                                    c.drawString(50, y, line[:100])
                                    y -= 15
                            
                            c.showPage()
                            recovered_pages += 1
                        except:
                            continue
                    
                    c.save()
                    os.remove(temp_path)
                    
                    if recovered_pages > 0:
                        status = f"✅ '{output_filename}' recriado! {recovered_pages} páginas com texto extraído."
                        return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
                except:
                    pass
                
                # Estratégia 5: Recuperação bruta de objetos
                try:
                    with open(temp_path, 'rb') as f:
                        data = f.read()
                    
                    # Procura por objetos stream
                    streams = re.findall(rb'stream\s*(.+?)\s*endstream', data, re.DOTALL)
                    
                    if len(streams) > 0:
                        base_name = os.path.splitext(file.filename)[0]
                        output_filename = f"{base_name}_reparado.pdf"
                        output_path = os.path.join(downloads_dir, output_filename)
                        
                        counter = 1
                        while os.path.exists(output_path):
                            output_filename = f"{base_name}_reparado_{counter}.pdf"
                            output_path = os.path.join(downloads_dir, output_filename)
                            counter += 1
                        
                        # Cria PDF mínimo com objetos recuperados
                        new_pdf = b'%PDF-1.4\n'
                        new_pdf += b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'
                        new_pdf += b'2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n'
                        new_pdf += b'xref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n'
                        new_pdf += b'trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF'
                        
                        with open(output_path, 'wb') as f:
                            f.write(new_pdf)
                        
                        os.remove(temp_path)
                        status = f"✅ '{output_filename}' parcialmente recuperado! {len(streams)} objetos encontrados."
                        return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
                except:
                    pass
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                error = "PDF muito danificado. Nenhuma estratégia de recuperação funcionou."
            
            except ImportError as e:
                error = f"Biblioteca necessária não instalada: {str(e)}"
            except Exception as e:
                error = f"Erro ao reparar PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_repair.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/protect", methods=["GET", "POST"], strict_slashes=False)
def pdfs_protect():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        elif password != confirm_password:
            error = "As senhas não coincidem."
        elif len(password) < 4:
            error = "A senha deve ter pelo menos 4 caracteres."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                reader = PdfReader(file.stream)
                writer = PdfWriter()
                
                for page in reader.pages:
                    writer.add_page(page)
                
                writer.encrypt(password)
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_protegido.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_protegido_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                status = f"✅ '{output_filename}' protegido e salvo na pasta Downloads!"
            
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao proteger PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_protect.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/unlock/progress", methods=["POST"])
def pdfs_unlock_progress():
    def generate():
        file = request.files.get('file')
        password = request.form.get('password', '')
        force_unlock = request.form.get('force_unlock', '')
        
        if not file or not _is_pdf_filename(file.filename):
            yield f"data: {json.dumps({'error': 'Arquivo invalido'})}\n\n"
            return
        
        try:
            from PyPDF2 import PdfReader, PdfWriter
            import time
            import subprocess
            
            downloads_dir = str(Path.home() / "Downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            temp_path = os.path.join(downloads_dir, f"temp_{file.filename}")
            file.save(temp_path)
            
            yield f"data: {json.dumps({'progress': 5, 'text': 'Analisando PDF...'})}\n\n"
            
            reader = PdfReader(temp_path)
            unlocked = False
            found_password = None
            
            if reader.is_encrypted:
                if password:
                    yield f"data: {json.dumps({'progress': 10, 'text': 'Testando senha fornecida...'})}\n\n"
                    if reader.decrypt(password) != 0:
                        unlocked = True
                        found_password = password
                
                if not unlocked and force_unlock:
                    common_passwords = [
                        '', '123456', 'password', '12345678', '123456789', 'qwerty',
                        '123', '1234', '12345', '111111', '1234567', 'sunshine',
                        'password1', 'admin', 'welcome', 'monkey', 'login', 'abc123',
                        'starwars', '123123', 'dragon', 'passw0rd', 'master', 'hello',
                        'freedom', 'whatever', 'qazwsx', 'trustno1', 'jordan', 'password123',
                        '0000', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999',
                        '0123', '1234', '2345', '3456', '4567', '5678', '6789', '7890',
                        'user', 'root', 'toor', 'pass', 'test', 'guest', 'info', 'adm',
                        'mysql', 'oracle', 'ftp', 'ssh', 'http', 'https', 'www', 'web',
                        'sql', 'qwerty123', 'zxcvbnm', 'asdfgh', 'qwertyuiop',
                        'senha', 'senha123', 'admin123', 'root123', '123mudar'
                    ]
                    
                    total_common = len(common_passwords)
                    for idx, pwd in enumerate(common_passwords):
                        try:
                            test_reader = PdfReader(temp_path)
                            if test_reader.decrypt(pwd) != 0:
                                unlocked = True
                                found_password = pwd
                                reader = test_reader
                                break
                            progress = 15 + int((idx / total_common) * 20)
                            if idx % 5 == 0:
                                msg = f'Testando senhas comuns... ({idx}/{total_common})'
                                yield f"data: {json.dumps({'progress': progress, 'text': msg})}\n\n"
                            time.sleep(0.001)
                        except:
                            continue
                    
                    if not unlocked:
                        yield f"data: {json.dumps({'progress': 35, 'text': 'Iniciando forca bruta numerica...'})}\n\n"
                        batch_size = 100
                        for i in range(0, 10000, batch_size):
                            for j in range(batch_size):
                                num = i + j
                                if num >= 10000:
                                    break
                                pwd = str(num).zfill(4)
                                try:
                                    test_reader = PdfReader(temp_path)
                                    if test_reader.decrypt(pwd) != 0:
                                        unlocked = True
                                        found_password = pwd
                                        reader = test_reader
                                        break
                                except:
                                    continue
                            if unlocked:
                                break
                            progress = 35 + int((i / 10000) * 30)
                            if i % 500 == 0:
                                msg = f'Forca bruta... ({i}/10000)'
                                yield f"data: {json.dumps({'progress': progress, 'text': msg})}\n\n"
                            time.sleep(0.01)
                    
                    if not unlocked:
                        yield f"data: {json.dumps({'progress': 65, 'text': 'Tentando pikepdf...'})}\n\n"
                        try:
                            import pikepdf
                            pdf = pikepdf.open(temp_path, password='')
                            decrypted_path = temp_path + '.pikepdf_decrypted.pdf'
                            pdf.save(decrypted_path)
                            pdf.close()
                            os.remove(temp_path)
                            temp_path = decrypted_path
                            reader = PdfReader(temp_path)
                            unlocked = True
                            found_password = 'pikepdf'
                        except:
                            pass
                    
                    if not unlocked:
                        yield f"data: {json.dumps({'progress': 75, 'text': 'Tentando qpdf...'})}\n\n"
                        try:
                            result = subprocess.run(
                                ['qpdf', '--decrypt', temp_path, temp_path + '.unlocked'],
                                capture_output=True, timeout=30
                            )
                            if result.returncode == 0:
                                os.remove(temp_path)
                                temp_path = temp_path + '.unlocked'
                                reader = PdfReader(temp_path)
                                unlocked = True
                                found_password = 'qpdf'
                        except:
                            pass
                
                if not unlocked:
                    os.remove(temp_path)
                    yield f"data: {json.dumps({'error': 'Nao foi possivel desbloquear'})}\n\n"
                    return
            
            yield f"data: {json.dumps({'progress': 85, 'text': 'Salvando arquivo...'})}\n\n"
            
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            
            base_name = os.path.splitext(file.filename)[0]
            output_filename = f"{base_name}_desbloqueado.pdf"
            output_path = os.path.join(downloads_dir, output_filename)
            
            counter = 1
            while os.path.exists(output_path):
                output_filename = f"{base_name}_desbloqueado_{counter}.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                counter += 1
            
            with open(output_path, 'wb') as f:
                writer.write(f)
            
            os.remove(temp_path)
            
            result_data = {'progress': 100, 'text': 'Concluido!', 'success': True, 'filename': output_filename, 'password': found_password}
            yield f"data: {json.dumps(result_data)}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route("/pdfs/unlock", methods=["GET", "POST"], strict_slashes=False)
def pdfs_unlock():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        password = request.form.get('password', '')
        force_unlock = request.form.get('force_unlock', '')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                import time
                import subprocess
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                temp_path = os.path.join(downloads_dir, f"temp_{file.filename}")
                file.save(temp_path)
                
                reader = PdfReader(temp_path)
                unlocked = False
                found_password = None
                
                if reader.is_encrypted:
                    if password:
                        if reader.decrypt(password) != 0:
                            unlocked = True
                            found_password = password
                    
                    if not unlocked and force_unlock:
                        common_passwords = [
                            '', '123456', 'password', '12345678', '123456789', 'qwerty',
                            '123', '1234', '12345', '111111', '1234567', 'sunshine',
                            'password1', 'admin', 'welcome', 'monkey', 'login', 'abc123',
                            'starwars', '123123', 'dragon', 'passw0rd', 'master', 'hello',
                            'freedom', 'whatever', 'qazwsx', 'trustno1', 'jordan', 'password123',
                            '0000', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999',
                            '0123', '1234', '2345', '3456', '4567', '5678', '6789', '7890',
                            'user', 'root', 'toor', 'pass', 'test', 'guest', 'info', 'adm',
                            'mysql', 'oracle', 'ftp', 'ssh', 'http', 'https', 'www', 'web',
                            'sql', 'qwerty123', 'zxcvbnm', 'asdfgh', 'qwertyuiop',
                            'senha', 'senha123', 'admin123', 'root123', '123mudar'
                        ]
                        
                        for idx, pwd in enumerate(common_passwords):
                            try:
                                test_reader = PdfReader(temp_path)
                                if test_reader.decrypt(pwd) != 0:
                                    unlocked = True
                                    found_password = pwd
                                    reader = test_reader
                                    break
                                time.sleep(0.001)
                            except:
                                continue
                        
                        if not unlocked:
                            batch_size = 100
                            for i in range(0, 10000, batch_size):
                                for j in range(batch_size):
                                    num = i + j
                                    if num >= 10000:
                                        break
                                    pwd = str(num).zfill(4)
                                    try:
                                        test_reader = PdfReader(temp_path)
                                        if test_reader.decrypt(pwd) != 0:
                                            unlocked = True
                                            found_password = pwd
                                            reader = test_reader
                                            break
                                    except:
                                        continue
                                if unlocked:
                                    break
                                time.sleep(0.01)
                        
                        if not unlocked:
                            try:
                                import pikepdf
                                pdf = pikepdf.open(temp_path, password='')
                                decrypted_path = temp_path + '.pikepdf_decrypted.pdf'
                                pdf.save(decrypted_path)
                                pdf.close()
                                os.remove(temp_path)
                                temp_path = decrypted_path
                                reader = PdfReader(temp_path)
                                unlocked = True
                                found_password = 'pikepdf'
                            except:
                                pass

                        if not unlocked:
                            try:
                                result = subprocess.run(
                                    ['qpdf', '--decrypt', temp_path, temp_path + '.unlocked'],
                                    capture_output=True, timeout=30
                                )
                                if result.returncode == 0:
                                    os.remove(temp_path)
                                    temp_path = temp_path + '.unlocked'
                                    reader = PdfReader(temp_path)
                                    unlocked = True
                                    found_password = 'qpdf'
                            except:
                                pass
                    
                    if not unlocked:
                        os.remove(temp_path)
                        error = "Não foi possível desbloquear. Senha muito forte ou criptografia avançada."
                        return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_unlock.html', 'r', encoding='utf-8').read(), status=status, error=error)
                
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_desbloqueado.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_desbloqueado_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                os.remove(temp_path)
                
                if found_password and found_password not in ['pikepdf', 'qpdf']:
                    status = f"✅ '{output_filename}' desbloqueado! Senha encontrada: '{found_password}'"
                else:
                    status = f"✅ '{output_filename}' desbloqueado e salvo na pasta Downloads!"
            
            except ImportError as e:
                error = f"Biblioteca necessária não instalada: {str(e)}"
            except Exception as e:
                error = f"Erro ao desbloquear PDF: {str(e)}"
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_unlock.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/edit", methods=["GET", "POST"], strict_slashes=False)
def pdfs_edit():
    status = None
    error = None
    
    if request.method == "POST":
        edited_text = request.form.get('edited_text', '')
        filename = request.form.get('filename', 'documento.pdf')
        
        if not edited_text:
            error = "Nenhum texto para salvar."
        else:
            try:
                from weasyprint import HTML
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                base_name = os.path.splitext(filename)[0]
                output_filename = f"{base_name}_editado.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_editado_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        @page {{
                            size: A4;
                            margin: 2cm;
                        }}
                        body {{
                            font-family: 'Times New Roman', serif;
                            font-size: 14px;
                            line-height: 1.8;
                            color: #1a1a1a;
                        }}
                        p {{ margin: 0 0 12px 0; }}
                        b, strong {{ font-weight: bold; }}
                        i, em {{ font-style: italic; }}
                        u {{ text-decoration: underline; }}
                        ul, ol {{ margin: 12px 0; padding-left: 40px; }}
                        li {{ margin: 6px 0; }}
                    </style>
                </head>
                <body>
                    {edited_text}
                </body>
                </html>
                """
                
                HTML(string=html_content).write_pdf(output_path)
                status = f"✅ '{output_filename}' salvo na pasta Downloads!"
            
            except ImportError:
                error = "WeasyPrint não está instalado. Execute: pip install weasyprint"
            except Exception as e:
                error = f"Erro ao salvar PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_edit.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/edit/extract", methods=["POST"], strict_slashes=False)
def pdfs_edit_extract():
    try:
        from PyPDF2 import PdfReader
        
        file = request.files.get('file')
        if not file:
            return jsonify({"success": False, "error": "Nenhum arquivo enviado"})
        
        reader = PdfReader(file.stream)
        text = ""
        
        for page in reader.pages:
            text += page.extract_text() + "\n\n"
        
        return jsonify({"success": True, "text": text.strip()})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/pdfs/watermark", methods=["GET", "POST"], strict_slashes=False)
def pdfs_watermark():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        watermark_type = request.form.get('type', 'text')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import letter
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                from PIL import Image
                import io
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                reader = PdfReader(file.stream)
                writer = PdfWriter()
                
                if watermark_type == 'text':
                    text = request.form.get('text', 'MARCA D\'ÁGUA')
                    position = request.form.get('position', 'center')
                    custom_x = request.form.get('custom_x', '')
                    custom_y = request.form.get('custom_y', '')
                    font = request.form.get('font', 'Helvetica')
                    size = int(request.form.get('size', 40))
                    opacity = float(request.form.get('opacity', 0.3))
                    if opacity > 1:
                        opacity = opacity / 100
                    color = request.form.get('color', '#808080')
                    rotation = int(request.form.get('rotation', 45))
                    
                    for page in reader.pages:
                        packet = io.BytesIO()
                        can = canvas.Canvas(packet, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
                        
                        r = int(color[1:3], 16) / 255
                        g = int(color[3:5], 16) / 255
                        b = int(color[5:7], 16) / 255
                        can.setFillColorRGB(r, g, b, alpha=opacity)
                        can.setFont(font, size)
                        
                        w = float(page.mediabox.width)
                        h = float(page.mediabox.height)
                        
                        if position == 'full':
                            can.saveState()
                            can.translate(w/2, h/2)
                            can.rotate(rotation)
                            for y in range(-int(h), int(h), 150):
                                for x in range(-int(w), int(w), 300):
                                    can.drawCentredString(x, y, text)
                            can.restoreState()
                        elif position == 'drag' and custom_x and custom_y:
                            # Converte porcentagem do preview para coordenadas reais do PDF
                            # Preview usa top-left como origem, PDF usa bottom-left
                            x = (float(custom_x) / 100) * w
                            y = h - (float(custom_y) / 100) * h  # Inverte Y: h - y_preview
                            can.saveState()
                            can.translate(x, y)
                            can.rotate(rotation)
                            can.drawString(0, 0, text)  # drawString ao invés de drawCentredString
                            can.restoreState()
                        else:
                            positions = {
                                'center': (w/2, h/2),
                                'top-left': (w*0.08, h*0.92),
                                'top-center-left': (w*0.30, h*0.92),
                                'top-center': (w/2, h*0.92),
                                'top-center-right': (w*0.70, h*0.92),
                                'top-right': (w*0.92, h*0.92),
                                'middle-left': (w*0.08, h/2),
                                'middle-center-left': (w*0.30, h/2),
                                'middle-center-right': (w*0.70, h/2),
                                'middle-right': (w*0.92, h/2),
                                'bottom-left': (w*0.08, h*0.08),
                                'bottom-center-left': (w*0.30, h*0.08),
                                'bottom-center': (w/2, h*0.08),
                                'bottom-center-right': (w*0.70, h*0.08),
                                'bottom-right': (w*0.92, h*0.08)
                            }
                            x, y = positions.get(position, (w/2, h/2))
                            can.saveState()
                            can.translate(x, y)
                            can.rotate(rotation)
                            can.drawCentredString(0, 0, text)
                            can.restoreState()
                        
                        can.save()
                        packet.seek(0)
                        watermark = PdfReader(packet)
                        page.merge_page(watermark.pages[0])
                        writer.add_page(page)
                
                else:
                    watermark_file = request.files.get('watermark_image')
                    if not watermark_file:
                        error = "Selecione uma imagem para marca d'água."
                        return render_template_string(open('/opt/lampp/htdocs/Verto/PDFs/pdfs_watermark.html', 'r', encoding='utf-8').read(), status=status, error=error)
                    
                    position = request.form.get('position', 'center')
                    custom_x = request.form.get('custom_x', '')
                    custom_y = request.form.get('custom_y', '')
                    img_size = int(request.form.get('img_size', 200))
                    opacity = float(request.form.get('opacity', 0.5))
                    if opacity > 1:
                        opacity = opacity / 100
                    
                    img = Image.open(watermark_file.stream)
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    
                    img.thumbnail((img_size, img_size), Image.Resampling.LANCZOS)
                    
                    alpha = img.split()[3]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    img.putalpha(alpha)
                    
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    for page in reader.pages:
                        packet = io.BytesIO()
                        can = canvas.Canvas(packet, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
                        
                        w = float(page.mediabox.width)
                        h = float(page.mediabox.height)
                        
                        if position == 'full':
                            for y in range(0, int(h), img_size + 50):
                                for x in range(0, int(w), img_size + 50):
                                    img_buffer.seek(0)
                                    can.drawImage(img_buffer, x, y, width=img_size, height=img_size, mask='auto')
                        elif position == 'drag' and custom_x and custom_y:
                            # Converte porcentagem do preview para coordenadas reais do PDF
                            # Preview usa top-left como origem, PDF usa bottom-left
                            x = (float(custom_x) / 100) * w
                            y = h - (float(custom_y) / 100) * h - img_size  # Inverte Y e ajusta altura da imagem
                            img_buffer.seek(0)
                            can.drawImage(img_buffer, x, y, width=img_size, height=img_size, mask='auto')
                        else:
                            positions = {
                                'center': (w/2 - img_size/2, h/2 - img_size/2),
                                'top-left': (w*0.08, h - h*0.08 - img_size),
                                'top-center-left': (w*0.30, h - h*0.08 - img_size),
                                'top-center': (w/2 - img_size/2, h - h*0.08 - img_size),
                                'top-center-right': (w*0.70, h - h*0.08 - img_size),
                                'top-right': (w*0.92 - img_size, h - h*0.08 - img_size),
                                'middle-left': (w*0.08, h/2 - img_size/2),
                                'middle-center-left': (w*0.30, h/2 - img_size/2),
                                'middle-center-right': (w*0.70, h/2 - img_size/2),
                                'middle-right': (w*0.92 - img_size, h/2 - img_size/2),
                                'bottom-left': (w*0.08, h*0.08),
                                'bottom-center-left': (w*0.30, h*0.08),
                                'bottom-center': (w/2 - img_size/2, h*0.08),
                                'bottom-center-right': (w*0.70, h*0.08),
                                'bottom-right': (w*0.92 - img_size, h*0.08)
                            }
                            x, y = positions.get(position, (w/2 - img_size/2, h/2 - img_size/2))
                            img_buffer.seek(0)
                            can.drawImage(img_buffer, x, y, width=img_size, height=img_size, mask='auto')
                        
                        can.save()
                        packet.seek(0)
                        watermark = PdfReader(packet)
                        page.merge_page(watermark.pages[0])
                        writer.add_page(page)
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_marca_dagua.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_marca_dagua_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                status = f"✅ '{output_filename}' criado com marca d'água!"
            
            except ImportError as e:
                error = f"Biblioteca necessária não instalada: {str(e)}"
            except Exception as e:
                error = f"Erro ao adicionar marca d'água: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_watermark.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/corrupt", methods=["GET", "POST"], strict_slashes=False)
def pdfs_corrupt():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        corruption_level = request.form.get('level', 'light')
        
        if not file or not _is_pdf_filename(file.filename):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                pdf_data = file.stream.read()
                
                if corruption_level == 'light':
                    # Corrupção leve: altera alguns bytes no meio
                    corrupted = bytearray(pdf_data)
                    for i in range(len(corrupted) // 2, len(corrupted) // 2 + 50, 10):
                        corrupted[i] = (corrupted[i] + 1) % 256
                    pdf_data = bytes(corrupted)
                elif corruption_level == 'medium':
                    # Corrupção média: remove parte do cabeçalho
                    corrupted = bytearray(pdf_data)
                    for i in range(100, 300, 5):
                        if i < len(corrupted):
                            corrupted[i] = 0
                    pdf_data = bytes(corrupted)
                elif corruption_level == 'heavy':
                    # Corrupção pesada: embaralha blocos
                    corrupted = bytearray(pdf_data)
                    for i in range(0, len(corrupted) - 100, 500):
                        corrupted[i:i+50] = bytes([0] * 50)
                    pdf_data = bytes(corrupted)
                else:  # extreme
                    # Corrupção extrema: remove EOF e trailer
                    pdf_data = pdf_data[:len(pdf_data)//2]
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_corrompido.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_corrompido_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    f.write(pdf_data)
                
                status = f"✅ '{output_filename}' corrompido com sucesso!"
            
            except Exception as e:
                error = f"Erro ao corromper PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/PDFs/pdfs_corrupt.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/pdfs/merge", methods=["GET", "POST"], strict_slashes=False)
def pdfs_merge():
    status = None
    error = None
    
    if request.method == "POST":
        files = request.files.getlist('files')
        pages_config = request.form.get('pages_config', '[]')
        
        if not files or len(files) < 1:
            error = "Selecione pelo menos 1 arquivo PDF."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                import json
                
                pages_list = json.loads(pages_config)
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                writer = PdfWriter()
                skipped = []

                for idx, file in enumerate(files):
                    if not _is_pdf_filename(file.filename):
                        skipped.append(file.filename)
                        continue

                    reader = PdfReader(file.stream)
                    # Índice fora da lista (front-end não mandou seleção pra esse arquivo)
                    # cai em "todas as páginas"; já uma string vazia é explícita - o usuário
                    # apagou todas as páginas desse arquivo na prévia - e deve resultar em
                    # nenhuma página dele entrando no PDF final, não em "todas".
                    pages_spec = pages_list[idx] if idx < len(pages_list) else 'all'

                    if pages_spec == 'all':
                        for page in reader.pages:
                            writer.add_page(page)
                    elif pages_spec:
                        page_numbers = [int(p.strip()) for p in pages_spec.split(',') if p.strip().isdigit()]
                        for page_num in page_numbers:
                            if 1 <= page_num <= len(reader.pages):
                                writer.add_page(reader.pages[page_num - 1])

                if len(writer.pages) == 0:
                    raise ValueError(
                        "Nenhuma página selecionada para mesclar. Verifique se os arquivos são PDFs válidos "
                        "e se pelo menos uma página está marcada."
                    )

                base_name = os.path.splitext(files[0].filename)[0]
                name_stem = f"{base_name}_organizado" if len(files) == 1 else "PDF_Mesclado"
                output_filename = f"{name_stem}.pdf"
                output_path = os.path.join(downloads_dir, output_filename)

                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{name_stem}_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
                
                status = f"✅ '{output_filename}' criado com sucesso na pasta Downloads!"
                if skipped:
                    status += f" (ignorado(s) por não ser PDF: {', '.join(skipped)})"
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao mesclar PDFs: {str(e)}"

    return render_template_string(PDFS_MERGE_HTML, status=status, error=error)

class UnsupportedConversionError(Exception):
    """Erro amigável quando o tipo de conversão pedido não é suportado de verdade."""
    pass


VIDEO_EXTS = ['3g2', '3gp', 'asf', 'avi', 'divx', 'dv', 'f4v', 'flv', 'm2ts', 'm2v',
              'm4v', 'mjpeg', 'mkv', 'mod', 'mov', 'mp4', 'mpeg', 'mpg', 'mts', 'mxf',
              'ogv', 'rm', 'rmvb', 'swf', 'tod', 'ts', 'vob', 'webm', 'wmv', 'wtv', 'xvid']

AUDIO_EXTS = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'oga', 'wma', 'm4a', 'opus', 'aiff',
              'ape', 'alac', 'ac3', 'dts', 'amr', 'au', 'mid', 'midi', 'mka', 'mp2',
              'mpc', 'ra', 'spx', 'tta', 'voc', 'vqf', 'wv', '3ga', 'aa', 'aax', 'act',
              'aif', 'aifc', 'caf', 'dss', 'dvf', 'gsm', 'iklax', 'ivs', 'm4b', 'm4p',
              'mmf', 'msv', 'nmf', 'nsf', 'mogg', 'rf64', 'sln', 'vox', 'webm', '8svx', 'cda']

# Formatos "pacote" (múltiplos arquivos): lemos/gravamos de verdade com zipfile/tarfile.
ARCHIVE_BUNDLE_FORMATS = {'zip', 'tar', 'tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz', 'jar', 'apk', 'ipa'}
# Formatos "fluxo único" (compressão de 1 arquivo): gzip/bz2/lzma da stdlib.
ARCHIVE_STREAM_FORMATS = {'gz', 'bz2', 'xz'}
# Extensões de entrada que reconhecemos como "é um arquivo compactado", mesmo quando
# não sabemos gerar esse formato de saída (ex: .rar só conseguimos rejeitar com uma
# mensagem clara, pois exigiria unrar/7z instalado no sistema).
ARCHIVE_ALL_EXTS = ['7z', 'ace', 'alz', 'apk', 'arc', 'arj', 'cab', 'cpio', 'deb', 'gz',
                     'bz2', 'xz', 'ipa', 'iso', 'dmg', 'pkg', 'jar', 'lha', 'rar', 'rpm',
                     'tar', 'tbz2', 'tgz', 'zip']


def _detect_file_category(filename, stream):
    """Descobre a categoria real do arquivo (não confia só na extensão)."""
    stream.seek(0)
    try:
        from PIL import Image
        img = Image.open(stream)
        img.load()
        return 'image'
    except Exception:
        pass
    finally:
        stream.seek(0)

    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in ARCHIVE_ALL_EXTS or zipfile.is_zipfile(stream):
        stream.seek(0)
        return 'archive'
    stream.seek(0)
    try:
        with tarfile.open(fileobj=stream):
            return 'archive'
    except Exception:
        return 'unsupported'
    finally:
        stream.seek(0)


def _downloads_output_path(desired_filename):
    downloads_dir = str(Path.home() / "Downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    base_name, ext = os.path.splitext(desired_filename)
    output_path = os.path.join(downloads_dir, desired_filename)
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(downloads_dir, f"{base_name}_{counter}{ext}")
        counter += 1
    return output_path


def _convert_image_file(file_storage, output_format):
    from PIL import Image

    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)

    # "ENC" não é um formato de imagem: é o botão para o caso clássico de arquivo
    # .enc do WhatsApp que na verdade já é uma imagem válida (JPEG/PNG) só com essa
    # extensão trocada pelo app. Aqui tratamos como um pedido de saída em PNG normal,
    # inclusive no nome do arquivo, para o resultado abrir em qualquer visualizador.
    if output_format == 'enc':
        output_format = 'png'

    if output_format in ('jpg', 'jpeg') and img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background

    original_name = os.path.splitext(file_storage.filename)[0]
    output_path = _downloads_output_path(f"{original_name}_convertido.{output_format}")

    try:
        # Deixa o Pillow inferir o formato pela extensão do arquivo de saída - é o
        # próprio Pillow (e plugins como o pillow-heif) que sabem mapear corretamente
        # ".jpg"/".heic"/etc para o codec certo.
        img.save(output_path)
    except (KeyError, OSError, ValueError) as e:
        raise UnsupportedConversionError(
            f"O Pillow não sabe salvar imagens no formato '{output_format.upper()}' ({e})."
        )

    return os.path.basename(output_path)


def _convert_media_file(file_storage, output_format):
    import subprocess
    import tempfile

    input_ext = os.path.splitext(file_storage.filename)[1] or '.tmp'
    tmp_in = tempfile.NamedTemporaryFile(suffix=input_ext, delete=False)
    try:
        file_storage.stream.seek(0)
        shutil.copyfileobj(file_storage.stream, tmp_in)
        tmp_in.close()

        original_name = os.path.splitext(file_storage.filename)[0]
        output_path = _downloads_output_path(f"{original_name}_convertido.{output_format}")

        result = subprocess.run(
            ['ffmpeg', '-y', '-i', tmp_in.name, output_path],
            capture_output=True, timeout=600
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            if os.path.exists(output_path):
                os.remove(output_path)
            stderr_lines = result.stderr.decode('utf-8', errors='ignore').strip().splitlines()
            detail = stderr_lines[-1] if stderr_lines else 'erro desconhecido do ffmpeg'
            raise UnsupportedConversionError(
                f"O ffmpeg não conseguiu converter para '.{output_format}': {detail}"
            )
    finally:
        os.remove(tmp_in.name)

    return os.path.basename(output_path)


def _read_archive(stream):
    """Lê o arquivo compactado e retorna ('bundle', [(nome, bytes), ...]) ou ('stream', bytes)."""
    stream.seek(0)
    if zipfile.is_zipfile(stream):
        stream.seek(0)
        entries = []
        with zipfile.ZipFile(stream) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    entries.append((info.filename, zf.read(info.filename)))
        return 'bundle', entries

    stream.seek(0)
    try:
        with tarfile.open(fileobj=stream) as tf:
            entries = []
            for member in tf.getmembers():
                if member.isfile():
                    extracted = tf.extractfile(member)
                    if extracted:
                        entries.append((member.name, extracted.read()))
            return 'bundle', entries
    except tarfile.ReadError:
        pass

    stream.seek(0)
    raw = stream.read()
    for decompress in (gzip.decompress, bz2.decompress, lzma.decompress):
        try:
            return 'stream', decompress(raw)
        except Exception:
            continue

    raise UnsupportedConversionError(
        "Este formato de arquivo compactado não é suportado (precisaria de uma "
        "ferramenta externa como unrar ou 7z)."
    )


def _write_bundle_archive(entries, output_format):
    buf = io.BytesIO()
    if output_format in ('zip', 'jar', 'apk', 'ipa'):
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries:
                zf.writestr(name, data)
    else:
        tar_modes = {
            'tar': 'w', 'tar.gz': 'w:gz', 'tgz': 'w:gz',
            'tar.bz2': 'w:bz2', 'tbz2': 'w:bz2', 'tar.xz': 'w:xz',
        }
        mode = tar_modes.get(output_format)
        if not mode:
            raise UnsupportedConversionError(
                f"Não é possível gerar um arquivo compactado no formato '{output_format}'."
            )
        with tarfile.open(fileobj=buf, mode=mode) as tf:
            for name, data in entries:
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _convert_archive_file(file_storage, output_format):
    file_storage.stream.seek(0)
    kind, payload = _read_archive(file_storage.stream)

    if output_format in ARCHIVE_STREAM_FORMATS:
        if kind == 'stream':
            raw = payload
        else:
            file_storage.stream.seek(0)
            raw = file_storage.stream.read()
        compressors = {'gz': gzip.compress, 'bz2': bz2.compress, 'xz': lzma.compress}
        data = compressors[output_format](raw)
    elif output_format in ARCHIVE_BUNDLE_FORMATS:
        if kind == 'bundle':
            entries = payload
        else:
            base_name = os.path.splitext(file_storage.filename)[0]
            entries = [(base_name, payload)]
        data = _write_bundle_archive(entries, output_format)
    else:
        raise UnsupportedConversionError(
            f"Conversão para '.{output_format}' não é suportada (precisaria de uma "
            "ferramenta externa como unrar, 7z ou dpkg)."
        )

    original_name = os.path.splitext(file_storage.filename)[0]
    output_path = _downloads_output_path(f"{original_name}_convertido.{output_format}")
    with open(output_path, 'wb') as f:
        f.write(data)
    return os.path.basename(output_path)


def _convert_uploaded_file(file_storage, output_format):
    category = _detect_file_category(file_storage.filename, file_storage.stream)
    if category == 'image':
        return _convert_image_file(file_storage, output_format)
    if category in ('audio', 'video'):
        return _convert_media_file(file_storage, output_format)
    if category == 'archive':
        return _convert_archive_file(file_storage, output_format)
    raise UnsupportedConversionError(
        "Este tipo de arquivo ainda não tem conversão real implementada nesta versão "
        "(documentos, apresentações, ebooks, fontes, CAD e modelos 3D não são suportados)."
    )


@app.route("/files", methods=["GET", "POST"], strict_slashes=False)
def files():
    status = None
    error = None

    if request.method == "POST":
        if 'file' not in request.files:
            error = "Nenhum arquivo selecionado."
        else:
            file = request.files['file']
            output_format = request.form.get('format', 'jpg').strip().lower()

            if file.filename == '':
                error = "Nenhum arquivo selecionado."
            else:
                try:
                    output_filename = _convert_uploaded_file(file, output_format)
                    status = f"✅ '{output_filename}' salvo na pasta Downloads!"
                except UnsupportedConversionError as e:
                    error = str(e)
                except Exception as e:
                    error = f"Erro ao converter: {str(e)}"

    return render_template_string(FILES_HTML, status=status, error=error)


@app.route("/estimate_size", methods=["POST"])
def estimate_size():
    try:
        if 'file' not in request.files:
            return jsonify({"success": False})

        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False})

        category = _detect_file_category(file.filename, file.stream)

        if category == 'image':
            from PIL import Image
            file.stream.seek(0)
            img = Image.open(file.stream)
            width, height = img.size
            pixels = width * height

            # Estimativas para todos os formatos de imagem
            sizes = {
                'jpg': int(pixels * 0.15), 'jpeg': int(pixels * 0.15), 'jpe': int(pixels * 0.15),
                'jif': int(pixels * 0.15), 'jfi': int(pixels * 0.15), 'jfif': int(pixels * 0.15),
                'jps': int(pixels * 0.15), 'png': int(pixels * 2.5), 'webp': int(pixels * 0.1),
                'bmp': int(pixels * 3), 'gif': int(pixels * 0.5), 'tiff': int(pixels * 3.5),
                'ico': int(pixels * 0.3), 'avif': int(pixels * 0.08), 'heic': int(pixels * 0.12),
                'heif': int(pixels * 0.12), 'svg': int(pixels * 0.05), 'psd': int(pixels * 4),
                'tga': int(pixels * 1), 'dds': int(pixels * 0.5), 'exr': int(pixels * 6),
                'hdr': int(pixels * 4), 'jp2': int(pixels * 0.2), 'jnx': int(pixels * 0.2),
                'pcx': int(pixels * 1), 'ppm': int(pixels * 3), 'pbm': int(pixels * 0.125),
                'pgm': int(pixels * 1), 'pnm': int(pixels * 1.5), 'pfm': int(pixels * 4),
                'pam': int(pixels * 3), 'pgx': int(pixels * 1), 'xcf': int(pixels * 3),
                'xpm': int(pixels * 1), 'xbm': int(pixels * 0.125), 'xwd': int(pixels * 3),
                'cur': int(pixels * 0.3), 'dcm': int(pixels * 2), 'fax': int(pixels * 0.125),
                'fts': int(pixels * 4), 'g3': int(pixels * 0.125), 'g4': int(pixels * 0.125),
                'gv': int(pixels * 0.5), 'hrz': int(pixels * 0.5), 'ipl': int(pixels * 1),
                'jbg': int(pixels * 0.125), 'jbig': int(pixels * 0.125), 'mac': int(pixels * 1),
                'map': int(pixels * 3), 'mng': int(pixels * 1), 'mtv': int(pixels * 1),
                'otb': int(pixels * 0.125), 'pal': int(pixels * 1.5), 'palm': int(pixels * 1),
                'pcd': int(pixels * 1), 'pct': int(pixels * 1), 'pdb': int(pixels * 1),
                'pes': int(pixels * 0.5), 'picon': int(pixels * 0.5), 'pict': int(pixels * 1),
                'pix': int(pixels * 3), 'plasma': int(pixels * 3), 'pwp': int(pixels * 1),
                'ras': int(pixels * 3), 'rgb': int(pixels * 3), 'rgba': int(pixels * 4),
                'rgbo': int(pixels * 4), 'rgf': int(pixels * 3), 'rla': int(pixels * 4),
                'rle': int(pixels * 1), 'sct': int(pixels * 3), 'sfw': int(pixels * 1),
                'sgi': int(pixels * 3), 'six': int(pixels * 0.5), 'sixel': int(pixels * 0.5),
                'sun': int(pixels * 3), 'tim': int(pixels * 2), 'tm2': int(pixels * 2),
                'uyvy': int(pixels * 2), 'viff': int(pixels * 3), 'vips': int(pixels * 3),
                'wbmp': int(pixels * 0.125), 'wmz': int(pixels * 1), 'wpg': int(pixels * 1),
                'xc': int(pixels * 3), 'xv': int(pixels * 3), 'yuv': int(pixels * 1.5),
                'cr2': int(pixels * 1.5), 'nef': int(pixels * 1.5), 'arw': int(pixels * 1.5),
                'dng': int(pixels * 1.5), 'orf': int(pixels * 1.5), 'raf': int(pixels * 1.5),
                'rw2': int(pixels * 1.5), 'pef': int(pixels * 1.5), 'sr2': int(pixels * 1.5),
                '3fr': int(pixels * 1.5), 'mef': int(pixels * 1.5), 'mrw': int(pixels * 1.5),
                'dcr': int(pixels * 1.5), 'kdc': int(pixels * 1.5), 'k25': int(pixels * 1.5),
                'crw': int(pixels * 1.5), 'erf': int(pixels * 1.5), 'iiq': int(pixels * 1.5),
                'nrw': int(pixels * 1.5), 'srf': int(pixels * 1.5), 'x3f': int(pixels * 1.5),
                'enc': int(pixels * 2.5)
            }

            return jsonify({"success": True, "sizes": sizes, "type": "image"})

        file.stream.seek(0)
        file_size = len(file.stream.read())

        if category == 'video':
            sizes = {ext: int(file_size * 0.8) for ext in VIDEO_EXTS}
            return jsonify({"success": True, "sizes": sizes, "type": "video"})

        if category == 'audio':
            sizes = {ext: int(file_size * 0.9) for ext in AUDIO_EXTS}
            return jsonify({"success": True, "sizes": sizes, "type": "audio"})

        if category == 'archive':
            supported = sorted(ARCHIVE_BUNDLE_FORMATS | ARCHIVE_STREAM_FORMATS)
            sizes = {ext: int(file_size * 0.9) for ext in supported}
            return jsonify({"success": True, "sizes": sizes, "type": "archive"})

        return jsonify({
            "success": False,
            "message": "Este tipo de arquivo ainda não é suportado para conversão "
                        "(documentos, apresentações, ebooks, fontes, CAD e 3D)."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

CONFIG_HTML = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Instruções - LocalTools</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: radial-gradient(at 0% 0%, rgba(34, 197, 94, 0.08) 0px, transparent 50%), radial-gradient(at 100% 0%, rgba(59, 130, 246, 0.06) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 40px 15px;
      padding-top: 100px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
    }
    .logo {
      font-size: 48px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-align: center;
      margin-bottom: 10px;
      letter-spacing: 8px;
    }
    .tagline {
      text-align: center;
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      font-weight: 500;
    }
    .app-section {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 20px;
      padding: 32px;
      margin-bottom: 24px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
    }
    .app-header {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
    }
    .app-icon {
      font-size: 48px;
    }
    .app-title {
      font-size: 28px;
      font-weight: 700;
      color: #f8fafc;
    }
    .app-description {
      font-size: 15px;
      color: #94a3b8;
      line-height: 1.8;
      margin-bottom: 20px;
    }
    .features {
      display: grid;
      gap: 12px;
    }
    .feature {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 12px;
      background: rgba(15, 23, 42, 0.6);
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    .feature-icon {
      font-size: 20px;
      flex-shrink: 0;
    }
    .feature-text {
      flex: 1;
    }
    .feature-title {
      font-size: 14px;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 4px;
    }
    .feature-desc {
      font-size: 13px;
      color: #64748b;
      line-height: 1.6;
    }
    .sub-section {
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
    }
    .sub-title {
      font-size: 18px;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 12px;
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="container">
    <div class="logo">LOCALTOOLS</div>
    <div class="tagline">Guia Completo de Funcionalidades</div>
    
    <!-- VERTO -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🎬</div>
        <div class="app-title">Verto - Conversor de Mídia</div>
      </div>
      <div class="app-description">
        Baixe vídeos e áudios do YouTube com seleção de qualidade e cálculo automático de tamanho.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">📺</div>
          <div class="feature-text">
            <div class="feature-title">Download de Vídeos MP4</div>
            <div class="feature-desc">Qualidades: 8K, 4K, 2K, 1080p, 720p, 480p, 360p. Tamanho estimado em tempo real.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎵</div>
          <div class="feature-text">
            <div class="feature-title">Download de Áudio MP3</div>
            <div class="feature-desc">Bitrates: 320kbps, 256kbps, 192kbps, 128kbps. Extração de áudio de alta qualidade.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🖼️</div>
          <div class="feature-text">
            <div class="feature-title">Download de Thumbnails</div>
            <div class="feature-desc">Formatos PNG e JPG. Resoluções: Máxima, Alta, Média, Padrão.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <div class="feature-text">
            <div class="feature-title">Preview em Tempo Real</div>
            <div class="feature-desc">Visualize thumbnail, título e duração antes de baixar.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- PURPLEFLIX -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🎮</div>
        <div class="app-title">PurpleFlix - Streaming</div>
      </div>
      <div class="app-description">
        Plataforma de streaming integrada.
      </div>
    </div>

    <!-- TEMPO -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">⏰</div>
        <div class="app-title">Tempo - Relógio e Calendário</div>
      </div>
      <div class="app-description">
        Relógio digital e analógico com calendário interativo e feriados brasileiros.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🕐</div>
          <div class="feature-text">
            <div class="feature-title">Relógio Duplo</div>
            <div class="feature-desc">Digital e analógico sincronizados em tempo real.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📅</div>
          <div class="feature-text">
            <div class="feature-title">Calendário Interativo</div>
            <div class="feature-desc">Navegação por meses e anos. Visualização de dias, meses e anos.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎉</div>
          <div class="feature-text">
            <div class="feature-title">Feriados Brasileiros</div>
            <div class="feature-desc">Lista completa de feriados nacionais de 2024-2026.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- PDFS -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">📄</div>
        <div class="app-title">PDFs - Suite Completa</div>
      </div>
      <div class="app-description">
        Ferramentas profissionais para manipulação de PDFs.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">✂️</div>
          <div class="feature-text">
            <div class="feature-title">Dividir PDF</div>
            <div class="feature-desc">Divida PDFs em múltiplos arquivos por intervalos de páginas personalizados.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔄</div>
          <div class="feature-text">
            <div class="feature-title">Converter PDF</div>
            <div class="feature-desc">PDF ↔ Imagens (JPG/PNG). Imagens → PDF.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🗜️</div>
          <div class="feature-text">
            <div class="feature-title">Comprimir PDF</div>
            <div class="feature-desc">Reduza o tamanho com 3 níveis de qualidade (Baixa, Média, Alta).</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔄</div>
          <div class="feature-text">
            <div class="feature-title">Girar PDF</div>
            <div class="feature-desc">Rotação de páginas: 90°, 180°, 270°. Individual ou em massa.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔍</div>
          <div class="feature-text">
            <div class="feature-title">Comparar PDFs</div>
            <div class="feature-desc">Compare múltiplos PDFs e veja diferenças e similaridades.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔧</div>
          <div class="feature-text">
            <div class="feature-title">Reparar PDF</div>
            <div class="feature-desc">5 estratégias de recuperação para PDFs corrompidos.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔒</div>
          <div class="feature-text">
            <div class="feature-title">Proteger PDF</div>
            <div class="feature-desc">Adicione senha de criptografia aos seus PDFs.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔓</div>
          <div class="feature-text">
            <div class="feature-title">Desbloquear PDF</div>
            <div class="feature-desc">Remova senhas com força bruta (10.000 combinações) ou senha conhecida.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">✏️</div>
          <div class="feature-text">
            <div class="feature-title">Editar PDF</div>
            <div class="feature-desc">Extraia texto e crie novo PDF editado.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💧</div>
          <div class="feature-text">
            <div class="feature-title">Marca D'água</div>
            <div class="feature-desc">Adicione texto ou imagem como marca d'água. 15 posições + arraste customizado.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💥</div>
          <div class="feature-text">
            <div class="feature-title">Corromper PDF</div>
            <div class="feature-desc">4 níveis de corrupção para testes (Leve, Médio, Pesado, Extremo).</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔗</div>
          <div class="feature-text">
            <div class="feature-title">Mesclar PDFs</div>
            <div class="feature-desc">Una múltiplos PDFs em um só. Selecione páginas específicas.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- OFFICE -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🗃️</div>
        <div class="app-title">Office - Conversor e Reparador</div>
      </div>
      <div class="app-description">
        Converta e recupere arquivos do pacote Office (Word, Excel, PowerPoint) usando o motor do LibreOffice.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🔄</div>
          <div class="feature-text">
            <div class="feature-title">Converter</div>
            <div class="feature-desc">DOCX/XLSX/PPTX ↔ ODT/ODS/ODP, PDF e imagens PNG/JPG (uma por página ou slide) sem problemas de fonte ou acentuação.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🩺</div>
          <div class="feature-text">
            <div class="feature-title">Reparar e Recuperar</div>
            <div class="feature-desc">5 níveis de recuperação: detecção do formato real (corrige extensão trocada), reconstrução do ZIP, validação nativa, reparo via LibreOffice e recuperação bruta de texto.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔀</div>
          <div class="feature-text">
            <div class="feature-title">Extensão errada não é problema</div>
            <div class="feature-desc">Se um .xlsx na verdade é um .docx por dentro (ou vice-versa), a ferramenta identifica o conteúdo real e recupera pelo formato certo.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- TRANSPARÊNCIA -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🎨</div>
        <div class="app-title">Transparência - Remover Fundo</div>
      </div>
      <div class="app-description">
        Remova fundos de imagens automaticamente usando IA.
      </div>
    </div>

    <!-- QR CODE -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🔲</div>
        <div class="app-title">QR Code - Gerador Gratuito</div>
      </div>
      <div class="app-description">
        Gere QR Codes estáticos permanentes sem marcas d'água ou expiração.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🔗</div>
          <div class="feature-text">
            <div class="feature-title">Links/URLs</div>
            <div class="feature-desc">Qualquer endereço web.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📶</div>
          <div class="feature-text">
            <div class="feature-title">Wi-Fi</div>
            <div class="feature-desc">Compartilhe credenciais de rede.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">👤</div>
          <div class="feature-text">
            <div class="feature-title">vCard</div>
            <div class="feature-desc">Cartão de visita digital.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💰</div>
          <div class="feature-text">
            <div class="feature-title">PIX</div>
            <div class="feature-desc">Pagamentos instantâneos.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎨</div>
          <div class="feature-text">
            <div class="feature-title">Customização Total</div>
            <div class="feature-desc">Cores, tamanho, bordas, logo central, 4 níveis de correção de erro.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- COMPRESSOR -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🗜️</div>
        <div class="app-title">Compressor - Redução de Tamanho</div>
      </div>
      <div class="app-description">
        Comprima imagens, vídeos e áudios mantendo qualidade.
      </div>
    </div>

    <!-- ARQUIVOS -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">📁</div>
        <div class="app-title">Arquivos - Conversor Universal</div>
      </div>
      <div class="app-description">
        Converta entre 150+ formatos de arquivo com estimativa de tamanho.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🖼️</div>
          <div class="feature-text">
            <div class="feature-title">Imagens (50+ formatos)</div>
            <div class="feature-desc">PNG, JPG, WEBP, HEIC, RAW, TIFF, BMP, GIF, SVG, PSD, etc.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎬</div>
          <div class="feature-text">
            <div class="feature-title">Vídeos (35+ formatos)</div>
            <div class="feature-desc">MP4, AVI, MKV, MOV, WEBM, FLV, etc.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎵</div>
          <div class="feature-text">
            <div class="feature-title">Áudios (40+ formatos)</div>
            <div class="feature-desc">MP3, WAV, FLAC, AAC, OGG, OPUS, etc.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📄</div>
          <div class="feature-text">
            <div class="feature-title">Documentos, eBooks, Fontes, CAD, 3D</div>
            <div class="feature-desc">PDF, DOCX, EPUB, TTF, DWG, OBJ e muito mais.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- TRANSCREVER -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🎤</div>
        <div class="app-title">Transcrever - Áudio para Texto</div>
      </div>
      <div class="app-description">
        Converta áudios e vídeos em texto formatado usando reconhecimento de voz.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🎯</div>
          <div class="feature-text">
            <div class="feature-title">Reconhecimento Avançado</div>
            <div class="feature-desc">Sample rate 48kHz, filtros de áudio (FFT, speechnorm), chunks de 20s.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🌍</div>
          <div class="feature-text">
            <div class="feature-title">Múltiplos Idiomas</div>
            <div class="feature-desc">PT-BR, EN-US, PT-PT, ES-ES com fallback automático.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📝</div>
          <div class="feature-text">
            <div class="feature-title">Formatação Automática</div>
            <div class="feature-desc">Capitalização de sentenças e texto limpo.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📋</div>
          <div class="feature-text">
            <div class="feature-title">Copiar Resultado</div>
            <div class="feature-desc">Botão para copiar transcrição para área de transferência.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- GHOST TOOL -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">👻</div>
        <div class="app-title">Ghost Tool - Removedor de Metadados</div>
      </div>
      <div class="app-description">
        Remova metadados de múltiplos arquivos simultaneamente. GPS, autor, datas, câmera - tudo apagado permanentemente.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">📷</div>
          <div class="feature-text">
            <div class="feature-title">Imagens (50+ formatos)</div>
            <div class="feature-desc">Remove EXIF, GPS, câmera, software. Recria pixel por pixel.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎬</div>
          <div class="feature-text">
            <div class="feature-title">Vídeos e Áudios (70+ formatos)</div>
            <div class="feature-desc">Remove metadados com FFmpeg. Mantém qualidade original.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📄</div>
          <div class="feature-text">
            <div class="feature-title">Documentos Office</div>
            <div class="feature-desc">Remove autor, empresa, datas de DOCX, XLSX, PPTX.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📚</div>
          <div class="feature-text">
            <div class="feature-title">PDFs, eBooks, Arquivos</div>
            <div class="feature-desc">Remove metadados de PDFs, EPUBs, ZIPs e mais.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <div class="feature-text">
            <div class="feature-title">Processamento em Massa</div>
            <div class="feature-desc">Múltiplos arquivos simultaneamente. Download em lote.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔒</div>
          <div class="feature-text">
            <div class="feature-title">100% Local</div>
            <div class="feature-desc">Arquivos nunca saem do seu computador.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- STEALTH -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🕵️</div>
        <div class="app-title">Stealth - Esteganografia Criptografada</div>
      </div>
      <div class="app-description">
        Esconda arquivos secretos dentro de imagens, vídeos, áudios ou PDFs com criptografia AES-256 opcional.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🔐</div>
          <div class="feature-text">
            <div class="feature-title">Esconder Arquivos</div>
            <div class="feature-desc">Múltiplos arquivos em imagens (LSB), vídeos, áudios ou PDFs. Senha opcional.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔓</div>
          <div class="feature-text">
            <div class="feature-title">Extrair Arquivos</div>
            <div class="feature-desc">Recupere arquivos escondidos com ou sem senha. Detecção automática.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🛡️</div>
          <div class="feature-text">
            <div class="feature-title">Criptografia AES-256-GCM</div>
            <div class="feature-desc">Criptografia militar com PBKDF2, salt, nonce e tag de autenticação.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎨</div>
          <div class="feature-text">
            <div class="feature-title">LSB Steganography</div>
            <div class="feature-desc">Esconde dados nos bits menos significativos dos pixels. Invisível ao olho humano.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📦</div>
          <div class="feature-text">
            <div class="feature-title">Múltiplos Arquivos</div>
            <div class="feature-desc">Esconda vários arquivos de uma vez. Compactação automática em ZIP.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎯</div>
          <div class="feature-text">
            <div class="feature-title">Formato Original Mantido</div>
            <div class="feature-desc">MP4 → MP4, MP3 → MP3, PDF → PDF. Arquivo de saída mantém formato de cobertura.</div>
          </div>
        </div>
      </div>
      <div class="sub-section">
        <div class="sub-title">📋 Casos de Uso</div>
        <div class="features">
          <div class="feature">
            <div class="feature-icon">📱</div>
            <div class="feature-text">
              <div class="feature-desc">Envie documentos secretos via redes sociais (Instagram, WhatsApp)</div>
            </div>
          </div>
          <div class="feature">
            <div class="feature-icon">💾</div>
            <div class="feature-text">
              <div class="feature-desc">Backup criptografado disfarçado em fotos comuns</div>
            </div>
          </div>
          <div class="feature">
            <div class="feature-icon">🔒</div>
            <div class="feature-text">
              <div class="feature-desc">Comunicação segura e discreta</div>
            </div>
          </div>
          <div class="feature">
            <div class="feature-icon">🎭</div>
            <div class="feature-text">
              <div class="feature-desc">Proteção de dados sensíveis em plain sight</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- CENSOR -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🔒</div>
        <div class="app-title">Censor - Proteção de Privacidade com IA</div>
      </div>
      <div class="app-description">
        Censura automática de informações sensíveis em imagens usando IA. Detecta e oculta rostos, documentos, placas, e-mails, telefones, cartões, sites, nomes, @IDs e mais.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">👤</div>
          <div class="feature-text">
            <div class="feature-title">Detecção de Rostos</div>
            <div class="feature-desc">BlazeFace (TensorFlow.js) detecta rostos automaticamente em tempo real.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔤</div>
          <div class="feature-text">
            <div class="feature-title">Documentos (CPF, RG, CNH)</div>
            <div class="feature-desc">OCR com Tesseract.js identifica números de documentos brasileiros.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🚗</div>
          <div class="feature-text">
            <div class="feature-title">Placas de Veículos</div>
            <div class="feature-desc">Detecta placas padrão brasileiro (ABC1D23) e Mercosul.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">✉️</div>
          <div class="feature-text">
            <div class="feature-title">E-mails</div>
            <div class="feature-desc">Identifica e censura endereços de e-mail em imagens.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📞</div>
          <div class="feature-text">
            <div class="feature-title">Telefones</div>
            <div class="feature-desc">Detecta números de telefone (fixo e celular) com DDD.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💳</div>
          <div class="feature-text">
            <div class="feature-title">Cartões de Crédito</div>
            <div class="feature-desc">Identifica padrões de 16 dígitos de cartões.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🌐</div>
          <div class="feature-text">
            <div class="feature-title">Sites e URLs</div>
            <div class="feature-desc">Detecta endereços web (http://, https://, www.) em imagens.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">👤</div>
          <div class="feature-text">
            <div class="feature-title">Nomes de Pessoas</div>
            <div class="feature-desc">Identifica nomes próprios (padrão Nome Sobrenome).</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">@</div>
          <div class="feature-text">
            <div class="feature-title">IDs e Handles</div>
            <div class="feature-desc">Detecta @usernames de redes sociais (Twitter, Instagram, etc).</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎨</div>
          <div class="feature-text">
            <div class="feature-title">8 Tipos de Censura</div>
            <div class="feature-desc">Desfoque, Pixelizar, Tarja Preta, Tarja Branca, Emoji 😎, Gradiente, Redação ████, Ruído.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🤖</div>
          <div class="feature-text">
            <div class="feature-title">Intensidade Automática</div>
            <div class="feature-desc">IA analisa brilho da imagem e ajusta intensidade automaticamente (ou manual: Baixa/Média/Alta).</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <div class="feature-text">
            <div class="feature-title">Processamento em Massa</div>
            <div class="feature-desc">Até 20 imagens simultaneamente com download em lote.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🔒</div>
          <div class="feature-text">
            <div class="feature-title">100% Local no Navegador</div>
            <div class="feature-desc">IA roda no navegador. Arquivos nunca saem do seu computador.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- SOCIAL PREVIEW -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">📱</div>
        <div class="app-title">Social Preview - Estúdio de Preview de Redes Sociais</div>
      </div>
      <div class="app-description">
        Visualize como seu conteúdo aparecerá em 8 plataformas diferentes em 3 tipos de dispositivos. Exporte em 11 formatos otimizados.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">📱</div>
          <div class="feature-text">
            <div class="feature-title">Preview Mobile</div>
            <div class="feature-desc">Twitter, LinkedIn, Facebook, WhatsApp, Open Graph, Instagram, Instagram Story, Instagram Reels.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💻</div>
          <div class="feature-text">
            <div class="feature-title">Preview Desktop</div>
            <div class="feature-desc">Visualização em tela grande para todas as 8 plataformas.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📡</div>
          <div class="feature-text">
            <div class="feature-title">Preview Tablet</div>
            <div class="feature-desc">Visualização intermediária para todas as 8 plataformas.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📦</div>
          <div class="feature-text">
            <div class="feature-title">Exportação em Massa</div>
            <div class="feature-desc">11 formatos otimizados: Twitter 1200×675, LinkedIn 1200×627, Facebook 1200×630, Instagram Square 1080×1080, Instagram Story 1080×1920, Instagram Reels 1080×1920, Open Graph 1200×630, Desktop Full HD 1920×1080, Desktop 2K 2560×1440, Tablet Landscape 1024×768, Tablet Portrait 768×1024.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">⚡</div>
          <div class="feature-text">
            <div class="feature-title">Atualização em Tempo Real</div>
            <div class="feature-desc">Todos os 24 previews atualizam simultaneamente ao editar.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- CLEAN READER -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🧹</div>
        <div class="app-title">Clean Reader - Limpador de Distração</div>
      </div>
      <div class="app-description">
        Extraia conteúdo limpo de qualquer site removendo anúncios, pop-ups e poluição visual. Leia ou exporte para PDF, Markdown ou EPUB.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🧹</div>
          <div class="feature-text">
            <div class="feature-title">Extração Inteligente</div>
            <div class="feature-desc">Remove scripts, styles, nav, header, footer, aside, forms, buttons automaticamente.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">👁️</div>
          <div class="feature-text">
            <div class="feature-title">Modo Leitura</div>
            <div class="feature-desc">Tela cheia com fundo branco, texto centralizado e fonte otimizada para leitura.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📄</div>
          <div class="feature-text">
            <div class="feature-title">Exportar PDF</div>
            <div class="feature-desc">Salva artigo limpo em PDF formatado com ReportLab.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📝</div>
          <div class="feature-text">
            <div class="feature-title">Exportar Markdown</div>
            <div class="feature-desc">Converte para Markdown preservando links e formatação.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📚</div>
          <div class="feature-text">
            <div class="feature-title">Exportar EPUB</div>
            <div class="feature-desc">Gera eBook para Kindle e leitores digitais.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ISOLADOR DE VOZ -->
    <div class="app-section">
      <div class="app-header">
        <div class="app-icon">🎤</div>
        <div class="app-title">Isolador de Voz - Neural Audio Splitter</div>
      </div>
      <div class="app-description">
        Separe voz e música de qualquer áudio usando IA Demucs (Meta). Ideal para remover ruídos, extrair vocais ou criar versões instrumentais.
      </div>
      <div class="features">
        <div class="feature">
          <div class="feature-icon">🎤</div>
          <div class="feature-text">
            <div class="feature-title">Isolar Voz</div>
            <div class="feature-desc">Extrai apenas a voz do áudio, removendo música e ruídos de fundo.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🎵</div>
          <div class="feature-text">
            <div class="feature-title">Isolar Música</div>
            <div class="feature-desc">Extrai apenas a música instrumental, removendo vocais.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">🤖</div>
          <div class="feature-text">
            <div class="feature-title">IA Demucs (Meta)</div>
            <div class="feature-desc">Modelo neural state-of-the-art da Meta/Facebook Research. Open-source e gratuito.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">⏱️</div>
          <div class="feature-text">
            <div class="feature-title">Sem Limite de Tempo</div>
            <div class="feature-desc">Processa áudios de qualquer duração. Contador de tempo em tempo real.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">📁</div>
          <div class="feature-text">
            <div class="feature-title">Múltiplos Formatos</div>
            <div class="feature-desc">Suporta MP3, WAV, MP4, M4A, OGG, FLAC e mais. Saída em WAV de alta qualidade.</div>
          </div>
        </div>
        <div class="feature">
          <div class="feature-icon">💾</div>
          <div class="feature-text">
            <div class="feature-title">Salva em Downloads</div>
            <div class="feature-desc">Arquivos processados salvos automaticamente na pasta Downloads com nomes únicos.</div>
          </div>
        </div>
      </div>
    </div>

    <div style="height: 60px;"></div>
  </div>
</body>
</html>
"""
FILES_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Conversor de Arquivos</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
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
      padding: 40px 15px;
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
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 8px 24px rgba(0, 0, 0, 0.5),
        0 0 40px rgba(34, 197, 94, 0.03);
    }
    .back-button::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
      box-shadow: 
        0 0 0 1px rgba(34, 197, 94, 0.2),
        0 12px 32px rgba(0, 0, 0, 0.6),
        0 0 60px rgba(34, 197, 94, 0.15);
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4));
      animation: glow-pulse 3s ease-in-out infinite;
      margin-bottom: 10px;
      position: relative;
      z-index: 1;
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
    .format-selector {
      display: flex;
      gap: 12px;
      margin-bottom: 40px;
      justify-content: center;
      flex-wrap: wrap;
      position: relative;
      z-index: 1;
      max-width: 95vw;
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
    }
    .format-btn.unavailable {
      opacity: 0.4;
      pointer-events: none;
    }
    .format-btn:hover {
      border-color: rgba(34, 197, 94, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      transform: translateY(-2px);
    }
    .format-btn.active {
      border-color: #22c55e;
      background: rgba(34, 197, 94, 0.12);
      color: #22c55e;
      box-shadow: 0 0 24px rgba(34, 197, 94, 0.2);
    }
    .file-size-info {
      margin-top: 16px;
      padding: 12px;
      background: rgba(34, 197, 94, 0.08);
      border-radius: 10px;
      border: 1px solid rgba(34, 197, 94, 0.2);
      text-align: center;
      display: none;
    }
    .file-size-info.show {
      display: block;
    }
    .file-size-info p {
      margin: 0;
      font-size: 13px;
      color: #22c55e;
      font-weight: 600;
    }
    .file-preview {
      margin-top: 16px;
      padding: 12px;
      background: rgba(15, 23, 42, 0.6);
      border-radius: 10px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      display: none;
      text-align: center;
    }
    .file-preview.show {
      display: block;
    }
    .file-preview img {
      max-width: 100%;
      max-height: 200px;
      border-radius: 8px;
      object-fit: contain;
    }
    .file-input-wrapper {
      position: relative;
    }
    .file-label-wrapper {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .clear-file {
      width: 24px;
      height: 24px;
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.4);
      border-radius: 50%;
      display: none;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      color: #ef4444;
      font-size: 16px;
      font-weight: bold;
      transition: all 0.3s;
    }
    .clear-file:hover {
      background: rgba(239, 68, 68, 0.3);
      border-color: #ef4444;
      transform: scale(1.1);
    }
    .clear-file.show {
      display: flex;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 20px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(34, 197, 94, 0.05);
      width: 100%;
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
    input[type="file"] {
      width: 100%;
      padding: 16px;
      border-radius: 12px;
      border: 2px dashed rgba(148, 163, 184, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      font-size: 14px;
      outline: none;
      transition: all 0.3s;
      cursor: pointer;
      text-align: center;
    }
    input[type="file"]::file-selector-button {
      padding: 12px 28px;
      border: none;
      border-radius: 999px;
      background: linear-gradient(135deg, #22c55e, #16a34a);
      color: white;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      margin-right: 16px;
      transition: all 0.3s;
      box-shadow: 0 4px 12px rgba(34, 197, 94, 0.2);
    }
    input[type="file"]::file-selector-button:hover {
      background: linear-gradient(135deg, #16a34a, #15803d);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(34, 197, 94, 0.3);
    }
    input[type="file"]:hover {
      border-color: rgba(34, 197, 94, 0.5);
      background: rgba(15, 23, 42, 0.8);
      border-style: solid;
    }
    input[type="file"]:focus {
      border-color: #22c55e;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
      border-style: solid;
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
    @media (max-width: 640px) {
      body { padding: 30px 10px; padding-top: 100px; }
      .logo { font-size: 48px; letter-spacing: 12px; }
      .card { padding: 24px 16px; }
    }
    .more-formats {
      margin-top: 48px;
      width: 100%;
      max-width: 1200px;
      position: relative;
      z-index: 1;
    }
    .more-formats h2 {
      font-size: 20px;
      color: #cbd5e1;
      margin-bottom: 24px;
      text-align: center;
      font-weight: 600;
    }
    .format-category {
      margin-bottom: 32px;
    }
    .format-category h3 {
      font-size: 16px;
      color: #94a3b8;
      margin-bottom: 12px;
      font-weight: 600;
    }
    .formats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(85px, 1fr));
      gap: 8px;
      background: rgba(15, 23, 42, 0.4);
      border-radius: 16px;
      padding: 16px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
    }
    .format-item {
      padding: 10px 6px;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 8px;
      text-align: center;
      font-size: 10px;
      font-weight: 600;
      color: #64748b;
      cursor: pointer;
      transition: all 0.3s;
      opacity: 0.4;
      min-height: 38px;
      display: flex;
      align-items: center;
      justify-content: center;
      word-break: break-word;
      hyphens: auto;
    }
    .format-item.available {
      opacity: 1;
      color: #94a3b8;
    }
    .format-item.available:hover {
      background: rgba(34, 197, 94, 0.12);
      border-color: #22c55e;
      color: #22c55e;
      transform: translateY(-2px);
    }
    .format-item.active {
      background: rgba(34, 197, 94, 0.12);
      border-color: #22c55e;
      color: #22c55e;
      box-shadow: 0 0 16px rgba(34, 197, 94, 0.2);
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">Arquivos</div>
  <div class="tagline">Conversor de Arquivos Profissional</div>
  
  <div class="format-selector">
    <div class="format-btn active" data-format="png"><span>🖼️ PNG</span></div>
    <div class="format-btn" data-format="jpg"><span>📷 JPG</span></div>
    <div class="format-btn" data-format="jpeg"><span>📷 JPEG</span></div>
    <div class="format-btn" data-format="webp"><span>🌐 WEBP</span></div>
    <div class="format-btn" data-format="heic"><span>📱 HEIC</span></div>
    <div class="format-btn" data-format="enc"><span>🔐 ENC</span></div>
  </div>
  
  <div class="card">
    <h1>Conversor de Imagens</h1>
    <p class="subtitle">Selecione uma imagem e escolha o formato de saída</p>

    <form method="POST" enctype="multipart/form-data" id="convert-form">
      <div class="file-label-wrapper">
        <label for="file">Arquivo de entrada</label>
        <div class="clear-file" id="clear-file" onclick="clearFile()">×</div>
      </div>
      <div class="file-input-wrapper">
        <input type="file" id="file" name="file" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.rar,.7z,.tar,.gz,.bz2,.txt,.csv,.json,.xml,.html,.css,.js,.py,.java,.cpp,.c,.h,.php,.rb,.go,.rs,.swift,.kt,.ts,.jsx,.tsx,.vue,.sql,.md,.yaml,.yml,.toml,.ini,.cfg,.conf,.log,.sh,.bat,.ps1,.cmd,.exe,.dll,.so,.dylib,.app,.dmg,.pkg,.deb,.rpm,.apk,.ipa,.iso,.img,.bin,.dat,.db,.sqlite,.mdb,.accdb,.psd,.ai,.eps,.svg,.sketch,.fig,.xd,.indd,.dwg,.dxf,.stl,.obj,.fbx,.blend,.max,.ma,.mb,.3ds,.dae,.gltf,.glb,.usd,.wrl,.x3d,.ply,.off,.iges,.step,.stp,.sat,.sab,.catpart,.prt,.asm,.sldprt,.ifc,.rvt,.rfa,.skp,.3dm,.nef,.cr2,.arw,.dng,.orf,.raf,.rw2,.pef,.sr2,.raw,.heic,.heif,.avif,.webp,.tiff,.tif,.bmp,.ico,.cur,.ani,.pcx,.tga,.dds,.exr,.hdr,.jp2,.j2k,.jpf,.jpx,.jpm,.mj2,.jxr,.wdp,.hdp" required>
      </div>
      
      <input type="hidden" id="format" name="format" value="png">
      
      <div class="file-size-info" id="file-size-info">
        <p id="size-text">Tamanho estimado: Calculando...</p>
      </div>
      
      <div class="file-preview" id="file-preview">
        <img id="preview-image" src="" alt="Preview">
      </div>
      
      <button type="submit" id="convert-button">
        <span class="btn-text">🔄 Converter</span>
      </button>
    </form>

    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% else %}
      <div class="status">Pronto para converter.</div>
    {% endif %}
  </div>
  
  <div class="more-formats">
    <h2>Mais Formatos Suportados</h2>
    <div class="format-category">
      <h3>📷 Imagens</h3>
      <div class="formats-grid" id="image-formats">
        <div class="format-item" data-format="bmp" data-category="image">BMP</div>
        <div class="format-item" data-format="gif" data-category="image">GIF</div>
        <div class="format-item" data-format="tiff" data-category="image">TIFF</div>
        <div class="format-item" data-format="ico" data-category="image">ICO</div>
        <div class="format-item" data-format="avif" data-category="image">AVIF</div>
        <div class="format-item" data-format="svg" data-category="image">SVG</div>
        <div class="format-item" data-format="psd" data-category="image">PSD</div>
        <div class="format-item" data-format="tga" data-category="image">TGA</div>
        <div class="format-item" data-format="dds" data-category="image">DDS</div>
        <div class="format-item" data-format="exr" data-category="image">EXR</div>
        <div class="format-item" data-format="hdr" data-category="image">HDR</div>
        <div class="format-item" data-format="heif" data-category="image">HEIF</div>
        <div class="format-item" data-format="jp2" data-category="image">JP2</div>
        <div class="format-item" data-format="jfif" data-category="image">JFIF</div>
        <div class="format-item" data-format="jpe" data-category="image">JPE</div>
        <div class="format-item" data-format="jif" data-category="image">JIF</div>
        <div class="format-item" data-format="jfi" data-category="image">JFI</div>
        <div class="format-item" data-format="jps" data-category="image">JPS</div>
        <div class="format-item" data-format="jnx" data-category="image">JNX</div>
        <div class="format-item" data-format="pcx" data-category="image">PCX</div>
        <div class="format-item" data-format="ppm" data-category="image">PPM</div>
        <div class="format-item" data-format="pbm" data-category="image">PBM</div>
        <div class="format-item" data-format="pgm" data-category="image">PGM</div>
        <div class="format-item" data-format="pnm" data-category="image">PNM</div>
        <div class="format-item" data-format="pfm" data-category="image">PFM</div>
        <div class="format-item" data-format="pam" data-category="image">PAM</div>
        <div class="format-item" data-format="pgx" data-category="image">PGX</div>
        <div class="format-item" data-format="xcf" data-category="image">XCF</div>
        <div class="format-item" data-format="xpm" data-category="image">XPM</div>
        <div class="format-item" data-format="xbm" data-category="image">XBM</div>
        <div class="format-item" data-format="xwd" data-category="image">XWD</div>
        <div class="format-item" data-format="cur" data-category="image">CUR</div>
        <div class="format-item" data-format="dcm" data-category="image">DCM</div>
        <div class="format-item" data-format="fax" data-category="image">FAX</div>
        <div class="format-item" data-format="fts" data-category="image">FTS</div>
        <div class="format-item" data-format="g3" data-category="image">G3</div>
        <div class="format-item" data-format="g4" data-category="image">G4</div>
        <div class="format-item" data-format="gv" data-category="image">GV</div>
        <div class="format-item" data-format="hrz" data-category="image">HRZ</div>
        <div class="format-item" data-format="ipl" data-category="image">IPL</div>
        <div class="format-item" data-format="jbg" data-category="image">JBG</div>
        <div class="format-item" data-format="jbig" data-category="image">JBIG</div>
        <div class="format-item" data-format="mac" data-category="image">MAC</div>
        <div class="format-item" data-format="map" data-category="image">MAP</div>
        <div class="format-item" data-format="mng" data-category="image">MNG</div>
        <div class="format-item" data-format="mtv" data-category="image">MTV</div>
        <div class="format-item" data-format="otb" data-category="image">OTB</div>
        <div class="format-item" data-format="pal" data-category="image">PAL</div>
        <div class="format-item" data-format="palm" data-category="image">PALM</div>
        <div class="format-item" data-format="pcd" data-category="image">PCD</div>
        <div class="format-item" data-format="pct" data-category="image">PCT</div>
        <div class="format-item" data-format="pdb" data-category="image">PDB</div>
        <div class="format-item" data-format="pes" data-category="image">PES</div>
        <div class="format-item" data-format="picon" data-category="image">PICON</div>
        <div class="format-item" data-format="pict" data-category="image">PICT</div>
        <div class="format-item" data-format="pix" data-category="image">PIX</div>
        <div class="format-item" data-format="plasma" data-category="image">PLASMA</div>
        <div class="format-item" data-format="pwp" data-category="image">PWP</div>
        <div class="format-item" data-format="ras" data-category="image">RAS</div>
        <div class="format-item" data-format="rgb" data-category="image">RGB</div>
        <div class="format-item" data-format="rgba" data-category="image">RGBA</div>
        <div class="format-item" data-format="rgbo" data-category="image">RGBO</div>
        <div class="format-item" data-format="rgf" data-category="image">RGF</div>
        <div class="format-item" data-format="rla" data-category="image">RLA</div>
        <div class="format-item" data-format="rle" data-category="image">RLE</div>
        <div class="format-item" data-format="sct" data-category="image">SCT</div>
        <div class="format-item" data-format="sfw" data-category="image">SFW</div>
        <div class="format-item" data-format="sgi" data-category="image">SGI</div>
        <div class="format-item" data-format="six" data-category="image">SIX</div>
        <div class="format-item" data-format="sixel" data-category="image">SIXEL</div>
        <div class="format-item" data-format="sun" data-category="image">SUN</div>
        <div class="format-item" data-format="tim" data-category="image">TIM</div>
        <div class="format-item" data-format="tm2" data-category="image">TM2</div>
        <div class="format-item" data-format="uyvy" data-category="image">UYVY</div>
        <div class="format-item" data-format="viff" data-category="image">VIFF</div>
        <div class="format-item" data-format="vips" data-category="image">VIPS</div>
        <div class="format-item" data-format="wbmp" data-category="image">WBMP</div>
        <div class="format-item" data-format="wmz" data-category="image">WMZ</div>
        <div class="format-item" data-format="wpg" data-category="image">WPG</div>
        <div class="format-item" data-format="xc" data-category="image">XC</div>
        <div class="format-item" data-format="xv" data-category="image">XV</div>
        <div class="format-item" data-format="yuv" data-category="image">YUV</div>
        <div class="format-item" data-format="enc" data-category="image">ENC</div>
      </div>
    </div>
    <div class="format-category">
      <h3>📸 RAW (Câmeras)</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="cr2" data-category="image">CR2</div>
        <div class="format-item" data-format="nef" data-category="image">NEF</div>
        <div class="format-item" data-format="arw" data-category="image">ARW</div>
        <div class="format-item" data-format="dng" data-category="image">DNG</div>
        <div class="format-item" data-format="orf" data-category="image">ORF</div>
        <div class="format-item" data-format="raf" data-category="image">RAF</div>
        <div class="format-item" data-format="rw2" data-category="image">RW2</div>
        <div class="format-item" data-format="pef" data-category="image">PEF</div>
        <div class="format-item" data-format="sr2" data-category="image">SR2</div>
        <div class="format-item" data-format="3fr" data-category="image">3FR</div>
        <div class="format-item" data-format="mef" data-category="image">MEF</div>
        <div class="format-item" data-format="mrw" data-category="image">MRW</div>
        <div class="format-item" data-format="dcr" data-category="image">DCR</div>
        <div class="format-item" data-format="kdc" data-category="image">KDC</div>
        <div class="format-item" data-format="k25" data-category="image">K25</div>
        <div class="format-item" data-format="crw" data-category="image">CRW</div>
        <div class="format-item" data-format="erf" data-category="image">ERF</div>
        <div class="format-item" data-format="iiq" data-category="image">IIQ</div>
        <div class="format-item" data-format="nrw" data-category="image">NRW</div>
        <div class="format-item" data-format="srf" data-category="image">SRF</div>
        <div class="format-item" data-format="x3f" data-category="image">X3F</div>
      </div>
    </div>
    <div class="format-category">
      <h3>🎬 Vídeos</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="mp4" data-category="video">MP4</div>
        <div class="format-item" data-format="avi" data-category="video">AVI</div>
        <div class="format-item" data-format="mkv" data-category="video">MKV</div>
        <div class="format-item" data-format="mov" data-category="video">MOV</div>
        <div class="format-item" data-format="webm" data-category="video">WEBM</div>
        <div class="format-item" data-format="flv" data-category="video">FLV</div>
        <div class="format-item" data-format="wmv" data-category="video">WMV</div>
        <div class="format-item" data-format="3gp" data-category="video">3GP</div>
        <div class="format-item" data-format="3g2" data-category="video">3G2</div>
        <div class="format-item" data-format="mpg" data-category="video">MPG</div>
        <div class="format-item" data-format="mpeg" data-category="video">MPEG</div>
        <div class="format-item" data-format="m4v" data-category="video">M4V</div>
        <div class="format-item" data-format="ogv" data-category="video">OGV</div>
        <div class="format-item" data-format="vob" data-category="video">VOB</div>
        <div class="format-item" data-format="m2ts" data-category="video">M2TS</div>
        <div class="format-item" data-format="mts" data-category="video">MTS</div>
        <div class="format-item" data-format="ts" data-category="video">TS</div>
        <div class="format-item" data-format="f4v" data-category="video">F4V</div>
        <div class="format-item" data-format="rm" data-category="video">RM</div>
        <div class="format-item" data-format="rmvb" data-category="video">RMVB</div>
        <div class="format-item" data-format="asf" data-category="video">ASF</div>
        <div class="format-item" data-format="swf" data-category="video">SWF</div>
        <div class="format-item" data-format="divx" data-category="video">DIVX</div>
        <div class="format-item" data-format="xvid" data-category="video">XVID</div>
      </div>
    </div>
    <div class="format-category">
      <h3>🎵 Áudio</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="mp3" data-category="audio">MP3</div>
        <div class="format-item" data-format="wav" data-category="audio">WAV</div>
        <div class="format-item" data-format="flac" data-category="audio">FLAC</div>
        <div class="format-item" data-format="aac" data-category="audio">AAC</div>
        <div class="format-item" data-format="ogg" data-category="audio">OGG</div>
        <div class="format-item" data-format="wma" data-category="audio">WMA</div>
        <div class="format-item" data-format="m4a" data-category="audio">M4A</div>
        <div class="format-item" data-format="opus" data-category="audio">OPUS</div>
        <div class="format-item" data-format="aiff" data-category="audio">AIFF</div>
        <div class="format-item" data-format="ape" data-category="audio">APE</div>
        <div class="format-item" data-format="alac" data-category="audio">ALAC</div>
        <div class="format-item" data-format="ac3" data-category="audio">AC3</div>
        <div class="format-item" data-format="dts" data-category="audio">DTS</div>
        <div class="format-item" data-format="amr" data-category="audio">AMR</div>
        <div class="format-item" data-format="au" data-category="audio">AU</div>
        <div class="format-item" data-format="mid" data-category="audio">MID</div>
        <div class="format-item" data-format="midi" data-category="audio">MIDI</div>
        <div class="format-item" data-format="mka" data-category="audio">MKA</div>
        <div class="format-item" data-format="mp2" data-category="audio">MP2</div>
        <div class="format-item" data-format="mpc" data-category="audio">MPC</div>
        <div class="format-item" data-format="oga" data-category="audio">OGA</div>
        <div class="format-item" data-format="ra" data-category="audio">RA</div>
        <div class="format-item" data-format="spx" data-category="audio">SPX</div>
        <div class="format-item" data-format="tta" data-category="audio">TTA</div>
        <div class="format-item" data-format="voc" data-category="audio">VOC</div>
        <div class="format-item" data-format="wv" data-category="audio">WV</div>
        <div class="format-item" data-format="3ga" data-category="audio">3GA</div>
        <div class="format-item" data-format="caf" data-category="audio">CAF</div>
        <div class="format-item" data-format="gsm" data-category="audio">GSM</div>
        <div class="format-item" data-format="m4b" data-category="audio">M4B</div>
        <div class="format-item" data-format="m4p" data-category="audio">M4P</div>
        <div class="format-item" data-format="raw" data-category="audio">RAW</div>
      </div>
    </div>
    <div class="format-category">
      <h3>📄 Documentos</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="pdf" data-category="document">PDF</div>
        <div class="format-item" data-format="doc" data-category="document">DOC</div>
        <div class="format-item" data-format="docx" data-category="document">DOCX</div>
        <div class="format-item" data-format="txt" data-category="document">TXT</div>
        <div class="format-item" data-format="rtf" data-category="document">RTF</div>
        <div class="format-item" data-format="odt" data-category="document">ODT</div>
        <div class="format-item" data-format="html" data-category="document">HTML</div>
        <div class="format-item" data-format="htm" data-category="document">HTM</div>
        <div class="format-item" data-format="xls" data-category="document">XLS</div>
        <div class="format-item" data-format="xlsx" data-category="document">XLSX</div>
        <div class="format-item" data-format="csv" data-category="document">CSV</div>
        <div class="format-item" data-format="docm" data-category="document">DOCM</div>
        <div class="format-item" data-format="dot" data-category="document">DOT</div>
        <div class="format-item" data-format="dotx" data-category="document">DOTX</div>
        <div class="format-item" data-format="xps" data-category="document">XPS</div>
        <div class="format-item" data-format="oxps" data-category="document">OXPS</div>
        <div class="format-item" data-format="ods" data-category="document">ODS</div>
        <div class="format-item" data-format="ots" data-category="document">OTS</div>
        <div class="format-item" data-format="numbers" data-category="document">NUMBERS</div>
        <div class="format-item" data-format="pages" data-category="document">PAGES</div>
        <div class="format-item" data-format="tex" data-category="document">TEX</div>
        <div class="format-item" data-format="md" data-category="document">MD</div>
        <div class="format-item" data-format="markdown" data-category="document">MARKDOWN</div>
        <div class="format-item" data-format="rst" data-category="document">RST</div>
        <div class="format-item" data-format="abw" data-category="document">ABW</div>
        <div class="format-item" data-format="aw" data-category="document">AW</div>
        <div class="format-item" data-format="dbk" data-category="document">DBK</div>
        <div class="format-item" data-format="djvu" data-category="document">DJVU</div>
        <div class="format-item" data-format="dotm" data-category="document">DOTM</div>
        <div class="format-item" data-format="kwd" data-category="document">KWD</div>
        <div class="format-item" data-format="sxw" data-category="document">SXW</div>
        <div class="format-item" data-format="wps" data-category="document">WPS</div>
      </div>
    </div>
    <div class="format-category">
      <h3>📊 Apresentações</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="ppt" data-category="presentation">PPT</div>
        <div class="format-item" data-format="pptx" data-category="presentation">PPTX</div>
        <div class="format-item" data-format="odp" data-category="presentation">ODP</div>
        <div class="format-item" data-format="pps" data-category="presentation">PPS</div>
        <div class="format-item" data-format="ppsx" data-category="presentation">PPSX</div>
        <div class="format-item" data-format="pptm" data-category="presentation">PPTM</div>
        <div class="format-item" data-format="potx" data-category="presentation">POTX</div>
        <div class="format-item" data-format="pot" data-category="presentation">POT</div>
        <div class="format-item" data-format="potm" data-category="presentation">POTM</div>
        <div class="format-item" data-format="ppsm" data-category="presentation">PPSM</div>
        <div class="format-item" data-format="key" data-category="presentation">KEY</div>
        <div class="format-item" data-format="sxi" data-category="presentation">SXI</div>
        <div class="format-item" data-format="sti" data-category="presentation">STI</div>
      </div>
    </div>
    <div class="format-category">
      <h3>📚 eBooks</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="epub" data-category="ebook">EPUB</div>
        <div class="format-item" data-format="mobi" data-category="ebook">MOBI</div>
        <div class="format-item" data-format="azw3" data-category="ebook">AZW3</div>
        <div class="format-item" data-format="fb2" data-category="ebook">FB2</div>
        <div class="format-item" data-format="azw" data-category="ebook">AZW</div>
        <div class="format-item" data-format="azw4" data-category="ebook">AZW4</div>
        <div class="format-item" data-format="cbr" data-category="ebook">CBR</div>
        <div class="format-item" data-format="cbz" data-category="ebook">CBZ</div>
        <div class="format-item" data-format="cb7" data-category="ebook">CB7</div>
        <div class="format-item" data-format="cbt" data-category="ebook">CBT</div>
        <div class="format-item" data-format="cba" data-category="ebook">CBA</div>
        <div class="format-item" data-format="lit" data-category="ebook">LIT</div>
        <div class="format-item" data-format="prc" data-category="ebook">PRC</div>
        <div class="format-item" data-format="lrf" data-category="ebook">LRF</div>
        <div class="format-item" data-format="rb" data-category="ebook">RB</div>
        <div class="format-item" data-format="snb" data-category="ebook">SNB</div>
        <div class="format-item" data-format="tcr" data-category="ebook">TCR</div>
      </div>
    </div>
    <div class="format-category">
      <h3>🗜️ Arquivos</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="zip" data-category="archive">ZIP</div>
        <div class="format-item" data-format="rar" data-category="archive">RAR</div>
        <div class="format-item" data-format="7z" data-category="archive">7Z</div>
        <div class="format-item" data-format="tar" data-category="archive">TAR</div>
        <div class="format-item" data-format="gz" data-category="archive">GZ</div>
        <div class="format-item" data-format="bz2" data-category="archive">BZ2</div>
        <div class="format-item" data-format="xz" data-category="archive">XZ</div>
        <div class="format-item" data-format="iso" data-category="archive">ISO</div>
        <div class="format-item" data-format="dmg" data-category="archive">DMG</div>
        <div class="format-item" data-format="apk" data-category="archive">APK</div>
        <div class="format-item" data-format="ipa" data-category="archive">IPA</div>
        <div class="format-item" data-format="ace" data-category="archive">ACE</div>
        <div class="format-item" data-format="alz" data-category="archive">ALZ</div>
        <div class="format-item" data-format="arc" data-category="archive">ARC</div>
        <div class="format-item" data-format="arj" data-category="archive">ARJ</div>
        <div class="format-item" data-format="cab" data-category="archive">CAB</div>
        <div class="format-item" data-format="cpio" data-category="archive">CPIO</div>
        <div class="format-item" data-format="deb" data-category="archive">DEB</div>
        <div class="format-item" data-format="jar" data-category="archive">JAR</div>
        <div class="format-item" data-format="lha" data-category="archive">LHA</div>
        <div class="format-item" data-format="rpm" data-category="archive">RPM</div>
        <div class="format-item" data-format="tbz2" data-category="archive">TBZ2</div>
        <div class="format-item" data-format="tgz" data-category="archive">TGZ</div>
      </div>
    </div>
    <div class="format-category">
      <h3>🔤 Fontes</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="ttf" data-category="font">TTF</div>
        <div class="format-item" data-format="otf" data-category="font">OTF</div>
        <div class="format-item" data-format="woff" data-category="font">WOFF</div>
        <div class="format-item" data-format="woff2" data-category="font">WOFF2</div>
        <div class="format-item" data-format="eot" data-category="font">EOT</div>
        <div class="format-item" data-format="pfa" data-category="font">PFA</div>
        <div class="format-item" data-format="pfb" data-category="font">PFB</div>
        <div class="format-item" data-format="fon" data-category="font">FON</div>
        <div class="format-item" data-format="fnt" data-category="font">FNT</div>
        <div class="format-item" data-format="bdf" data-category="font">BDF</div>
        <div class="format-item" data-format="pcf" data-category="font">PCF</div>
        <div class="format-item" data-format="snf" data-category="font">SNF</div>
        <div class="format-item" data-format="afm" data-category="font">AFM</div>
        <div class="format-item" data-format="cff" data-category="font">CFF</div>
        <div class="format-item" data-format="cid" data-category="font">CID</div>
        <div class="format-item" data-format="dfont" data-category="font">DFONT</div>
        <div class="format-item" data-format="sfd" data-category="font">SFD</div>
        <div class="format-item" data-format="ufo" data-category="font">UFO</div>
      </div>
    </div>
    <div class="format-category">
      <h3>📏 CAD</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="dwg" data-category="cad">DWG</div>
        <div class="format-item" data-format="dxf" data-category="cad">DXF</div>
        <div class="format-item" data-format="dwf" data-category="cad">DWF</div>
        <div class="format-item" data-format="dgn" data-category="cad">DGN</div>
        <div class="format-item" data-format="step" data-category="cad">STEP</div>
        <div class="format-item" data-format="stp" data-category="cad">STP</div>
        <div class="format-item" data-format="iges" data-category="cad">IGES</div>
        <div class="format-item" data-format="igs" data-category="cad">IGS</div>
        <div class="format-item" data-format="ifc" data-category="cad">IFC</div>
        <div class="format-item" data-format="sat" data-category="cad">SAT</div>
        <div class="format-item" data-format="sab" data-category="cad">SAB</div>
        <div class="format-item" data-format="rvt" data-category="cad">RVT</div>
        <div class="format-item" data-format="rfa" data-category="cad">RFA</div>
        <div class="format-item" data-format="skp" data-category="cad">SKP</div>
      </div>
    </div>
    <div class="format-category">
      <h3>🎮 Modelos 3D</h3>
      <div class="formats-grid">
        <div class="format-item" data-format="obj" data-category="3d">OBJ</div>
        <div class="format-item" data-format="fbx" data-category="3d">FBX</div>
        <div class="format-item" data-format="stl" data-category="3d">STL</div>
        <div class="format-item" data-format="3ds" data-category="3d">3DS</div>
        <div class="format-item" data-format="dae" data-category="3d">DAE</div>
        <div class="format-item" data-format="blend" data-category="3d">BLEND</div>
        <div class="format-item" data-format="gltf" data-category="3d">GLTF</div>
        <div class="format-item" data-format="glb" data-category="3d">GLB</div>
        <div class="format-item" data-format="ply" data-category="3d">PLY</div>
        <div class="format-item" data-format="usd" data-category="3d">USD</div>
        <div class="format-item" data-format="usda" data-category="3d">USDA</div>
        <div class="format-item" data-format="usdc" data-category="3d">USDC</div>
        <div class="format-item" data-format="usdz" data-category="3d">USDZ</div>
        <div class="format-item" data-format="x3d" data-category="3d">X3D</div>
        <div class="format-item" data-format="vrml" data-category="3d">VRML</div>
        <div class="format-item" data-format="wrl" data-category="3d">WRL</div>
        <div class="format-item" data-format="ma" data-category="3d">MA</div>
        <div class="format-item" data-format="mb" data-category="3d">MB</div>
        <div class="format-item" data-format="max" data-category="3d">MAX</div>
        <div class="format-item" data-format="c4d" data-category="3d">C4D</div>
      </div>
    </div>
  </div>
  
  <script>
    const formatBtns = document.querySelectorAll('.format-btn');
    const formatItems = document.querySelectorAll('.format-item');
    const formatInput = document.getElementById('format');
    const fileInput = document.getElementById('file');
    const sizeInfo = document.getElementById('file-size-info');
    const sizeText = document.getElementById('size-text');
    const clearFileBtn = document.getElementById('clear-file');
    const filePreview = document.getElementById('file-preview');
    const previewImage = document.getElementById('preview-image');
    let currentFormat = 'png';
    let formatSizes = {};
    let availableFormats = [];
    let fileType = 'image';
    
    function clearFile() {
      fileInput.value = '';
      sizeInfo.classList.remove('show');
      clearFileBtn.classList.remove('show');
      filePreview.classList.remove('show');
      formatItems.forEach(item => {
        item.classList.remove('available');
        item.classList.remove('active');
      });
      formatBtns.forEach(btn => {
        btn.classList.remove('unavailable');
        if (btn.dataset.format !== currentFormat) {
          btn.classList.remove('active');
        }
      });
      formatSizes = {};
      availableFormats = [];
    }
    
    formatBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.classList.contains('unavailable')) return;
        formatBtns.forEach(b => b.classList.remove('active'));
        formatItems.forEach(i => i.classList.remove('active'));
        btn.classList.add('active');
        currentFormat = btn.dataset.format;
        formatInput.value = currentFormat;
        updateSizeDisplay();
      });
    });
    
    formatItems.forEach(item => {
      item.addEventListener('click', () => {
        if (!item.classList.contains('available')) return;
        formatBtns.forEach(b => b.classList.remove('active'));
        formatItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        currentFormat = item.dataset.format;
        formatInput.value = currentFormat;
        updateSizeDisplay();
      });
    });
    
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) {
        clearFile();
        return;
      }
      
      // Mostrar preview
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          previewImage.src = e.target.result;
          filePreview.classList.add('show');
        };
        reader.readAsDataURL(file);
      }
      
      clearFileBtn.classList.add('show');
      sizeInfo.classList.add('show');
      sizeText.textContent = 'Tamanho estimado: Calculando...';
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const response = await fetch('/estimate_size', {
          method: 'POST',
          body: formData
        });
        
        const result = await response.json();
        
        if (result.success && result.sizes) {
          formatSizes = result.sizes;
          availableFormats = Object.keys(result.sizes);
          fileType = result.type || 'image';
          
          // Mostrar apenas formatos da mesma categoria nos itens
          formatItems.forEach(item => {
            const itemCategory = item.dataset.category;
            if (itemCategory === fileType && availableFormats.includes(item.dataset.format)) {
              item.classList.add('available');
            } else {
              item.classList.remove('available');
            }
          });
          
          // Mostrar apenas formatos disponíveis nos botões do topo
          formatBtns.forEach(btn => {
            if (availableFormats.includes(btn.dataset.format)) {
              btn.classList.remove('unavailable');
            } else {
              btn.classList.add('unavailable');
              if (btn.classList.contains('active')) {
                btn.classList.remove('active');
              }
            }
          });
          
          // Auto-selecionar formato similar se o atual não estiver disponível
          if (!availableFormats.includes(currentFormat)) {
            const similarFormat = findSimilarFormat(fileType);
            if (similarFormat && availableFormats.includes(similarFormat)) {
              currentFormat = similarFormat;
              formatInput.value = similarFormat;
              formatBtns.forEach(btn => {
                btn.classList.remove('active');
                if (btn.dataset.format === similarFormat) {
                  btn.classList.add('active');
                }
              });
              formatItems.forEach(item => {
                item.classList.remove('active');
                if (item.dataset.format === similarFormat) {
                  item.classList.add('active');
                }
              });
            }
          } else {
            // Manter o formato atual ativo visualmente
            formatBtns.forEach(btn => {
              if (btn.dataset.format === currentFormat) {
                btn.classList.add('active');
              }
            });
            formatItems.forEach(item => {
              if (item.dataset.format === currentFormat) {
                item.classList.add('active');
              }
            });
          }
          
          updateSizeDisplay();
        } else {
          formatSizes = {};
          availableFormats = [];
          formatItems.forEach(item => item.classList.remove('available', 'active'));
          formatBtns.forEach(btn => {
            btn.classList.add('unavailable');
            btn.classList.remove('active');
          });
          sizeText.textContent = result.message || 'Não foi possível calcular o tamanho';
        }
      } catch (error) {
        sizeText.textContent = 'Erro ao calcular tamanho';
      }
    });
    
    function findSimilarFormat(type) {
      const defaults = {
        'image': 'png',
        'video': 'mp4',
        'audio': 'mp3',
        'document': 'pdf',
        'presentation': 'pptx',
        'ebook': 'epub',
        'archive': 'zip',
        'font': 'ttf',
        'cad': 'dwg',
        '3d': 'obj'
      };
      return defaults[type] || 'png';
    }
    
    function updateSizeDisplay() {
      if (formatSizes[currentFormat]) {
        const size = formatBytes(formatSizes[currentFormat]);
        sizeText.textContent = `Tamanho estimado em ${currentFormat.toUpperCase()}: ${size}`;
      }
    }
    
    function formatBytes(bytes) {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
  </script>
</body>
</html>
"""

TEMPO_HTML = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tempo - Relógio e Calendário</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: 
        radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.08) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(96, 165, 250, 0.06) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(147, 197, 253, 0.05) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 15px;
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
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(59, 130, 246, 0.4);
      color: #3b82f6;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 64px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #93c5fd 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 6px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(59, 130, 246, 0.7));
      animation: glow-pulse-blue 3s ease-in-out infinite;
      margin-bottom: 10px;
      position: relative;
      z-index: 1;
    }
    @keyframes glow-pulse-blue {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(59, 130, 246, 0.7)); }
      50% { filter: drop-shadow(0 0 35px rgba(59, 130, 246, 0.9)); }
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 40px;
      font-weight: 500;
      letter-spacing: 0.5px;
      position: relative;
      z-index: 1;
    }
    .container {
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
      justify-content: center;
      max-width: 1200px;
      position: relative;
      z-index: 1;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 32px;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      width: 344px;
    }
    .card.calendar {
      width: 400px;
      display: flex;
      flex-direction: column;
    }
    .card.holidays {
      width: 420px;
      max-height: 520px;
      overflow-y: auto;
      display: none;
    }
    .card.holidays.show {
      display: block;
    }
    .digital-clock {
      font-size: 64px;
      font-weight: 700;
      color: #3b82f6;
      text-align: center;
      margin-bottom: 16px;
      text-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
    }
    .date-display {
      font-size: 18px;
      color: #94a3b8;
      text-align: center;
      margin-bottom: 8px;
    }
    .analog-clock {
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: rgba(15, 23, 42, 0.6);
      border: 4px solid rgba(59, 130, 246, 0.3);
      position: relative;
      box-shadow: 0 0 40px rgba(59, 130, 246, 0.2), inset 0 0 40px rgba(0, 0, 0, 0.3);
      margin: 0 auto;
    }
    .clock-number {
      position: absolute;
      font-size: 18px;
      font-weight: 700;
      color: #3b82f6;
      text-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
    }
    .clock-mark {
      position: absolute;
      background: rgba(59, 130, 246, 0.4);
      transform-origin: bottom center;
      left: 50%;
      bottom: 50%;
    }
    .clock-mark.hour {
      width: 3px;
      height: 12px;
      margin-left: -1.5px;
      background: rgba(59, 130, 246, 0.6);
    }
    .clock-mark.minute {
      width: 1px;
      height: 8px;
      margin-left: -0.5px;
    }
    .analog-clock::before {
      content: '';
      position: absolute;
      width: 12px;
      height: 12px;
      background: #3b82f6;
      border-radius: 50%;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      z-index: 10;
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.8);
    }
    .hand {
      position: absolute;
      bottom: 50%;
      left: 50%;
      transform-origin: bottom center;
      border-radius: 10px;
    }
    .hour-hand {
      width: 6px;
      height: 70px;
      background: linear-gradient(to top, #3b82f6, #60a5fa);
      margin-left: -3px;
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
    }
    .minute-hand {
      width: 4px;
      height: 100px;
      background: linear-gradient(to top, #60a5fa, #93c5fd);
      margin-left: -2px;
      box-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
    }
    .second-hand {
      width: 2px;
      height: 110px;
      background: #ef4444;
      margin-left: -1px;
      box-shadow: 0 0 6px rgba(239, 68, 68, 0.5);
    }
    .calendar {
      width: 100%;
      max-width: 400px;
    }
    .calendar-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }
    .calendar-header h2 {
      font-size: 20px;
      color: #3b82f6;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.3s;
    }
    .calendar-header h2:hover {
      color: #60a5fa;
      transform: scale(1.05);
    }
    .nav-btn {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      background: rgba(59, 130, 246, 0.1);
      border: 1px solid rgba(59, 130, 246, 0.3);
      color: #3b82f6;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: 700;
      transition: all 0.3s;
    }
    .nav-btn:hover {
      background: rgba(59, 130, 246, 0.2);
      border-color: #3b82f6;
      transform: scale(1.1);
    }
    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
      flex: 1;
      align-content: start;
    }
    .calendar-grid.months {
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      align-content: center;
    }
    .calendar-grid.years {
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      align-content: center;
    }
    .calendar-day {
      aspect-ratio: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
      background: rgba(15, 23, 42, 0.4);
      border: 1px solid rgba(148, 163, 184, 0.1);
      transition: all 0.3s;
    }
    .calendar-grid.months .calendar-day,
    .calendar-grid.years .calendar-day {
      aspect-ratio: auto;
      height: 70px;
      font-size: 14px;
    }
    .calendar-day.header {
      background: transparent;
      border: none;
      color: #3b82f6;
      font-weight: 700;
    }
    .calendar-day.today {
      background: linear-gradient(135deg, #3b82f6, #60a5fa);
      color: white;
      box-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
      border-color: #3b82f6;
    }
    .calendar-day.other-month {
      opacity: 0.3;
    }
    .calendar-day.weekend {
      color: #ef4444;
    }
    /* Cada categoria de data tem sua própria cor - feriado de verdade, ponto
       facultativo, dia sem aula e data comemorativa não são a mesma coisa e
       não deveriam parecer a mesma coisa no calendário. */
    .calendar-day.holiday-nacional {
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1));
      border-color: rgba(239, 68, 68, 0.4);
      color: #ef4444;
      font-weight: 700;
    }
    .calendar-day.holiday-estadual {
      background: linear-gradient(135deg, rgba(249, 115, 22, 0.2), rgba(234, 88, 12, 0.1));
      border-color: rgba(249, 115, 22, 0.4);
      color: #f97316;
      font-weight: 700;
    }
    .calendar-day.holiday-ubatuba {
      background: linear-gradient(135deg, rgba(234, 179, 8, 0.2), rgba(202, 138, 4, 0.1));
      border-color: rgba(234, 179, 8, 0.4);
      color: #eab308;
      font-weight: 700;
    }
    .calendar-day.holiday-saosebastiao {
      background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(147, 51, 234, 0.1));
      border-color: rgba(168, 85, 247, 0.4);
      color: #a855f7;
      font-weight: 700;
    }
    .calendar-day.holiday-caraguatatuba {
      background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(8, 145, 178, 0.1));
      border-color: rgba(6, 182, 212, 0.4);
      color: #06b6d4;
      font-weight: 700;
    }
    .calendar-day.holiday-ilhabela {
      background: linear-gradient(135deg, rgba(236, 72, 153, 0.2), rgba(219, 39, 119, 0.1));
      border-color: rgba(236, 72, 153, 0.4);
      color: #ec4899;
      font-weight: 700;
    }
    .calendar-day.holiday-facultativo {
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(37, 99, 235, 0.1));
      border-color: rgba(59, 130, 246, 0.4);
      color: #60a5fa;
      font-weight: 700;
    }
    .calendar-day.holiday-fatec {
      background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(22, 163, 74, 0.1));
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      font-weight: 700;
    }
    .calendar-day.holiday-comemorativa {
      border-color: rgba(148, 163, 184, 0.5);
      border-style: dashed;
    }
    .day-dots {
      position: absolute;
      bottom: 3px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 2px;
    }
    .day-dots .dot {
      width: 4px;
      height: 4px;
      border-radius: 50%;
    }
    .calendar-day {
      position: relative;
    }
    .calendar-day.selectable {
      cursor: pointer;
    }
    .calendar-day.selectable:hover {
      background: rgba(59, 130, 246, 0.2);
      border-color: #3b82f6;
      transform: scale(1.05);
    }
    .holiday-toggle {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
      cursor: pointer;
      user-select: none;
    }
    .holiday-toggle input[type="checkbox"] {
      display: none;
    }
    .calendar-checkbox {
      width: 40px;
      height: 40px;
      background: rgba(15, 23, 42, 0.6);
      border: 2px solid rgba(148, 163, 184, 0.2);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      position: relative;
    }
    .calendar-checkbox::before {
      content: '';
      position: absolute;
      top: 6px;
      left: 0;
      right: 0;
      height: 8px;
      background: rgba(148, 163, 184, 0.2);
      border-radius: 4px 4px 0 0;
    }
    .calendar-checkbox-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 2px;
      margin-top: 4px;
    }
    .calendar-checkbox-cell {
      width: 6px;
      height: 6px;
      background: rgba(148, 163, 184, 0.2);
      border-radius: 1px;
      transition: all 0.3s;
    }
    input[type="checkbox"]:checked + .calendar-checkbox {
      background: rgba(59, 130, 246, 0.2);
      border-color: #3b82f6;
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);
    }
    input[type="checkbox"]:checked + .calendar-checkbox::before {
      background: #3b82f6;
    }
    input[type="checkbox"]:checked + .calendar-checkbox .calendar-checkbox-cell {
      background: #60a5fa;
    }
    .holiday-toggle:hover .calendar-checkbox {
      border-color: #60a5fa;
    }
    .holiday-toggle label.text-label {
      font-size: 14px;
      color: #94a3b8;
      cursor: default;
      margin: 0;
      font-weight: 500;
      pointer-events: none;
    }
    .holidays h3 {
      font-size: 18px;
      color: #f8fafc;
      margin-bottom: 4px;
      font-weight: 700;
    }
    .holidays .subtitle {
      font-size: 12px;
      color: #64748b;
      margin-bottom: 16px;
      line-height: 1.5;
    }
    /* Legenda das categorias - cada cor definida uma única vez e reaproveitada
       via variável CSS tanto na legenda quanto nos itens da lista. */
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 18px;
      padding-bottom: 16px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }
    .legend-chip {
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 4px 9px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.08);
      font-size: 10.5px;
      font-weight: 600;
      color: #cbd5e1;
      white-space: nowrap;
    }
    .legend-chip .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--cat-color);
      box-shadow: 0 0 6px var(--cat-color);
      flex-shrink: 0;
    }
    .holiday-item {
      padding: 12px 14px;
      margin-bottom: 8px;
      background: rgba(15, 23, 42, 0.6);
      border-radius: 12px;
      border-left: 4px solid var(--cat-color);
    }
    .holiday-item:last-child {
      margin-bottom: 0;
    }
    .holiday-date {
      font-size: 13px;
      font-weight: 700;
      color: var(--cat-color);
      margin-bottom: 4px;
    }
    .holiday-name {
      font-size: 14px;
      color: #f1f5f9;
      font-weight: 600;
      margin-bottom: 3px;
    }
    .holiday-type {
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--cat-color);
      background: color-mix(in srgb, var(--cat-color) 16%, transparent);
      padding: 2px 8px;
      border-radius: 999px;
      margin-bottom: 6px;
    }
    .holiday-desc {
      font-size: 12.5px;
      color: #94a3b8;
      line-height: 1.5;
    }
    @media (max-width: 768px) {
      .digital-clock { font-size: 48px; }
      .analog-clock { width: 220px; height: 220px; }
      .hour-hand { height: 55px; }
      .minute-hand { height: 80px; }
      .second-hand { height: 90px; }
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">TEMPO</div>
  <div class="tagline">Relógio e Calendário</div>
  
  <div class="container">
    <div class="card">
      <div class="digital-clock" id="digital-clock">00:00:00</div>
      <div class="date-display" id="date-display">Carregando...</div>
      <div class="analog-clock" id="analog-clock">
        <div class="hand hour-hand" id="hour-hand"></div>
        <div class="hand minute-hand" id="minute-hand"></div>
        <div class="hand second-hand" id="second-hand"></div>
      </div>
    </div>
    
    <div class="card calendar">
      <div class="calendar-header">
        <div class="nav-btn" onclick="navigate(-1)">‹</div>
        <h2 id="calendar-month" onclick="toggleView()">Janeiro 2024</h2>
        <div class="nav-btn" onclick="navigate(1)">›</div>
      </div>
      <div class="calendar-grid" id="calendar-grid"></div>
      <div class="holiday-toggle">
        <input type="checkbox" id="holiday-checkbox" onchange="toggleHolidaysCard()">
        <label for="holiday-checkbox" class="calendar-checkbox">
          <div class="calendar-checkbox-grid">
            <div class="calendar-checkbox-cell"></div>
            <div class="calendar-checkbox-cell"></div>
            <div class="calendar-checkbox-cell"></div>
            <div class="calendar-checkbox-cell"></div>
            <div class="calendar-checkbox-cell"></div>
            <div class="calendar-checkbox-cell"></div>
          </div>
        </label>
        <span class="text-label">Mostrar feriados</span>
      </div>
    </div>
    
    <div class="card holidays" id="holidays-card">
      <h3>🎉 Feriados e Datas Comemorativas</h3>
      <p class="subtitle">Feriados nacionais, estaduais, das cidades do Litoral Norte e pontos facultativos são calculados automaticamente para qualquer ano. Dias sem aula da Fatec são cadastrados manualmente ano a ano, conforme o calendário acadêmico oficial.</p>
      <div class="legend">
        <div class="legend-chip" style="--cat-color:#ef4444"><span class="dot"></span>Feriado Nacional</div>
        <div class="legend-chip" style="--cat-color:#f97316"><span class="dot"></span>Feriado Estadual (SP)</div>
        <div class="legend-chip" style="--cat-color:#a855f7"><span class="dot"></span>São Sebastião</div>
        <div class="legend-chip" style="--cat-color:#eab308"><span class="dot"></span>Ubatuba</div>
        <div class="legend-chip" style="--cat-color:#06b6d4"><span class="dot"></span>Caraguatatuba</div>
        <div class="legend-chip" style="--cat-color:#ec4899"><span class="dot"></span>Ilhabela</div>
        <div class="legend-chip" style="--cat-color:#3b82f6"><span class="dot"></span>Ponto Facultativo</div>
        <div class="legend-chip" style="--cat-color:#22c55e"><span class="dot"></span>Sem Aula (Fatec/Escolas)</div>
        <div class="legend-chip" style="--cat-color:#94a3b8"><span class="dot"></span>Data Comemorativa (tem aula/expediente normal)</div>
      </div>
      <div id="holidays-list"></div>
    </div>
  </div>
  
  <script>
    let currentMonth = new Date().getMonth();
    let currentYear = new Date().getFullYear();
    let viewMode = 'days';
    
    // Cada categoria tem um rótulo (mostrado como badge na lista/legenda) e uma
    // cor. CATEGORY_PRIORITY define qual cor "vence" no quadradinho do dia
    // quando mais de uma categoria cai na mesma data (ex: feriado municipal e
    // ponto facultativo da Fatec no mesmo dia).
    const CATEGORIES = {
      nacional:      { label: 'Feriado Nacional',         color: '#ef4444' },
      estadual:      { label: 'Feriado Estadual (SP)',    color: '#f97316' },
      saosebastiao:  { label: 'São Sebastião',            color: '#a855f7' },
      ubatuba:       { label: 'Ubatuba',                  color: '#eab308' },
      caraguatatuba: { label: 'Caraguatatuba',            color: '#06b6d4' },
      ilhabela:      { label: 'Ilhabela',                 color: '#ec4899' },
      fatec:         { label: 'Sem Aula (Fatec/Escolas)', color: '#22c55e' },
      facultativo:   { label: 'Ponto Facultativo',        color: '#3b82f6' },
      comemorativa:  { label: 'Data Comemorativa',        color: '#94a3b8' }
    };
    const CATEGORY_PRIORITY = ['nacional', 'estadual', 'saosebastiao', 'ubatuba', 'caraguatatuba', 'ilhabela', 'fatec', 'facultativo', 'comemorativa'];

    const holidays = {
      // Dia/mês fixo, repete em qualquer ano.
      fixed: [
        {day: 1, month: 1, name: 'Confraternização Universal', type: 'nacional', desc: 'Feriado nacional de Ano Novo.'},
        {day: 20, month: 1, name: 'São Sebastião (Padroeiro)', type: 'saosebastiao', desc: 'Feriado municipal de São Sebastião-SP em homenagem ao padroeiro da cidade.'},
        {day: 2, month: 2, name: "N. Sra. D'Ajuda e Bonsucesso (Padroeira)", type: 'ilhabela', desc: 'Feriado municipal de Ilhabela-SP em homenagem à padroeira da cidade.'},
        {day: 3, month: 2, name: 'Aniversário de Ubatuba', type: 'ubatuba', desc: 'Feriado municipal pela fundação de Ubatuba-SP.'},
        {day: 14, month: 2, name: "Valentine's Day", type: 'comemorativa', desc: 'Data comemorativa internacional - não é o Dia dos Namorados brasileiro (esse é 12/06).'},
        {day: 8, month: 3, name: 'Dia Internacional da Mulher', type: 'comemorativa', desc: 'Data comemorativa, sem alteração de expediente.'},
        {day: 20, month: 4, name: 'Aniversário de Caraguatatuba', type: 'caraguatatuba', desc: 'Feriado municipal pela emancipação político-administrativa de Caraguatatuba-SP em 20/04/1857 (Lei Municipal nº 871/1972).'},
        {day: 21, month: 4, name: 'Tiradentes', type: 'nacional', desc: 'Feriado nacional em homenagem a Joaquim José da Silva Xavier.'},
        {day: 1, month: 5, name: 'Dia do Trabalho', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 12, month: 6, name: 'Dia dos Namorados', type: 'comemorativa', desc: 'Data comemorativa brasileira, véspera do Dia de Santo Antônio.'},
        {day: 24, month: 6, name: 'São João', type: 'comemorativa', desc: 'Data comemorativa das festas juninas.'},
        {day: 9, month: 7, name: 'Revolução Constitucionalista', type: 'estadual', desc: 'Feriado estadual em São Paulo, em memória à Revolução de 1932.'},
        {day: 7, month: 9, name: 'Independência do Brasil', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 12, month: 10, name: 'Nossa Senhora Aparecida', type: 'nacional', desc: 'Feriado nacional, padroeira do Brasil.'},
        {day: 15, month: 10, name: 'Dia do Professor', type: 'fatec', desc: 'Dia não letivo em escolas e faculdades (Decreto Federal nº 52.682/1963).'},
        {day: 28, month: 10, name: 'Dia do Servidor Público', type: 'facultativo', desc: 'Ponto facultativo tradicional no funcionalismo público, incluindo Fatec/Centro Paula Souza.'},
        {day: 31, month: 10, name: 'Halloween', type: 'comemorativa', desc: 'Data comemorativa, sem alteração de expediente no Brasil.'},
        {day: 2, month: 11, name: 'Finados', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 15, month: 11, name: 'Proclamação da República', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 20, month: 11, name: 'Consciência Negra', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 24, month: 12, name: 'Véspera de Natal', type: 'facultativo', desc: 'Ponto facultativo tradicional no funcionalismo público a partir do meio-dia.'},
        {day: 25, month: 12, name: 'Natal', type: 'nacional', desc: 'Feriado nacional.'},
        {day: 31, month: 12, name: 'Véspera de Ano Novo', type: 'facultativo', desc: 'Ponto facultativo tradicional no funcionalismo público.'}
      ],

      // Datas confirmadas só para anos específicos (decretos anuais, calendário
      // acadêmico da Fatec, eleições...) - não dá pra calcular por fórmula
      // porque dependem de decisão do governo/Fatec a cada ano. Só entram aqui
      // anos com fonte oficial conferida; anos fora desta lista simplesmente não
      // mostram esses extras (em vez de arriscar uma data inventada).
      byYear: {
        2026: [
          {startDay: 14, startMonth: 2, endDay: 18, endMonth: 2, name: 'Recesso de Carnaval e Quarta de Cinzas', type: 'fatec', desc: 'Não haverá aula na Fatec (Calendário Acadêmico 2026 - CGESG/Centro Paula Souza): feriado e emenda de Carnaval e Quarta-feira de Cinzas.'},
          {startDay: 3, startMonth: 4, endDay: 4, endMonth: 4, name: 'Emenda da Paixão de Cristo', type: 'fatec', desc: 'Não haverá aula na Fatec em 2026 (Calendário Acadêmico CGESG): feriado e emenda da Sexta-feira Santa.'},
          {day: 20, month: 4, name: 'Emenda de Tiradentes (Fatec)', type: 'fatec', desc: 'Não haverá aula na Fatec em 2026 (Calendário Acadêmico CGESG): véspera de Tiradentes.'},
          {day: 10, month: 7, name: 'Emenda da Revolução Constitucionalista', type: 'facultativo', desc: 'Ponto facultativo no funcionalismo estadual em 2026 (Decreto Estadual nº 70.273/2025).'},
          {startDay: 10, startMonth: 7, endDay: 25, endMonth: 7, name: 'Recesso Escolar da Fatec', type: 'fatec', desc: 'Recesso entre os semestres letivos de 2026 (Calendário Acadêmico CGESG/Centro Paula Souza).'},
          {startDay: 2, startMonth: 10, endDay: 4, endMonth: 10, name: 'Preparo e 1º turno das Eleições', type: 'fatec', desc: 'Fatec sem aula em 2026 para preparo do local de votação e 1º turno das Eleições Nacionais.'},
          {startDay: 23, startMonth: 10, endDay: 25, endMonth: 10, name: 'Preparo e 2º turno das Eleições', type: 'fatec', desc: 'Fatec sem aula em 2026 para preparo do local de votação e 2º turno das Eleições Nacionais.'},
          {startDay: 20, startMonth: 11, endDay: 21, endMonth: 11, name: 'Emenda da Consciência Negra', type: 'fatec', desc: 'Não haverá aula na Fatec em 2026 (Calendário Acadêmico CGESG): feriado e emenda da Consciência Negra.'}
        ]
      },

      movable: function(year) {
        const easter = this.getEaster(year);
        const d = offset => new Date(easter.getTime() + offset * 86400000);
        const mothersDay = this.getSecondSunday(year, 4); // Maio
        const fathersDay = this.getSecondSunday(year, 7); // Agosto
        return [
          {date: d(-48), name: 'Carnaval (Segunda-feira)', type: 'facultativo', desc: 'Ponto facultativo tradicional, dois dias antes da Quarta-feira de Cinzas.'},
          {date: d(-47), name: 'Carnaval (Terça-feira)', type: 'facultativo', desc: 'Ponto facultativo tradicional, véspera da Quarta-feira de Cinzas.'},
          {date: d(-46), name: 'Quarta-feira de Cinzas', type: 'facultativo', desc: 'Ponto facultativo tradicional até o meio-dia, início da Quaresma.'},
          {date: d(-2), name: 'Sexta-feira Santa', type: 'nacional', desc: 'Feriado nacional cristão, dois dias antes da Páscoa.'},
          {date: d(0), name: 'Páscoa', type: 'comemorativa', desc: 'Data comemorativa cristã, sem alteração de expediente.'},
          {date: d(60), name: 'Corpus Christi', type: 'facultativo', desc: 'Ponto facultativo tradicional, 60 dias após a Páscoa.'},
          {date: mothersDay, name: 'Dia das Mães', type: 'comemorativa', desc: 'Data comemorativa, segundo domingo de maio.'},
          {date: fathersDay, name: 'Dia dos Pais', type: 'comemorativa', desc: 'Data comemorativa, segundo domingo de agosto.'}
        ];
      },
      getEaster: function(year) {
        const f = Math.floor, G = year % 19, C = f(year / 100),
              H = (C - f(C / 4) - f((8 * C + 13) / 25) + 19 * G + 15) % 30,
              I = H - f(H / 28) * (1 - f(29 / (H + 1)) * f((21 - G) / 11)),
              J = (year + f(year / 4) + I + 2 - C + f(C / 4)) % 7,
              L = I - J, month = 3 + f((L + 40) / 44),
              day = L + 28 - 31 * f(month / 4);
        return new Date(year, month - 1, day);
      },
      getSecondSunday: function(year, month) {
        const firstDay = new Date(year, month, 1);
        const firstSunday = 1 + (7 - firstDay.getDay()) % 7;
        return new Date(year, month, firstSunday + 7);
      },

      // Lista "humana" do ano inteiro: um item por evento (intervalos de vários
      // dias, como o recesso da Fatec, aparecem como um item só com data de
      // início e fim, não um item repetido por dia).
      getAllForYear: function(year) {
        const result = [];
        this.fixed.forEach(h => {
          result.push({date: new Date(year, h.month - 1, h.day), endDate: null, name: h.name, type: h.type, desc: h.desc});
        });
        this.movable(year).forEach(h => {
          result.push({date: h.date, endDate: null, name: h.name, type: h.type, desc: h.desc});
        });
        (this.byYear[year] || []).forEach(h => {
          if (h.startDay !== undefined) {
            result.push({
              date: new Date(year, h.startMonth - 1, h.startDay),
              endDate: new Date(year, h.endMonth - 1, h.endDay),
              name: h.name, type: h.type, desc: h.desc
            });
          } else {
            result.push({date: new Date(year, h.month - 1, h.day), endDate: null, name: h.name, type: h.type, desc: h.desc});
          }
        });
        result.sort((a, b) => a.date - b.date);
        return result;
      },
      getForYear: function(year) {
        return this.getAllForYear(year);
      },
      getForMonth: function(month, year) {
        return this.getAllForYear(year).filter(h => {
          if (h.endDate) return h.date.getMonth() <= month && h.endDate.getMonth() >= month;
          return h.date.getMonth() === month;
        });
      },
      // Pode haver mais de um evento no mesmo dia (ex: feriado municipal e
      // ponto facultativo da Fatec juntos) - por isso sempre retorna uma lista.
      getForDay: function(day, month, year) {
        const target = new Date(year, month, day);
        return this.getAllForYear(year).filter(h => {
          if (h.endDate) return target >= h.date && target <= h.endDate;
          return h.date.getFullYear() === target.getFullYear() && h.date.getMonth() === target.getMonth() && h.date.getDate() === target.getDate();
        });
      },
      getPrimaryType: function(day, month, year) {
        const items = this.getForDay(day, month, year);
        if (items.length === 0) return null;
        let best = items[0].type, bestRank = CATEGORY_PRIORITY.indexOf(best);
        items.forEach(h => {
          const rank = CATEGORY_PRIORITY.indexOf(h.type);
          if (rank < bestRank) { bestRank = rank; best = h.type; }
        });
        return best;
      }
    };

    function formatDateLabel(h) {
      const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
      if (h.endDate) {
        if (h.date.getMonth() === h.endDate.getMonth()) {
          return `${h.date.getDate()} a ${h.endDate.getDate()} de ${months[h.date.getMonth()]}`;
        }
        return `${h.date.getDate()} de ${months[h.date.getMonth()]} a ${h.endDate.getDate()} de ${months[h.endDate.getMonth()]}`;
      }
      return `${h.date.getDate()} de ${months[h.date.getMonth()]}`;
    }

    function renderHolidayItem(h) {
      const item = document.createElement('div');
      item.className = 'holiday-item';
      const cat = CATEGORIES[h.type];
      item.style.setProperty('--cat-color', cat.color);
      item.innerHTML = `
        <div class="holiday-date">${formatDateLabel(h)}</div>
        <div class="holiday-type">${cat.label}</div>
        <div class="holiday-name">${h.name}</div>
        <div class="holiday-desc">${h.desc}</div>
      `;
      return item;
    }
    
    function updateClock() {
      const now = new Date();
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      const seconds = String(now.getSeconds()).padStart(2, '0');
      
      document.getElementById('digital-clock').textContent = `${hours}:${minutes}:${seconds}`;
      
      const days = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];
      const months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
      document.getElementById('date-display').textContent = `${days[now.getDay()]}, ${now.getDate()} de ${months[now.getMonth()]} de ${now.getFullYear()}`;
      
      const hourHand = document.getElementById('hour-hand');
      const minuteHand = document.getElementById('minute-hand');
      const secondHand = document.getElementById('second-hand');
      
      const hourDeg = (now.getHours() % 12) * 30 + now.getMinutes() * 0.5;
      const minuteDeg = now.getMinutes() * 6 + now.getSeconds() * 0.1;
      const secondDeg = now.getSeconds() * 6;
      
      hourHand.style.transform = `rotate(${hourDeg}deg)`;
      minuteHand.style.transform = `rotate(${minuteDeg}deg)`;
      secondHand.style.transform = `rotate(${secondDeg}deg)`;
    }
    
    function addClockNumbers() {
      const clock = document.getElementById('analog-clock');
      const radius = 105;
      for (let i = 1; i <= 12; i++) {
        const angle = (i * 30 - 90) * (Math.PI / 180);
        const x = 140 + radius * Math.cos(angle);
        const y = 140 + radius * Math.sin(angle);
        const num = document.createElement('div');
        num.className = 'clock-number';
        num.textContent = i;
        num.style.left = `${x - 9}px`;
        num.style.top = `${y - 12}px`;
        clock.appendChild(num);
      }
      for (let i = 0; i < 60; i++) {
        const mark = document.createElement('div');
        mark.className = i % 5 === 0 ? 'clock-mark hour' : 'clock-mark minute';
        mark.style.transform = `rotate(${i * 6}deg) translateY(-${i % 5 === 0 ? 128 : 132}px)`;
        clock.appendChild(mark);
      }
    }
    
    function generateCalendar() {
      const now = new Date();
      const year = currentYear;
      const month = currentMonth;
      const today = (now.getMonth() === month && now.getFullYear() === year) ? now.getDate() : null;
      
      const months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
      document.getElementById('calendar-month').textContent = `${months[month]} ${year}`;
      
      const firstDay = new Date(year, month, 1).getDay();
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const daysInPrevMonth = new Date(year, month, 0).getDate();
      
      const grid = document.getElementById('calendar-grid');
      grid.className = 'calendar-grid';
      grid.innerHTML = '';
      
      const dayHeaders = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
      dayHeaders.forEach(day => {
        const header = document.createElement('div');
        header.className = 'calendar-day header';
        header.textContent = day;
        grid.appendChild(header);
      });
      
      for (let i = firstDay - 1; i >= 0; i--) {
        const day = document.createElement('div');
        day.className = 'calendar-day other-month';
        day.textContent = daysInPrevMonth - i;
        grid.appendChild(day);
      }
      
      for (let i = 1; i <= daysInMonth; i++) {
        const day = document.createElement('div');
        day.className = 'calendar-day';
        const dayOfWeek = new Date(year, month, i).getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) day.classList.add('weekend');

        const dayEvents = holidays.getForDay(i, month, year);
        if (dayEvents.length > 0) {
          const primary = holidays.getPrimaryType(i, month, year);
          day.classList.add('holiday-' + primary);
          // Se houver mais de uma categoria no mesmo dia, a cor de fundo mostra
          // a de maior prioridade e um pontinho por baixo indica cada categoria
          // extra - assim nenhuma informação fica escondida.
          const extraTypes = [...new Set(dayEvents.map(h => h.type))].filter(t => t !== primary);
          if (extraTypes.length > 0) {
            const dots = document.createElement('div');
            dots.className = 'day-dots';
            extraTypes.forEach(t => {
              const dot = document.createElement('div');
              dot.className = 'dot';
              dot.style.background = CATEGORIES[t].color;
              dots.appendChild(dot);
            });
            day.appendChild(dots);
          }
        }
        if (i === today) day.classList.add('today');
        day.appendChild(document.createTextNode(i));
        grid.appendChild(day);
      }
      
      const totalCells = firstDay + daysInMonth;
      const remainingCells = 7 - (totalCells % 7);
      if (remainingCells < 7) {
        for (let i = 1; i <= remainingCells; i++) {
          const day = document.createElement('div');
          day.className = 'calendar-day other-month';
          day.textContent = i;
          grid.appendChild(day);
        }
      }
    }
    
    function toggleHolidaysCard() {
      const checkbox = document.getElementById('holiday-checkbox');
      const card = document.getElementById('holidays-card');
      if (checkbox.checked) {
        card.classList.add('show');
        if (viewMode === 'days') {
          showHolidays();
        } else if (viewMode === 'months') {
          showYearHolidays();
        }
      } else {
        card.classList.remove('show');
      }
    }
    
    function showHolidays() {
      const holidaysList = holidays.getForMonth(currentMonth, currentYear);
      const card = document.getElementById('holidays-card');
      const list = document.getElementById('holidays-list');
      const checkbox = document.getElementById('holiday-checkbox');

      if (holidaysList.length === 0 || !checkbox.checked) {
        card.classList.remove('show');
        return;
      }

      card.classList.add('show');
      list.innerHTML = '';
      holidaysList.forEach(h => list.appendChild(renderHolidayItem(h)));
    }

    function showYearHolidays() {
      const holidaysList = holidays.getForYear(currentYear);
      const card = document.getElementById('holidays-card');
      const list = document.getElementById('holidays-list');
      const checkbox = document.getElementById('holiday-checkbox');

      if (!checkbox.checked) {
        card.classList.remove('show');
        return;
      }

      card.classList.add('show');
      list.innerHTML = '';
      holidaysList.forEach(h => list.appendChild(renderHolidayItem(h)));
    }
    
    function navigate(delta) {
      if (viewMode === 'days') {
        currentMonth += delta;
        if (currentMonth > 11) { currentMonth = 0; currentYear++; }
        else if (currentMonth < 0) { currentMonth = 11; currentYear--; }
      } else if (viewMode === 'months') {
        currentYear += delta;
      } else if (viewMode === 'years') {
        currentYear += delta * 10;
      }
      renderCalendar();
      checkHolidaysVisibility();
    }
    
    function toggleView() {
      if (viewMode === 'days') viewMode = 'months';
      else if (viewMode === 'months') viewMode = 'years';
      else viewMode = 'days';
      renderCalendar();
      checkHolidaysVisibility();
    }
    
    function checkHolidaysVisibility() {
      const checkbox = document.getElementById('holiday-checkbox');
      const card = document.getElementById('holidays-card');
      if (checkbox.checked) {
        card.classList.add('show');
      } else {
        card.classList.remove('show');
      }
    }
    
    function renderCalendar() {
      if (viewMode === 'days') {
        generateCalendar();
        showHolidays();
      } else if (viewMode === 'months') {
        generateMonthsView();
        showYearHolidays();
      } else {
        generateYearsView();
        document.getElementById('holidays-card').classList.remove('show');
      }
    }
    
    function generateMonthsView() {
      const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
      document.getElementById('calendar-month').textContent = currentYear;
      const grid = document.getElementById('calendar-grid');
      grid.className = 'calendar-grid months';
      grid.innerHTML = '';
      const now = new Date();
      months.forEach((month, i) => {
        const div = document.createElement('div');
        div.className = 'calendar-day selectable';
        if (i === now.getMonth() && currentYear === now.getFullYear()) div.classList.add('today');
        div.textContent = month;
        div.onclick = () => { currentMonth = i; viewMode = 'days'; renderCalendar(); checkHolidaysVisibility(); };
        grid.appendChild(div);
      });
    }
    
    function generateYearsView() {
      const startYear = Math.floor(currentYear / 10) * 10;
      document.getElementById('calendar-month').textContent = `${startYear} - ${startYear + 9}`;
      const grid = document.getElementById('calendar-grid');
      grid.className = 'calendar-grid years';
      grid.innerHTML = '';
      const now = new Date();
      for (let i = -1; i <= 10; i++) {
        const year = startYear + i;
        const div = document.createElement('div');
        div.className = 'calendar-day selectable';
        if (i === -1 || i === 10) div.classList.add('other-month');
        if (year === now.getFullYear()) div.classList.add('today');
        div.textContent = year;
        div.onclick = () => { currentYear = year; viewMode = 'months'; renderCalendar(); checkHolidaysVisibility(); };
        grid.appendChild(div);
      }
    }
    
    addClockNumbers();
    updateClock();
    renderCalendar();
    setInterval(updateClock, 1000);
  </script>
</body>
</html>
"""
PURPLEFLIX_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PurpleFlix - Streaming</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
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
      padding: 40px 15px;
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
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 8px 24px rgba(0, 0, 0, 0.5),
        0 0 40px rgba(34, 197, 94, 0.03);
    }
    .back-button::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
      box-shadow: 
        0 0 0 1px rgba(34, 197, 94, 0.2),
        0 12px 32px rgba(0, 0, 0, 0.6),
        0 0 60px rgba(34, 197, 94, 0.15);
    }
    .logo {
      font-size: 64px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 25%, #9333ea 50%, #a855f7 75%, #c084fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 6px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(147, 51, 234, 0.7)) drop-shadow(0 0 50px rgba(139, 92, 246, 0.4));
      animation: glow-pulse-purple 3s ease-in-out infinite;
      margin-bottom: 10px;
      margin-top: 20px;
      position: relative;
      z-index: 1;
    }
    @keyframes glow-pulse-purple {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(147, 51, 234, 0.7)) drop-shadow(0 0 50px rgba(139, 92, 246, 0.4)); }
      50% { filter: drop-shadow(0 0 35px rgba(147, 51, 234, 0.9)) drop-shadow(0 0 70px rgba(139, 92, 246, 0.6)); }
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 40px;
      font-weight: 500;
      letter-spacing: 0.5px;
      position: relative;
      z-index: 1;
    }
    .preview-container {
      width: 95vw;
      max-width: 1400px;
      height: 75vh;
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 0;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 20px 60px rgba(0, 0, 0, 0.6),
        0 0 80px rgba(34, 197, 94, 0.05);
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      z-index: 1;
      overflow: hidden;
    }
    .preview-container::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    }
    iframe {
      width: 100%;
      height: 100%;
      border: none;
      border-radius: 28px;
    }
    .access-button {
      margin-top: 24px;
      padding: 16px 48px;
      border: none;
      border-radius: 999px;
      font-size: 16px;
      font-weight: 600;
      cursor: pointer;
      background: linear-gradient(135deg, #9333ea, #7c3aed);
      color: white;
      box-shadow: 0 8px 24px rgba(147, 51, 234, 0.3);
      transition: all 0.3s;
      position: relative;
      z-index: 1;
    }
    .access-button:hover {
      background: linear-gradient(135deg, #7c3aed, #6d28d9);
      transform: translateY(-2px);
      box-shadow: 0 12px 32px rgba(147, 51, 234, 0.4);
    }
    @media (max-width: 640px) {
      body { padding: 30px 10px; padding-top: 100px; }
      .logo { font-size: 40px; letter-spacing: 3px; }
      .preview-container { height: 60vh; }
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">PURPLEFLIX</div>
  <div class="tagline">Preview do Streaming</div>
  
  <div class="preview-container">
    <iframe src="https://purpleflix3.vercel.app/" allowfullscreen></iframe>
  </div>
  
  <button class="access-button" onclick="window.open('https://purpleflix3.vercel.app/', '_blank')">
    🎬 Acessar PurpleFlix
  </button>
</body>
</html>
"""

INSTAGRAM_HTML = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Instagram Downloader</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', sans-serif;
      background: #0a0f1e;
      background-image: 
        radial-gradient(at 0% 0%, rgba(131, 58, 180, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(253, 29, 29, 0.15) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(252, 176, 69, 0.1) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 40px 15px;
      padding-top: 100px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
    }
    .back-button:hover {
      border-color: rgba(131, 58, 180, 0.4);
      color: #a855f7;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 48px;
      font-weight: 900;
      background: linear-gradient(135deg, #833ab4 0%, #fd1d1d 50%, #fcb045 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-align: center;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 40px;
      text-align: center;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
      max-width: 600px;
      margin: 0 auto;
    }
    h1 {
      font-size: 28px;
      color: #f8fafc;
      margin-bottom: 10px;
    }
    p.subtitle {
      font-size: 14px;
      color: #94a3b8;
      margin-bottom: 32px;
    }
    .info-box {
      background: linear-gradient(135deg, rgba(131, 58, 180, 0.1), rgba(253, 29, 29, 0.1));
      border: 1.5px solid rgba(131, 58, 180, 0.3);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 24px;
    }
    .info-title {
      font-size: 13px;
      font-weight: 600;
      color: #c084fc;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .info-list {
      font-size: 12px;
      color: #94a3b8;
      line-height: 1.8;
      padding-left: 20px;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #cbd5e1;
    }
    input[type="text"] {
      width: 100%;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1.5px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.8);
      color: #f1f5f9;
      font-size: 14px;
      outline: none;
      transition: all 0.3s;
      margin-bottom: 20px;
    }
    input[type="text"]:focus {
      border-color: #a855f7;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1);
    }
    input[type="text"]::placeholder {
      color: #64748b;
    }
    button {
      width: 100%;
      border: none;
      border-radius: 999px;
      padding: 14px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045);
      color: white;
      transition: all 0.3s;
    }
    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(131, 58, 180, 0.4);
    }
    .status {
      margin-top: 16px;
      font-size: 13px;
      color: #9ca3af;
      text-align: center;
      padding: 12px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.6);
    }
    .status.ok {
      color: #4ade80;
      background: rgba(74, 222, 128, 0.1);
      border: 1px solid rgba(74, 222, 128, 0.3);
    }
    .status.err {
      color: #f87171;
      background: rgba(248, 113, 113, 0.1);
      border: 1px solid rgba(248, 113, 113, 0.3);
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">
    <svg width="56" height="56" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="ig-grad" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:#FED576;stop-opacity:1" />
          <stop offset="25%" style="stop-color:#F47133;stop-opacity:1" />
          <stop offset="50%" style="stop-color:#BC3081;stop-opacity:1" />
          <stop offset="75%" style="stop-color:#8A3AB9;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#4C63D2;stop-opacity:1" />
        </linearGradient>
      </defs>
      <rect x="6" y="6" width="36" height="36" rx="8" stroke="url(#ig-grad)" stroke-width="3" fill="none"/>
      <circle cx="24" cy="24" r="7" stroke="url(#ig-grad)" stroke-width="3" fill="none"/>
      <circle cx="34" cy="14" r="2" fill="url(#ig-grad)"/>
    </svg>
    Instagram
  </div>
  <div class="tagline">Baixe posts, reels, stories e IGTV</div>
  
  <div class="card">
    <h1>Downloader</h1>
    <p class="subtitle">Cole o link do Instagram abaixo</p>

    <div class="info-box">
      <div class="info-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <path d="M12 16V12M12 8H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        Aceita qualquer link:
      </div>
      <ul class="info-list">
        <li>📸 Posts (link ou @username)</li>
        <li>🎬 Reels (link)</li>
        <li>📺 IGTV (link)</li>
        <li>🖼️ Posts recentes (@username)</li>
      </ul>
    </div>

    <form method="POST">
      <input type="hidden" name="action" value="fetch">
      <label for="input">Link ou @username</label>
      <input type="text" id="input" name="input" placeholder="Cole link ou digite @username" required>
      
      <button type="submit">
        <span style="display: flex; align-items: center; justify-content: center; gap: 8px;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 21L15 15M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          Buscar Mídias
        </span>
      </button>
    </form>

    {% if media_list %}
      <form method="POST" style="margin-top: 24px;">
        <input type="hidden" name="action" value="download">
        <div style="margin-bottom: 16px;">
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input type="checkbox" id="select-all" onclick="toggleAll(this)" style="width: auto;">
            <span>Selecionar Todas</span>
          </label>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px;">
          {% for media in media_list %}
            <label style="cursor: pointer; position: relative; border-radius: 8px; overflow: hidden; aspect-ratio: 1; background: rgba(15, 23, 42, 0.8); border: 2px solid rgba(148, 163, 184, 0.2); transition: all 0.3s;" class="media-item">
              <input type="checkbox" name="selected" value="{{ media.url }}" style="position: absolute; top: 8px; left: 8px; width: 20px; height: 20px; z-index: 10;">
              {% if media.type == 'video' %}
                <video src="{{ media.url }}" style="width: 100%; height: 100%; object-fit: cover;"></video>
                <div style="position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); padding: 4px 8px; border-radius: 4px; font-size: 11px;">🎬</div>
              {% else %}
                <img src="{{ media.url }}" style="width: 100%; height: 100%; object-fit: cover;">
              {% endif %}
            </label>
          {% endfor %}
        </div>
        <button type="submit" style="background: linear-gradient(135deg, #22c55e, #16a34a);">
          <span style="display: flex; align-items: center; justify-content: center; gap: 8px;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M7 10L12 15L17 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M12 15V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Baixar Selecionadas
          </span>
        </button>
      </form>
    {% endif %}

    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% elif not media_list %}
      <div class="status">Cole um link ou @username para buscar</div>
    {% endif %}
  </div>
  
  <script>
    function toggleAll(checkbox) {
      document.querySelectorAll('input[name="selected"]').forEach(cb => cb.checked = checkbox.checked);
    }
    
    document.querySelectorAll('.media-item').forEach(item => {
      item.addEventListener('click', function(e) {
        if (e.target.tagName !== 'INPUT') {
          const checkbox = this.querySelector('input[type="checkbox"]');
          checkbox.checked = !checkbox.checked;
        }
        this.style.borderColor = this.querySelector('input').checked ? '#a855f7' : 'rgba(148, 163, 184, 0.2)';
      });
    });
  </script>
</body>
</html>
"""

MUSICA_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Música - Player</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
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
      justify-content: center;
      padding: 40px 15px;
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
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px) saturate(180%);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 
        0 0 0 1px rgba(148, 163, 184, 0.1),
        0 8px 24px rgba(0, 0, 0, 0.5),
        0 0 40px rgba(34, 197, 94, 0.03);
    }
    .back-button::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
      box-shadow: 
        0 0 0 1px rgba(34, 197, 94, 0.2),
        0 12px 32px rgba(0, 0, 0, 0.6),
        0 0 60px rgba(34, 197, 94, 0.15);
    }
    .logo {
      font-size: 64px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 6px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4));
      animation: glow-pulse 3s ease-in-out infinite;
      margin-bottom: 10px;
      position: relative;
      z-index: 1;
    }
    @keyframes glow-pulse {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7)) drop-shadow(0 0 50px rgba(59, 130, 246, 0.4)); }
      50% { filter: drop-shadow(0 0 35px rgba(34, 197, 94, 0.9)) drop-shadow(0 0 70px rgba(59, 130, 246, 0.6)); }
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 40px;
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
      width: 100%;
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
    p {
      margin: 0 0 32px;
      font-size: 14px;
      color: #94a3b8;
      font-weight: 400;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">MÚSICA</div>
  <div class="tagline">Player de Música</div>
  
  <div class="card">
    <h1>🎵 Player de Música</h1>
    <p>Em desenvolvimento...</p>
  </div>
</body>
</html>
"""

PDFS_HTML = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PDFs - Editor e Conversor</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', sans-serif;
      background: #0a0f1e;
      background-image: 
        radial-gradient(at 0% 0%, rgba(239, 68, 68, 0.08) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(220, 38, 38, 0.06) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(185, 28, 28, 0.05) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 40px 15px;
      padding-top: 100px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
    }
    .back-button:hover {
      border-color: rgba(239, 68, 68, 0.4);
      color: #ef4444;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 50%, #b91c1c 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(239, 68, 68, 0.7));
      animation: glow-pulse 3s ease-in-out infinite;
      text-align: center;
      margin-bottom: 10px;
    }
    @keyframes glow-pulse {
      0%, 100% { filter: drop-shadow(0 0 25px rgba(239, 68, 68, 0.7)); }
      50% { filter: drop-shadow(0 0 35px rgba(239, 68, 68, 0.9)); }
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      text-align: center;
      font-weight: 500;
    }
    .tools-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .tool-card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 20px;
      padding: 24px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
      cursor: pointer;
      transition: all 0.3s;
    }
    .tool-card:hover {
      border-color: rgba(239, 68, 68, 0.3);
      transform: translateY(-4px);
      box-shadow: 0 12px 32px rgba(239, 68, 68, 0.2);
    }
    .tool-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
    .tool-title {
      font-size: 18px;
      font-weight: 700;
      color: #f8fafc;
      margin-bottom: 8px;
    }
    .tool-desc {
      font-size: 13px;
      color: #94a3b8;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">PDFs</div>
  <div class="tagline">Editor e Conversor de PDF Profissional</div>
  
  <div class="tools-grid">
    <div class="tool-card" onclick="window.location.href='/pdfs/merge'">
      <div class="tool-icon">🔗</div>
      <div class="tool-title">Juntar PDFs</div>
      <div class="tool-desc">Combine, reordene e delete páginas de múltiplos PDFs</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/split'">
      <div class="tool-icon">✂️</div>
      <div class="tool-title">Dividir PDF</div>
      <div class="tool-desc">Separe um PDF em vários arquivos ou extraia páginas específicas</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/convert'">
      <div class="tool-icon">🔄</div>
      <div class="tool-title">Converter PDF</div>
      <div class="tool-desc">Converta PDF para Word, Excel, PowerPoint, imagens e mais</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/edit'">
      <div class="tool-icon">📝</div>
      <div class="tool-title">Editar PDF</div>
      <div class="tool-desc">Extraia e edite texto com formatação rica</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/protect'">
      <div class="tool-icon">🔒</div>
      <div class="tool-title">Proteger PDF</div>
      <div class="tool-desc">Adicione senha e criptografia ao seu documento PDF</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/unlock'">
      <div class="tool-icon">🔓</div>
      <div class="tool-title">Desbloquear PDF</div>
      <div class="tool-desc">Remova senha e restrições de PDFs protegidos</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/compress'">
      <div class="tool-icon">🗜️</div>
      <div class="tool-title">Comprimir PDF</div>
      <div class="tool-desc">Reduza o tamanho do arquivo PDF mantendo a qualidade</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/rotate'">
      <div class="tool-icon">🔃</div>
      <div class="tool-title">Girar PDF</div>
      <div class="tool-desc">Rotacione páginas do PDF em 90, 180 ou 270 graus</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/compare'">
      <div class="tool-icon">🔍</div>
      <div class="tool-title">Comparar PDFs</div>
      <div class="tool-desc">Compare múltiplos PDFs e veja as diferenças entre eles</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/repair'">
      <div class="tool-icon">🔧</div>
      <div class="tool-title">Reparar PDF</div>
      <div class="tool-desc">Recupere dados de PDFs corrompidos ou danificados</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/watermark'">
      <div class="tool-icon">💧</div>
      <div class="tool-title">Marca d'água</div>
      <div class="tool-desc">Adicione marca d'água de texto ou imagem ao PDF</div>
    </div>
    
    <div class="tool-card" onclick="window.location.href='/pdfs/corrupt'">
      <div class="tool-icon">💥</div>
      <div class="tool-title">Corromper PDF</div>
      <div class="tool-desc">Corrompa PDFs de forma controlada para testes</div>
    </div>
  </div>
</body>
</html>
"""

PDFS_MERGE_HTML = """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Juntar PDFs</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', sans-serif;
      background: #0a0f1e;
      background-image: 
        radial-gradient(at 0% 0%, rgba(239, 68, 68, 0.08) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(220, 38, 38, 0.06) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 40px 15px;
      padding-top: 100px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
    }
    .back-button:hover {
      border-color: rgba(239, 68, 68, 0.4);
      color: #ef4444;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 48px;
      font-weight: 900;
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 50%, #b91c1c 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-align: center;
      margin-bottom: 10px;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 40px;
      text-align: center;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
      max-width: 600px;
      margin: 0 auto;
    }
    h1 {
      font-size: 28px;
      color: #f8fafc;
      margin-bottom: 10px;
    }
    p.subtitle {
      font-size: 14px;
      color: #94a3b8;
      margin-bottom: 32px;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #cbd5e1;
    }
    input[type="file"] {
      display: none;
    }
    .file-upload-area {
      width: 100%;
      padding: 40px;
      border-radius: 12px;
      border: 2px dashed rgba(239, 68, 68, 0.3);
      background: rgba(15, 23, 42, 0.6);
      text-align: center;
      cursor: pointer;
      transition: all 0.3s;
    }
    .file-upload-area:hover {
      border-color: rgba(239, 68, 68, 0.5);
      background: rgba(15, 23, 42, 0.8);
    }
    .file-upload-area.dragover {
      border-color: #ef4444;
      background: rgba(239, 68, 68, 0.1);
    }
    .upload-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
    .upload-text {
      color: #cbd5e1;
      font-size: 14px;
      margin-bottom: 8px;
    }
    .upload-hint {
      color: #64748b;
      font-size: 12px;
    }
    .files-list {
      margin-top: 20px;
      display: none;
    }
    .files-list.show {
      display: block;
    }
    .file-item {
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .file-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .file-info {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
    }
    .file-icon {
      font-size: 24px;
    }
    .file-details {
      flex: 1;
    }
    .file-name {
      color: #cbd5e1;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .file-pages {
      display: flex;
      gap: 4px;
      align-items: center;
      font-size: 11px;
      color: #64748b;
    }
    .toggle-preview {
      padding: 4px 12px;
      border-radius: 6px;
      border: 1px solid rgba(148, 163, 184, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      font-size: 11px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .toggle-preview:hover {
      background: rgba(239, 68, 68, 0.2);
      border-color: #ef4444;
    }
    .pages-preview {
      display: none;
      grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
      gap: 8px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
    }
    .pages-preview.show {
      display: grid;
    }
    .page-thumb {
      position: relative;
      aspect-ratio: 0.7;
      background: rgba(15, 23, 42, 0.9);
      border: 2px solid rgba(148, 163, 184, 0.2);
      border-radius: 6px;
      cursor: move;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      color: #64748b;
      transition: all 0.2s;
    }
    .page-thumb:hover {
      border-color: #ef4444;
      transform: scale(1.05);
    }
    .page-thumb.dragging {
      opacity: 0.5;
    }
    .page-number {
      font-size: 11px;
      font-weight: 600;
      color: #cbd5e1;
    }
    .page-delete {
      position: absolute;
      top: -6px;
      right: -6px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: #ef4444;
      color: white;
      border: 2px solid #0a0f1e;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      cursor: pointer;
      opacity: 0;
      transition: opacity 0.2s;
    }
    .page-thumb:hover .page-delete {
      opacity: 1;
    }
    .merge-all-btn {
      margin-top: 12px;
      padding: 8px 16px;
      border-radius: 6px;
      border: 1px solid rgba(34, 197, 94, 0.3);
      background: rgba(34, 197, 94, 0.1);
      color: #4ade80;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-block;
    }
    .merge-all-btn:hover {
      background: rgba(34, 197, 94, 0.2);
      border-color: #22c55e;
    }
    .file-actions {
      display: flex;
      gap: 8px;
    }
    .btn-move {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      transition: all 0.2s;
    }
    .btn-move:hover {
      background: rgba(239, 68, 68, 0.2);
      border-color: #ef4444;
    }
    .btn-remove {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      border: 1px solid rgba(239, 68, 68, 0.3);
      background: rgba(239, 68, 68, 0.1);
      color: #ef4444;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      transition: all 0.2s;
    }
    .btn-remove:hover {
      background: rgba(239, 68, 68, 0.2);
      border-color: #ef4444;
    }
    button {
      margin-top: 20px;
      width: 100%;
      padding: 14px;
      border: none;
      border-radius: 999px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
    }
    button:hover {
      background: linear-gradient(135deg, #dc2626, #b91c1c);
    }
    .status {
      margin-top: 16px;
      font-size: 13px;
      padding: 12px;
      border-radius: 8px;
      text-align: center;
    }
    .status.ok {
      background: rgba(34, 197, 94, 0.1);
      color: #4ade80;
      border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .status.err {
      background: rgba(239, 68, 68, 0.1);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.3);
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/pdfs'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">🔗 JUNTAR PDFs</div>
  <div class="tagline">Combine múltiplos arquivos PDF em um</div>
  
  <div class="card">
    <h1>Selecione os PDFs</h1>
    <p class="subtitle">Escolha um ou mais arquivos PDF para organizar e mesclar</p>
    
    <form method="POST" enctype="multipart/form-data" id="merge-form">
      <label>Arquivos PDF</label>
      <div class="file-upload-area" id="upload-area" onclick="document.getElementById('files').click()">
        <div class="upload-icon">📄</div>
        <div class="upload-text">Clique ou arraste arquivos aqui</div>
        <div class="upload-hint">Suporta um ou múltiplos arquivos PDF</div>
      </div>
      <input type="file" id="files" name="files" accept=".pdf" multiple>
      
      <div class="files-list" id="files-list"></div>
      
      <button type="button" class="merge-all-btn" id="merge-all-btn" style="display:none;" onclick="mergeAll()">✓ Juntar Tudo</button>
      <button type="submit" id="submit-btn" style="display:none;">🔗 Juntar PDFs Selecionados</button>
    </form>
    
    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% endif %}
  </div>
  
  <script>
    let filesArray = [];
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('files');
    const filesList = document.getElementById('files-list');
    const submitBtn = document.getElementById('submit-btn');
    const mergeAllBtn = document.getElementById('merge-all-btn');
    
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
      addFiles(files);
    });
    
    fileInput.addEventListener('change', (e) => {
      addFiles(Array.from(e.target.files));
    });
    
    function addFiles(files) {
      files.forEach(file => {
        if (!filesArray.find(f => f.name === file.name)) {
          const reader = new FileReader();
          reader.onload = function(e) {
            const loadingTask = pdfjsLib.getDocument({data: e.target.result});
            loadingTask.promise.then(pdf => {
              const pages = [];
              for (let i = 1; i <= pdf.numPages; i++) {
                pages.push({num: i, deleted: false});
              }
              filesArray.push({file, pages, totalPages: pdf.numPages, showPreview: false});
              renderFiles();
            });
          };
          reader.readAsArrayBuffer(file);
        }
      });
    }
    
    function renderFiles() {
      if (filesArray.length === 0) {
        filesList.classList.remove('show');
        submitBtn.style.display = 'none';
        mergeAllBtn.style.display = 'none';
        return;
      }
      
      filesList.classList.add('show');
      submitBtn.style.display = 'block';
      mergeAllBtn.style.display = 'inline-block';
      
      filesList.innerHTML = filesArray.map((item, fileIdx) => {
        const activePages = item.pages.filter(p => !p.deleted).length;
        return `
        <div class="file-item">
          <div class="file-header">
            <div class="file-info">
              <div class="file-icon">📄</div>
              <div class="file-details">
                <div class="file-name">${item.file.name}</div>
                <div class="file-pages">${activePages}/${item.totalPages} páginas</div>
              </div>
            </div>
            <div class="file-actions">
              <button type="button" class="toggle-preview" onclick="togglePreview(${fileIdx})">
                ${item.showPreview ? '▼ Ocultar' : '▶ Ver páginas'}
              </button>
              <button type="button" class="btn-move" onclick="moveFile(${fileIdx}, -1)" ${fileIdx === 0 ? 'disabled' : ''}>↑</button>
              <button type="button" class="btn-move" onclick="moveFile(${fileIdx}, 1)" ${fileIdx === filesArray.length - 1 ? 'disabled' : ''}>↓</button>
              <button type="button" class="btn-remove" onclick="removeFile(${fileIdx})">×</button>
            </div>
          </div>
          <div class="pages-preview ${item.showPreview ? 'show' : ''}" id="preview-${fileIdx}">
            ${item.pages.map((page, pageIdx) => !page.deleted ? `
              <div class="page-thumb" draggable="true" 
                ondragstart="dragStart(event, ${fileIdx}, ${pageIdx})" 
                ondragover="dragOver(event)" 
                ondrop="drop(event, ${fileIdx}, ${pageIdx})">
                <div class="page-number">Pág ${page.num}</div>
                <div class="page-delete" onclick="deletePage(${fileIdx}, ${pageIdx})">×</div>
              </div>
            ` : '').join('')}
          </div>
        </div>
      `;
      }).join('');
    }
    
    let draggedItem = null;
    
    function dragStart(e, fileIdx, pageIdx) {
      draggedItem = {fileIdx, pageIdx};
      e.target.classList.add('dragging');
    }
    
    function dragOver(e) {
      e.preventDefault();
    }
    
    function drop(e, targetFileIdx, targetPageIdx) {
      e.preventDefault();
      if (!draggedItem || draggedItem.fileIdx !== targetFileIdx) return;
      
      const file = filesArray[targetFileIdx];
      const pages = file.pages.filter(p => !p.deleted);
      const dragIdx = pages.findIndex(p => p.num === file.pages[draggedItem.pageIdx].num);
      const dropIdx = pages.findIndex(p => p.num === file.pages[targetPageIdx].num);
      
      [pages[dragIdx], pages[dropIdx]] = [pages[dropIdx], pages[dragIdx]];
      
      file.pages = file.pages.map(p => {
        if (p.deleted) return p;
        return pages.shift();
      });
      
      draggedItem = null;
      renderFiles();
    }
    
    function deletePage(fileIdx, pageIdx) {
      filesArray[fileIdx].pages[pageIdx].deleted = true;
      renderFiles();
    }
    
    function togglePreview(fileIdx) {
      filesArray[fileIdx].showPreview = !filesArray[fileIdx].showPreview;
      renderFiles();
    }
    
    function removeFile(index) {
      filesArray.splice(index, 1);
      renderFiles();
    }
    
    function moveFile(index, direction) {
      const newIndex = index + direction;
      if (newIndex >= 0 && newIndex < filesArray.length) {
        [filesArray[index], filesArray[newIndex]] = [filesArray[newIndex], filesArray[index]];
        renderFiles();
      }
    }
    
    function mergeAll() {
      filesArray.forEach(item => {
        item.pages.forEach(page => page.deleted = false);
      });
      document.getElementById('merge-form').submit();
    }
    
    document.getElementById('merge-form').addEventListener('submit', (e) => {
      const dt = new DataTransfer();
      filesArray.forEach(item => dt.items.add(item.file));
      fileInput.files = dt.files;
      
      const pagesConfig = filesArray.map(item => {
        const activePages = item.pages.filter(p => !p.deleted).map(p => p.num);
        return activePages.join(',');
      });
      
      const pagesInput = document.createElement('input');
      pagesInput.type = 'hidden';
      pagesInput.name = 'pages_config';
      pagesInput.value = JSON.stringify(pagesConfig);
      e.target.appendChild(pagesInput);
    });
  </script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <script>
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  </script>
</body>
</html>
"""


# Código para substituir no app.py a partir da linha 6348

@app.route("/transparent", methods=["GET", "POST"], strict_slashes=False)
def transparent():
    if request.method == "POST":
        file = request.files.get('file')
        action = request.form.get('action', 'color')
        color = request.form.get('color', '#FFFFFF')
        tolerance = int(request.form.get('tolerance', 30))

        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'Selecione uma imagem.'}), 400

        try:
            from PIL import Image
            import numpy as np

            img = Image.open(file.stream).convert('RGBA')
            img_array = np.array(img)

            if action == 'auto':
                # ImportError (rembg não instalado) é um caso bem diferente de uma
                # falha real durante a remoção (rede indisponível no primeiro
                # download do modelo, erro do onnxruntime etc.) - misturar os dois
                # num "except:" genérico mandava sempre a mesma mensagem de
                # "instale o rembg" mesmo quando ele já está instalado e funcionando.
                try:
                    from rembg import remove
                except ImportError:
                    return jsonify({'success': False, 'error': 'Instale: pip install rembg'})
                import io
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                output = remove(img_bytes.read())
                img = Image.open(io.BytesIO(output))
            else:
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                diff = np.abs(img_array[:,:,:3].astype(int) - [r,g,b])
                mask = np.all(diff < tolerance, axis=2)
                img_array[:,:,3] = np.where(mask, 0, 255)
                img = Image.fromarray(img_array, 'RGBA')

            downloads_dir = str(Path.home() / "Downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            # int(time.time()) só tem resolução de 1 segundo, e checar
            # os.path.exists antes de salvar tem uma janela de corrida entre duas
            # requisições concorrentes: as duas podem ver "não existe" e uma
            # sobrescreve a outra silenciosamente, ambas reportando sucesso. Um
            # sufixo aleatório curto elimina a colisão sem precisar de lock.
            import uuid
            filename = f"transparent_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
            output_path = os.path.join(downloads_dir, filename)
            img.save(output_path, 'PNG')

            return jsonify({'success': True, 'filename': filename})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    return render_template_string(TRANSPARENT_HTML)


TRANSPARENT_HTML = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Remover Fundo</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0f1e;background-image:radial-gradient(at 0% 0%,rgba(168,85,247,0.08) 0px,transparent 50%);color:#e2e8f0;min-height:100vh;padding:40px 20px;padding-top:100px}
.back-button{position:fixed;top:24px;left:24px;width:56px;height:56px;background:rgba(15,23,42,0.8);backdrop-filter:blur(40px);border-radius:16px;border:1.5px solid rgba(148,163,184,0.15);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all 0.3s;z-index:1000;color:#cbd5e1}
.back-button:hover{border-color:rgba(168,85,247,0.4);color:#a855f7;transform:translateX(-6px)}
.container{max-width:1200px;margin:0 auto}
.logo{text-align:center;font-size:56px;font-weight:800;background:linear-gradient(135deg,#a855f7,#9333ea);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}
.tagline{text-align:center;color:#94a3b8;font-size:16px;margin-bottom:48px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}
.card{background:rgba(15,23,42,0.6);backdrop-filter:blur(40px);border-radius:24px;border:1.5px solid rgba(148,163,184,0.15);padding:32px}
.upload-area{border:2px dashed rgba(168,85,247,0.3);border-radius:16px;padding:48px 24px;text-align:center;cursor:pointer;transition:all 0.3s;margin-bottom:24px}
.upload-area:hover{border-color:#a855f7;background:rgba(168,85,247,0.05)}
.upload-area input{display:none}
.preview-container{position:relative;min-height:300px;background:repeating-conic-gradient(#1e293b 0% 25%,#0f172a 0% 50%) 50%/20px 20px;border-radius:12px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.preview-container img{max-width:100%;max-height:400px;cursor:crosshair}
.color-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:16px 0}
.color-btn{width:100%;aspect-ratio:1;border-radius:8px;border:2px solid transparent;cursor:pointer;transition:all 0.3s;position:relative}
.color-btn:hover{transform:scale(1.1);border-color:#a855f7}
.color-btn.active{border-color:#a855f7;box-shadow:0 0 20px rgba(168,85,247,0.5)}
.color-picker-wrapper{display:flex;gap:12px;align-items:center;margin:16px 0}
.color-picker-wrapper input[type="color"]{width:60px;height:60px;border:none;border-radius:12px;cursor:pointer}
.tolerance-slider{width:100%;margin:16px 0}
.tolerance-slider input{width:100%}
button{width:100%;padding:14px;border:none;border-radius:999px;background:linear-gradient(135deg,#a855f7,#9333ea);color:white;font-weight:600;cursor:pointer;transition:all 0.3s;margin-top:16px}
button:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(168,85,247,0.3)}
.status{margin-top:16px;padding:12px;border-radius:8px;text-align:center;font-size:14px}
.status.ok{background:rgba(34,197,94,0.1);color:#22c55e;border:1px solid rgba(34,197,94,0.3)}
.status.err{background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3)}
@media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="back-button" onclick="location.href='/'">
<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
</div>
<div class="container">
<div class="logo">🎨 TRANSPARÊNCIA</div>
<div class="tagline">Remova fundos de imagens</div>
<div class="grid">
<div class="card">
<h3 style="margin-bottom:16px">📤 Upload</h3>
<div class="upload-area" onclick="document.getElementById('file').click()">
<div style="font-size:48px;margin-bottom:12px">📁</div>
<div style="font-size:14px;color:#cbd5e1">Clique para selecionar imagem</div>
<input type="file" id="file" accept="image/*">
</div>
<h3 style="margin-bottom:12px">🎨 Cores Comuns</h3>
<div class="color-grid">
<div class="color-btn" style="background:#FFFFFF" data-color="#FFFFFF" title="Branco"></div>
<div class="color-btn" style="background:#000000" data-color="#000000" title="Preto"></div>
<div class="color-btn" style="background:#00FF00" data-color="#00FF00" title="Verde Chroma"></div>
<div class="color-btn" style="background:#0000FF" data-color="#0000FF" title="Azul Chroma"></div>
<div class="color-btn" style="background:#F0F0F0" data-color="#F0F0F0" title="Cinza Claro"></div>
<div class="color-btn" style="background:#808080" data-color="#808080" title="Cinza"></div>
</div>
<div class="color-picker-wrapper">
<input type="color" id="colorPicker" value="#FFFFFF">
<span style="font-size:14px;color:#94a3b8">Ou selecione uma cor personalizada</span>
</div>
<div class="tolerance-slider">
<label style="font-size:13px;color:#cbd5e1;margin-bottom:8px;display:block">Tolerância: <span id="toleranceValue">30</span></label>
<input type="range" id="tolerance" min="1" max="100" value="30" oninput="document.getElementById('toleranceValue').textContent=this.value">
</div>
<button onclick="processImage('color')">🎨 Remover Cor</button>
<button onclick="processImage('auto')" style="background:linear-gradient(135deg,#22c55e,#16a34a)">🤖 Remover Fundo (Auto)</button>
<div id="status"></div>
</div>
<div class="card">
<h3 style="margin-bottom:16px">👁️ Preview</h3>
<div class="preview-container" id="preview">
<div style="color:#64748b;font-size:14px">Selecione uma imagem</div>
</div>
<div style="margin-top:12px;font-size:12px;color:#64748b;text-align:center">Clique na imagem para selecionar a cor</div>
</div>
</div>
</div>
<script>
let selectedColor='#FFFFFF';
let imageData=null;
const fileInput=document.getElementById('file');
const preview=document.getElementById('preview');
const colorPicker=document.getElementById('colorPicker');
const colorBtns=document.querySelectorAll('.color-btn');

fileInput.addEventListener('change',e=>{
const file=e.target.files[0];
if(!file)return;
const reader=new FileReader();
reader.onload=e=>{
imageData=e.target.result;
preview.innerHTML=`<img src="${imageData}" id="previewImg">`;
document.getElementById('previewImg').addEventListener('click',pickColor);
};
reader.readAsDataURL(file);
});

colorBtns.forEach(btn=>{
btn.addEventListener('click',()=>{
colorBtns.forEach(b=>b.classList.remove('active'));
btn.classList.add('active');
selectedColor=btn.dataset.color;
colorPicker.value=selectedColor;
});
});

colorPicker.addEventListener('input',e=>{
selectedColor=e.target.value;
colorBtns.forEach(b=>b.classList.remove('active'));
});

function pickColor(e){
const img=e.target;
const canvas=document.createElement('canvas');
canvas.width=img.naturalWidth;
canvas.height=img.naturalHeight;
const ctx=canvas.getContext('2d');
ctx.drawImage(img,0,0);
const rect=img.getBoundingClientRect();
const x=Math.floor((e.clientX-rect.left)*(img.naturalWidth/rect.width));
const y=Math.floor((e.clientY-rect.top)*(img.naturalHeight/rect.height));
const pixel=ctx.getImageData(x,y,1,1).data;
selectedColor=`#${[pixel[0],pixel[1],pixel[2]].map(x=>x.toString(16).padStart(2,'0')).join('')}`.toUpperCase();
colorPicker.value=selectedColor;
colorBtns.forEach(b=>b.classList.remove('active'));
}

async function processImage(action){
if(!fileInput.files[0]){
showStatus('Selecione uma imagem','err');
return;
}
const formData=new FormData();
formData.append('file',fileInput.files[0]);
formData.append('action',action);
formData.append('color',selectedColor);
formData.append('tolerance',document.getElementById('tolerance').value);
showStatus('Processando...','ok');
try{
const res=await fetch('/transparent',{method:'POST',body:formData});
const data=await res.json();
if(data.success){
showStatus(`✅ Salvo: ${data.filename}`,'ok');
}else{
showStatus(`❌ ${data.error}`,'err');
}
}catch(e){
showStatus(`❌ Erro: ${e.message}`,'err');
}
}

function showStatus(msg,type){
const status=document.getElementById('status');
status.textContent=msg;
status.className=`status ${type}`;
}
</script>
</body>
</html>
"""
def _pix_crc16(payload):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) - o mesmo usado no BR Code do Pix."""
    crc = 0xFFFF
    for byte in payload.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return format(crc, '04X')


def _pix_tlv(field_id, value):
    return f"{field_id}{len(value):02d}{value}"


def _pix_sanitize(value, max_len):
    import unicodedata
    ascii_value = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode('ascii')
    ascii_value = ''.join(ch for ch in ascii_value if 32 <= ord(ch) <= 126).strip()
    return (ascii_value or 'NA')[:max_len]


def build_pix_payload(pix_key, pix_name, pix_city, pix_value):
    """Monta o payload EMV/BR Code do Pix (o mesmo formato usado no 'Pix Copia e Cola'),
    seguindo o Manual de Padrões para Iniciação do Pix do Banco Central."""
    pix_key = (pix_key or '').strip()
    merchant_name = _pix_sanitize(pix_name, 25)
    merchant_city = _pix_sanitize(pix_city, 15)

    merchant_account_info = _pix_tlv('00', 'br.gov.bcb.pix') + _pix_tlv('01', pix_key)

    payload = (
        _pix_tlv('00', '01') +
        _pix_tlv('26', merchant_account_info) +
        _pix_tlv('52', '0000') +
        _pix_tlv('53', '986')
    )

    raw_value = (pix_value or '').strip().replace(',', '.')
    if raw_value:
        try:
            amount = float(raw_value)
            if amount > 0:
                payload += _pix_tlv('54', f"{amount:.2f}")
        except ValueError:
            pass

    payload += _pix_tlv('58', 'BR')
    payload += _pix_tlv('59', merchant_name)
    payload += _pix_tlv('60', merchant_city)
    payload += _pix_tlv('62', _pix_tlv('05', '***'))

    payload_with_crc_id = payload + '6304'
    return payload_with_crc_id + _pix_crc16(payload_with_crc_id)


def _wifi_escape(value):
    import re
    return re.sub(r'([\\;,":])', r'\\\1', value or '')


@app.route("/qrcode", methods=["GET", "POST"], strict_slashes=False)
def qrcode_generator():
    status = None
    error = None
    qr_preview = None
    
    if request.method == "POST":
        try:
            import qrcode
            import base64
            from io import BytesIO
            
            qr_type = request.form.get('type', 'url')

            # Funções de extração automática
            import re
            from urllib.parse import quote
            
            def extract_youtube_id(url):
                patterns = [
                    r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)',
                    r'youtube\.com\/embed\/([\w-]+)',
                    r'youtube\.com\/v\/([\w-]+)',
                    r'youtube\.com\/shorts\/([\w-]+)',
                    r'youtube\.com\/channel\/([\w-]+)',
                    r'youtube\.com\/@([\w-]+)'
                ]
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        return match.group(1)
                return url
            
            def extract_instagram_user(url):
                match = re.search(r'instagram\.com\/([\w.]+)', url)
                return match.group(1) if match else url.replace('@', '')
            
            def extract_tiktok_user(url):
                match = re.search(r'tiktok\.com\/@([\w.]+)', url)
                return match.group(1) if match else url.replace('@', '')
            
            def extract_twitter_user(url):
                match = re.search(r'(?:twitter|x)\.com\/([\w]+)', url)
                return match.group(1) if match else url.replace('@', '')
            
            def extract_spotify_uri(url):
                if 'spotify.com' in url:
                    match = re.search(r'spotify\.com\/(track|album|playlist|artist)\/([\w]+)', url)
                    if match:
                        return f"spotify:{match.group(1)}:{match.group(2)}"
                return url
            
            def extract_facebook_user(url):
                match = re.search(r'facebook\.com\/([\w.]+)', url)
                return match.group(1) if match else url
            
            def extract_linkedin_user(url):
                match = re.search(r'linkedin\.com\/(in|company)\/([\w-]+)', url)
                if match:
                    return (match.group(2), match.group(1))
                return (url, 'in')
            
            # Gerar dados baseado no tipo
            if qr_type == 'url':
                data = request.form.get('url', '')
            elif qr_type == 'whatsapp':
                number = request.form.get('whatsapp_number', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                message = request.form.get('whatsapp_message', '')
                data = f"https://wa.me/{number}?text={quote(message)}" if message else f"https://wa.me/{number}"
            elif qr_type == 'instagram':
                user_input = request.form.get('instagram_user', '')
                user = extract_instagram_user(user_input)
                data = f"https://instagram.com/{user}"
            elif qr_type == 'facebook':
                user_input = request.form.get('facebook_user', '')
                user = extract_facebook_user(user_input)
                data = f"https://facebook.com/{user}"
            elif qr_type == 'twitter':
                user_input = request.form.get('twitter_user', '')
                user = extract_twitter_user(user_input)
                data = f"https://twitter.com/{user}"
            elif qr_type == 'linkedin':
                user_input = request.form.get('linkedin_user', '')
                linkedin_type = request.form.get('linkedin_type', 'in')
                if 'linkedin.com' in user_input:
                    user, detected_type = extract_linkedin_user(user_input)
                    linkedin_type = detected_type
                else:
                    user = user_input
                data = f"https://linkedin.com/{linkedin_type}/{user}"
            elif qr_type == 'youtube':
                channel_input = request.form.get('youtube_channel', '')
                youtube_type = request.form.get('youtube_type', 'channel')
                
                if 'youtube.com' in channel_input or 'youtu.be' in channel_input:
                    extracted_id = extract_youtube_id(channel_input)
                    if 'watch?v=' in channel_input or 'youtu.be' in channel_input or 'shorts' in channel_input:
                        data = f"https://youtube.com/watch?v={extracted_id}"
                    elif '@' in channel_input or '@' in extracted_id:
                        data = f"https://youtube.com/@{extracted_id.replace('@', '')}"
                    else:
                        data = f"https://youtube.com/channel/{extracted_id}"
                else:
                    if youtube_type == 'channel':
                        data = f"https://youtube.com/{channel_input}" if channel_input.startswith('@') else f"https://youtube.com/@{channel_input}"
                    else:
                        data = f"https://youtube.com/watch?v={channel_input}"
            elif qr_type == 'tiktok':
                user_input = request.form.get('tiktok_user', '')
                user = extract_tiktok_user(user_input)
                data = f"https://tiktok.com/@{user}"
            elif qr_type == 'telegram':
                user = request.form.get('telegram_user', '')
                data = f"https://t.me/{user}"
            elif qr_type == 'spotify':
                uri_input = request.form.get('spotify_uri', '')
                uri = extract_spotify_uri(uri_input)
                data = uri
            elif qr_type == 'location':
                lat = request.form.get('location_lat', '')
                lng = request.form.get('location_lng', '')
                label = request.form.get('location_label', '')
                data = f"geo:{lat},{lng}?q={lat},{lng}({label})" if label else f"geo:{lat},{lng}"
            elif qr_type == 'event':
                title = request.form.get('event_title', '')
                location = request.form.get('event_location', '')
                start = request.form.get('event_start', '').replace('T', '').replace('-', '').replace(':', '')
                end = request.form.get('event_end', '').replace('T', '').replace('-', '').replace(':', '')
                description = request.form.get('event_description', '')
                data = f"BEGIN:VEVENT\nSUMMARY:{title}\nLOCATION:{location}\nDTSTART:{start}\nDTEND:{end}\nDESCRIPTION:{description}\nEND:VEVENT"
            elif qr_type == 'wifi':
                ssid = request.form.get('ssid', '')
                password = request.form.get('password', '')
                security = request.form.get('security', 'WPA')
                data = f"WIFI:T:{security};S:{_wifi_escape(ssid)};P:{_wifi_escape(password)};;"
            elif qr_type == 'vcard':
                name = request.form.get('name', '')
                phone = request.form.get('phone', '')
                email = request.form.get('email', '')
                org = request.form.get('org', '')
                vcard_url = request.form.get('vcard_url', '')
                address = request.form.get('address', '')
                data = f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone}\nEMAIL:{email}\nORG:{org}\nURL:{vcard_url}\nADR:{address}\nEND:VCARD"
            elif qr_type == 'pix':
                pix_key = request.form.get('pix_key', '')
                pix_name = request.form.get('pix_name', '')
                pix_city = request.form.get('pix_city', '')
                pix_value = request.form.get('pix_value', '')
                data = build_pix_payload(pix_key, pix_name, pix_city, pix_value)
            elif qr_type == 'email':
                email_to = request.form.get('email_to', '')
                email_subject = request.form.get('email_subject', '')
                email_body = request.form.get('email_body', '')
                data = f"mailto:{email_to}?subject={quote(email_subject)}&body={quote(email_body)}"
            elif qr_type == 'sms':
                sms_number = request.form.get('sms_number', '')
                sms_message = request.form.get('sms_message', '')
                data = f"smsto:{sms_number}:{sms_message}"
            elif qr_type == 'phone':
                phone_number = request.form.get('phone_number', '')
                data = f"tel:{phone_number}"
            elif qr_type == 'text':
                data = request.form.get('text', '')
            else:
                data = ''
            
            if not data:
                error = "Preencha os campos necessários"
            else:
                # Configurações avançadas
                error_correction = request.form.get('error_correction', 'M').upper()
                if error_correction not in ('L', 'M', 'Q', 'H'):
                    error_correction = 'M'
                box_size = int(request.form.get('box_size', 10))
                border = int(request.form.get('border', 4))
                fg_color = request.form.get('fg_color', '#000000')
                bg_color = request.form.get('bg_color', '#FFFFFF')

                has_logo = 'logo' in request.files and request.files['logo'].filename
                if has_logo:
                    # Um logo no centro cobre parte dos módulos: força o nível mais alto
                    # de correção de erro para o QR continuar lendo mesmo assim.
                    error_correction = 'H'

                # Criar QR Code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=getattr(qrcode.constants, f'ERROR_CORRECT_{error_correction}'),
                    box_size=box_size,
                    border=border,
                )
                qr.add_data(data)
                qr.make(fit=True)

                img = qr.make_image(fill_color=fg_color, back_color=bg_color).convert('RGB')

                # Adicionar logo se fornecido
                if has_logo:
                    try:
                        from PIL import Image
                        logo_file = request.files['logo']
                        logo = Image.open(logo_file.stream).convert('RGBA')

                        # Redimensionar logo
                        qr_width, qr_height = img.size
                        logo_size = min(qr_width, qr_height) // 4
                        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

                        # Posicionar logo no centro
                        logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                        # Usa o próprio canal alfa do logo como máscara para respeitar
                        # fundos transparentes em vez de colar um quadrado sólido.
                        img.paste(logo, logo_pos, mask=logo)
                    except:
                        pass
                
                # Salvar na pasta Downloads
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                filename = f"qrcode_{qr_type}_{int(time.time())}.png"
                filepath = os.path.join(downloads_dir, filename)
                img.save(filepath)
                
                # Gerar preview base64
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                qr_preview = base64.b64encode(buffered.getvalue()).decode()
                
                status = f"✅ QR Code salvo: {filename}"
        
        except ImportError:
            error = "Biblioteca qrcode não instalada. Execute: pip install qrcode[pil]"
        except Exception as e:
            error = f"Erro ao gerar QR Code: {str(e)}"
    
    try:
        with open('templates/qrcode.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error, qr_preview=qr_preview)
    except:
        return "<h1>Error loading template</h1>"

@app.route("/compress", methods=["GET", "POST"], strict_slashes=False)
def compress():
    status = None
    error = None
    
    if request.method == "POST":
        file = request.files.get('file')
        quality = int(request.form.get('quality', 50))
        
        if not file or not file.filename:
            error = "Selecione um arquivo válido."
        else:
            temp_input = None
            try:
                from PIL import Image
                import subprocess
                import lzma

                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)

                original_name = os.path.splitext(file.filename)[0]
                file_ext = os.path.splitext(file.filename)[1].lower()
                
                # Salvar arquivo temporário para verificar tamanho
                temp_input = os.path.join(downloads_dir, f"temp_{file.filename}")
                file.save(temp_input)
                original_size = os.path.getsize(temp_input)
                
                output_filename = f"{original_name}_compressed{file_ext}"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{original_name}_compressed_{counter}{file_ext}"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                compressed = False
                
                # Imagens
                if file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif', '.gif']:
                    img = Image.open(temp_input)
                    
                    # Calcular nova dimensão
                    if quality <= 20:
                        scale = 0.3
                    elif quality <= 40:
                        scale = 0.5
                    elif quality <= 60:
                        scale = 0.7
                    elif quality <= 80:
                        scale = 0.85
                    else:
                        scale = 1.0
                    
                    if scale < 1.0:
                        new_size = (int(img.width * scale), int(img.height * scale))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Converter para RGB se necessário
                    if file_ext in ['.jpg', '.jpeg'] and img.mode in ('RGBA', 'LA', 'P'):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        if img.mode == 'RGBA':
                            bg.paste(img, mask=img.split()[-1])
                        else:
                            bg.paste(img)
                        img = bg
                    
                    # Salvar com compressão máxima
                    if file_ext in ['.jpg', '.jpeg']:
                        img.save(output_path, 'JPEG', quality=quality, optimize=True, progressive=True)
                    elif file_ext == '.png':
                        img.save(output_path, 'PNG', compress_level=9, optimize=True)
                    elif file_ext == '.webp':
                        img.save(output_path, 'WEBP', quality=quality, method=6)
                    else:
                        img.save(output_path, optimize=True)
                    
                    compressed = True
                
                # Vídeos
                elif file_ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg']:
                    # Determinar resolução, CRF e faixa de áudio de acordo com a qualidade
                    if quality <= 20:
                        scale = "scale=640:360"
                        crf = 35
                        audio_bitrate, audio_channels = '48k', '1'
                    elif quality <= 40:
                        scale = "scale=854:480"
                        crf = 30
                        audio_bitrate, audio_channels = '64k', '1'
                    elif quality <= 60:
                        scale = "scale=1280:720"
                        crf = 26
                        audio_bitrate, audio_channels = '96k', '2'
                    elif quality <= 80:
                        scale = "scale=1920:1080"
                        crf = 23
                        audio_bitrate, audio_channels = '128k', '2'
                    else:
                        scale = "scale=1920:1080"
                        crf = 20
                        audio_bitrate, audio_channels = '192k', '2'

                    result = subprocess.run([
                        'ffmpeg', '-y', '-i', temp_input, '-vf', scale, '-c:v', 'libx264',
                        '-crf', str(crf), '-preset', 'slow', '-c:a', 'aac',
                        '-b:a', audio_bitrate, '-ac', audio_channels, output_path
                    ], capture_output=True, timeout=600)

                    compressed = result.returncode == 0

                # Áudio
                elif file_ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']:
                    bitrate = max(32, int(quality * 1.28))
                    # Só reduz para mono/baixa taxa de amostragem em qualidades bem baixas;
                    # do contrário mantém estéreo, mesmo comprimindo o bitrate.
                    sample_rate = '44100' if quality > 60 else ('32000' if quality > 30 else '22050')
                    channels = '2' if quality > 30 else '1'

                    result = subprocess.run([
                        'ffmpeg', '-y', '-i', temp_input, '-b:a', f'{bitrate}k',
                        '-ar', sample_rate, '-ac', channels, output_path
                    ], capture_output=True, timeout=300)

                    compressed = result.returncode == 0
                
                # PDFs
                elif file_ext == '.pdf':
                    try:
                        import fitz
                        doc = fitz.open(temp_input)
                        
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            
                            for img_index, img in enumerate(page.get_images()):
                                xref = img[0]
                                try:
                                    base_image = doc.extract_image(xref)
                                    image_bytes = base_image["image"]
                                    
                                    img_pil = Image.open(io.BytesIO(image_bytes))
                                    
                                    # Redimensionar imagem
                                    max_dim = 1024 if quality < 50 else 1920
                                    if img_pil.width > max_dim or img_pil.height > max_dim:
                                        ratio = min(max_dim / img_pil.width, max_dim / img_pil.height)
                                        new_size = (int(img_pil.width * ratio), int(img_pil.height * ratio))
                                        img_pil = img_pil.resize(new_size, Image.Resampling.LANCZOS)
                                    
                                    if img_pil.mode in ('RGBA', 'LA', 'P'):
                                        img_pil = img_pil.convert('RGB')
                                    
                                    img_buffer = io.BytesIO()
                                    img_pil.save(img_buffer, format='JPEG', quality=max(30, quality), optimize=True)
                                    
                                    page.insert_image(page.rect, stream=img_buffer.getvalue())
                                except:
                                    pass
                        
                        doc.save(output_path, garbage=4, deflate=True, clean=True, linear=True)
                        doc.close()
                        compressed = True
                    except:
                        from PyPDF2 import PdfReader, PdfWriter
                        reader = PdfReader(temp_input)
                        writer = PdfWriter()
                        for page in reader.pages:
                            page.compress_content_streams()
                            writer.add_page(page)
                        with open(output_path, 'wb') as f:
                            writer.write(f)
                        compressed = True
                
                # Outros arquivos - LZMA
                else:
                    output_filename = output_filename + '.xz'
                    output_path = output_path + '.xz'
                    # A extensão .xz muda o nome final, então repete a checagem de
                    # colisão para não sobrescrever um .xz de uma compressão anterior.
                    counter = 1
                    while os.path.exists(output_path):
                        output_filename = f"{original_name}_compressed_{counter}{file_ext}.xz"
                        output_path = os.path.join(downloads_dir, output_filename)
                        counter += 1
                    with open(temp_input, 'rb') as f_in:
                        with lzma.open(output_path, 'wb', preset=9) as f_out:
                            f_out.write(f_in.read())
                    compressed = True
                
                # Verificar se comprimiu
                if compressed and os.path.exists(output_path):
                    compressed_size = os.path.getsize(output_path)
                    original_size_mb = round(original_size / (1024 * 1024), 2)
                    compressed_size_mb = round(compressed_size / (1024 * 1024), 2)
                    
                    if compressed_size >= original_size:
                        # Arquivo comprimido é maior ou igual, usar original
                        os.remove(output_path)
                        import shutil
                        shutil.copy(temp_input, output_path)
                        status = f"⚠️ '{output_filename}' mantido no tamanho original ({original_size_mb} MB) - compressão não reduziu o arquivo"
                    else:
                        reduction = round((1 - compressed_size / original_size) * 100, 1)
                        status = f"✅ '{output_filename}' comprimido! Original: {original_size_mb} MB → Comprimido: {compressed_size_mb} MB (Redução: {reduction}%)"
                else:
                    error = "Erro ao comprimir arquivo"
                
                # Limpar arquivo temporário
                if temp_input and os.path.exists(temp_input):
                    os.remove(temp_input)

            except subprocess.TimeoutExpired:
                error = "Timeout: arquivo muito grande"
                if temp_input and os.path.exists(temp_input):
                    os.remove(temp_input)
            except Exception as e:
                error = f"Erro: {str(e)}"
                if temp_input and os.path.exists(temp_input):
                    os.remove(temp_input)
    
    try:
        with open('templates/compress.html', 'r', encoding='utf-8') as f:
            template = f.read()
        return render_template_string(template, status=status, error=error)
    except:
        return "<h1>Error loading template</h1>"

TRANSCRIBE_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Transcrever - Áudio para Texto</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: radial-gradient(at 0% 0%, rgba(34, 197, 94, 0.08) 0px, transparent 50%), radial-gradient(at 100% 0%, rgba(59, 130, 246, 0.06) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 15px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(34, 197, 94, 0.4);
      color: #22c55e;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #3b82f6 0%, #16a34a 25%, #22c55e 50%, #16a34a 75%, #3b82f6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(34, 197, 94, 0.7));
      margin-bottom: 10px;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      font-weight: 500;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6);
      width: 100%;
      max-width: 720px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      font-weight: 700;
      color: #f8fafc;
    }
    p.subtitle {
      margin: 0 0 32px;
      font-size: 14px;
      color: #94a3b8;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #cbd5e1;
    }
    input[type="file"] {
      width: 100%;
      padding: 16px;
      border-radius: 12px;
      border: 2px dashed rgba(148, 163, 184, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      font-size: 14px;
      cursor: pointer;
      text-align: center;
      transition: all 0.3s;
    }
    input[type="file"]::file-selector-button {
      padding: 12px 28px;
      border: none;
      border-radius: 999px;
      background: linear-gradient(135deg, #22c55e, #16a34a);
      color: white;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      margin-right: 16px;
      transition: all 0.3s;
      box-shadow: 0 4px 12px rgba(34, 197, 94, 0.2);
    }
    input[type="file"]::file-selector-button:hover {
      background: linear-gradient(135deg, #16a34a, #15803d);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(34, 197, 94, 0.3);
    }
    input[type="file"]:hover {
      border-color: rgba(34, 197, 94, 0.5);
      background: rgba(15, 23, 42, 0.8);
      border-style: solid;
    }
    input[type="file"]:focus {
      border-color: #22c55e;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1);
      border-style: solid;
    }
    input[type="file"]:hover {
      border-color: rgba(34, 197, 94, 0.5);
      border-style: solid;
    }
    button {
      margin-top: 14px;
      width: 100%;
      border: none;
      border-radius: 999px;
      padding: 12px;
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
    .status.ok { color: #4ade80; }
    .status.err { color: #f97373; }
    .result {
      margin-top: 24px;
      padding: 20px;
      background: rgba(15, 23, 42, 0.8);
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      display: none;
    }
    .result.show { display: block; }
    .result h3 {
      font-size: 16px;
      color: #22c55e;
      margin-bottom: 12px;
    }
    .result-text {
      font-size: 14px;
      line-height: 1.8;
      color: #cbd5e1;
      white-space: pre-wrap;
      max-height: 400px;
      overflow-y: auto;
    }
    .copy-btn {
      margin-top: 12px;
      background: rgba(59, 130, 246, 0.2);
      border: 1px solid rgba(59, 130, 246, 0.4);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 12px;
      width: auto;
    }
    .copy-btn:hover {
      background: rgba(59, 130, 246, 0.3);
    }
    .spinner {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      animation: spin 0.7s linear infinite;
      display: none;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">TRANSCREVER</div>
  <div class="tagline">Conversor de Áudio/Vídeo para Texto</div>
  
  <div class="card">
    <h1>🎤 Transcrição de Áudio</h1>
    <p class="subtitle">Envie um arquivo de áudio ou vídeo para transcrever</p>

    <form method="POST" enctype="multipart/form-data" id="transcribe-form">
      <label for="file">Arquivo de áudio/vídeo</label>
      <input type="file" id="file" name="file" accept="audio/*,video/*" required>
      
      <button type="submit" id="transcribe-button">
        <span class="btn-text">▶️ Transcrever</span>
        <span class="spinner" id="btn-spinner"></span>
      </button>
    </form>

    {% if status %}
      <div class="status ok">{{ status }}</div>
    {% elif error %}
      <div class="status err">{{ error }}</div>
    {% else %}
      <div class="status">Pronto para transcrever.</div>
    {% endif %}
    
    {% if transcription %}
    <div class="result show">
      <h3>✅ Transcrição Completa</h3>
      <div class="result-text" id="result-text">{{ transcription }}</div>
      <button class="copy-btn" onclick="copyText()">📋 Copiar Texto</button>
    </div>
    {% endif %}
  </div>
  
  <script>
    const form = document.getElementById('transcribe-form');
    const button = document.getElementById('transcribe-button');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.getElementById('btn-spinner');
    
    form.addEventListener('submit', () => {
      button.disabled = true;
      btnText.textContent = 'Transcrevendo...';
      spinner.style.display = 'inline-block';
    });
    
    function copyText() {
      const text = document.getElementById('result-text').textContent;
      navigator.clipboard.writeText(text).then(() => {
        alert('✅ Texto copiado!');
      });
    }
  </script>
</body>
</html>
"""

@app.route("/transcribe", methods=["GET", "POST"], strict_slashes=False)
def transcribe():
    status = None
    error = None
    transcription = None
    
    if request.method == "POST":
        file = request.files.get('file')
        
        if not file:
            error = "Selecione um arquivo."
        else:
            try:
                import speech_recognition as sr
                import subprocess
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                temp_input = os.path.join(downloads_dir, f"temp_input_{int(time.time())}{os.path.splitext(file.filename)[1]}")
                temp_audio = os.path.join(downloads_dir, f"temp_audio_{int(time.time())}.wav")
                
                file.save(temp_input)
                
                # Converter com máxima qualidade para reconhecimento
                result = subprocess.run([
                    'ffmpeg', '-i', temp_input,
                    '-vn',  # Remover vídeo
                    '-ar', '48000',  # Sample rate alto
                    '-ac', '1',  # Mono
                    '-acodec', 'pcm_s16le',
                    '-af', 'highpass=f=80,lowpass=f=8000,afftdn=nf=-25,volume=3,speechnorm',  # Filtros avançados
                    '-y', temp_audio
                ], capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    raise Exception("Erro ao processar áudio")
                
                # Reconhecimento otimizado
                recognizer = sr.Recognizer()

                full_transcription = []

                with sr.AudioFile(temp_audio) as source:
                    audio_length = int(source.DURATION)
                    chunk_duration = 20  # Chunks menores = mais precisão

                    for i in range(0, audio_length, chunk_duration):
                        try:
                            chunk = recognizer.record(source, duration=min(chunk_duration, audio_length - i))
                            
                            # Tentar com show_all para pegar melhor resultado
                            text = None
                            for lang in ['pt-BR', 'en-US', 'pt-PT', 'es-ES']:
                                try:
                                    result = recognizer.recognize_google(chunk, language=lang, show_all=True)
                                    if result and 'alternative' in result:
                                        # Pegar a alternativa com maior confiança
                                        text = result['alternative'][0]['transcript']
                                        if text:
                                            break
                                except:
                                    try:
                                        text = recognizer.recognize_google(chunk, language=lang)
                                        if text:
                                            break
                                    except:
                                        continue
                            
                            if text:
                                full_transcription.append(text.strip())
                        except:
                            continue
                
                if full_transcription:
                    # Formatar texto
                    transcription = ' '.join(full_transcription)
                    # Capitalizar primeira letra de cada sentença
                    sentences = transcription.split('. ')
                    transcription = '. '.join([s.capitalize() for s in sentences])
                    status = "✅ Transcrição concluída!"
                else:
                    error = "Não foi possível transcrever. Tente um áudio com voz mais clara."
                
                # Limpar
                if os.path.exists(temp_input): os.remove(temp_input)
                if os.path.exists(temp_audio): os.remove(temp_audio)
                
            except ImportError:
                error = "Instale: pip install SpeechRecognition"
            except subprocess.TimeoutExpired:
                error = "Arquivo muito grande. Tente um áudio menor."
                if 'temp_input' in locals() and os.path.exists(temp_input): os.remove(temp_input)
                if 'temp_audio' in locals() and os.path.exists(temp_audio): os.remove(temp_audio)
            except Exception as e:
                error = "Erro ao processar áudio. Verifique o formato do arquivo."
                if 'temp_input' in locals() and os.path.exists(temp_input): os.remove(temp_input)
                if 'temp_audio' in locals() and os.path.exists(temp_audio): os.remove(temp_audio)
    
    return render_template_string(TRANSCRIBE_HTML, status=status, error=error, transcription=transcription)

GHOST_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ghost Tool - Removedor de Metadados</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: radial-gradient(at 0% 0%, rgba(139, 92, 246, 0.08) 0px, transparent 50%), radial-gradient(at 100% 0%, rgba(168, 85, 247, 0.06) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 15px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(139, 92, 246, 0.4);
      color: #8b5cf6;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 50%, #c4b5fd 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(139, 92, 246, 0.7));
      margin-bottom: 10px;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      font-weight: 500;
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6);
      width: 100%;
      max-width: 720px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      font-weight: 700;
      color: #f8fafc;
    }
    p.subtitle {
      margin: 0 0 32px;
      font-size: 14px;
      color: #94a3b8;
      line-height: 1.6;
    }
    .drop-zone {
      border: 2px dashed rgba(139, 92, 246, 0.3);
      border-radius: 16px;
      padding: 40px;
      text-align: center;
      background: rgba(15, 23, 42, 0.6);
      cursor: pointer;
      transition: all 0.3s;
      margin-bottom: 24px;
    }
    .drop-zone:hover, .drop-zone.dragover {
      border-color: #8b5cf6;
      background: rgba(139, 92, 246, 0.1);
      transform: scale(1.02);
    }
    .drop-zone-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }
    .drop-zone-text {
      font-size: 16px;
      color: #cbd5e1;
      font-weight: 600;
      margin-bottom: 8px;
    }
    .drop-zone-hint {
      font-size: 13px;
      color: #64748b;
    }
    input[type="file"] {
      display: none;
    }
    .file-list {
      margin-bottom: 24px;
      max-height: 300px;
      overflow-y: auto;
    }
    .file-item {
      background: rgba(15, 23, 42, 0.8);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    .file-info {
      flex: 1;
    }
    .file-name {
      font-size: 14px;
      color: #cbd5e1;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .file-meta {
      font-size: 12px;
      color: #64748b;
    }
    .file-status {
      font-size: 12px;
      padding: 4px 12px;
      border-radius: 6px;
      font-weight: 600;
    }
    .file-status.pending {
      background: rgba(251, 191, 36, 0.2);
      color: #fbbf24;
    }
    .file-status.cleaned {
      background: rgba(34, 197, 94, 0.2);
      color: #22c55e;
    }
    .file-status.error {
      background: rgba(239, 68, 68, 0.2);
      color: #ef4444;
    }
    .remove-btn {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #ef4444;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      cursor: pointer;
      margin-left: 12px;
      transition: all 0.3s;
    }
    .remove-btn:hover {
      background: rgba(239, 68, 68, 0.3);
    }
    .action-buttons {
      display: flex;
      gap: 12px;
    }
    button {
      flex: 1;
      border: none;
      border-radius: 999px;
      padding: 14px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.3s;
    }
    .btn-primary {
      background: linear-gradient(135deg, #8b5cf6, #7c3aed);
      color: white;
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(139, 92, 246, 0.4);
    }
    .btn-primary:disabled {
      opacity: 0.6;
      cursor: default;
      transform: none;
    }
    .btn-secondary {
      background: rgba(59, 130, 246, 0.2);
      border: 1px solid rgba(59, 130, 246, 0.4);
      color: #3b82f6;
    }
    .btn-secondary:hover {
      background: rgba(59, 130, 246, 0.3);
    }
    .btn-secondary:disabled {
      opacity: 0.6;
      cursor: default;
    }
    .privacy-badge {
      margin-top: 24px;
      padding: 16px;
      background: rgba(139, 92, 246, 0.1);
      border-radius: 12px;
      border: 1px solid rgba(139, 92, 246, 0.2);
      text-align: center;
    }
    .privacy-badge-icon {
      font-size: 24px;
      margin-bottom: 8px;
    }
    .privacy-badge-text {
      font-size: 13px;
      color: #a78bfa;
      font-weight: 600;
    }
    .spinner {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">GHOST</div>
  <div class="tagline">Removedor de Metadados em Massa</div>
  
  <div class="card">
    <h1>👻 Ghost Tool</h1>
    <p class="subtitle">🔒 Remova metadados de múltiplos arquivos simultaneamente. GPS, autor, datas, câmera, software - tudo apagado permanentemente. Processamento 100% local.</p>

    <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
      <div class="drop-zone-icon">📁</div>
      <div class="drop-zone-text">Arraste arquivos aqui ou clique para selecionar</div>
      <div class="drop-zone-hint">Suporta: Imagens, PDFs, Documentos, Vídeos, Áudios (150+ formatos)</div>
    </div>
    
    <input type="file" id="file-input" multiple accept="*/*">
    
    <div class="file-list" id="file-list"></div>
    
    <div class="action-buttons">
      <button class="btn-primary" id="clean-btn" onclick="cleanMetadata()" disabled>
        <span>🧹 Limpar Metadados</span>
      </button>
      <button class="btn-secondary" id="download-btn" onclick="downloadAll()" disabled>
        <span>⬇️ Baixar Todos</span>
      </button>
    </div>
    
    <div class="privacy-badge">
      <div class="privacy-badge-icon">🔐</div>
      <div class="privacy-badge-text">Processamento 100% Local - Seus arquivos nunca saem do seu computador</div>
    </div>
  </div>
  
  <script>
    let files = [];
    let cleanedFiles = [];
    
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileList = document.getElementById('file-list');
    const cleanBtn = document.getElementById('clean-btn');
    const downloadBtn = document.getElementById('download-btn');
    
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      handleFiles(e.dataTransfer.files);
    });
    
    fileInput.addEventListener('change', (e) => {
      handleFiles(e.target.files);
    });
    
    function handleFiles(newFiles) {
      files = [...files, ...Array.from(newFiles)];
      renderFileList();
      cleanBtn.disabled = false;
    }
    
    function renderFileList() {
      fileList.innerHTML = files.map((file, index) => `
        <div class="file-item" id="file-${index}">
          <div class="file-info">
            <div class="file-name">${file.name}</div>
            <div class="file-meta">${formatBytes(file.size)} • ${file.type || 'Desconhecido'}</div>
          </div>
          <div class="file-status pending" id="status-${index}">Pendente</div>
          <button class="remove-btn" onclick="removeFile(${index})">×</button>
        </div>
      `).join('');
    }
    
    function removeFile(index) {
      files.splice(index, 1);
      cleanedFiles.splice(index, 1);
      renderFileList();
      if (files.length === 0) {
        cleanBtn.disabled = true;
        downloadBtn.disabled = true;
      }
    }
    
    function formatBytes(bytes) {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    async function cleanMetadata() {
      cleanBtn.disabled = true;
      cleanBtn.innerHTML = '<span class="spinner"></span><span>Limpando...</span>';
      
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));
      
      try {
        const response = await fetch('/ghost/clean', {
          method: 'POST',
          body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
          result.files.forEach((fileData, index) => {
            const statusEl = document.getElementById(`status-${index}`);
            if (fileData.success) {
              statusEl.className = 'file-status cleaned';
              statusEl.textContent = '✅ Limpo';
              cleanedFiles[index] = fileData;
            } else {
              statusEl.className = 'file-status error';
              statusEl.textContent = '❌ Erro';
            }
          });
          downloadBtn.disabled = false;
        }
      } catch (error) {
        alert('Erro ao limpar metadados');
      }
      
      cleanBtn.innerHTML = '<span>🧹 Limpar Metadados</span>';
      cleanBtn.disabled = false;
    }
    
    async function downloadAll() {
      for (let i = 0; i < cleanedFiles.length; i++) {
        if (cleanedFiles[i] && cleanedFiles[i].success) {
          const response = await fetch(`/ghost/download/${cleanedFiles[i].filename}`);
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = cleanedFiles[i].original_name;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }
    }
  </script>
</body>
</html>
"""

@app.route("/ghost", methods=["GET"], strict_slashes=False)
def ghost():
    return render_template_string(GHOST_HTML)

@app.route("/ghost/clean", methods=["POST"], strict_slashes=False)
def ghost_clean():
    files = request.files.getlist('files')
    results = []
    
    downloads_dir = str(Path.home() / "Downloads" / "ghost_cleaned")
    os.makedirs(downloads_dir, exist_ok=True)
    
    for file in files:
        try:
            import subprocess
            from PIL import Image
            import shutil
            
            ext = os.path.splitext(file.filename)[1].lower()
            temp_input = os.path.join(downloads_dir, f"temp_{int(time.time())}_{file.filename}")
            output_file = os.path.join(downloads_dir, f"clean_{int(time.time())}_{file.filename}")
            
            file.save(temp_input)
            success = False
            
            # Imagens (50+ formatos)
            image_exts = ['.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.gif', '.ico', '.heic', '.heif', 
                         '.avif', '.svg', '.psd', '.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.raf', '.rw2', 
                         '.pef', '.sr2', '.jfif', '.jpe', '.jif', '.jfi', '.jp2', '.j2k', '.jpf', '.jpx', '.jpm', 
                         '.mj2', '.exr', '.hdr', '.tga', '.dds', '.pcx', '.ppm', '.pbm', '.pgm', '.pnm']
            
            if ext in image_exts:
                is_animated = False
                try:
                    with Image.open(temp_input) as probe:
                        is_animated = getattr(probe, 'is_animated', False)
                except Exception:
                    pass

                if is_animated:
                    # getdata()/putdata() só reconstrói o frame atual - para GIF/WEBP
                    # animados isso jogava fora todos os outros frames e a imagem
                    # "limpa" virava uma imagem estática. O exiftool apaga os metadados
                    # direto no arquivo, sem decodificar/recompor frames, então a
                    # animação é preservada.
                    try:
                        subprocess.run(['exiftool', '-all=', '-overwrite_original', temp_input], capture_output=True, timeout=30)
                        shutil.move(temp_input, output_file)
                        success = True
                    except Exception:
                        shutil.copy2(temp_input, output_file)
                        success = True
                else:
                    try:
                        img = Image.open(temp_input)
                        # Remover EXIF e criar imagem limpa
                        data = list(img.getdata())
                        img_clean = Image.new(img.mode, img.size)
                        img_clean.putdata(data)
                        if ext in ['.jpg', '.jpeg', '.jfif', '.jpe']:
                            img_clean.save(output_file, 'JPEG', quality=95, optimize=True)
                        elif ext == '.png':
                            img_clean.save(output_file, 'PNG', optimize=True)
                        else:
                            img_clean.save(output_file)
                        success = True
                    except:
                        # Fallback: usar exiftool ou ffmpeg
                        subprocess.run(['exiftool', '-all=', '-overwrite_original', temp_input], capture_output=True, timeout=30)
                        shutil.move(temp_input, output_file)
                        success = True
            
            # PDFs
            elif ext == '.pdf':
                try:
                    from PyPDF2 import PdfReader, PdfWriter
                    reader = PdfReader(temp_input)
                    writer = PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    writer.add_metadata({})
                    with open(output_file, 'wb') as f:
                        writer.write(f)
                    success = True
                except:
                    # Fallback: qpdf
                    subprocess.run(['qpdf', '--linearize', '--remove-unreferenced-resources=yes', temp_input, output_file], 
                                 capture_output=True, timeout=60)
                    success = True
            
            # Vídeos (30+ formatos)
            elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg', '.3gp', 
                        '.3g2', '.f4v', '.swf', '.vob', '.ogv', '.m2ts', '.mts', '.ts', '.divx', '.xvid', '.asf', 
                        '.rm', '.rmvb', '.dv', '.mxf', '.mod', '.tod']:
                ffmpeg_result = subprocess.run(['ffmpeg', '-i', temp_input, '-map_metadata', '-1', '-map_metadata:s:v', '-1',
                              '-map_metadata:s:a', '-1', '-codec', 'copy', '-y', output_file],
                             capture_output=True, timeout=180)
                success = ffmpeg_result.returncode == 0

            # Áudios (40+ formatos)
            elif ext in ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.opus', '.aiff', '.ape', '.alac',
                        '.ac3', '.dts', '.amr', '.au', '.mid', '.midi', '.mka', '.mp2', '.mpc', '.oga', '.ra', '.spx',
                        '.tta', '.voc', '.wv', '.3ga', '.caf', '.gsm', '.m4b', '.m4p', '.oga', '.mogg']:
                ffmpeg_result = subprocess.run(['ffmpeg', '-i', temp_input, '-map_metadata', '-1', '-codec', 'copy', '-y', output_file],
                             capture_output=True, timeout=120)
                success = ffmpeg_result.returncode == 0
            
            # Documentos Office (DOCX, XLSX, PPTX)
            elif ext in ['.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm']:
                import zipfile
                temp_dir = os.path.join(downloads_dir, f"temp_extract_{int(time.time())}")
                os.makedirs(temp_dir, exist_ok=True)
                with zipfile.ZipFile(temp_input, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                # Apagar a pasta docProps inteira deixava [Content_Types].xml e
                # _rels/.rels com referências para arquivos que não existem mais -
                # o pacote OOXML ficava estruturalmente inválido (Word abre em modo
                # de reparo). Em vez de apagar, zeramos o conteúdo dos metadados
                # (autor, empresa, datas, contagens etc.) mantendo os arquivos no lugar.
                core_xml_path = os.path.join(temp_dir, 'docProps', 'core.xml')
                if os.path.exists(core_xml_path):
                    with open(core_xml_path, 'w', encoding='utf-8') as f:
                        f.write(
                            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                            '<cp:coreProperties '
                            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                            'xmlns:dcterms="http://purl.org/dc/terms/" '
                            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
                            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
                        )
                app_xml_path = os.path.join(temp_dir, 'docProps', 'app.xml')
                if os.path.exists(app_xml_path):
                    with open(app_xml_path, 'w', encoding='utf-8') as f:
                        f.write(
                            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                            '<Properties '
                            'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
                            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
                        )
                # Recriar arquivo
                with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                    for root, dirs, files_in_dir in os.walk(temp_dir):
                        for f in files_in_dir:
                            file_path = os.path.join(root, f)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zip_out.write(file_path, arcname)
                shutil.rmtree(temp_dir)
                success = True
            
            # Documentos antigos Office (DOC, XLS, PPT)
            elif ext in ['.doc', '.xls', '.ppt']:
                # Usar antiword/catdoc ou copiar sem metadados
                shutil.copy2(temp_input, output_file)
                subprocess.run(['exiftool', '-all=', '-overwrite_original', output_file], capture_output=True, timeout=30)
                success = True
            
            # eBooks (10+ formatos)
            elif ext in ['.epub', '.mobi', '.azw', '.azw3', '.fb2', '.cbr', '.cbz', '.cb7']:
                if ext == '.epub':
                    import zipfile
                    temp_dir = os.path.join(downloads_dir, f"temp_epub_{int(time.time())}")
                    os.makedirs(temp_dir, exist_ok=True)
                    with zipfile.ZipFile(temp_input, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    # Remover metadata.xml
                    for root, dirs, files_in_dir in os.walk(temp_dir):
                        for f in files_in_dir:
                            if 'metadata' in f.lower():
                                os.remove(os.path.join(root, f))
                    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                        for root, dirs, files_in_dir in os.walk(temp_dir):
                            for f in files_in_dir:
                                file_path = os.path.join(root, f)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zip_out.write(file_path, arcname)
                    shutil.rmtree(temp_dir)
                    success = True
                else:
                    shutil.copy2(temp_input, output_file)
                    success = True
            
            # Arquivos compactados (10+ formatos)
            elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso']:
                # Recomprimir sem metadados
                if ext == '.zip':
                    import zipfile
                    temp_dir = os.path.join(downloads_dir, f"temp_zip_{int(time.time())}")
                    os.makedirs(temp_dir, exist_ok=True)
                    with zipfile.ZipFile(temp_input, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                        for root, dirs, files_in_dir in os.walk(temp_dir):
                            for f in files_in_dir:
                                file_path = os.path.join(root, f)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zip_out.write(file_path, arcname)
                    shutil.rmtree(temp_dir)
                    success = True
                else:
                    shutil.copy2(temp_input, output_file)
                    success = True
            
            # Fontes (10+ formatos)
            elif ext in ['.ttf', '.otf', '.woff', '.woff2', '.eot']:
                shutil.copy2(temp_input, output_file)
                success = True
            
            # CAD (5+ formatos)
            elif ext in ['.dwg', '.dxf', '.dwf', '.dgn', '.stl']:
                shutil.copy2(temp_input, output_file)
                success = True
            
            # Modelos 3D (10+ formatos)
            elif ext in ['.obj', '.fbx', '.dae', '.blend', '.3ds', '.gltf', '.glb', '.ply', '.stl']:
                shutil.copy2(temp_input, output_file)
                success = True
            
            # Texto puro e código (20+ formatos)
            elif ext in ['.txt', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js', '.py', '.java', '.cpp', 
                        '.c', '.h', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.sql']:
                # Decodificar como UTF-8 com errors='ignore' e regravar corrompia
                # silenciosamente qualquer arquivo em outra codificação (ex: CSV do
                # Excel em Latin-1 com acentos) - os bytes que não eram UTF-8 válido
                # simplesmente desapareciam. Texto puro não carrega metadados de
                # verdade, então só copiamos os bytes como estão, removendo um BOM
                # UTF-8 no início se houver.
                with open(temp_input, 'rb') as f:
                    raw = f.read()
                if raw.startswith(b'\xef\xbb\xbf'):
                    raw = raw[3:]
                with open(output_file, 'wb') as f:
                    f.write(raw)
                success = True
            
            # Fallback universal: exiftool
            else:
                try:
                    shutil.copy2(temp_input, output_file)
                    subprocess.run(['exiftool', '-all=', '-overwrite_original', output_file], 
                                 capture_output=True, timeout=30)
                    success = True
                except:
                    # Último fallback: copiar arquivo
                    shutil.copy2(temp_input, output_file)
                    success = True
            
            if os.path.exists(temp_input):
                os.remove(temp_input)
            
            if success and os.path.exists(output_file):
                results.append({'success': True, 'filename': os.path.basename(output_file), 'original_name': file.filename})
            else:
                results.append({'success': False, 'error': 'Falha ao processar'})
        
        except Exception as e:
            if 'temp_input' in locals() and os.path.exists(temp_input):
                os.remove(temp_input)
            results.append({'success': False, 'error': 'Erro ao processar arquivo'})
    
    return jsonify({'success': True, 'files': results})

@app.route("/ghost/download/<filename>", methods=["GET"], strict_slashes=False)
def ghost_download(filename):
    downloads_dir = str(Path.home() / "Downloads" / "ghost_cleaned")
    return send_file(os.path.join(downloads_dir, filename), as_attachment=True)

STEALTH_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stealth - Esteganografia Criptografada</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0a0f1e;
      background-image: radial-gradient(at 0% 0%, rgba(239, 68, 68, 0.08) 0px, transparent 50%), radial-gradient(at 100% 0%, rgba(220, 38, 38, 0.06) 0px, transparent 50%);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 15px;
    }
    .back-button {
      position: fixed;
      top: 24px;
      left: 24px;
      width: 56px;
      height: 56px;
      background: rgba(15, 23, 42, 0.8);
      backdrop-filter: blur(40px);
      border-radius: 16px;
      border: 1.5px solid rgba(148, 163, 184, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s;
      z-index: 1000;
      color: #cbd5e1;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 8px 24px rgba(0, 0, 0, 0.5);
    }
    .back-button:hover {
      background: rgba(15, 23, 42, 0.95);
      border-color: rgba(239, 68, 68, 0.4);
      color: #ef4444;
      transform: translateX(-6px);
    }
    .logo {
      font-size: 72px;
      font-weight: 900;
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 50%, #b91c1c 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      letter-spacing: 18px;
      text-transform: uppercase;
      filter: drop-shadow(0 0 25px rgba(239, 68, 68, 0.7));
      margin-bottom: 10px;
    }
    .tagline {
      color: #64748b;
      font-size: 15px;
      margin-bottom: 48px;
      font-weight: 500;
    }
    .mode-selector {
      display: flex;
      gap: 12px;
      margin-bottom: 40px;
      background: rgba(15, 23, 42, 0.6);
      padding: 6px;
      border-radius: 16px;
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    .mode-btn {
      padding: 12px 32px;
      border-radius: 12px;
      border: none;
      background: transparent;
      color: #94a3b8;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s;
    }
    .mode-btn.active {
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
    }
    .card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 40px;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6);
      width: 100%;
      max-width: 720px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px);
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      font-weight: 700;
      color: #f8fafc;
    }
    p.subtitle {
      margin: 0 0 32px;
      font-size: 14px;
      color: #94a3b8;
      line-height: 1.6;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #cbd5e1;
    }
    input[type="file"] {
      width: 100%;
      padding: 16px;
      border-radius: 12px;
      border: 2px dashed rgba(148, 163, 184, 0.3);
      background: rgba(15, 23, 42, 0.6);
      color: #cbd5e1;
      font-size: 14px;
      cursor: pointer;
      text-align: center;
      transition: all 0.3s;
      margin-bottom: 16px;
    }
    input[type="file"]::file-selector-button {
      padding: 12px 28px;
      border: none;
      border-radius: 999px;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      margin-right: 16px;
      transition: all 0.3s;
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
    }
    input[type="file"]::file-selector-button:hover {
      background: linear-gradient(135deg, #dc2626, #b91c1c);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3);
    }
    input[type="file"]:hover {
      border-color: rgba(239, 68, 68, 0.5);
      background: rgba(15, 23, 42, 0.8);
      border-style: solid;
    }
    input[type="file"]:focus {
      border-color: #ef4444;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
      border-style: solid;
    }
    input[type="password"], textarea {
      width: 100%;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.8);
      color: #f1f5f9;
      font-size: 14px;
      outline: none;
      transition: all 0.2s;
      margin-bottom: 16px;
      font-family: inherit;
    }
    input[type="password"]:focus, textarea:focus {
      border-color: #ef4444;
      background: rgba(15, 23, 42, 0.95);
      box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
    }
    textarea {
      min-height: 120px;
      resize: vertical;
    }
    button {
      width: 100%;
      border: none;
      border-radius: 999px;
      padding: 14px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.3s;
    }
    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(239, 68, 68, 0.4);
    }
    button:disabled {
      opacity: 0.6;
      cursor: default;
      transform: none;
    }
    .status {
      margin-top: 16px;
      padding: 12px;
      border-radius: 12px;
      font-size: 13px;
      font-weight: 600;
      text-align: center;
      display: none;
    }
    .status.show { display: block; }
    .status.success {
      background: rgba(34, 197, 94, 0.2);
      border: 1px solid rgba(34, 197, 94, 0.4);
      color: #22c55e;
    }
    .status.error {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #ef4444;
    }
    .security-badge {
      margin-top: 24px;
      padding: 16px;
      background: rgba(239, 68, 68, 0.1);
      border-radius: 12px;
      border: 1px solid rgba(239, 68, 68, 0.2);
      text-align: center;
    }
    .security-badge-icon {
      font-size: 24px;
      margin-bottom: 8px;
    }
    .security-badge-text {
      font-size: 13px;
      color: #fca5a5;
      font-weight: 600;
      line-height: 1.6;
    }
    .spinner {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .mode-content {
      display: none;
    }
    .mode-content.active {
      display: block;
    }
  </style>
</head>
<body>
  <div class="back-button" onclick="location.href='/'">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  
  <div class="logo">STEALTH</div>
  <div class="tagline">Esteganografia com Criptografia AES-256</div>
  
  <div class="mode-selector">
    <button class="mode-btn active" onclick="switchMode('hide')">🔒 Esconder</button>
    <button class="mode-btn" onclick="switchMode('extract')">🔓 Extrair</button>
  </div>
  
  <div class="card">
    <!-- MODO ESCONDER -->
    <div class="mode-content active" id="hide-mode">
      <h1>🕵️ Esconder Arquivo</h1>
      <p class="subtitle">🔐 Esconda múltiplos arquivos dentro de imagens, vídeos, áudios ou PDFs. Criptografia AES-256 opcional.</p>

      <form method="POST" enctype="multipart/form-data" action="/stealth/hide" id="hide-form">
        <label for="cover-image">Arquivo de Cobertura (Imagem/Vídeo/Áudio/PDF)</label>
        <input type="file" id="cover-image" name="cover_image" accept="image/*,video/*,audio/*,.pdf" required>
        
        <label for="secret-file">Arquivo(s) Secreto(s) - Múltiplos permitidos</label>
        <input type="file" id="secret-file" name="secret_files" multiple required>
        
        <label for="password-hide">Senha (Opcional - deixe vazio para sem senha)</label>
        <input type="password" id="password-hide" name="password" placeholder="Senha forte (opcional)" minlength="8">
        
        <button type="submit" id="hide-btn">
          <span>🔒 Esconder Arquivo(s)</span>
        </button>
      </form>
      
      <div class="status" id="hide-status"></div>
    </div>
    
    <!-- MODO EXTRAIR -->
    <div class="mode-content" id="extract-mode">
      <h1>🔓 Extrair Arquivo</h1>
      <p class="subtitle">🔍 Extraia arquivos de imagens, vídeos, áudios ou PDFs esteganográficos. Senha opcional.</p>

      <form method="POST" enctype="multipart/form-data" action="/stealth/extract" id="extract-form">
        <label for="stego-image">Arquivo com Dados Escondidos</label>
        <input type="file" id="stego-image" name="stego_image" accept="*/*" required>
        
        <label for="password-extract">Senha (Deixe vazio se não usou senha)</label>
        <input type="password" id="password-extract" name="password" placeholder="Senha (se usou)">
        
        <button type="submit" id="extract-btn">
          <span>🔓 Extrair Arquivo(s)</span>
        </button>
      </form>
      
      <div class="status" id="extract-status"></div>
    </div>
    
    <div class="security-badge">
      <div class="security-badge-icon">🛡️</div>
      <div class="security-badge-text">Criptografia AES-256 + LSB Steganography<br>Arquivos processados localmente - Máxima segurança</div>
    </div>
  </div>
  
  <script>
    function switchMode(mode) {
      document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.mode-content').forEach(content => content.classList.remove('active'));
      
      if (mode === 'hide') {
        document.querySelector('.mode-btn:first-child').classList.add('active');
        document.getElementById('hide-mode').classList.add('active');
      } else {
        document.querySelector('.mode-btn:last-child').classList.add('active');
        document.getElementById('extract-mode').classList.add('active');
      }
    }
    
    document.getElementById('hide-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('hide-btn');
      const status = document.getElementById('hide-status');
      
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span><span>Processando...</span>';
      status.classList.remove('show');
      
      const formData = new FormData(e.target);
      
      try {
        const response = await fetch('/stealth/hide', {
          method: 'POST',
          body: formData
        });
        
        if (response.ok) {
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          // O servidor manda o nome/extensão reais no Content-Disposition (o
          // arquivo pode ser vídeo/áudio/pdf, não só png) - usar sempre
          // "stealth_image.png" salvava, por exemplo, um MP4 com extensão .png.
          const disposition = response.headers.get('Content-Disposition') || '';
          const match = disposition.match(/filename="?([^";]+)"?/);
          a.download = match ? match[1] : 'stealth_image.png';
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
          
          status.className = 'status success show';
          status.textContent = '✅ Arquivo escondido com sucesso! Download iniciado.';
        } else {
          const result = await response.json();
          status.className = 'status error show';
          status.textContent = '❌ ' + (result.error || 'Erro ao esconder arquivo');
        }
      } catch (error) {
        status.className = 'status error show';
        status.textContent = '❌ Erro ao processar';
      }
      
      btn.disabled = false;
      btn.innerHTML = '<span>🔒 Esconder Arquivo</span>';
    });
    
    document.getElementById('extract-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('extract-btn');
      const status = document.getElementById('extract-status');
      
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span><span>Extraindo...</span>';
      status.classList.remove('show');
      
      const formData = new FormData(e.target);
      
      try {
        const response = await fetch('/stealth/extract', {
          method: 'POST',
          body: formData
        });
        
        if (response.ok) {
          const blob = await response.blob();
          const filename = response.headers.get('X-Filename') || 'extracted_file';
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
          
          status.className = 'status success show';
          status.textContent = '✅ Arquivo extraído com sucesso! Download iniciado.';
        } else {
          const result = await response.json();
          status.className = 'status error show';
          status.textContent = '❌ ' + (result.error || 'Erro ao extrair arquivo');
        }
      } catch (error) {
        status.className = 'status error show';
        status.textContent = '❌ Erro ao processar';
      }
      
      btn.disabled = false;
      btn.innerHTML = '<span>🔓 Extrair Arquivo</span>';
    });
  </script>
</body>
</html>
"""

@app.route("/stealth", methods=["GET"], strict_slashes=False)
def stealth():
    return render_template_string(STEALTH_HTML)

@app.route("/stealth/hide", methods=["POST"], strict_slashes=False)
def stealth_hide():
    try:
        from PIL import Image
        from Crypto.Cipher import AES
        from Crypto.Random import get_random_bytes
        from Crypto.Protocol.KDF import PBKDF2
        import io
        import zipfile
        import subprocess
        
        cover_file = request.files.get('cover_image')
        secret_files = request.files.getlist('secret_files')
        password = request.form.get('password', '').strip()
        
        if not all([cover_file, secret_files]):
            return jsonify({'error': 'Dados incompletos'}), 400
        
        # Ler arquivo de cobertura
        cover_data = cover_file.read()
        cover_ext = os.path.splitext(cover_file.filename)[1].lower()
        
        # Preparar múltiplos arquivos secretos
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for secret_file in secret_files:
                zf.writestr(secret_file.filename, secret_file.read())
        secret_data = zip_buffer.getvalue()
        
        # Criptografar se senha fornecida
        if password:
            salt = get_random_bytes(16)
            key = PBKDF2(password, salt, dkLen=32)
            cipher = AES.new(key, AES.MODE_GCM)
            ciphertext, tag = cipher.encrypt_and_digest(secret_data)
            # Header: MAGIC + salt + nonce + tag + data_len + data
            header = b'STLTH' + salt + cipher.nonce + tag + len(ciphertext).to_bytes(4, 'big')
            full_data = header + ciphertext
        else:
            # Sem senha: MAGIC + data_len + data
            header = b'STLTH' + b'\x00' * 48 + len(secret_data).to_bytes(4, 'big')
            full_data = header + secret_data
        
        # Esconder baseado no tipo de arquivo
        if cover_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif']:
            # LSB em imagens
            img = Image.open(io.BytesIO(cover_data))
            # Forçar RGB sempre descartava a transparência de PNGs/GIFs com alpha,
            # tornando uma imagem de capa transparente em opaca - o oposto de
            # "discreto", que é a proposta de uma ferramenta de esteganografia.
            # Os bits são gravados só em R/G/B, então dá para preservar o alfa
            # original sem mexer no processo de extração (convert('RGB') em cima
            # de RGBA só descarta o canal alfa, não altera os valores de R/G/B).
            has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
            img = img.convert('RGBA') if has_alpha else img.convert('RGB')
            pixels = list(img.getdata())

            data_bits = ''.join(format(byte, '08b') for byte in full_data)
            max_bits = len(pixels) * 3

            if len(data_bits) > max_bits - 32:
                return jsonify({'error': 'Arquivo de cobertura muito pequeno'}), 400

            new_pixels = []
            bit_index = 0

            for pixel in pixels:
                if has_alpha:
                    r, g, b, a = pixel
                else:
                    r, g, b = pixel
                if bit_index < len(data_bits):
                    r = (r & 0xFE) | int(data_bits[bit_index])
                    bit_index += 1
                if bit_index < len(data_bits):
                    g = (g & 0xFE) | int(data_bits[bit_index])
                    bit_index += 1
                if bit_index < len(data_bits):
                    b = (b & 0xFE) | int(data_bits[bit_index])
                    bit_index += 1
                new_pixels.append((r, g, b, a) if has_alpha else (r, g, b))

            stego_img = Image.new('RGBA' if has_alpha else 'RGB', img.size)
            stego_img.putdata(new_pixels)
            output = io.BytesIO()
            stego_img.save(output, format='PNG')
            output.seek(0)

            output_ext = '.png'
            return send_file(output, as_attachment=True, download_name=f'stealth{output_ext}')
        
        else:
            # Para vídeos, áudios, PDFs e outros: anexar ao final
            output = io.BytesIO()
            output.write(cover_data)
            output.write(full_data)
            output.seek(0)
            
            # Manter extensão e mimetype original
            mimetype_map = {
                '.mp4': 'video/mp4',
                '.avi': 'video/x-msvideo',
                '.mkv': 'video/x-matroska',
                '.mov': 'video/quicktime',
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.flac': 'audio/flac',
                '.m4a': 'audio/mp4',
                '.ogg': 'audio/ogg',
                '.pdf': 'application/pdf'
            }
            
            mimetype = mimetype_map.get(cover_ext, 'application/octet-stream')
            filename = f'stealth{cover_ext}'
            
            return send_file(output, mimetype=mimetype, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/stealth/extract", methods=["POST"], strict_slashes=False)
def stealth_extract():
    try:
        from PIL import Image
        from Crypto.Cipher import AES
        from Crypto.Protocol.KDF import PBKDF2
        import io
        import zipfile
        
        stego_file = request.files.get('stego_image')
        password = request.form.get('password', '').strip()
        
        if not stego_file:
            return jsonify({'error': 'Arquivo não fornecido'}), 400
        
        file_data = stego_file.read()
        file_ext = os.path.splitext(stego_file.filename)[1].lower()
        
        data_bytes = None
        
        # Extrair baseado no tipo
        if file_ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']:
            # LSB de imagens
            img = Image.open(io.BytesIO(file_data))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            pixels = list(img.getdata())
            
            bits = []
            for pixel in pixels:
                r, g, b = pixel
                bits.append(str(r & 1))
                bits.append(str(g & 1))
                bits.append(str(b & 1))
            
            bit_string = ''.join(bits)
            data_bytes = bytearray()
            for i in range(0, len(bit_string), 8):
                byte = bit_string[i:i+8]
                if len(byte) == 8:
                    data_bytes.append(int(byte, 2))
        
        else:
            # Buscar MAGIC no final do arquivo
            data_bytes = bytearray(file_data)
        
        # Procurar por MAGIC marker
        magic = b'STLTH'
        magic_index = -1
        
        for i in range(len(data_bytes) - len(magic)):
            if bytes(data_bytes[i:i+len(magic)]) == magic:
                magic_index = i
                break
        
        if magic_index == -1:
            return jsonify({'error': 'Nenhum arquivo escondido encontrado'}), 400
        
        # Extrair header
        header_start = magic_index + len(magic)
        salt = bytes(data_bytes[header_start:header_start+16])
        
        # Verificar se tem senha
        has_password = salt != b'\x00' * 16
        
        if has_password:
            if not password:
                return jsonify({'error': 'Este arquivo requer senha'}), 400
            
            nonce = bytes(data_bytes[header_start+16:header_start+32])
            tag = bytes(data_bytes[header_start+32:header_start+48])
            data_len = int.from_bytes(bytes(data_bytes[header_start+48:header_start+52]), 'big')
            ciphertext = bytes(data_bytes[header_start+52:header_start+52+data_len])
            
            # Descriptografar
            key = PBKDF2(password, salt, dkLen=32)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        else:
            # Sem senha
            data_len = int.from_bytes(bytes(data_bytes[header_start+48:header_start+52]), 'big')
            plaintext = bytes(data_bytes[header_start+52:header_start+52+data_len])
        
        # Extrair ZIP com múltiplos arquivos
        zip_buffer = io.BytesIO(plaintext)
        
        # Se for apenas 1 arquivo, retornar diretamente
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            files = zf.namelist()
            if len(files) == 1:
                filename = files[0]
                file_data = zf.read(filename)
                output = io.BytesIO(file_data)
                output.seek(0)
                response = send_file(output, as_attachment=True, download_name=filename)
                response.headers['X-Filename'] = filename
                return response
            else:
                # Múltiplos arquivos: retornar ZIP
                output = io.BytesIO(plaintext)
                output.seek(0)
                response = send_file(output, as_attachment=True, download_name='extracted_files.zip')
                response.headers['X-Filename'] = 'extracted_files.zip'
                return response
    
    except Exception as e:
        return jsonify({'error': 'Erro ao extrair: senha incorreta ou arquivo inválido'}), 400

@app.route("/censor", methods=["GET"], strict_slashes=False)
def censor():
    try:
        with open('templates/censor.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "<h1>Erro ao carregar Censor</h1>"

@app.route("/social", methods=["GET"], strict_slashes=False)
def social():
    try:
        with open('templates/social.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "<h1>Erro ao carregar Social Preview</h1>"

@app.route("/clean", methods=["GET"], strict_slashes=False)
def clean():
    try:
        with open('templates/clean.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "<h1>Erro ao carregar Clean Reader</h1>"

@app.route("/clean/extract", methods=["POST"], strict_slashes=False)
def clean_extract():
    try:
        import requests
        from bs4 import BeautifulSoup

        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL inválida'})

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        title = None
        clean_html = None

        # Usa o readability-lxml (já é dependência do projeto) para achar o conteúdo
        # principal de verdade - é bem melhor que só pegar <article>/<main>/<body>,
        # que na prática trazia menus, barras laterais e rodapé junto do texto.
        try:
            from readability import Document
            doc = Document(response.text)
            title = doc.title()
            article_soup = BeautifulSoup(doc.summary(), 'html.parser')
            for tag in article_soup.find_all(['script', 'style', 'iframe', 'noscript']):
                tag.decompose()
            for tag in article_soup.find_all(True):
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in ['href', 'src', 'alt']}
            if article_soup.get_text(strip=True):
                clean_html = str(article_soup)
        except Exception:
            clean_html = None

        soup = BeautifulSoup(response.text, 'html.parser')

        if not title:
            title_tag = soup.find('title')
            title = title_tag.get_text() if title_tag else 'Artigo'

        if not clean_html:
            # Fallback para quando o readability não conseguir extrair nada.
            for tag in soup.find_all(['script', 'style', 'iframe', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'button']):
                tag.decompose()
            main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=['content', 'post', 'article', 'entry']) or soup.find('body')
            if main_content:
                for tag in main_content.find_all(True):
                    tag.attrs = {k: v for k, v in tag.attrs.items() if k in ['href', 'src', 'alt']}
                clean_html = str(main_content)
            else:
                clean_html = '<p>Não foi possível extrair o conteúdo</p>'

        text_only = BeautifulSoup(clean_html, 'html.parser').get_text(separator='\n', strip=True)
        if not text_only:
            text_only = 'Não foi possível extrair o conteúdo'

        return jsonify({
            'success': True,
            'title': title,
            'content': clean_html,
            'text': text_only,
            'url': url
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route("/clean/export", methods=["POST"], strict_slashes=False)
def clean_export():
    try:
        data = request.get_json()
        format_type = data.get('format', 'pdf')
        title = data.get('title', 'Artigo')
        content = data.get('content', '')
        
        downloads_dir = str(Path.home() / "Downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        
        filename = f"{title[:50].replace('/', '-')}"
        
        if format_type == 'pdf':
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from bs4 import BeautifulSoup
            
            output_path = os.path.join(downloads_dir, f"{filename}.pdf")
            doc = SimpleDocTemplate(output_path, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=30)
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 0.2*inch))
            
            soup = BeautifulSoup(content, 'html.parser')
            for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'li']):
                text = p.get_text(strip=True)
                if text:
                    story.append(Paragraph(text, styles['BodyText']))
                    story.append(Spacer(1, 0.1*inch))
            
            doc.build(story)
            return jsonify({'success': True, 'filename': f"{filename}.pdf"})
        
        elif format_type == 'markdown':
            from bs4 import BeautifulSoup
            import html2text
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            markdown = h.handle(content)
            
            output_path = os.path.join(downloads_dir, f"{filename}.md")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n{markdown}")
            
            return jsonify({'success': True, 'filename': f"{filename}.md"})
        
        elif format_type == 'epub':
            from ebooklib import epub
            from bs4 import BeautifulSoup
            
            book = epub.EpubBook()
            book.set_title(title)
            book.set_language('pt')
            
            c1 = epub.EpubHtml(title='Conteúdo', file_name='content.xhtml', lang='pt')
            c1.content = f'<html><body><h1>{title}</h1>{content}</body></html>'
            book.add_item(c1)
            
            book.toc = (epub.Link('content.xhtml', title, 'content'),)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ['nav', c1]
            
            output_path = os.path.join(downloads_dir, f"{filename}.epub")
            epub.write_epub(output_path, book)
            
            return jsonify({'success': True, 'filename': f"{filename}.epub"})
        
        return jsonify({'success': False, 'error': 'Formato não suportado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route("/isolate", methods=["GET"], strict_slashes=False)
def isolate():
    try:
        with open('templates/isolate.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "<h1>Erro ao carregar Isolador de Voz</h1>"

@app.route("/isolate/process", methods=["POST"], strict_slashes=False)
def isolate_process():
    temp_dir = None
    try:
        import subprocess
        import sys
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Nenhum arquivo enviado'})
        
        file = request.files['file']
        stem_type = request.form.get('stem', 'vocals')
        
        downloads_dir = str(Path.home() / "Downloads")
        temp_dir = os.path.join(downloads_dir, f'temp_isolate_{int(time.time())}')
        os.makedirs(temp_dir, exist_ok=True)
        
        input_path = os.path.join(temp_dir, file.filename)
        file.save(input_path)
        
        output_dir = os.path.join(temp_dir, 'output')
        python_path = sys.executable
        
        # Executar demucs com backend soundfile
        env = os.environ.copy()
        env['TORCHAUDIO_BACKEND'] = 'soundfile'

        # O demucs só sabe separar em torno de um stem real do modelo (vocals/drums/
        # bass/other). "accompaniment" não existe para ele - por isso sempre separamos
        # por "vocals" (que já gera vocals + no_vocals) e escolhemos qual dos dois
        # arquivos entregar de acordo com o que o usuário pediu.
        # Pedimos saída em --mp3: o demucs grava wav/flac via torchaudio, que em
        # versões recentes exige o pacote opcional torchcodec (com build casada à
        # CUDA da máquina) só para salvar o arquivo; o mp3 usa o encoder lameenc
        # embutido no próprio demucs, sem essa dependência frágil.
        process = subprocess.Popen(
            [python_path, '-m', 'demucs', '--two-stems', 'vocals', '--mp3', '-o', output_dir, input_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )

        output_lines = []
        for line in process.stdout:
            output_lines.append(line.strip())
            if len(output_lines) > 50:
                output_lines.pop(0)

        process.wait()

        if process.returncode != 0:
            error_msg = '\n'.join(output_lines[-10:])
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return jsonify({'success': False, 'error': f'Erro no processamento:\n{error_msg}'})

        base_name = os.path.splitext(file.filename)[0]
        model_folder = os.path.join(output_dir, 'htdemucs', base_name)

        if stem_type == 'vocals':
            output_file = os.path.join(model_folder, 'vocals.mp3')
            final_name = f"{base_name}_voz.mp3"
        else:
            output_file = os.path.join(model_folder, 'no_vocals.mp3')
            final_name = f"{base_name}_instrumental.mp3"
        
        if not os.path.exists(output_file):
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return jsonify({'success': False, 'error': f'Arquivo não encontrado. Esperado: {output_file}'})
        
        final_path = os.path.join(downloads_dir, final_name)
        counter = 1
        while os.path.exists(final_path):
            final_name = f"{base_name}_voz_{counter}.mp3" if stem_type == 'vocals' else f"{base_name}_instrumental_{counter}.mp3"
            final_path = os.path.join(downloads_dir, final_name)
            counter += 1
        
        shutil.move(output_file, final_path)
        
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        return jsonify({'success': True, 'filename': final_name})
    except Exception as e:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        return jsonify({'success': False, 'error': f'Erro: {str(e)}'})

@app.route("/isolate/progress/<task_id>", methods=["GET"], strict_slashes=False)
def isolate_progress(task_id):
    progress_file = os.path.join(str(Path.home() / "Downloads"), f'progress_{task_id}.json')
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({'progress': 0, 'eta': 'Calculando...'})

if __name__ == "__main__":
    # threaded=True: necessário para o polling de progresso (ex.: geração por
    # IA do Matcha Effect) funcionar enquanto o trabalho pesado roda em thread
    # de fundo — sem isso o servidor de desenvolvimento atende 1 requisição
    # por vez e a aba trava esperando a geração terminar.
    app.run(debug=True, threaded=True)
