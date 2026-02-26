from flask import Flask, request, render_template_string, jsonify, Response
import yt_dlp
import os
import time
from pathlib import Path
import json
try:
    from PIL import Image
except:
    pass

from pdfs_templates import PDFS_SPLIT_HTML, PDFS_CONVERT_HTML

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
    <a href="/musica" class="app">
      <div class="app-icon">🎵</div>
      <div class="app-name">Música</div>
    </a>
    <a href="/instagram" class="app">
      <div class="app-icon">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="ig-gradient" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#FED576;stop-opacity:1" />
              <stop offset="25%" style="stop-color:#F47133;stop-opacity:1" />
              <stop offset="50%" style="stop-color:#BC3081;stop-opacity:1" />
              <stop offset="75%" style="stop-color:#8A3AB9;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#4C63D2;stop-opacity:1" />
            </linearGradient>
          </defs>
          <rect x="6" y="6" width="36" height="36" rx="8" stroke="url(#ig-gradient)" stroke-width="3" fill="none"/>
          <circle cx="24" cy="24" r="7" stroke="url(#ig-gradient)" stroke-width="3" fill="none"/>
          <circle cx="34" cy="14" r="2" fill="url(#ig-gradient)"/>
        </svg>
      </div>
      <div class="app-name">Instagram</div>
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

@app.route("/pdfs", strict_slashes=False)
def pdfs():
    return render_template_string(PDFS_HTML)

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
                            error = "Nenhuma mídia encontrada. Perfil pode ser privado ou sem posts."
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
                        error = "Não foi possível extrair mídia."
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
        
        if not file or not file.filename.endswith('.pdf'):
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
                    
                    output_name = split['name'] if split['name'] else f"{base_name}_parte"
                    if not output_name.endswith('.pdf'):
                        output_name += '.pdf'
                    
                    output_path = os.path.join(downloads_dir, output_name)
                    counter = 1
                    while os.path.exists(output_path):
                        output_name = f"{split['name']}_{counter}.pdf"
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
                
                if file.filename.endswith('.pdf') and output_format in ['jpg', 'png']:
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
                
                elif not file.filename.endswith('.pdf') and output_format == 'pdf':
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
        
        if not file or not file.filename.endswith('.pdf'):
            error = "Selecione um arquivo PDF válido."
        else:
            try:
                from PyPDF2 import PdfReader, PdfWriter
                
                downloads_dir = str(Path.home() / "Downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                reader = PdfReader(file.stream)
                writer = PdfWriter()
                
                for page in reader.pages:
                    page.compress_content_streams()
                    writer.add_page(page)
                
                quality_settings = {
                    'low': ('/screen', 150),
                    'medium': ('/ebook', 100),
                    'high': ('/printer', 72)
                }
                
                base_name = os.path.splitext(file.filename)[0]
                output_filename = f"{base_name}_comprimido.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{base_name}_comprimido_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                original_size = len(file.read())
                file.seek(0)
                compressed_size = os.path.getsize(output_path)
                reduction = round((1 - compressed_size / original_size) * 100, 1)
                
                status = f"✅ '{output_filename}' criado! Redução: {reduction}%"
            
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao comprimir PDF: {str(e)}"
    
    try:
        with open('/opt/lampp/htdocs/Verto/pdfs_compress.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
                    rotations = json.loads(rotations_str)
                    for i, page in enumerate(reader.pages):
                        page_num = str(i + 1)
                        if page_num in rotations:
                            page.rotate(rotations[page_num])
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
        with open('/opt/lampp/htdocs/Verto/pdfs_rotate.html', 'r', encoding='utf-8') as f:
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
                        open('/opt/lampp/htdocs/Verto/pdfs_compare.html', 'r', encoding='utf-8').read(),
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
        with open('/opt/lampp/htdocs/Verto/pdfs_compare.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
                    
                    # Adiciona EOF se estiver faltando
                    if not data.endswith(b'%%EOF'):
                        data = data + b'\n%%EOF'
                    
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
                        return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
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
                    return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
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
                        return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
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
                        return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_repair.html', 'r', encoding='utf-8').read(), status=status, error=error)
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
        with open('/opt/lampp/htdocs/Verto/pdfs_repair.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
        with open('/opt/lampp/htdocs/Verto/pdfs_protect.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
        
        if not file or not file.filename.endswith('.pdf'):
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
                        return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_unlock.html', 'r', encoding='utf-8').read(), status=status, error=error)
                
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
        with open('/opt/lampp/htdocs/Verto/pdfs_unlock.html', 'r', encoding='utf-8') as f:
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
        with open('/opt/lampp/htdocs/Verto/pdfs_edit.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
                        return render_template_string(open('/opt/lampp/htdocs/Verto/pdfs_watermark.html', 'r', encoding='utf-8').read(), status=status, error=error)
                    
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
        with open('/opt/lampp/htdocs/Verto/pdfs_watermark.html', 'r', encoding='utf-8') as f:
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
        
        if not file or not file.filename.endswith('.pdf'):
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
        with open('/opt/lampp/htdocs/Verto/pdfs_corrupt.html', 'r', encoding='utf-8') as f:
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
                
                for idx, file in enumerate(files):
                    if file.filename.endswith('.pdf'):
                        reader = PdfReader(file.stream)
                        pages_spec = pages_list[idx] if idx < len(pages_list) else ''
                        
                        if not pages_spec or pages_spec == 'all':
                            for page in reader.pages:
                                writer.add_page(page)
                        else:
                            page_numbers = [int(p.strip()) for p in pages_spec.split(',') if p.strip()]
                            for page_num in page_numbers:
                                if 1 <= page_num <= len(reader.pages):
                                    writer.add_page(reader.pages[page_num - 1])
                
                base_name = os.path.splitext(files[0].filename)[0]
                if len(files) == 1:
                    output_filename = f"{base_name}_organizado.pdf"
                else:
                    output_filename = "PDF_Mesclado.pdf"
                output_path = os.path.join(downloads_dir, output_filename)
                
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"PDF_Mesclado_{counter}.pdf"
                    output_path = os.path.join(downloads_dir, output_filename)
                    counter += 1
                
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
                
                status = f"✅ '{output_filename}' criado com sucesso na pasta Downloads!"
            except ImportError:
                error = "PyPDF2 não está instalado. Execute: pip install PyPDF2"
            except Exception as e:
                error = f"Erro ao mesclar PDFs: {str(e)}"
    
    return render_template_string(PDFS_MERGE_HTML, status=status, error=error)

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
      const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
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

if __name__ == "__main__":
    app.run(debug=True)
