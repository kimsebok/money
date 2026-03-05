#!/bin/bash
# 지폐 교환기 지연 실행: 터치/마우스가 준비된 뒤 앱 실행 (부팅 직후 입력 안 되는 현상 방지)
# 사용: ./start_money_exchange.sh 또는 autostart .desktop에서 Exec로 지정

cd /home/se/money || exit 1

# DISPLAY가 없으면 대기 (X 세션 준비)
for i in 1 2 3 4 5 6 7 8 9 10; do
  [ -n "$DISPLAY" ] && break
  sleep 1
done
[ -z "$DISPLAY" ] && export DISPLAY=:0

# 터치/마우스 입력 장치가 준비될 때까지 대기 (최대 25초)
# autotouch 및 udev가 터치 연동을 끝낸 뒤 실행
wait_sec=0
while [ $wait_sec -lt 25 ]; do
  if ls /dev/input/event* 1>/dev/null 2>&1; then
    # 최소 5초는 대기 (autotouch 등 시스템 초기화 여유)
    if [ $wait_sec -ge 5 ]; then
      break
    fi
  fi
  sleep 1
  wait_sec=$((wait_sec + 1))
done

# 추가로 2초 대기해 입력 장치가 X에 완전히 등록되도록 함
sleep 2

exec python3 /home/se/money/money_exchange.py
