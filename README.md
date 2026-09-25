# ZapTV

Playlist IPTV curada (Argentina, deportes, historia/documentales, hogar/lifestyle y USA), armada **solo con streams públicos y legítimos**: emisoras abiertas/públicas y canales FAST (Pluto TV, Samsung TV Plus, Tubi, Xumo, Plex, Roku).

Fuente de datos: [iptv-org](https://github.com/iptv-org/iptv). Los canales premium quedan afuera (ver [NO_INCLUIDOS.md](NO_INCLUIDOS.md)).

## Uso en VLC (celular y TV)

Cargar esta URL en ambos dispositivos:

```
https://raw.githubusercontent.com/zayitus/zaptv/main/ZapTV.m3u
```

- **VLC Android / Android TV:** Más → Transmisión (Stream) → pegar la URL.
- **VLC iOS / Apple TV:** Red → Transmitir en red → pegar la URL.

Cada vez que se actualiza el archivo en GitHub, los dos dispositivos ven la misma lista.

## Regenerar la lista

```bash
python build.py           # genera ZapTV.m3u
python build.py --check   # además descarta streams que no responden
```

Conviene correr `--check` **desde casa**: el geobloqueo depende de la IP.

## Estructura

| Grupo | Contenido |
|---|---|
| 🇦🇷 Argentina | Noticias, TV abierta, Cultura y educación, Infantil, Patagonia |
| 🏆 Deportes | Motor, Fútbol, Aventura y outdoor, Otros (en español) |
| 🎬 Historia y Documentales | Historia, Naturaleza, Ciencia, Documentales (en español) |
| 🏠 Hogar y Lifestyle | Casa y diseño, Cocina, Viajes, Lifestyle (en español) |
| 🇺🇸 USA | Historia, Documentales, Ciencia, Home & Garden, Lifestyle, Deportes (en inglés) |

La configuración (lista blanca de Argentina, bloqueos y reglas de clasificación) está al principio de `build.py`.
