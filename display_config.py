"""키오스크 디스플레이 해상도. 모니터 교체 시 DISPLAY_WIDTH / DISPLAY_HEIGHT 만 수정."""

DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# 원래 UI 설계 기준 (픽셀)
_DESIGN_W = 1024
_DESIGN_H = 600

_SX = DISPLAY_WIDTH / _DESIGN_W
_SY = DISPLAY_HEIGHT / _DESIGN_H


def px(n, axis="y"):
    """디자인 기준 픽셀 값을 현재 해상도로 스케일 (axis: 'x' 가로, 'y' 세로)."""
    s = _SX if axis == "x" else _SY
    return max(1, round(n * s))


def fs(n):
    """폰트 크기(포인트)."""
    return max(6, round(n * _SY))


def cw(n):
    """Button / Entry 등 Tk 문자 폭(텍스트 유닛)."""
    return max(1, round(n * _SX))


def ch(n):
    """Button 등 텍스트 줄 수."""
    return max(1, round(n * _SY))
