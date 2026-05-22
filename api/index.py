import os
import time
import subprocess
import tempfile
import certifi
import yt_dlp
import imageio_ffmpeg
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Configure SSL certificates globally for Lambda/macOS
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

@app.route("/")
def index():
    """Serves the static index.html locally."""
    return app.send_static_file("index.html")


def extract_stream_url(video_url):
    """Extract direct video stream URL using yt-dlp."""
    opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if "entries" in info:
                info = info["entries"][0]
            url = info.get("url")
            if url:
                return url
    except Exception as e:
        raise Exception(f"Extraction failed: {e}")
    raise Exception("Could not extract stream URL.")


def slice_video(stream_url, start, end, out_path):
    """Slice the remote stream using imageio-ffmpeg's static binary."""
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_bin, "-y"]

    if start:
        cmd.extend(["-ss", start])
    if end:
        cmd.extend(["-to", end])

    cmd.extend(["-i", stream_url, "-c", "copy", out_path])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.returncode == 0


@app.route("/clip", methods=["POST"])
@app.route("/api/index.py", methods=["POST"])
@app.route("/<path:path>", methods=["POST"])
def clip(path=None):
    """Grab and download a video clip."""
    data = request.json or {}
    url = data.get("url", "").strip()

    # Normalize x.com to twitter.com for yt-dlp compatibility
    if "x.com" in url:
        url = url.replace("x.com", "twitter.com")

    start = data.get("start", "").strip()
    end = data.get("end", "").strip()

    if not url:
        return jsonify({"error": "Missing video URL"}), 400

    try:
        stream_url = extract_stream_url(url)
        if not stream_url:
            return jsonify({"error": "Failed to extract video stream"}), 400

        out_name = f"ClipGrab-video_{int(time.time())}.mp4"
        out_path = os.path.join(tempfile.gettempdir(), out_name)

        if not slice_video(stream_url, start, end, out_path):
            return jsonify({"error": "FFmpeg slice failed. Check your timestamps."}), 500

        return send_file(
            out_path,
            mimetype="video/mp4",
            as_attachment=True,
            download_name=out_name,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    app.run(host="0.0.0.0", port=port)
