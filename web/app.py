from flask import Flask, request, jsonify, send_from_directory
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)

def download_video(url, quality):
    downloads_dir = "downloads"
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
        return title

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url", "").strip()
    quality = data.get("quality", "best")
    
    if not url:
        return jsonify({"success": False, "error": "Insira uma URL válida."})
    
    try:
        title = download_video(url, quality)
        quality_text = {"best": "melhor qualidade", "1080p": "1080p", "720p": "720p", "480p": "480p", "360p": "360p"}.get(quality, quality)
        return jsonify({"success": True, "message": f"✅ '{title}' baixado em {quality_text}!"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Erro no download: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True)