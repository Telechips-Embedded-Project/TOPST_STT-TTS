#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import socket

# ==== TCP 송신 ==== 
# 포트명 수정 필요
TCP_HOST = os.getenv("DISPATCH_TX_HOST", "127.0.0.1")
TCP_PORT = int(os.getenv("DISPATCH_TX_PORT", "13001"))

def send_payload(payload: dict) -> None:
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with socket.create_connection((TCP_HOST, TCP_PORT), timeout=1.5) as s:
            s.sendall(data)
        print(f"[TX] {payload}")
    except Exception as e:
        print(f"[ERROR] TCP send failed: {e}")
        print(f"[TX-LOCAL] {payload}")

# 장치 제어 명령 -> send_payload 호출 (TCP 송신)
def emit_device(device: str, command: str, value=None):
    payload = {"device": device, "command": command}
    if value is not None:
        payload["value"] = value
    send_payload(payload)
    return True, True  # handled, device_hit


# ==== 전처리 ====

def to_lowercase(s: str) -> str:
    return s.lower()

def remove_punctuation(s: str) -> str:
    cleaned = []
    for ch in s:
        if ch.isalpha() or ch.isdigit() or ch.isspace():
            cleaned.append(ch)
    return "".join(cleaned)

def tokenize(s: str):
    return set(s.split())

def word_exists(tokens: set, word: str) -> bool:
    return word in tokens


# ==== 공통 유틸 ====

ACTION_WORDS = {
    # 공통
    "on", "off", "set", "start", "turn",
    # 창문
    "open", "close", "stop",
    # 와이퍼
    "fast", "slow",
    # 앰비언트
    "red", "yellow", "green", "rainbow", "brightness",
    # 음악/볼륨
    "play", "stop", "next", "skip", "previous", "back", "last",
    "up", "down", "increase", "decrease", "louder", "quieter",
}

def has_action_word(tokens: set) -> bool:
    return any(w in tokens for w in ACTION_WORDS)

def extract_int(text: str) -> int:
    m = re.search(r"\d+", text)
    return int(m.group()) if m else -1


# ==== 상태 질의 키워드 ====

STATUS_WORDS = {
    "status", "state", "is", "are", "what", "how", "check", "show",
}

SENSOR_WORDS = {
    "temperature", "temp", "co2", "co₂", "humidity",
}

INDOOR_WORDS = {"indoor", "inside", "room", "실내", "내부"}

DEVICE_TOKENS = {
    "aircon", "ac", "window", "wiper", "ambient", "music", "song", "volume", "headlamp",
    "air", "conditioner",
}

def detect_question(text: str, tokens: set):
    """
    상태 질의면 (command, value) 반환.
    - 디바이스 상태: command = aircon/window/wiper/ambient/music/headlamp
    - 센서 상태: command = temperature/co2/humidity, value="indoor"(옵션)
    상태 질의가 아니면 (None, None).
    """
    if not any(w in tokens for w in STATUS_WORDS):
        return None, None

    # 센서 우선
    if any(w in tokens for w in SENSOR_WORDS):
        if any(w in tokens for w in {"temperature", "temp", "온도"}):
            return "temperature", ("indoor" if any(w in tokens for w in INDOOR_WORDS) else None)
        if any(w in tokens for w in {"co2", "co₂", "이산화탄소"}):
            return "co2", ("indoor" if any(w in tokens for w in INDOOR_WORDS) else None)
        if any(w in tokens for w in {"humidity", "습도"}):
            return "humidity", ("indoor" if any(w in tokens for w in INDOOR_WORDS) else None)

    # 디바이스 상태
    device_map = {
        "aircon": "aircon", "ac": "aircon",
        "window": "window",
        "wiper": "wiper",
        "ambient": "ambient",
        "music": "music", "song": "music", "volume": "music",
        "headlamp": "headlamp",
    }
    for tk in device_map:
        if tk in tokens:
            return device_map[tk], None
    if "air" in tokens and "conditioner" in tokens:
        return "aircon", None

    return None, None


# ==== 디바이스 핸들러 ====
# 각 핸들러는 (handled, device_hit) 반환

def handle_aircon(text: str, tokens: set):
    device_hit = (
        "aircon" in tokens or "ac" in tokens or
        ("airconditioner" in text) or ("air conditioner" in text)
    )
    if not device_hit:
        return False, False

    # --- 숫자 우선 (무조건 set) ---
    target = extract_int(text)
    if target > 0:
        return emit_device("aircon", "set", target)

    # 그 다음 off > on
    if "off" in tokens:
        return emit_device("aircon", "off")
    if "on" in tokens:
        return emit_device("aircon", "on")

    return False, True

def handle_window(text: str, tokens: set):
    device_hit = "window" in tokens
    if not device_hit:
        return False, False

    if "open" in tokens:
        return emit_device("window", "open")
    if "close" in tokens:
        return emit_device("window", "close")
    if "stop" in tokens:
        return emit_device("window", "stop")

    pos = extract_int(text)
    if pos >= 0 and ("set" in tokens or pos >= 0):
        return emit_device("window", "set", pos)

    return False, True

def handle_wiper(text: str, tokens: set):
    device_hit = "wiper" in tokens
    if not device_hit:
        return False, False

    if "off" in tokens:
        return emit_device("wiper", "off")
    if "fast" in tokens:
        return emit_device("wiper", "fast")
    if "slow" in tokens:
        return emit_device("wiper", "slow")
    if "on" in tokens or "set" in tokens or "start" in tokens:
        return emit_device("wiper", "on")

    mode = extract_int(text)
    if mode >= 0 and "set" in tokens:
        return emit_device("wiper", "set", mode)

    return False, True

def handle_ambient(text: str, tokens: set):
    device_hit = "ambient" in tokens
    if not device_hit:
        return False, False

    # off 우선
    if "off" in tokens:
        return emit_device("ambient", "off")

    # 색상
    color = None
    if "red" in tokens:
        color = "red"
    elif "yellow" in tokens:
        color = "yellow"
    elif "green" in tokens:
        color = "green"
    elif "rainbow" in tokens:
        color = "rainbow"

    # 밝기
    brightness = None
    if "low" in tokens:
        brightness = "low"
    elif "mid" in tokens or "middle" in tokens:
        brightness = "mid"
    elif "high" in tokens:
        brightness = "high"

    sent_any = False
    if color:
        emit_device("ambient", "on", color)
        sent_any = True
    if brightness:
        emit_device("ambient", "brightness", brightness)
        sent_any = True
    if sent_any:
        return True, True

    # 단순 on
    if "on" in tokens or "set" in tokens or "start" in tokens or "turn" in tokens:
        return emit_device("ambient", "on", "green")  # 기본값

    return False, True

def handle_music(text: str, tokens: set):
    device_hit = ("music" in tokens) or ("song" in tokens) or ("volume" in tokens)
    if not device_hit:
        return False, False

    if "off" in tokens or "stop" in tokens:
        return emit_device("music", "stop")
    if "on" in tokens or "start" in tokens or "play" in tokens:
        return emit_device("music", "play")
    if "next" in tokens or "skip" in tokens:
        return emit_device("music", "next")
    if "previous" in tokens or "back" in tokens or "last" in tokens:
        return emit_device("music", "previous")

    if "volume" in tokens:
        if "up" in tokens or "increase" in tokens or "louder" in tokens:
            return emit_device("music", "volume_up")
        if "down" in tokens or "decrease" in tokens or "quieter" in tokens:
            return emit_device("music", "volume_down")

    return False, True

def handle_headlamp(text: str, tokens: set):
    device_hit = "headlamp" in tokens
    if not device_hit:
        return False, False

    if "off" in tokens:
        return emit_device("headlamp", "off")
    if "on" in tokens:
        return emit_device("headlamp", "on")

    val = extract_int(text)
    if "set" in tokens and val >= 0:
        return emit_device("headlamp", "set", val)

    return False, True


DEVICE_HANDLERS = [
    ("AIRCON", handle_aircon),
    ("WINDOW", handle_window),
    ("WIPER", handle_wiper),
    ("AMBIENT", handle_ambient),
    ("MUSIC", handle_music),
    ("HEADLAMP", handle_headlamp),
]


# ==== 디스패처 ====
## 여기서 각각의 LLM에게 HTTP로 보내기
def dispatch_route(device_hit_any: bool, action_hit_any: bool, raw_text: str):
    if device_hit_any and not action_hit_any:
        print(f'[ROUTE] COMMAND_LLM (device-only) -> "{raw_text}"')
    elif action_hit_any and not device_hit_any:
        print(f'[ROUTE] COMMAND_LLM (action-only) -> "{raw_text}"')
    elif not device_hit_any and not action_hit_any:
        print(f'[ROUTE] CHAT_LLM -> "{raw_text}"')
    else:
        print(f'[ROUTE] COMMAND_LLM (device+action, unknown mapping) -> "{raw_text}"')


# ==== 핵심 처리 ====

def process_command(raw_text: str) -> None:
    text = to_lowercase(remove_punctuation(raw_text))
    tokens = tokenize(text)

    # 0) 상태 질의하는지 체크 → JSON (device: question)
    q_cmd, q_val = detect_question(text, tokens)
    if q_cmd:
        payload = {"device": "question", "command": q_cmd}
        if q_val is not None:
            payload["value"] = q_val
        send_payload(payload)
        return

    # 1) 명령(액션) 감지
    global_action_hit = has_action_word(tokens)

    # 2) 디바이스 제어 시도 → JSON 송신
    device_hit_any = False
    for _, handler in DEVICE_HANDLERS:
        handled, device_hit = handler(text, tokens)
        device_hit_any = device_hit_any or device_hit
        if handled:
            return  # 전송 완료

    # 3) 하드코딩 매칭 실패 → 라우팅 로그
    dispatch_route(device_hit_any, global_action_hit, raw_text)


# ==== 메인 루프 ====

def main():
    while True:
        try:
            user_input = input("Enter STT command: ")
        except EOFError:
            break
        user_input = user_input.rstrip("\n")
        if not user_input.strip():
            continue
        process_command(user_input)

if __name__ == "__main__":
    main()
