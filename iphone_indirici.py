"""
YouTube İndirici — iPhone sürümü (a-Shell için)

Kurulum (a-Shell içinde bir kez):
    pip install yt-dlp

Kullanım:
    python3 iphone_indirici.py                 -> link ve format sorar
    python3 iphone_indirici.py <link>          -> en iyi kalite video
    python3 iphone_indirici.py <link> ses      -> sadece ses
    python3 iphone_indirici.py <link> 720      -> en fazla 720p video

Dosyalar a-Shell'in Documents klasörüne kaydedilir.
"Dosyalar" uygulaması > a-Shell klasöründen erişebilirsin.
"""

import os
import shutil
import sys

try:
    import yt_dlp
except ImportError:
    print("yt-dlp kurulu değil. Önce şunu çalıştır:\n    pip install yt-dlp")
    sys.exit(1)

KLASOR = os.path.expanduser("~/Documents/YouTube")
FFMPEG = shutil.which("ffmpeg") is not None


def ilerleme(d):
    if d["status"] == "downloading":
        toplam = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        inen = d.get("downloaded_bytes", 0)
        yuzde = inen / toplam * 100 if toplam else 0
        print(f"\rİndiriliyor: %{yuzde:5.1f}", end="", flush=True)
    elif d["status"] == "finished":
        print("\rİndirme bitti, dosya hazırlanıyor…      ")


def ayarlar(secim):
    opts = {
        "outtmpl": os.path.join(KLASOR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [ilerleme],
        "quiet": True,
        "no_warnings": True,
        "windowsfilenames": True,
    }
    if secim == "ses":
        if FFMPEG:
            opts["format"] = "ba/b"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        else:
            opts["format"] = "ba[ext=m4a]/ba/b"
        return opts

    sinir = int(secim) if secim.isdigit() else None
    if FFMPEG:
        opts["format"] = f"bv*[height<={sinir}]+ba/b[height<={sinir}]/b" if sinir else "bv*+ba/b"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = f"b[height<={sinir}][ext=mp4]/b[height<={sinir}]/b" if sinir else "b[ext=mp4]/b"
    return opts


def main():
    args = sys.argv[1:]
    url = args[0] if args else input("YouTube linki: ").strip()
    if not url:
        print("Link girilmedi.")
        return

    if len(args) > 1:
        secim = args[1].lower()
    elif args:
        secim = "en-iyi"
    else:
        print("1) En iyi video  2) 720p  3) 480p  4) Sadece ses")
        secim = {"1": "en-iyi", "2": "720", "3": "480", "4": "ses"}.get(input("Seçim [1]: ").strip(), "en-iyi")

    os.makedirs(KLASOR, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(ayarlar(secim)) as ydl:
            ydl.download([url])
        print(f"Tamamlandı! Dosya: Dosyalar > a-Shell > YouTube")
    except yt_dlp.utils.DownloadError as e:
        print("Hata:", str(e).replace("ERROR: ", ""))


if __name__ == "__main__":
    main()
