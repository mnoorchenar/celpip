# Installation Guide — CELPIP Practice Studio

## 1. Python packages (one command)

```
pip install flask pillow numpy scipy pydub edge-tts kokoro-onnx soundfile huggingface_hub
```

---

## 2. FFmpeg (required — not a Python package)

**Download from:** https://ffmpeg.org/download.html

- **Windows:** Download a pre-built binary from https://www.gyan.dev/ffmpeg/builds/
  - Grab the **ffmpeg-release-essentials.zip**
  - Extract it, then add the `bin` folder to your system **PATH**
  - Test: open a terminal and run `ffmpeg -version`

- **Mac:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

---

## 3. Python itself

**Version required:** Python 3.10 or newer (3.11 recommended)

**Download from:** https://www.python.org/downloads/

---

## 4. Notes

- **Kokoro TTS model files** (~130 MB) are downloaded automatically on first use from GitHub. No manual download needed.
- **edge-tts** requires an internet connection each time it's used (it streams from Microsoft servers). It's only used for shadowing practice audio, not for video generation.
- No GPU required — everything runs on CPU.
