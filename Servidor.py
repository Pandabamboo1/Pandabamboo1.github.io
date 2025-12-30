from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Carpeta temporal para descargas
DOWNLOAD_FOLDER = Path("downloads")
DOWNLOAD_FOLDER.mkdir(exist_ok=True)

# Almacenamiento de progreso (en memoria)
download_progress = {}

def cleanup_old_files():
    """Limpia archivos antiguos cada hora"""
    while True:
        try:
            current_time = time.time()
            for file in DOWNLOAD_FOLDER.iterdir():
                if file.is_file():
                    file_age = current_time - file.stat().st_mtime
                    if file_age > 3600:  # Más de 1 hora
                        file.unlink()
        except Exception as e:
            print(f"Error limpiando archivos: {e}")
        time.sleep(3600)  # Cada hora

# Iniciar limpieza automática
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def progress_hook(d, download_id):
    """Hook para actualizar progreso"""
    if d['status'] == 'downloading':
        try:
            percent = d.get('_percent_str', '0%').strip().rstrip('%')
            download_progress[download_id] = {
                'status': 'downloading',
                'percent': float(percent),
                'speed': d.get('_speed_str', 'N/A'),
                'eta': d.get('_eta_str', 'N/A')
            }
        except:
            pass
    elif d['status'] == 'finished':
        download_progress[download_id] = {
            'status': 'processing',
            'percent': 100,
            'message': 'Finalizando...'
        }

@app.route('/api/download', methods=['POST'])
def download_media():
    """Endpoint principal para descargar media"""
    try:
        data = request.json
        url = data.get('url')
        media_type = data.get('type', 'video')
        quality = data.get('quality', 'best')

        if not url:
            return jsonify({'error': 'URL requerida'}), 400

        # Generar ID único para esta descarga
        download_id = str(uuid.uuid4())
        download_progress[download_id] = {'status': 'starting', 'percent': 0}

        # Configurar yt-dlp
        output_template = str(DOWNLOAD_FOLDER / f"{download_id}.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_template,
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'quiet': False,
            'no_warnings': False,
        }

        # Configuración según tipo
        if media_type == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            # SOLUCIÓN AL BUG: Forzar merge de video y audio
            if quality == 'best':
                format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
            else:
                format_str = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
            
            ydl_opts.update({
                'format': format_str,
                'merge_output_format': 'mp4',  # Forzar merge a MP4
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',  # Asegurar MP4 final
                }],
            })

        # Descargar
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Obtener nombre del archivo descargado
            if media_type == 'audio':
                filename = f"{download_id}.mp3"
            else:
                filename = f"{download_id}.mp4"
            
            filepath = DOWNLOAD_FOLDER / filename

            # Verificar que el archivo existe
            if not filepath.exists():
                # Buscar el archivo con cualquier extensión
                possible_files = list(DOWNLOAD_FOLDER.glob(f"{download_id}.*"))
                if possible_files:
                    filepath = possible_files[0]
                else:
                    return jsonify({'error': 'Archivo no encontrado después de descarga'}), 500

            download_progress[download_id] = {
                'status': 'completed',
                'percent': 100,
                'filename': filepath.name,
                'title': info.get('title', 'download')
            }

            return jsonify({
                'success': True,
                'download_id': download_id,
                'filename': filepath.name,
                'title': info.get('title', 'download'),
                'message': '¡Descarga completada!'
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/progress/<download_id>', methods=['GET'])
def get_progress(download_id):
    """Obtener progreso de descarga"""
    progress = download_progress.get(download_id, {'status': 'not_found'})
    return jsonify(progress)

@app.route('/api/file/<filename>', methods=['GET'])
def get_file(filename):
    """Descargar archivo"""
    try:
        filepath = DOWNLOAD_FOLDER / filename
        if filepath.exists():
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename
            )
        return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/info', methods=['POST'])
def get_info():
    """Obtener información del video sin descargar"""
    try:
        data = request.json
        url = data.get('url')

        if not url:
            return jsonify({'error': 'URL requerida'}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                'title': info.get('title'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'uploader': info.get('uploader'),
                'formats': len(info.get('formats', [])),
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'healthy', 'service': 'Media Downloader API'})

if __name__ == '__main__':
    # Para desarrollo local
    app.run(debug=True, host='0.0.0.0', port=5000)