#!/usr/bin/env bash
#
# setup.sh – richtet die Kaffeekasse als Desktop-Anwendung ein (GNOME/Linux).
#
# Was es tut:
#   1. macht kaffeekasse.py ausführbar
#   2. erzeugt ein einfaches Icon (falls keines vorhanden ist)
#   3. installiert den .desktop-Starter ins Anwendungsmenü
#
# Voraussetzung: kaffeekasse.py und kaffeekasse.desktop liegen in ~/kaffeekasse
#
# Aufruf:  bash setup.sh

set -euo pipefail

APP_DIR="$HOME/kaffeekasse"
SCRIPT="$APP_DIR/kaffeekasse.py"
DESKTOP_DEST="$HOME/.local/share/applications/kaffeekasse.desktop"
ICON="$APP_DIR/kaffeekasse.png"

echo "==> Prüfe Dateien in $APP_DIR ..."
if [[ ! -f "$SCRIPT" ]]; then
    echo "FEHLER: $SCRIPT nicht gefunden. Liegt das Skript wirklich in ~/kaffeekasse?"
    exit 1
fi

# 1. ausführbar machen
echo "==> Mache kaffeekasse.py ausführbar"
chmod +x "$SCRIPT"

# 2. Icon erzeugen, falls keines da ist (kleines PNG mit einer Kaffeetasse via Python)
if [[ ! -f "$ICON" ]]; then
    echo "==> Erzeuge ein einfaches Icon"
    python3 - "$ICON" << 'PYEOF'
import sys
# Erzeugt ein 128x128 PNG ohne Fremdbibliotheken (minimaler PNG-Writer).
import struct, zlib

W = H = 128
# Hintergrund transparent, Tasse in Braun, Dampf in Grau.
px = bytearray(4 * W * H)  # RGBA

def setpx(x, y, r, g, b, a=255):
    if 0 <= x < W and 0 <= y < H:
        i = 4 * (y * W + x)
        px[i:i+4] = bytes((r, g, b, a))

# Tassenkörper (Rechteck mit leicht gerundetem Eindruck)
for y in range(50, 100):
    for x in range(35, 85):
        setpx(x, y, 111, 78, 55)
# Henkel
for y in range(58, 88):
    for x in range(85, 100):
        # grober Ring
        dx, dy = x - 88, y - 73
        d = (dx*dx + dy*dy) ** 0.5
        if 11 < d < 16:
            setpx(x, y, 111, 78, 55)
# Kaffee-Oberfläche
for y in range(50, 58):
    for x in range(35, 85):
        setpx(x, y, 60, 40, 28)
# Dampf
for off in (48, 60, 72):
    for y in range(20, 46):
        x = off + int(4 * __import__("math").sin(y / 4.0))
        setpx(x, y, 180, 180, 180, 200)
        setpx(x+1, y, 180, 180, 180, 200)

# PNG zusammenbauen
def chunk(typ, data):
    c = typ + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

raw = bytearray()
for y in range(H):
    raw.append(0)  # Filter-Byte
    raw += px[4*y*W : 4*(y+1)*W]
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
       + chunk(b"IEND", b""))
with open(sys.argv[1], "wb") as f:
    f.write(png)
print("Icon geschrieben:", sys.argv[1])
PYEOF
else
    echo "==> Icon existiert bereits, lasse es unverändert"
fi

# 3. .desktop-Starter installieren
# Wichtig: Wir schreiben absolute Pfade direkt hinein. Der Platzhalter %h
# wird von GNOME nur im Exec-Feld zuverlässig ersetzt, nicht in Path= oder
# Icon= – das führte sonst zu "Failed to change to directory %h/...".
echo "==> Installiere Starter ins Anwendungsmenü (mit absoluten Pfaden)"
mkdir -p "$(dirname "$DESKTOP_DEST")"
cat > "$DESKTOP_DEST" << EOF
[Desktop Entry]
Type=Application
Name=Kaffeekasse
Comment=Verwaltung der Büro-Kaffeekasse
Exec=python3 $SCRIPT
Path=$APP_DIR
Icon=$ICON
Terminal=false
Categories=Office;Utility;
EOF
chmod +x "$DESKTOP_DEST"

# Datenbank der Anwendungen aktualisieren (falls verfügbar)
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$(dirname "$DESKTOP_DEST")" >/dev/null 2>&1 || true
fi

echo
echo "Fertig. 'Kaffeekasse' sollte jetzt im Anwendungsmenü auftauchen."
echo "Eventuell einmal ab- und wieder anmelden, falls es nicht sofort"
echo "erscheint. Du kannst es von dort auch ins Dock / auf den Desktop ziehen."