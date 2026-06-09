#!/bin/bash
# 라즈베리 파이 부팅 시 지폐 교환기 자동 실행 등록
# 사용: ./install_autostart.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_SRC="$SCRIPT_DIR/autostart-지폐교환기.desktop"
DESKTOP_DST="$AUTOSTART_DIR/autostart-지폐교환기.desktop"

mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_SRC" "$DESKTOP_DST"
echo "부팅 자동실행 등록 완료: $DESKTOP_DST"
