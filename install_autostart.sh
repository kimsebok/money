#!/bin/bash
# 라즈베리 파이 부팅 시 지폐 교환기 자동 실행 등록
# 사용: bash install_autostart.sh  (또는 chmod +x 후 ./install_autostart.sh)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$SCRIPT_DIR/launch_money_exchange.sh"
MONEY_PY="$SCRIPT_DIR/money_exchange.py"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_DST="$AUTOSTART_DIR/autostart-지폐교환기.desktop"

if [ ! -f "$MONEY_PY" ]; then
  echo "오류: money_exchange.py를 찾을 수 없습니다: $MONEY_PY"
  exit 1
fi

chmod +x "$LAUNCHER"

mkdir -p "$AUTOSTART_DIR"

cat > "$DESKTOP_DST" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=지폐 교환기 (부팅 시 자동실행)
Comment=부팅 시 지폐 교환기 자동 실행 (앱 시작 5초 후 git 업데이트)
Exec=$LAUNCHER
Path=$SCRIPT_DIR
Icon=python3
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF

chmod 644 "$DESKTOP_DST"

echo "부팅 자동실행 등록 완료"
echo "  desktop: $DESKTOP_DST"
echo "  launcher: $LAUNCHER"
echo ""
echo "확인:"
echo "  ls -l $AUTOSTART_DIR"
echo "  cat $DESKTOP_DST"
echo ""
echo "수동 테스트: $LAUNCHER"
echo "재부팅: sudo reboot"
