"""
Video İndirici — Web uygulaması (Flask + yt-dlp)
iPhone'da Safari'den açılır, "Ana Ekrana Ekle" ile uygulama gibi kurulur.
İndirilen videolar uygulamanın İÇİNDE saklanır (tarayıcı veritabanı / IndexedDB)
ve internet olmadan da "İndirilenler" sekmesinden izlenebilir.

Yerelde deneme:
    pip install -r requirements.txt
    python app.py            -> http://localhost:5000
"""

import os
import shutil
import tempfile
import threading
import time
import uuid

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_file

import yt_dlp

app = Flask(__name__)
KOK = os.path.dirname(os.path.abspath(__file__))

SIFRE = os.environ.get("APP_SIFRE", "")   # isteğe bağlı erişim şifresi
FFMPEG = shutil.which("ffmpeg") is not None
GECICI = tempfile.mkdtemp(prefix="vidweb_")
MAKS_SURE_SN = 60 * 60                     # 1 saatten uzun videolar reddedilir

ISLER = {}
KILIT = threading.Lock()


def is_guncelle(is_id, **alanlar):
    with KILIT:
        if is_id in ISLER:
            ISLER[is_id].update(alanlar)


def format_sec(secim):
    """iPhone'da oynatılabilen biçimler: H.264 (avc1) video + AAC (m4a) ses, mp4 kabında."""
    if secim == "ses":
        if FFMPEG:
            return "ba[ext=m4a]/ba/b", [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
        return "ba[ext=m4a]/b[ext=mp4]", []
    sinir = int(secim) if secim.isdigit() else 1080
    h = f"[height<={sinir}]"
    if FFMPEG:
        return f"bv*[vcodec^=avc1]{h}+ba[ext=m4a]/b[ext=mp4]{h}/b[ext=mp4]", []
    return f"b[ext=mp4]{h}/b[ext=mp4]", []


def indir(is_id, url, secim):
    klasor = os.path.join(GECICI, is_id)
    os.makedirs(klasor, exist_ok=True)

    def kanca(d):
        if d["status"] == "downloading":
            toplam = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            yuzde = d.get("downloaded_bytes", 0) / toplam * 100 if toplam else 0
            is_guncelle(is_id, yuzde=round(yuzde, 1), mesaj="Sunucuya indiriliyor…")
        elif d["status"] == "finished":
            is_guncelle(is_id, yuzde=100, mesaj="Dosya hazırlanıyor…")

    def sure_filtresi(info, *, incomplete):
        sure = info.get("duration")
        if sure and sure > MAKS_SURE_SN:
            return "Video 1 saatten uzun."
        return None

    fmt, islemciler = format_sec(secim)
    opts = {
        "format": fmt,
        "postprocessors": islemciler,
        "outtmpl": os.path.join(klasor, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [kanca],
        "match_filter": sure_filtresi,
        "quiet": True,
        "no_warnings": True,
        "windowsfilenames": True,
    }
    if FFMPEG and secim != "ses":
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            bilgi = ydl.extract_info(url, download=True)
        dosyalar = [f for f in os.listdir(klasor) if not f.endswith((".part", ".ytdl"))]
        if not dosyalar:
            raise RuntimeError("Video indirilemedi (1 saatten uzun olabilir).")
        ad = dosyalar[0]
        is_guncelle(
            is_id,
            durum="hazir",
            mesaj="Uygulamaya kaydediliyor…",
            dosya=os.path.join(klasor, ad),
            ad=ad,
            baslik=(bilgi or {}).get("title") or os.path.splitext(ad)[0],
            sure=(bilgi or {}).get("duration"),
            kapak=(bilgi or {}).get("thumbnail"),
        )
    except Exception as e:
        mesaj = str(e).replace("ERROR: ", "")
        if "Sign in to confirm" in mesaj or "bot" in mesaj.lower():
            mesaj = "YouTube bu sunucuyu engelledi (bot kontrolü). Uygulamayı evdeki bilgisayarda çalıştırmayı deneyin."
        is_guncelle(is_id, durum="hata", mesaj=mesaj[:300])


def is_sil(is_id):
    with KILIT:
        ISLER.pop(is_id, None)
    shutil.rmtree(os.path.join(GECICI, is_id), ignore_errors=True)


def temizleyici():
    """Telefona aktarılmamış dosyaları 30 dakika sonra siler."""
    while True:
        time.sleep(300)
        simdi = time.time()
        with KILIT:
            eskiler = [k for k, v in ISLER.items() if simdi - v["zaman"] > 1800]
        for k in eskiler:
            is_sil(k)


threading.Thread(target=temizleyici, daemon=True).start()


def sifre_kontrol():
    if SIFRE and request.values.get("sifre", "") != SIFRE:
        abort(403)


# ---------------- Sayfalar ve uygulama dosyaları ----------------

@app.get("/")
def ana_sayfa():
    return render_template_string(SAYFA, sifre_gerekli=bool(SIFRE))


@app.get("/manifest.webmanifest")
def manifest():
    return jsonify(
        name="Video İndirici",
        short_name="İndirici",
        start_url="/",
        display="standalone",
        background_color="#f4f4f6",
        theme_color="#14466e",
        icons=[
            {"src": "/icon.png", "sizes": "180x180", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    )


@app.get("/icon.png")
def ikon():
    return send_file(os.path.join(KOK, "icon.png"), mimetype="image/png")


@app.get("/icon-512.png")
def ikon_buyuk():
    return send_file(os.path.join(KOK, "icon-512.png"), mimetype="image/png")


@app.get("/sw.js")
def service_worker():
    # Uygulama kabuğunu önbelleğe alır: internet yokken de açılır, İndirilenler izlenir.
    js = """
const ONBELLEK = "indirici-v2";
const DOSYALAR = ["/", "/icon.png", "/manifest.webmanifest"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(ONBELLEK).then(c => c.addAll(DOSYALAR)));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== ONBELLEK).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || !DOSYALAR.includes(u.pathname)) return;
  // Önce ağ, olmazsa önbellek
  e.respondWith(
    fetch(e.request).then(r => { const k = r.clone(); caches.open(ONBELLEK).then(c => c.put(e.request, k)); return r; })
      .catch(() => caches.match(e.request))
  );
});
"""
    return Response(js, mimetype="application/javascript", headers={"Cache-Control": "no-cache"})


# ---------------- API ----------------

@app.post("/baslat")
def baslat():
    sifre_kontrol()
    url = (request.form.get("url") or "").strip()
    secim = request.form.get("format", "720")
    if not url.startswith(("http://", "https://")):
        return jsonify(hata="Geçerli bir link girin."), 400
    if secim not in {"1080", "720", "480", "ses"}:
        secim = "720"
    is_id = uuid.uuid4().hex
    with KILIT:
        ISLER[is_id] = {"durum": "calisiyor", "yuzde": 0, "mesaj": "Başlatılıyor…", "dosya": None,
                        "ad": None, "baslik": None, "sure": None, "kapak": None, "zaman": time.time()}
    threading.Thread(target=indir, args=(is_id, url, secim), daemon=True).start()
    return jsonify(id=is_id)


@app.get("/durum/<is_id>")
def durum(is_id):
    with KILIT:
        isim = ISLER.get(is_id)
        if not isim:
            return jsonify(durum="hata", mesaj="İş bulunamadı."), 404
        return jsonify({k: isim[k] for k in ("durum", "yuzde", "mesaj", "ad", "baslik", "sure")})


@app.get("/dosya/<is_id>")
def dosya(is_id):
    with KILIT:
        isim = ISLER.get(is_id)
    if not isim or isim["durum"] != "hazir":
        abort(404)
    return send_file(isim["dosya"], as_attachment=False, download_name=isim["ad"])


@app.post("/bitti/<is_id>")
def bitti(is_id):
    """Telefon dosyayı kaydettikten sonra sunucudaki kopya silinir."""
    is_sil(is_id)
    return jsonify(ok=True)


SAYFA = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="İndirici">
<meta name="theme-color" content="#14466e">
<link rel="apple-touch-icon" href="/icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<title>Video İndirici</title>
<style>
  :root { --bg:#f2f2f7; --kart:#fff; --yazi:#1c1c1e; --soluk:#6e6e73; --vurgu:#1f6fb2; --yesil:#248a3d;
          --kirmizi:#d70015; --cizgi:#e3e3e8; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#000; --kart:#1c1c1e; --yazi:#f2f2f7; --soluk:#98989f; --vurgu:#4a9fe6; --yesil:#30d158;
            --kirmizi:#ff453a; --cizgi:#38383a; }
  }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html, body { margin:0; background:var(--bg); color:var(--yazi);
    font:17px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  main { max-width:520px; margin:0 auto;
    padding:max(16px, env(safe-area-inset-top)) 16px calc(96px + env(safe-area-inset-bottom)); }
  h1 { font-size:32px; margin:12px 4px 16px; letter-spacing:-.02em; }
  .kart { background:var(--kart); border-radius:16px; padding:16px; }
  label { display:block; font-size:13px; color:var(--soluk); margin:0 4px 6px; text-transform:uppercase; letter-spacing:.03em; }
  input, select { width:100%; font-size:17px; padding:12px; border-radius:10px; border:1px solid var(--cizgi);
    background:var(--bg); color:var(--yazi); margin-bottom:14px; -webkit-appearance:none; appearance:none; }
  .satir { display:flex; gap:8px; } .satir input { flex:1; min-width:0; }
  button { font:inherit; font-weight:600; border:0; border-radius:12px; padding:14px; cursor:pointer; }
  .ana { background:var(--vurgu); color:#fff; width:100%; } .ana:disabled { opacity:.5; }
  .ikinci { background:var(--bg); color:var(--vurgu); padding:12px 14px; margin-bottom:14px; }
  .cubuk { height:8px; background:var(--cizgi); border-radius:4px; overflow:hidden; margin:18px 0 8px; display:none; }
  .cubuk div { height:100%; width:0; background:var(--vurgu); transition:width .3s; }
  #durum { color:var(--soluk); font-size:15px; min-height:1.4em; margin:8px 4px 0; overflow-wrap:anywhere; }
  .not { color:var(--soluk); font-size:13px; margin:14px 6px 0; }

  /* İndirilenler */
  .bos { text-align:center; color:var(--soluk); padding:48px 16px; }
  .liste { display:flex; flex-direction:column; gap:10px; }
  .oge { background:var(--kart); border-radius:14px; padding:12px; display:flex; gap:12px; align-items:center; }
  .oge .ikon { flex:none; width:52px; height:52px; border-radius:10px; background:var(--vurgu); color:#fff;
    display:grid; place-items:center; font-size:22px; }
  .oge .bilgi { flex:1; min-width:0; }
  .oge .ad { font-weight:600; font-size:16px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
  .oge .ek { color:var(--soluk); font-size:13px; margin-top:2px; }
  .oge .islem { display:flex; gap:6px; flex:none; }
  .kucuk { padding:8px 10px; font-size:14px; background:var(--bg); color:var(--vurgu); border-radius:10px; }
  .kucuk.sil { color:var(--kirmizi); }
  .alan { color:var(--soluk); font-size:13px; margin:12px 6px 0; text-align:center; }

  /* Oynatıcı */
  #oynatici { position:fixed; inset:0; background:#000; display:none; flex-direction:column; z-index:10; }
  #oynatici.acik { display:flex; }
  #oynatici header { display:flex; align-items:center; gap:10px;
    padding:max(10px, env(safe-area-inset-top)) 12px 10px; color:#fff; }
  #oynatici header span { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600; }
  #oynatici header button { background:rgba(255,255,255,.15); color:#fff; padding:8px 14px; }
  #oynatici .sahne { flex:1; display:grid; place-items:center; padding-bottom:env(safe-area-inset-bottom); }
  #oynatici video, #oynatici audio { max-width:100%; max-height:100%; width:100%; }

  /* Alt sekme çubuğu */
  nav { position:fixed; left:0; right:0; bottom:0; display:flex; justify-content:center;
    background:color-mix(in srgb, var(--kart) 92%, transparent); -webkit-backdrop-filter:blur(20px); backdrop-filter:blur(20px);
    border-top:1px solid var(--cizgi); padding:6px 0 calc(6px + env(safe-area-inset-bottom)); }
  nav button { background:none; color:var(--soluk); font-size:11px; font-weight:500; padding:4px 28px;
    display:flex; flex-direction:column; align-items:center; gap:2px; }
  nav button.secili { color:var(--vurgu); }
  nav svg { width:26px; height:26px; }
  .rozet { background:var(--kirmizi); color:#fff; border-radius:9px; font-size:11px; padding:0 6px; margin-left:4px; }
  .gizli { display:none !important; }
</style>
</head>
<body>
<main>
  <!-- İNDİR SEKMESİ -->
  <section id="sekmeIndir">
    <h1>İndir</h1>
    <form id="form" class="kart">
      <label for="url">Video linki</label>
      <div class="satir">
        <input id="url" name="url" type="url" inputmode="url" placeholder="Linki buraya yapıştır" required autocomplete="off">
        <button type="button" class="ikinci" id="yapistir">Yapıştır</button>
      </div>
      <label for="format">Kalite</label>
      <select id="format" name="format">
        <option value="720" selected>Video – 720p (önerilen)</option>
        <option value="1080">Video – 1080p (büyük dosya)</option>
        <option value="480">Video – 480p (küçük dosya)</option>
        <option value="ses">Sadece ses</option>
      </select>
      {% if sifre_gerekli %}
      <label for="sifre">Şifre</label>
      <input id="sifre" name="sifre" type="password" autocomplete="current-password">
      {% endif %}
      <button class="ana" id="btn" type="submit">İndir</button>
      <div class="cubuk" id="cubuk"><div id="dolgu"></div></div>
      <div id="durum"></div>
    </form>
    <p class="not" id="kurulumNotu">Uygulama gibi kullanmak için: Safari'de <b>Paylaş</b> → <b>Ana Ekrana Ekle</b>.</p>
  </section>

  <!-- İNDİRİLENLER SEKMESİ -->
  <section id="sekmeListe" class="gizli">
    <h1>İndirilenler</h1>
    <div class="liste" id="liste"></div>
    <div class="alan" id="alan"></div>
  </section>
</main>

<div id="oynatici">
  <header><span id="oynaticiAd"></span><button id="kapat">Kapat</button></header>
  <div class="sahne" id="sahne"></div>
</div>

<nav>
  <button id="tabIndir" class="secili">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v9M8 12l4 4 4-4"/></svg>İndir
  </button>
  <button id="tabListe">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z"/></svg><span>İndirilenler<span id="rozet" class="rozet gizli"></span></span>
  </button>
</nav>

<script>
const $ = id => document.getElementById(id);

/* ---------- Uygulama içi depolama (IndexedDB) ---------- */
let dbSoz;
function db() {
  if (!dbSoz) dbSoz = new Promise((ok, hata) => {
    const r = indexedDB.open("video-indirici", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("videolar", { keyPath: "id", autoIncrement: true });
    r.onsuccess = () => ok(r.result);
    r.onerror = () => hata(r.error);
  });
  return dbSoz;
}
async function islem(mod, fn) {
  const d = await db();
  return new Promise((ok, hata) => {
    const t = d.transaction("videolar", mod);
    const sonuc = fn(t.objectStore("videolar"));
    t.oncomplete = () => ok(sonuc && sonuc.result);
    t.onerror = () => hata(t.error);
    t.onabort = () => hata(t.error || new Error("İşlem iptal edildi"));
  });
}
const kaydet = v => islem("readwrite", s => s.add(v));
const hepsi = () => islem("readonly", s => s.getAll());
const getir = id => islem("readonly", s => s.get(id));
const sil = id => islem("readwrite", s => s.delete(id));

// Tarayıcının verileri silmemesi için kalıcı depolama iste
if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
if (window.navigator.standalone || matchMedia("(display-mode: standalone)").matches) $("kurulumNotu").classList.add("gizli");

/* ---------- Yardımcılar ---------- */
const boyutYaz = b => b > 1e9 ? (b / 1e9).toFixed(2) + " GB" : (b / 1e6).toFixed(1) + " MB";
const sureYaz = s => { if (!s) return ""; s = Math.round(s); const d = Math.floor(s / 60), sn = s % 60;
  return d >= 60 ? `${Math.floor(d / 60)}:${String(d % 60).padStart(2, "0")}:${String(sn).padStart(2, "0")}` : `${d}:${String(sn).padStart(2, "0")}`; };
const tarihYaz = t => new Date(t).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });

/* ---------- Sekmeler ---------- */
function sekme(ad) {
  $("sekmeIndir").classList.toggle("gizli", ad !== "indir");
  $("sekmeListe").classList.toggle("gizli", ad !== "liste");
  $("tabIndir").classList.toggle("secili", ad === "indir");
  $("tabListe").classList.toggle("secili", ad === "liste");
  if (ad === "liste") { $("rozet").classList.add("gizli"); listele(); }
}
$("tabIndir").onclick = () => sekme("indir");
$("tabListe").onclick = () => sekme("liste");

/* ---------- İndirme ---------- */
const p = new URLSearchParams(location.search);
const gelen = p.get("url") || p.get("text");
if (gelen) $("url").value = gelen;
try { const s = localStorage.getItem("sifre"); if (s && $("sifre")) $("sifre").value = s; } catch (e) {}

$("yapistir").onclick = async () => {
  try { $("url").value = (await navigator.clipboard.readText()).trim(); } catch (e) { $("url").focus(); }
};

function durumYaz(m, yuzde) {
  $("durum").textContent = m;
  if (yuzde != null) $("dolgu").style.width = yuzde + "%";
}
function bitir(m) { durumYaz(m); $("btn").disabled = false; }

$("form").onsubmit = async ev => {
  ev.preventDefault();
  const veri = new FormData($("form"));
  if ($("sifre")) { try { localStorage.setItem("sifre", $("sifre").value); } catch (e) {} }
  $("btn").disabled = true; $("cubuk").style.display = "block";
  durumYaz("Başlatılıyor…", 0);
  let r;
  try { r = await fetch("/baslat", { method: "POST", body: veri }); }
  catch (e) { return bitir("Sunucuya bağlanılamadı. İnternet bağlantını kontrol et."); }
  if (r.status === 403) return bitir("Şifre yanlış.");
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return bitir(j.hata || "Hata oluştu.");
  takip(j.id, veri.get("format"));
};

async function takip(id, format) {
  let j;
  try { j = await (await fetch("/durum/" + id)).json(); }
  catch (e) { return setTimeout(() => takip(id, format), 2000); }
  if (j.durum === "calisiyor") {
    durumYaz(j.mesaj + (j.yuzde ? " %" + j.yuzde : ""), j.yuzde || 0);
    return setTimeout(() => takip(id, format), 1000);
  }
  if (j.durum === "hata") return bitir(j.mesaj);
  telefonaAl(id, j, format);
}

// Sunucudaki hazır dosyayı telefona çekip uygulama içine kaydeder
async function telefonaAl(id, bilgi, format) {
  try {
    durumYaz("Telefona aktarılıyor…", 0);
    const r = await fetch("/dosya/" + id);
    if (!r.ok) throw new Error("Dosya alınamadı.");
    const toplam = +r.headers.get("Content-Length") || 0;
    const tur = r.headers.get("Content-Type") || (format === "ses" ? "audio/mp4" : "video/mp4");
    const okuyucu = r.body.getReader();
    const parcalar = []; let alinan = 0;
    for (;;) {
      const { done, value } = await okuyucu.read();
      if (done) break;
      parcalar.push(value); alinan += value.length;
      durumYaz(`Telefona aktarılıyor… ${boyutYaz(alinan)}${toplam ? " / " + boyutYaz(toplam) : ""}`,
               toplam ? alinan / toplam * 100 : 50);
    }
    const blob = new Blob(parcalar, { type: tur });
    await kaydet({ baslik: bilgi.baslik || bilgi.ad, ad: bilgi.ad, tur, ses: format === "ses",
                   boyut: blob.size, sure: bilgi.sure, tarih: Date.now(), blob });
    fetch("/bitti/" + id, { method: "POST" }).catch(() => {});
    $("url").value = "";
    $("rozet").textContent = "Yeni"; $("rozet").classList.remove("gizli");
    bitir("✓ Kaydedildi: " + (bilgi.baslik || bilgi.ad) + " — İndirilenler sekmesinde.");
    durumYaz($("durum").textContent, 100);
  } catch (e) {
    const yer = (e && e.name === "QuotaExceededError") ? " Telefonda yer kalmamış olabilir; eski videoları silmeyi dene." : "";
    bitir("Kaydedilemedi: " + (e.message || e) + yer);
  }
}

/* ---------- İndirilenler listesi ---------- */
async function listele() {
  let ogeler = [];
  try { ogeler = await hepsi(); } catch (e) {}
  ogeler.sort((a, b) => b.tarih - a.tarih);
  const liste = $("liste"); liste.innerHTML = "";
  if (!ogeler.length) {
    liste.innerHTML = '<div class="bos">Henüz indirilen video yok.<br>“İndir” sekmesinden link yapıştırarak başla.</div>';
  }
  for (const v of ogeler) {
    const el = document.createElement("div"); el.className = "oge";
    el.innerHTML = `<div class="ikon">${v.ses ? "♪" : "▶"}</div>
      <div class="bilgi"><div class="ad"></div><div class="ek"></div></div>
      <div class="islem"><button class="kucuk pay">Paylaş</button><button class="kucuk sil">Sil</button></div>`;
    el.querySelector(".ad").textContent = v.baslik;
    el.querySelector(".ek").textContent = [sureYaz(v.sure), boyutYaz(v.boyut), tarihYaz(v.tarih)].filter(Boolean).join(" · ");
    el.querySelector(".ikon").onclick = el.querySelector(".bilgi").onclick = () => oynat(v.id);
    el.querySelector(".sil").onclick = async () => {
      if (!confirm(`“${v.baslik}” silinsin mi?`)) return;
      await sil(v.id); listele();
    };
    el.querySelector(".pay").onclick = () => paylas(v.id);
    liste.appendChild(el);
  }
  if (navigator.storage && navigator.storage.estimate) {
    const t = await navigator.storage.estimate().catch(() => null);
    if (t && t.usage != null) $("alan").textContent = `Uygulamada kullanılan alan: ${boyutYaz(t.usage)}`;
  }
}

/* ---------- Oynatıcı ---------- */
let aktifUrl = null;
async function oynat(id) {
  const v = await getir(id); if (!v) return;
  if (aktifUrl) URL.revokeObjectURL(aktifUrl);
  aktifUrl = URL.createObjectURL(v.blob);
  const m = document.createElement(v.ses ? "audio" : "video");
  m.src = aktifUrl; m.controls = true; m.playsInline = true; m.autoplay = true;
  m.setAttribute("x-webkit-airplay", "allow");
  $("sahne").innerHTML = ""; $("sahne").appendChild(m);
  $("oynaticiAd").textContent = v.baslik;
  $("oynatici").classList.add("acik");
}
$("kapat").onclick = () => {
  const m = $("sahne").firstChild; if (m) m.pause();
  $("sahne").innerHTML = ""; $("oynatici").classList.remove("acik");
  if (aktifUrl) { URL.revokeObjectURL(aktifUrl); aktifUrl = null; }
};

// İsteğe bağlı: Dosyalar'a / Fotoğraflar'a da kaydetmek için iOS paylaşım menüsü
async function paylas(id) {
  const v = await getir(id); if (!v) return;
  const dosya = new File([v.blob], v.ad, { type: v.tur });
  if (navigator.canShare && navigator.canShare({ files: [dosya] })) {
    try { await navigator.share({ files: [dosya], title: v.baslik }); } catch (e) {}
  } else {
    alert("Bu cihazda paylaşım desteklenmiyor.");
  }
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
