from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Carpeta temporal para descargas
DOWNLOAD_FOLDER = Path("downloads")
DOWNLOAD_FOLDER.mkdir(exist_ok=True)

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'healthy', 'service': 'Media Downloader API'})

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

        # Generar ID único
        download_id = str(uuid.uuid4())
        output_template = str(DOWNLOAD_FOLDER / f"{download_id}.%(ext)s")
        
        # Configurar yt-dlp
        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
        }

        # Configuración según tipo
        if media_type == 'audio':
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        else:
            if quality == 'best':
                ydl_opts['format'] = 'best[ext=mp4]/best'
            else:
                ydl_opts['format'] = f'best[height<={quality}][ext=mp4]/best[height<={quality}]'

        # Descargar
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Buscar el archivo descargado
            possible_files = list(DOWNLOAD_FOLDER.glob(f"{download_id}.*"))
            if not possible_files:
                return jsonify({'error': 'Archivo no encontrado'}), 500
            
            filepath = possible_files[0]

            return jsonify({
                'success': True,
                'download_id': download_id,
                'filename': filepath.name,
                'title': info.get('title', 'download'),
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<filename>', methods=['GET'])
def get_file(filename):
    """Descargar archivo"""
    try:
        filepath = DOWNLOAD_FOLDER / filename
        if filepath.exists():
            return send_file(filepath, as_attachment=True, download_name=filename)
        return jsonify({'error': 'Archivo no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)