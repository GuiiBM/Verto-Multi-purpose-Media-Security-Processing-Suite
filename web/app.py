from flask import Flask, request, jsonify, send_from_directory
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)

def download_video(url, format_type, quality):
    downloads_dir = "downloads"
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

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url", "").strip()
    format_type = data.get("format", "mp4")
    quality = data.get("quality", "best")
    
    if not url:
        return jsonify({"success": False, "error": "Insira uma URL válida."})
    
    try:
        title = download_video(url, format_type, quality)
        if format_type == "mp3":
            quality_text = {'best': 'melhor qualidade', 'worst': 'menor arquivo'}.get(quality, f"{quality}kbps")
            return jsonify({"success": True, "message": f"✅ '{title}' baixado em MP3 {quality_text}!"})
        elif format_type == "thumbnail":
            return jsonify({"success": True, "message": f"✅ Thumbnail de '{title}' salva em PNG!"})
        elif format_type == "jpg":
            return jsonify({"success": True, "message": f"✅ Thumbnail de '{title}' salva em JPG!"})
        else:
            quality_text = {"best": "melhor qualidade", "1080p": "1080p", "720p": "720p", "480p": "480p", "360p": "360p"}.get(quality, quality)
            return jsonify({"success": True, "message": f"✅ '{title}' baixado em {quality_text}!"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Erro no download: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True)