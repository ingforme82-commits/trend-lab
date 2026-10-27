"""전원 연결 중에는 PC가 저절로 대기(절전)에 들어가지 않게 붙잡아 두는 도우미 (메인 PC 전용).

- 동영상 재생 프로그램처럼 Windows에 '시스템 사용 중'을 알리는 방식(SetThreadExecutionState). 전원 설정은 바꾸지 않는다.
- 화면은 평소대로 꺼진다(화면 유지는 요청하지 않음).
- 배터리로 바뀌면 붙잡지 않는다(배터리 보호). 덮개를 닫거나 직접 절전을 누르면 그대로 절전된다.
- 로그온할 때 예약 작업 '트렌드랩_깨어있기'가 pythonw 로 창 없이 실행한다. 끄려면 그 작업을 끝내면 된다.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE), ("BatteryLifePercent", wintypes.BYTE),
                ("SystemStatusFlag", wintypes.BYTE), ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def on_ac() -> bool:
    st = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return True
    return st.ACLineStatus == 1


def main() -> None:
    k = ctypes.windll.kernel32
    held = None
    while True:
        want = on_ac()
        if want != held:
            k.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if want else 0))
            held = want
        time.sleep(60)


if __name__ == "__main__":
    main()
