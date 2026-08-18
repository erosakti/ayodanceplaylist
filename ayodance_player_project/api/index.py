from flask import Flask, Response, jsonify, render_template, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__, template_folder='../templates')
BASE_CDN = "http://122.102.49.131/audition/ABM/"

# Kamus Judul Lagu (Bisa Anda tambah sendiri nanti)
KNOWN_SONGS = {
    "b0000.tbm": "Audition - BGM Intro Default",
    "b0001.tbm": "Audition - Let's Dance",
    "b0002.tbm": "Audition - Euro 2005",
    "k0093.tbm": "Epik High - Fly"
}

def strip_tbm_header(raw_data):
    # Cari struktur OGG
    pos = raw_data.find(b"OggS")
    if pos != -1:
        return raw_data[pos:], "audio/ogg"
    
    # Cari struktur MP3 (ID3)
    pos = raw_data.find(b"ID3")
    if pos != -1:
        return raw_data[pos:], "audio/mpeg"
        
    # Cari struktur MP3 murni
    for sync in [b"\xff\xfb", b"\xff\xfa", b"\xff\xf3", b"\xff\xf2"]:
        pos = raw_data.find(sync)
        if pos != -1:
            return raw_data[pos:], "audio/mpeg"
            
    return raw_data, "audio/mpeg"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/playlist")
def get_playlist():
    try:
        res = requests.get(BASE_CDN, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            dynamic_playlist = []
            
            for a in soup.find_all("a"):
                href = a.get("href")
                if href and href.endswith(".tbm"):
                    filename = href.split("/")[-1]
                    title = KNOWN_SONGS.get(filename, f"Track ({filename})")
                    
                    dynamic_playlist.append({
                        "id": filename,
                        "title": title,
                        "bpm": "-",
                    })
            if dynamic_playlist:
                return jsonify(dynamic_playlist)
    except Exception as e:
        print("Error scraping:", e)
    
    return jsonify([{"id": "error", "title": "Gagal memuat server", "bpm": "-"}])

@app.route("/stream/<filename>")
def stream_audio(filename):
    url = BASE_CDN + filename
    try:
        # Download file dari IP server
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            return "File tidak ditemukan", 404
            
        # Potong Header TBM
        audio_clean, mime_type = strip_tbm_header(res.content)
        file_size = len(audio_clean)
        
        # === LOGIKA PARTIAL CONTENT (HTTP 206) ===
        range_header = request.headers.get('Range', None)
        
        if not range_header:
            # Jika browser tidak meminta Range, kirim seluruhnya
            response = Response(audio_clean, 200, mimetype=mime_type)
            response.headers.add('Content-Length', str(file_size))
            response.headers.add('Accept-Ranges', 'bytes')
            return response
            
        # Jika browser meminta potongan/chunk audio (seperti saat awal play atau di-seek)
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            byte1, byte2 = match.groups()
            byte1 = int(byte1)
            byte2 = int(byte2) if byte2 else file_size - 1
            
            length = byte2 - byte1 + 1
            data = audio_clean[byte1:byte2+1]
            
            response = Response(data, 206, mimetype=mime_type)
            response.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            response.headers.add('Accept-Ranges', 'bytes')
            response.headers.add('Content-Length', str(length))
            return response
            
    except Exception as e:
        return str(e), 500