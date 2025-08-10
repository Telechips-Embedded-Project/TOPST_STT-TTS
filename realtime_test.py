# 파일: realtime_test.py

import sounddevice as sd
import queue
import sys
import json
from vosk import Model, KaldiRecognizer

DEVICE_INDEX = 1
# 마이크가 지원하는 샘플레이트로 설정 (48000)
SAMPLE_RATE = 48000

q = queue.Queue()

def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

# 1. Vosk 모델은 이제 '마이크의 샘플레이트'로 초기화해야 함
print(">> Vosk 모델 로딩 중...")
model = Model("model")
# KaldiRecognizer는 마이크에서 들어오는 오디오의 실제 샘플레이트를 알아야 함
rec = KaldiRecognizer(model, SAMPLE_RATE)
print(">> Vosk 모델 로딩 완료.")

# 2. sounddevice도 '마이크의 샘플레이트'로 열어야 함
try:
    with sd.RawInputStream(device=DEVICE_INDEX, samplerate=SAMPLE_RATE, blocksize=8000,
                           dtype='int16', channels=1, callback=callback):
        print(f"마이크가 켜졌습니다 (장치: {DEVICE_INDEX}, 샘플레이트: {SAMPLE_RATE}). 말해보세요.")
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "")
                if text:
                    print("결과:", text)
            # else:
            #     partial = json.loads(rec.PartialResult())
            #     if partial.get("partial"):
            #         # print("중간:", partial["partial"])
            #         pass
except KeyboardInterrupt:
    print("\n>> 프로그램 종료.")
except Exception as e:
    print(f"에러 발생: {e}")
