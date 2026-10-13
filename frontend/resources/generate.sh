#!/usr/bin/env bash
# Regenerate the Android / iOS app icons and splash screens from the SVGs here.
# Needs google-chrome (renders the SVGs) and ImageMagick `convert`.
# Run from anywhere:  frontend/resources/generate.sh
set -euo pipefail
cd "$(dirname "$0")"
RES=../android/app/src/main/res
IOS=../ios/App/App/Assets.xcassets

render() {  # render <name>  -> <name>.png at the SVG's own pixel size
  local size; size=$(grep -o 'width="[0-9]*"' "$1.svg" | head -1 | tr -dc 0-9)
  google-chrome --headless=new --disable-gpu --hide-scrollbars \
    --default-background-color=00000000 --window-size="$size,$size" \
    --screenshot="$PWD/$1.png" "file://$PWD/$1.svg" 2>/dev/null
}
for f in icon icon-background icon-foreground splash; do render "$f"; done

# ── iOS: one 1024 px icon (no alpha channel allowed), one universal splash
convert icon.png -alpha off "$IOS/AppIcon.appiconset/AppIcon-512@2x.png"
for f in splash-2732x2732.png splash-2732x2732-1.png splash-2732x2732-2.png; do
  convert splash.png -alpha off "$IOS/Splash.imageset/$f"
done

# ── Android launcher icons per density (dp scale: mdpi 1 … xxxhdpi 4)
convert icon-background.png icon-foreground.png -composite adaptive-full.png
for pair in mdpi:1 hdpi:1.5 xhdpi:2 xxhdpi:3 xxxhdpi:4; do
  d=${pair%%:*}; s=${pair##*:}
  legacy=$(python3 -c "print(round(48*$s))"); layer=$(python3 -c "print(round(108*$s))")
  r=$(python3 -c "print(round(48*$s*0.22))")
  out="$RES/mipmap-$d"
  # Pre-Android 8 square and round icons
  convert icon.png -resize "${legacy}x${legacy}" \
    \( -size "${legacy}x${legacy}" xc:none -fill white -draw "roundrectangle 0,0 $((legacy-1)),$((legacy-1)) $r,$r" \) \
    -compose DstIn -composite "$out/ic_launcher.png"
  convert adaptive-full.png -resize "${legacy}x${legacy}" \
    \( -size "${legacy}x${legacy}" xc:none -fill white -draw "circle $((legacy/2)),$((legacy/2)) $((legacy/2)),0" \) \
    -compose DstIn -composite "$out/ic_launcher_round.png"
  # Android 8+ adaptive icon layers
  convert icon-foreground.png -resize "${layer}x${layer}" "$out/ic_launcher_foreground.png"
  convert icon-background.png -resize "${layer}x${layer}" "$out/ic_launcher_background.png"
done
rm -f adaptive-full.png

# ── Android pre-12 splash images: keep each slot's size, logo centred on white
find "$RES" -path '*drawable*' -name splash.png | while read -r f; do
  dims=$(identify -format '%wx%h' "$f")
  convert splash.png -resize "${dims}^" -gravity center -extent "$dims" -alpha off "$f"
done
echo "icons and splash screens regenerated"
