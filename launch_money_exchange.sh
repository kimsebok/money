#!/bin/bash
# 부팅 autostart용: X/입력 장치 준비 후 지폐 교환기 실행
# install_autostart.sh 가 생성·등록합니다. 직접 수정하지 마세요.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export DISPLAY="${DISPLAY:-:0}"

# X 세션·입력 장치 준비 대기
sleep 8

exec python3 "$SCRIPT_DIR/money_exchange.py"
