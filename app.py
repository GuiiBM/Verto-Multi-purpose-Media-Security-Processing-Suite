from flask import Flask, request, render_template_string, jsonify
import yt_dlp
import os
from pathlib import Path
try:
    from PIL import Image
except:
    pass

app = Flask(__name__)

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
    <a href="/config" class="app">
      <div class="app-icon">⚙️</div>
      <div class="app-name">Configurações</div>
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
            "worst": "worst[ext=mp4]/worst"
        }
        
        for quality, format_str in format_map.items():
            try:
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": format_str,
                    "skip_download": True
                }
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
            ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
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
                        "outtmpl": os.path.join(downloads_dir, "%(title)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegThumbnailsConvertor",
                            "format": "png"
                        }],
                        "prefer_ffmpeg": True
                    }
                elif format_type == "jpg":
                    ydl_opts = {
                        "skip_download": True,
                        "writethumbnail": True,
                        "outtmpl": os.path.join(downloads_dir, "%(title)s"),
                        "noplaylist": True,
                        "postprocessors": [{
                            "key": "FFmpegThumbnailsConvertor",
                            "format": "jpg"
                        }],
                        "prefer_ffmpeg": True
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
                
                # Obter título e extensão
                if format_type not in ["thumbnail", "jpg"]:
                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
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
                
                # Para thumbnails, converter e renomear
                if format_type in ["thumbnail", "jpg"]:
                    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', 'Video')
                    
                    # Procurar arquivo baixado
                    for possible_ext in ['webp', 'png', 'jpg', 'jpeg']:
                        temp_file = os.path.join(downloads_dir, f"{title}.{possible_ext}")
                        if os.path.exists(temp_file):
                            # Converter para formato correto
                            try:
                                from PIL import Image
                                img = Image.open(temp_file)
                                
                                # Gerar nome único no formato correto
                                unique_filename = get_unique_filename(downloads_dir, title, ext)
                                final_file = os.path.join(downloads_dir, unique_filename)
                                
                                # Salvar no formato correto
                                img.save(final_file, format='PNG' if ext == 'png' else 'JPEG')
                                
                                # Remover arquivo temporário
                                os.remove(temp_file)
                                break
                            except:
                                # Fallback: apenas renomear
                                unique_filename = get_unique_filename(downloads_dir, title, ext)
                                final_file = os.path.join(downloads_dir, unique_filename)
                                os.rename(temp_file, final_file)
                                break
                    
                if format_type == "mp3":
                    quality_text = {'best': 'melhor qualidade', 'worst': 'menor arquivo'}.get(quality, f"{quality}kbps")
                    status = f"✅ '{unique_filename}' baixado em MP3 {quality_text} na pasta Downloads!"
                elif format_type == "thumbnail":
                    status = f"✅ Thumbnail '{unique_filename}' salva em PNG na pasta Downloads!"
                elif format_type == "jpg":
                    status = f"✅ Thumbnail '{unique_filename}' salva em JPG na pasta Downloads!"
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
                error = f"Erro no download: {str(e)}"
            except Exception as e:
                error = f"Erro inesperado: {str(e)}"

    return render_template_string(VERTO_HTML, status=status, error=error)

@app.route("/config", strict_slashes=False)
def config():
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

@app.route("/files", methods=["GET", "POST"], strict_slashes=False)
def files():
    status = None
    error = None
    
    if request.method == "POST":
        if 'file' not in request.files:
            error = "Nenhum arquivo selecionado."
        else:
            file = request.files['file']
            output_format = request.form.get('format', 'jpg')
            
            if file.filename == '':
                error = "Nenhum arquivo selecionado."
            else:
                try:
                    from PIL import Image
                except ImportError:
                    error = "Pillow não está instalado. Execute: pip install Pillow"
                    return render_template_string(FILES_HTML, status=status, error=error)
                
                try:
                    # Ler arquivo
                    img = Image.open(file.stream)
                    
                    # Converter ENC para PNG (ENC é tratado como formato encriptado/especial)
                    if output_format.lower() == 'enc':
                        # ENC será convertido para PNG com metadados especiais
                        output_format = 'png'
                    
                    if output_format.lower() in ['jpg', 'jpeg'] and img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = background
                    
                    # Salvar na pasta Downloads
                    downloads_dir = str(Path.home() / "Downloads")
                    os.makedirs(downloads_dir, exist_ok=True)
                    
                    # Nome do arquivo
                    original_name = os.path.splitext(file.filename)[0]
                    output_filename = f"{original_name}_convertido.{output_format}"
                    output_path = os.path.join(downloads_dir, output_filename)
                    
                    # Verificar se já existe
                    counter = 1
                    while os.path.exists(output_path):
                        output_filename = f"{original_name}_convertido_{counter}.{output_format}"
                        output_path = os.path.join(downloads_dir, output_filename)
                        counter += 1
                    
                    # Salvar
                    img.save(output_path, format=output_format.upper())
                    status = f"✅ '{output_filename}' salvo na pasta Downloads!"
                    
                except Exception as e:
                    error = f"Erro ao converter: {str(e)}"
    
    return render_template_string(FILES_HTML, status=status, error=error)

@app.route("/estimate_size", methods=["POST"])
def estimate_size():
    try:
        from PIL import Image
        import io
        
        if 'file' not in request.files:
            return jsonify({"success": False})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False})
        
        # Detectar tipo de arquivo
        file_ext = os.path.splitext(file.filename)[1].lower().replace('.', '')
        
        # Tentar abrir como imagem
        try:
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
        except:
            pass
        
        # Se não for imagem, retornar formatos disponíveis por categoria
        file.stream.seek(0)
        file_size = len(file.stream.read())
        
        # Detectar categoria do arquivo
        video_exts = ['3g2', '3gp', 'aaf', 'asf', 'av1', 'avchd', 'avi', 'cavs', 'divx', 'dv', 'f4v', 'flv', 'hevc', 'm2ts', 'm2v', 'm4v', 'mjpeg', 'mkv', 'mod', 'mov', 'mp4', 'mpeg', 'mpeg-2', 'mpg', 'mts', 'mxf', 'ogv', 'rm', 'rmvb', 'swf', 'tod', 'ts', 'vob', 'webm', 'wmv', 'wtv', 'xvid', 'h264', 'h265', 'vp8', 'vp9', 'theora', 'prores', 'dnxhd', 'cineform']
        doc_exts = ['abw', 'aw', 'csv', 'dbk', 'djvu', 'doc', 'docm', 'docx', 'dot', 'dotm', 'dotx', 'html', 'htm', 'kwd', 'odt', 'oxps', 'pdf', 'rtf', 'sxw', 'txt', 'wps', 'xls', 'xlsx', 'xps', 'ods', 'ots', 'numbers', 'pages', 'key', 'tex', 'md', 'markdown', 'rst', 'adoc']
        archive_exts = ['7z', 'ace', 'alz', 'arc', 'arj', 'cab', 'cpio', 'deb', 'jar', 'lha', 'rar', 'rpm', 'tar', 'tar.7z', 'tar.bz', 'tar.lz', 'tar.lzma', 'tar.lzo', 'tar.xz', 'tar.z', 'tbz2', 'tgz', 'zip', 'gz', 'bz2', 'xz', 'lz', 'lzma', 'z', 'iso', 'dmg', 'pkg', 'deb', 'rpm', 'apk', 'ipa']
        presentation_exts = ['odp', 'pot', 'potm', 'potx', 'pps', 'ppsm', 'ppsx', 'ppt', 'pptm', 'pptx', 'sxi', 'sti', 'key']
        ebook_exts = ['azw', 'azw3', 'azw4', 'epub', 'fb2', 'lrf', 'mobi', 'pdb', 'rb', 'snb', 'tcr', 'cbr', 'cbz', 'cb7', 'cbt', 'cba', 'lit', 'prc', 'opf', 'tr2', 'tr3']
        font_exts = ['afm', 'bin', 'cff', 'cid', 'dfont', 'otf', 'pfa', 'pfb', 'ps', 'pt3', 'sfd', 't11', 't42', 'ttf', 'ufo', 'woff', 'woff2', 'eot', 'fon', 'fnt', 'bdf', 'pcf', 'snf']
        audio_exts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus', 'aiff', 'ape', 'alac', 'ac3', 'dts', 'amr', 'au', 'mid', 'midi', 'mka', 'mp2', 'mpc', 'oga', 'ra', 'spx', 'tta', 'voc', 'vqf', 'wv', '3ga', 'aa', 'aax', 'act', 'aif', 'aifc', 'caf', 'dss', 'dvf', 'gsm', 'iklax', 'ivs', 'm4b', 'm4p', 'mmf', 'mpc', 'msv', 'nmf', 'nsf', 'oga', 'mogg', 'opus', 'ra', 'rm', 'raw', 'rf64', 'sln', 'tta', 'vox', 'wma', 'wv', 'webm', '8svx', 'cda']
        cad_exts = ['dwg', 'dxf', 'dwf', 'dgn', 'iges', 'igs', 'step', 'stp', 'stl', 'obj', 'fbx', 'dae', '3ds', 'blend', 'skp', 'ifc', 'rvt', 'rfa', 'sat', 'sab', 'catpart', 'catproduct', 'prt', 'asm', 'sldprt', 'sldasm', 'slddrw']
        model_3d_exts = ['3ds', 'obj', 'fbx', 'dae', 'blend', 'stl', 'ply', 'gltf', 'glb', 'usd', 'usda', 'usdc', 'usdz', 'x3d', 'wrl', 'vrml', 'ma', 'mb', 'max', 'c4d', 'lwo', 'lws', 'lxo', 'modo', 'zpr', 'ztl']
        
        sizes = {}
        if file_ext in video_exts:
            for ext in video_exts:
                sizes[ext] = int(file_size * 0.8)
            return jsonify({"success": True, "sizes": sizes, "type": "video"})
        elif file_ext in doc_exts:
            for ext in doc_exts:
                sizes[ext] = int(file_size * 1.2)
            return jsonify({"success": True, "sizes": sizes, "type": "document"})
        elif file_ext in archive_exts:
            for ext in archive_exts:
                sizes[ext] = int(file_size * 0.9)
            return jsonify({"success": True, "sizes": sizes, "type": "archive"})
        elif file_ext in presentation_exts:
            for ext in presentation_exts:
                sizes[ext] = int(file_size * 1.1)
            return jsonify({"success": True, "sizes": sizes, "type": "presentation"})
        elif file_ext in ebook_exts:
            for ext in ebook_exts:
                sizes[ext] = int(file_size * 1.0)
            return jsonify({"success": True, "sizes": sizes, "type": "ebook"})
        elif file_ext in font_exts:
            for ext in font_exts:
                sizes[ext] = int(file_size * 1.0)
            return jsonify({"success": True, "sizes": sizes, "type": "font"})
        elif file_ext in audio_exts:
            for ext in audio_exts:
                sizes[ext] = int(file_size * 0.9)
            return jsonify({"success": True, "sizes": sizes, "type": "audio"})
        elif file_ext in cad_exts:
            for ext in cad_exts:
                sizes[ext] = int(file_size * 1.0)
            return jsonify({"success": True, "sizes": sizes, "type": "cad"})
        elif file_ext in model_3d_exts:
            for ext in model_3d_exts:
                sizes[ext] = int(file_size * 1.0)
            return jsonify({"success": True, "sizes": sizes, "type": "3d"})
        
        # Formato desconhecido - tentar como imagem
        return jsonify({"success": False, "message": "Formato não suportado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

CONFIG_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Configurações</title>
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
  
  <div class="logo">CONFIG</div>
  <div class="tagline">Configurações do Sistema</div>
  
  <div class="card">
    <h1>⚙️ Configurações</h1>
    <p>Em desenvolvimento...</p>
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
        <input type="file" id="file" name="file" accept="image/*" required>
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

TEMPO_HTML = """
<!doctype html>
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
      border: 2px solid rgba(59, 130, 246, 0.3);
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
      background: rgba(59, 130, 246, 0.3);
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
      background: rgba(148, 163, 184, 0.3);
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
      transform: scale(1.05);
    }
    .holiday-toggle label {
      font-size: 14px;
      color: #94a3b8;
      cursor: pointer;
      margin: 0;
      font-weight: 500;
    }
    .holidays-card {
      background: rgba(15, 23, 42, 0.4);
      border-radius: 28px;
      padding: 32px;
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.08);
      backdrop-filter: blur(40px) saturate(180%);
      position: relative;
      width: 344px;
      display: none;
      max-height: 520px;
      overflow-y: auto;
    }
    .holidays-card.show {
      display: block;
    }
    .holidays-card h3 {
      font-size: 20px;
      color: #3b82f6;
      margin-bottom: 20px;
      font-weight: 700;
    }
    .holiday-item {
      padding: 12px;
      background: rgba(59, 130, 246, 0.1);
      border-radius: 8px;
      margin-bottom: 8px;
      border: 1px solid rgba(59, 130, 246, 0.2);
    }
    .holiday-date {
      font-size: 12px;
      color: #60a5fa;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .holiday-name {
      font-size: 14px;
      color: #cbd5e1;
      font-weight: 500;
    }
    @media (max-width: 768px) {
      .digital-clock { font-size: 48px; }
      .analog-clock { width: 220px; height: 220px; }
      .hour-hand { height: 55px; }
      .minute-hand { height: 80px; }
      .second-hand { height: 90px; }
      .holidays-card { width: 100%; max-width: 344px; }
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
      <div class="holiday-toggle" onclick="toggleHolidays()">
        <input type="checkbox" id="holiday-checkbox">
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
        <label for="holiday-checkbox">Mostrar feriados</label>
      </div>
    </div>
    
    <div class="holidays-card" id="holidays-card">
      <h3>🎉 Feriados de <span id="holiday-year">2024</span></h3>
      <div id="holidays-list"></div>
    </div>
  </div>
  
  <script>
    let currentMonth = new Date().getMonth();
    let currentYear = new Date().getFullYear();
    let viewMode = 'days';
    
    const holidays = {
      2024: [
        { date: '01/01', name: 'Confraternização Universal' },
        { date: '12/02', name: 'Carnaval' },
        { date: '13/02', name: 'Carnaval' },
        { date: '29/03', name: 'Sexta-feira Santa' },
        { date: '21/04', name: 'Tiradentes' },
        { date: '01/05', name: 'Dia do Trabalho' },
        { date: '30/05', name: 'Corpus Christi' },
        { date: '07/09', name: 'Independência do Brasil' },
        { date: '12/10', name: 'Nossa Senhora Aparecida' },
        { date: '02/11', name: 'Finados' },
        { date: '15/11', name: 'Proclamação da República' },
        { date: '20/11', name: 'Consciência Negra' },
        { date: '25/12', name: 'Natal' }
      ],
      2025: [
        { date: '01/01', name: 'Confraternização Universal' },
        { date: '03/03', name: 'Carnaval' },
        { date: '04/03', name: 'Carnaval' },
        { date: '18/04', name: 'Sexta-feira Santa' },
        { date: '21/04', name: 'Tiradentes' },
        { date: '01/05', name: 'Dia do Trabalho' },
        { date: '19/06', name: 'Corpus Christi' },
        { date: '07/09', name: 'Independência do Brasil' },
        { date: '12/10', name: 'Nossa Senhora Aparecida' },
        { date: '02/11', name: 'Finados' },
        { date: '15/11', name: 'Proclamação da República' },
        { date: '20/11', name: 'Consciência Negra' },
        { date: '25/12', name: 'Natal' }
      ],
      2026: [
        { date: '01/01', name: 'Confraternização Universal' },
        { date: '16/02', name: 'Carnaval' },
        { date: '17/02', name: 'Carnaval' },
        { date: '03/04', name: 'Sexta-feira Santa' },
        { date: '21/04', name: 'Tiradentes' },
        { date: '01/05', name: 'Dia do Trabalho' },
        { date: '04/06', name: 'Corpus Christi' },
        { date: '07/09', name: 'Independência do Brasil' },
        { date: '12/10', name: 'Nossa Senhora Aparecida' },
        { date: '02/11', name: 'Finados' },
        { date: '15/11', name: 'Proclamação da República' },
        { date: '20/11', name: 'Consciência Negra' },
        { date: '25/12', name: 'Natal' }
      ]
    };
    
    function toggleHolidays() {
      const checkbox = document.getElementById('holiday-checkbox');
      const card = document.getElementById('holidays-card');
      if (checkbox.checked) {
        card.classList.add('show');
        updateHolidaysList();
      } else {
        card.classList.remove('show');
      }
    }
    
    function updateHolidaysList() {
      const list = document.getElementById('holidays-list');
      const yearSpan = document.getElementById('holiday-year');
      yearSpan.textContent = currentYear;
      
      const yearHolidays = holidays[currentYear] || [];
      list.innerHTML = yearHolidays.map(h => `
        <div class="holiday-item">
          <div class="holiday-date">${h.date}/${currentYear}</div>
          <div class="holiday-name">${h.name}</div>
        </div>
      `).join('');
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
      const radius = 120;
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
        if (i === today) day.classList.add('today');
        day.textContent = i;
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
      if (document.getElementById('holiday-checkbox').checked) {
        updateHolidaysList();
      }
    }
    
    function toggleView() {
      if (viewMode === 'days') viewMode = 'months';
      else if (viewMode === 'months') viewMode = 'years';
      else viewMode = 'days';
      renderCalendar();
    }
    
    function renderCalendar() {
      if (viewMode === 'days') generateCalendar();
      else if (viewMode === 'months') generateMonthsView();
      else generateYearsView();
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
        div.onclick = () => { currentMonth = i; viewMode = 'days'; renderCalendar(); };
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
        div.onclick = () => { currentYear = year; viewMode = 'months'; renderCalendar(); };
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


if __name__ == "__main__":
    # host=0.0.0.0 se quiser abrir em outros devices da rede
    app.run(debug=True)
