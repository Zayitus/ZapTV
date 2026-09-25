#!/usr/bin/env python3
"""
ZapTV - generador de playlist IPTV curada (solo fuentes públicas/legítimas).

Fuente: iptv-org (https://github.com/iptv-org/iptv + /database).
Reglas:
  * Argentina: lista blanca explícita de canales abiertos/públicos.
  * Temáticos en español: listas FAST (Pluto MX/ES, Rakuten ES).
  * USA: listas FAST de EE.UU. (Pluto, Samsung TV Plus, Tubi, Xumo, Plex, Roku).
  * Premium de cable: nunca se incluyen (ver NO_INCLUIDOS.md).
  * Se descartan streams marcados [Geo-blocked].

Uso:
  python build.py            -> genera ZapTV.m3u
  python build.py --check    -> además prueba cada stream y descarta los caídos
                                (correrlo desde casa: el geobloqueo depende de tu IP)
"""
import csv, io, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

RAW_STREAMS = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/{}"
RAW_DB = "https://raw.githubusercontent.com/iptv-org/database/master/data/{}"

FAST_ES = ["mx_pluto.m3u", "es_pluto.m3u", "es_rakuten.m3u"]
FAST_US = ["us_pluto.m3u", "us_samsung.m3u", "us_tubi.m3u",
           "us_xumo.m3u", "us_plex.m3u", "us_roku.m3u"]

# ---------------- Argentina: lista blanca ----------------
AR = {
    "Noticias": ["A24.ar", "TN.ar", "Canal26.ar", "IPNoticias.ar", "NETTV.ar",
                 "CanalE.ar", "247CanaldeNoticias.ar"],
    "TV abierta": ["name:TV Publica", "TelefeBuenosAires.ar", "ElTrece.ar",
                   "AmericaTV.ar", "ElNueve.ar"],
    "Cultura y educación": ["SenalU.ar", "TVUniversidad.ar", "CanalUniversidad.ar",
                            "ChamameTV.ar", "FolcloreandoTV.ar"],
    "Infantil": ["Pakapaka.ar", "PlimPlim.ar"],
    "Patagonia": ["TVPublicaFueguina.ar", "Canal2deUshuaia.ar", "Canal7Neuquen.ar",
                  "RTN.ar", "RadioTVNeuquen.ar", "ABTVBariloche.ar", "Canal4Esquel.ar",
                  "Telecinco.ar", "Canal12Web.ar", "Canal3LaPampa.ar"],
}

# Premium / cable: bloqueados aunque aparezcan en alguna lista
#BLOCK_IDS = {"TyCSports.ar", "TyCSportsUSA.ar", "DisneyChannelLatinAmerica.ar",
             "DisneyJrLatinAmerica.ar", "ElGourmet.ar", "FilmArts.ar",
             "EuropaEuropa.ar", "SonyChannel.ar", "Volver.ar",
             "GarageTVLatinAmerica.ar", "TelefeInternacional.ar"}

# Canales que no aportan a las categorías pedidas (o falsos positivos por nombre)
SKIP_NAMES = ["teen mom", "ink master", "revry", "draftkings", "sala de emergencias",
              "paranormal", "jojo", "cine de autor", "star trek", "mystery science theater",
              "wild 'n out", "wild wild west", "wild west tv", "supernatural", "funniest home",
              "hometown drama", "ultratumba", "johnny carson"]

# ---------------- Clasificación temática ----------------
# (subgrupo, regex sobre el nombre, categorías iptv-org). Gana la primera que coincide.
RULES = [
    ("Historia",         r"\bhistor|modern marvels|alone by|pickers|warfare", []),
    ("Casa y diseño",    r"\bhome\b(?! cooking)|homeful|\bhogar\b|garden|design|diseño|mueble|antiques|handyman|magnolia|\bdiy\b", []),
    ("Viajes",           r"travel|viajes?\b|journy", ["travel"]),
    ("Naturaleza",       r"\bnatur|\bearth\b|animal|\bwild|\bpets\b|lucky dog|wilderness", []),
    ("Ciencia",          r"science|ciencia|\bwonder|smithsonian|unidentified|magellan|\bspace\b", ["science"]),
    ("Motor",            r"motor|top gear|turbo|powernation|racing|\bracer\b|rally|nhra|chopper|\bcars\b|\bautos?\b", ["auto"]),
    ("Cocina",           r"food|cocina|kitchen|chef|ramsay|jamie|gusto|hungry|bon app|tastemade", ["cooking"]),
    ("Fútbol",           r"fifa|golazo|f[uú]tbol|soccer|bein|fox sports", []),
    ("Aventura y outdoor", r"red bull|outdoor|adventure|backcountry|xtreme|waypoint|pursuit|outside tv", ["outdoor"]),
    ("Otros deportes",   None, ["sports"]),
    ("Documentales",     None, ["documentary", "education"]),
    ("Lifestyle",        None, ["lifestyle"]),
]

ES_GROUPS = {  # subgrupo -> grupo principal (canales en español)
    "Historia": "🎬 Historia y Documentales", "Naturaleza": "🎬 Historia y Documentales",
    "Ciencia": "🎬 Historia y Documentales", "Documentales": "🎬 Historia y Documentales",
    "Cocina": "🏠 Hogar y Lifestyle", "Viajes": "🏠 Hogar y Lifestyle",
    "Casa y diseño": "🏠 Hogar y Lifestyle", "Lifestyle": "🏠 Hogar y Lifestyle",
    "Motor": "🏆 Deportes", "Fútbol": "🏆 Deportes",
    "Aventura y outdoor": "🏆 Deportes", "Otros deportes": "🏆 Deportes",
}
US_SUB = {  # subgrupo -> subgrupo dentro de USA
    "Historia": "Historia", "Naturaleza": "Documentales", "Documentales": "Documentales",
    "Ciencia": "Ciencia", "Casa y diseño": "Home & Garden", "Cocina": "Lifestyle",
    "Viajes": "Lifestyle", "Lifestyle": "Lifestyle", "Motor": "Deportes",
    "Fútbol": "Deportes", "Aventura y outdoor": "Deportes", "Otros deportes": "Deportes",
}


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_m3u(text, src):
    lines = text.splitlines()
    out = []
    for i, l in enumerate(lines):
        if l.startswith("#EXTINF") and i + 1 < len(lines):
            m = re.search(r'tvg-id="([^"@]*)', l)
            ua = re.search(r'http-user-agent="([^"]*)"', l)
            ref = re.search(r'http-referrer="([^"]*)"', l)
            j = i + 1
            opts = []
            while j < len(lines) and lines[j].startswith("#EXTVLCOPT"):
                opts.append(lines[j].strip()); j += 1
            out.append({"id": m.group(1) if m else "", "name": l.split(",", 1)[1].strip(),
                        "url": lines[j].strip() if j < len(lines) else "", "src": src,
                        "opts": opts, "ua": ua.group(1) if ua else None,
                        "ref": ref.group(1) if ref else None})
    return out


def quality(s):
    n = s["name"]
    res = re.search(r"\((\d+)p\)", n)
    return (("Geo-blocked" not in n), ("Not 24/7" not in n), int(res.group(1)) if res else 0)


def classify(s, cats):
    n = s["name"].lower()
    if any(k in n for k in SKIP_NAMES):
        return None
    for sub, rx, cs in RULES:
        if (rx and re.search(rx, n)) or (set(cs) & cats):
            return sub
    return None


def best_per_channel(streams):
    best = {}
    for s in streams:
        key = s["id"] or s["name"]
        if key not in best or quality(s) > quality(best[key]):
            best[key] = s
    return list(best.values())


def alive(s):
    try:
        req = urllib.request.Request(s["url"], headers={"User-Agent": s["ua"] or "VLC/3.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status < 400
    except Exception:
        return False


def main():
    check = "--check" in sys.argv
    channels = {r["id"]: r for r in csv.DictReader(io.StringIO(fetch(RAW_DB.format("channels.csv"))))}
    logos = {}
    for r in csv.DictReader(io.StringIO(fetch(RAW_DB.format("logos.csv")))):
        logos.setdefault(r["channel"], r["url"])

    entries = []  # (grupo, stream)

    # Argentina
    ar = parse_m3u(fetch(RAW_STREAMS.format("ar.m3u")), "ar")
    for sub, keys in AR.items():
        for k in keys:
            cand = [s for s in ar if (s["name"].startswith(k[5:] + " (") or s["name"] == k[5:])
                    ] if k.startswith("name:") else [s for s in ar if s["id"] == k]
            cand = [s for s in cand if s["id"] not in BLOCK_IDS and "Geo-blocked" not in s["name"]]
            if cand:
                entries.append((f"🇦🇷 Argentina | {sub}", max(cand, key=quality)))

    # Temáticos en español y USA
    for files, lang in ((FAST_ES, "es"), (FAST_US, "us")):
        pool = []
        for f in files:
            for s in parse_m3u(fetch(RAW_STREAMS.format(f)), f):
                if "Geo-blocked" in s["name"] or s["id"] in BLOCK_IDS:
                    continue
                cats = set((channels.get(s["id"], {}).get("categories") or "").split(";"))
                sub = classify(s, cats)
                if sub:
                    s["sub"] = sub
                    pool.append(s)
        for s in best_per_channel(pool):
            g = f"{ES_GROUPS[s['sub']]} | {s['sub']}" if lang == "es" else f"🇺🇸 USA | {US_SUB[s['sub']]}"
            entries.append((g, s))

    if check:
        with ThreadPoolExecutor(20) as ex:
            ok = list(ex.map(lambda e: alive(e[1]), entries))
        dead = [e for e, o in zip(entries, ok) if not o]
        entries = [e for e, o in zip(entries, ok) if o]
        print(f"Descartados por no responder: {len(dead)}")

    order = ["🇦🇷", "🏆", "🎬", "🏠", "🇺🇸"]
    entries.sort(key=lambda e: (next(i for i, p in enumerate(order) if e[0].startswith(p)),
                                e[0], e[1]["name"].lower()))

    out = ["#EXTM3U"]
    for g, s in entries:
        logo = logos.get(s["id"], "")
        name = re.sub(r"\s*\[(Not 24/7)\]", r" [\1]", s["name"])
        out.append(f'#EXTINF:-1 tvg-id="{s["id"]}" tvg-logo="{logo}" group-title="{g}",{name}')
        if s["ua"]:
            out.append(f"#EXTVLCOPT:http-user-agent={s['ua']}")
        if s["ref"]:
            out.append(f"#EXTVLCOPT:http-referrer={s['ref']}")
        out += [o for o in s["opts"] if "user-agent" not in o and "referrer" not in o]
        out.append(s["url"])
    # Agregados a mano (canales oficiales que no están en iptv-org)
    import os
    if os.path.exists("extras.m3u"):
        extra = [l.rstrip() for l in open("extras.m3u", encoding="utf-8")
                 if l.strip() and not l.startswith("#EXTM3U") and not l.startswith("# ")]
        out += extra
        print(f"Extras agregados: {sum(l.startswith('#EXTINF') for l in extra)}")
    open("ZapTV.m3u", "w", encoding="utf-8").write("\n".join(out) + "\n")

    from collections import Counter
    for g, n in sorted(Counter(g for g, _ in entries).items(),
                       key=lambda x: next(i for i, p in enumerate(order) if x[0].startswith(p))):
        print(f"{n:4d}  {g}")
    print(f"Total: {len(entries)} canales -> ZapTV.m3u")


if __name__ == "__main__":
    main()
