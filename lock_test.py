
import tkinter as tk
from tkinter import messagebox
import gpiozero # 혹은 lgpio 사용 가능
from time import sleep

# GPIO 설정 (GPIO 17번 핀 사용)
# 회로 보호를 위해 Relay나 MOSFET 제어용 OutputDevice 선언
lock = gpiozero.OutputDevice(17, active_high=True, initial_value=False)

def unlock():
    """잠금을 3초간 해제하고 다시 잠그는 함수"""
    try:
        lock.on()  # MOSFET 활성화 (락 해제)
        status_label.config(text="상태: 잠금 해제됨", fg="red")
        root.update()
        
        sleep(1)   # 3초 유지 (상황에 따라 조절)
        
        lock.off() # MOSFET 비활성화 (다시 잠김)
        status_label.config(text="상태: 잠김", fg="black")
    except Exception as e:
        messagebox.showerror("오류", f"제어 실패: {e}")

# GUI 창 설정
root = tk.Tk()
root.title("Kiosk Lock Control")
root.geometry("300x200")

# UI 요소
title_label = tk.Label(root, text="전자락 제어 시스템", font=("Arial", 14))
title_label.pack(pady=10)

status_label = tk.Label(root, text="상태: 잠김", font=("Arial", 12))
status_label.pack(pady=5)

unlock_button = tk.Button(root, text="잠금 해제 (3초)", command=unlock, 
                          width=20, height=2, bg="lightblue")
unlock_button.pack(pady=20)

# 프로그램 종료 시 GPIO 정리
root.protocol("WM_DELETE_WINDOW", lambda: [lock.close(), root.destroy()])

root.mainloop()


