#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pyaudio
import queue
import json
import requests
import re
import socket
import threading
import time
from vosk import Model, KaldiRecognizer
import numpy as np

# ==============================================================================
# 1. Dispatcher 클래스 (완성본)
# ==============================================================================
class CommandDispatcher:
    def __init__(self, llm_control_url, llm_chat_url):
        self.llm_control_url = llm_control_url
        self.llm_chat_url = llm_chat_url
        self.ACTION_WORDS = {"on", "off", "set", "start", "turn", "open", "close", "stop", "fast", "slow", "red", "yellow", "green", "rainbow", "brightness", "play", "next", "skip", "previous", "back", "last", "up", "down", "increase", "decrease", "louder", "quieter"}
        self.DEVICE_TOKENS = {"aircon", "ac", "window", "wiper", "ambient", "music", "song", "volume", "headlamp", "air", "conditioner"}
        self.DEVICE_HANDLERS = [self.handle_aircon, self.handle_window, self.handle_wiper, self.handle_ambient, self.handle_music, self.handle_headlamp]
    def _preprocess(self, raw_text: str):
        text = raw_text.lower()
        cleaned = "".join(ch for ch in text if ch.isalpha() or ch.isdigit() or ch.isspace())
        tokens = set(cleaned.split())
        return cleaned, tokens
    def _has_action_word(self, tokens: set) -> bool:
        return any(w in tokens for w in self.ACTION_WORDS)
    def _extract_int(self, text: str) -> int:
        m = re.search(r"\d+", text)
        return int(m.group()) if m else -1

    def _send_to_vehicle(self, payload: dict):
        TCP_HOST = "192.168.137.2"
        TCP_PORT = 60003
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        data.replace("\n", " ")
        try:
            with socket.create_connection((TCP_HOST, TCP_PORT), timeout=5.5) as s:
                s.sendall(data)
            print(f"[VEHICLE CMD SENT] {payload}")
        except Exception as e:
            print(f"[ERROR] Vehicle control TCP send failed: {e}")

    def _call_llm(self, url: str, text: str, role: str):
        print(f"[{role} LLM] Forwarding text: '{text}' to {url}")
        prompt_text = text
        if role == "CONTROL":
            prompt_text = (f"Analyze the following user command and convert it into a JSON format. Respond with ONLY the JSON object and nothing else. The JSON should contain 'device', 'command', and 'value'. User command: '{text}'")
        headers = {"Content-Type": "application/json"}
        data = {"prompt": prompt_text, "temperature": 0.1, "n_predict": 32}
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            if response.status_code == 200:
                result = response.json()
                content = result.get("content", "").strip()
                print(f"[{role} LLM response]: {content}")
                if role == "CONTROL":
                    # json 파싱 로직 추가
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)

                    if not json_match:
                        print(f"[ERROR] No JSON object found in the LLM response: {content}")
                        return
                    json_str = json_match.group(0)
                    try:
                        control_payload = json.loads(json_str)
                        if "device" in control_payload and "command" in control_payload:
                             self._send_to_vehicle(control_payload)
                        else:
                             print(f"[WARNING] Control LLM returned invalid JSON: {json_str}")
                    except json.JSONDecodeError:
                        print(f"[ERROR] Failed to parse JSON from Control LLM: {json_str}")
                else: # CHAT LLM
                    if content: # 응답이 비어있지 않을 때만
                        chat_payload = {
                            "device": "llm",
                            "command": "speak",
                            "value": content
                        }
                        self._send_to_vehicle(chat_payload)
                        print(f"[SIMULATING TTS] Playing: '{content}'") 
            else:
                print(f"[ERROR] LLM server returned status {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"[FATAL] Failed to connect to LLM server at {url}: {e}")
    def _emit_device(self, device: str, command: str, value=None):
        payload = {"device": device, "command": command}
        if value is not None: payload["value"] = value
        self._send_to_vehicle(payload)
        return True, True
    def handle_aircon(self, text: str, tokens: set):
        device_hit = ("aircon" in tokens or "ac" in tokens or ("air" in tokens and "conditioner" in tokens))
        if not device_hit: return False, False
        target = self._extract_int(text)
        if target > 0: return self._emit_device("aircon", "set", target)
        if "off" in tokens: return self._emit_device("aircon", "off")
        if "on" in tokens: return self._emit_device("aircon", "on")
        return False, True
    def handle_window(self, text: str, tokens: set):
        device_hit = "window" in tokens
        if not device_hit: return False, False
        if "open" in tokens: return self._emit_device("window", "open")
        if "close" in tokens: return self._emit_device("window", "close")
        if "stop" in tokens: return self._emit_device("window", "stop")
        pos = self._extract_int(text)
        if pos >= 0: return self._emit_device("window", "set", pos)
        return False, True
    def handle_wiper(self, text: str, tokens: set):
        device_hit = "wiper" in tokens
        if not device_hit: return False, False
        if "off" in tokens: return self._emit_device("wiper", "off")
        if "fast" in tokens: return self._emit_device("wiper", "fast")
        if "slow" in tokens: return self._emit_device("wiper", "slow")
        if "on" in tokens or "start" in tokens: return self._emit_device("wiper", "on")
        return False, True
    def handle_ambient(self, text: str, tokens: set):
        device_hit = "ambient" in tokens
        if not device_hit: return False, False
        if "off" in tokens: return self._emit_device("ambient", "off")
        color = next((c for c in ["red", "yellow", "green", "rainbow"] if c in tokens), None)
        if color: return self._emit_device("ambient", "on", color)
        if "on" in tokens or "turn" in tokens: return self._emit_device("ambient", "on", "green")
        return False, True
    def handle_music(self, text: str, tokens: set):
        device_hit = ("music" in tokens or "song" in tokens or "volume" in tokens)
        if not device_hit: return False, False
        if "stop" in tokens: return self._emit_device("music", "stop")
        if "play" in tokens: return self._emit_device("music", "play")
        if "next" in tokens or "skip" in tokens: return self._emit_device("music", "next")
        if "previous" in tokens or "back" in tokens: return self._emit_device("music", "previous")
        if "volume" in tokens:
            if "up" in tokens or "louder" in tokens: return self._emit_device("music", "volume_up")
            if "down" in tokens or "quieter" in tokens: return self._emit_device("music", "volume_down")
        return False, True
    def handle_headlamp(self, text: str, tokens: set):
        device_hit = "headlamp" in tokens
        if not device_hit: return False, False
        if "off" in tokens: return self._emit_device("headlamp", "off")
        if "on" in tokens: return self._emit_device("headlamp", "on")
        val = self._extract_int(text)
        if "set" in tokens and val >= 0: return self._emit_device("headlamp", "set", val)
        return False, True
    def process_text(self, raw_text: str):
        if not raw_text.strip(): return
        print(f"\n--- Processing: '{raw_text}' ---")
        text, tokens = self._preprocess(raw_text)
        device_hit_any = False
        for handler in self.DEVICE_HANDLERS:
            handled, device_hit = handler(text, tokens)
            device_hit_any = device_hit_any or device_hit
            if handled:
                print("--- Hard-coded command processed. ---\n")
                return
        action_hit_any = self._has_action_word(tokens)
        if device_hit_any or action_hit_any:
            self._call_llm(self.llm_control_url, raw_text, "CONTROL")
        else:
            self._call_llm(self.llm_chat_url, raw_text, "CHAT")
        print("--- LLM routing finished. ---\n")


# ==============================================================================
# 2. VoiceProcessor 클래스 (Vosk 2-Recognizer 버전으로 수정)
# ==============================================================================
class VoiceProcessor:
    def __init__(self, vosk_model_path, device_index, dispatcher):
        self.VOSK_MODEL_PATH = vosk_model_path
        self.AUDIO_DEVICE_INDEX = device_index
        self.dispatcher = dispatcher
        self.stop_event = threading.Event()
        

    def start(self):
        self.main_thread = threading.Thread(target=self._vosk_main_loop)
        self.main_thread.start()
        print(">> Vosk Voice Assistant 시스템이 시작되었습니다. (Ctrl+C로 종료)")

    def stop(self):
        print("\n>> 시스템 종료 중...")
        self.stop_event.set()
        # self.q.put(None) 제거
        self.main_thread.join(timeout=2)
        print(">> 스레드가 정상적으로 종료되었습니다.")

    def _vosk_main_loop(self):
        pa, stream = None, None
        try:
            # ## 마이크 샘플레이트 설정은 TOPST 48000Hz
            HARDWARE_RATE = 48000

            # ## Vosk 모델 샘플레이트 설정은 모델이 요구하는 16000Hz
            VOSK_RATE = 16000

            # 리샘플링 비율 계산 (48000 -> 16000 이므로 3:1)
            DOWNSAMPLE_RATIO = HARDWARE_RATE // VOSK_RATE

            FRAMES_PER_BUFFER = 1024 * DOWNSAMPLE_RATIO
            WAKE_WORDS = ["hi telly", "hey telly"]
            COMMAND_TIMEOUT_S = 5

            model = Model(self.VOSK_MODEL_PATH)

            # ## Recognizer - Vosk가 요구하는 16000Hz로 초기화
            WAKE_WORD_GRAMMAR = json.dumps(WAKE_WORDS, ensure_ascii=False)
            wake_word_recognizer = KaldiRecognizer(model, VOSK_RATE, WAKE_WORD_GRAMMAR)
            command_recognizer = KaldiRecognizer(model, VOSK_RATE)

            # --- 오디오 스트림 시작 ---
            pa = pyaudio.PyAudio()
            # ## 스트림은 TOPST가 지원하는 48000Hz로 open
            stream = pa.open(rate=HARDWARE_RATE, channels=1, format=pyaudio.paInt16,
                             input=True, frames_per_buffer=FRAMES_PER_BUFFER,
                             input_device_index=self.AUDIO_DEVICE_INDEX)

            print(f">> 마이크 시작됨 (장치: {self.AUDIO_DEVICE_INDEX}, 하드웨어 샘플레이트: {HARDWARE_RATE})")
            print(f">> Vosk 모델 샘플레이트: {VOSK_RATE}")

            is_in_command_mode = False
            command_mode_timeout = 0
            print(f">> Wake word 대기 중... {WAKE_WORDS}")

            while not self.stop_event.is_set():
                # 48000Hz로 녹음된 원본 오디오 데이터 읽기
                data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)

                # ## 실시간 리샘플링 
                # 바이트 데이터를 numpy 배열로 변환
                audio_data_np = np.frombuffer(data, dtype=np.int16)
                # 3개의 샘플마다 1개씩만 선택하여 1/3로 줄임 (48000Hz -> 16000Hz)
                resampled_data_np = audio_data_np[::DOWNSAMPLE_RATIO]
                # 다시 바이트 데이터로 변환
                resampled_data_bytes = resampled_data_np.tobytes()

                # ## 리샘플링된 16000Hz 데이터를 Vosk에 전달
                if is_in_command_mode:
                    if command_recognizer.AcceptWaveform(resampled_data_bytes):
                        res = json.loads(command_recognizer.Result())
                        text = res.get("text", "").strip()
                        if text:
                            self.dispatcher.process_text(text)
                        is_in_command_mode = False
                        wake_word_recognizer.Reset()
                        print(f"\n>> 다시 wake word 대기 중... {WAKE_WORDS}")

                    if time.time() > command_mode_timeout:
                        print(">> 시간 초과. 다시 wake word 대기 중...")
                        is_in_command_mode = False
                        wake_word_recognizer.Reset()
                else:
                    if wake_word_recognizer.AcceptWaveform(resampled_data_bytes):
                        res = json.loads(wake_word_recognizer.Result())
                        text = res.get("text", "").strip()
                        if text in WAKE_WORDS:
                            print(f"\n[Wake Word 감지: '{text}']")
                            is_in_command_mode = True
                            command_mode_timeout = time.time() + COMMAND_TIMEOUT_S
                            command_recognizer.Reset()
                            print(f">> 음성 명령을 말씀하세요... ({COMMAND_TIMEOUT_S}초 내)")

        except Exception as e:
            print(f"[ERROR] 메인 스레드 에러: {e}")
        finally:
            if stream: stream.close()
            if pa: pa.terminate()
            print(">> 마이크 리소스 정리 완료.")


# ==============================================================================
# 3. 애플리케이션 실행 부분 (최종 수정)
# ==============================================================================
if __name__ == "__main__":
    VOSK_MODEL_PATH = "model"
    AUDIO_DEVICE_INDEX = 1 

    voice_processor = None
    try:
        dispatcher = CommandDispatcher(
            llm_control_url="http://127.0.0.1:8081/completion",
            llm_chat_url="http://127.0.0.1:8082/completion"
        )

        voice_processor = VoiceProcessor(
            vosk_model_path=VOSK_MODEL_PATH,
            device_index=AUDIO_DEVICE_INDEX, # audio_device_index -> device_index
            dispatcher=dispatcher
        )
        # --------------------------------

        voice_processor.start()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n>> Ctrl+C 감지. 종료 시퀀스 시작.")
    finally:
        if voice_processor:
            voice_processor.stop()