# Sumber video booth v3 (tema gelap, konsep utama baru)

Video ±92 detik, 1920 × 1080, 30 fps. Setiap adegan dirender frame demi frame dengan Playwright + Three.js, lalu dikodekan dengan ffmpeg.

```bash
npm install                      # three, playwright
node record.js                   # semua adegan -> out/scenes/*.mp4
node record.js 09_hardware       # satu adegan saja
node peek.js '[["03_live_gradcam",4]]' /tmp   # pratinjau satu frame
```

Gabungkan adegan dengan `ffmpeg -f concat -safe 0 -i list.txt -c copy video.mp4`, lalu tambahkan musik dengan `-c:v copy`.

- `assets/music.mp3` (Pixabay) **tidak disimpan di repo**; letakkan sendiri sebelum menggabungkan.
- `assets/airlens_node_concept.glb` dan `airlens_beta.glb` adalah salinan dari `web/static/product/models/`.

Yang masih placeholder dan diisi di tahap akhir:
- adegan 12: rekaman layar website;
- adegan 14: QR code ke alamat ngrok.
