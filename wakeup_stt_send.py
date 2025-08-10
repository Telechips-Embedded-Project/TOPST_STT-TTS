import pvporcupine
import pyaudio
import struct
import queue
import json
import time
import threading
from vosk import Model, KaldiRecognizer
import socket

# --- 설정값 (이 부분을 사용자 환경에 맞게 수정하세요) ---
ACCESS_KEY = "qvg3+n8HIzQe1zCVVhps8yXTNYjlGO52eQ7RTk9T5/E90OS7+KespA=="
KEYWORD_PATH = "porcupine/Hi-Telly_en_raspberry-pi_v3_0_0.ppn"  # 플랫폼에 맞는 .ppn 파일 경로
VOSK_MODEL_PATH = "model"
AUDIO_DEVICE_INDEX = 1      # sounddevice에서 확인한 USB 마이크의 인덱스 번호
WAKE_WORD = "Bumblebee"     # 사용하는 키워드에 맞게 수정

# --- 전역 변수 ---
# 두 스레드 간의 통신을 위한 큐와 플래그
audio_q = queue.Queue()
recognize_now = False

def send_text_to_pi1(text):
    HOST = '192.168.1.111'
    PORT = 60002
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(text.encode('utf-8'))
            print(">> Pi1에게 텍스트 전송 완료:", text)
    except Exception as e:
        print(">> 전송 실패:", e)

# [수정됨] 이 스레드는 이제 마이크를 직접 열지 않고, 큐에서 데이터를 받기만 합니다.
def wake_word_and_vosk_processor():
    """
    오디오 큐에서 데이터를 받아 Porcupine과 Vosk를 모두 처리하는 단일 프로세서 스레드
    """
    global recognize_now

    porcupine = None
    recognizer = None
    
    try:
        # Porcupine 초기화
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=[KEYWORD_PATH]
        )
        print(">> Porcupine 엔진 초기화 성공")
        
        # Vosk 모델 로드 및 Recognizer 초기화
        # Porcupine의 샘플레이트(16000)를 사용합니다.
        model = Model(VOSK_MODEL_PATH)
        recognizer = KaldiRecognizer(model, porcupine.sample_rate)
        print(">> Vosk 모델 로드 성공")

        print(f">> Wake word 대기 중... ('{WAKE_WORD}')")
        
        while True:
            # 큐에서 오디오 데이터 가져오기
            pcm_data = audio_q.get()
            
            # Wake word 감지 모드
            if not recognize_now:
                pcm = struct.unpack_from("h" * porcupine.frame_length, pcm_data)
                result = porcupine.process(pcm)
                if result >= 0:
                    print(">> Wake word 감지됨!")
                    recognize_now = True
                    # Wake word 감지 후 약 5초간 음성 인식 시도
                    recognition_timeout = time.time() + 5
            
            # 음성 인식 모드
            else:
                if recognizer.AcceptWaveform(pcm_data):
                    res = json.loads(recognizer.Result())
                    text = res.get("text", "")
                    if text.strip():
                        print("[인식 결과]:", text)
                        send_text_to_pi1(text)
                    
                    # 다시 Wake word 대기 모드로 전환
                    recognize_now = False
                    recognizer.Reset()
                    print(f">> 다시 wake word 대기 중... ('{WAKE_WORD}')")

                # 타임아웃 처리
                if time.time() > recognition_timeout:
                    print(">> 시간 초과. 다시 wake word 대기 중...")
                    recognize_now = False
                    recognizer.Reset()

    except pvporcupine.PorcupineError as e:
        print(f"Porcupine 에러 발생: {e}")
    except Exception as e:
        print(f"처리 스레드에서 에러 발생: {e}")
    finally:
        if porcupine is not None:
            porcupine.delete()

# [새로 추가됨] 이 스레드는 오직 마이크를 열고 큐에 데이터를 넣는 역할만 합니다.
def audio_capture_thread():
    """
    PyAudio를 사용해 마이크 입력을 받고 큐에 데이터를 넣는 스레드
    """
    pa = None
    stream = None
    
    try:
        # Porcupine은 16000Hz, 512 프레임으로 고정되어 있음
        SAMPLE_RATE = 48000 
        FRAMES_PER_BUFFER = 512

        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=FRAMES_PER_BUFFER,
            input_device_index=AUDIO_DEVICE_INDEX
        )
        print(f">> 마이크 시작됨 (장치: {AUDIO_DEVICE_INDEX}, 샘플레이트: {SAMPLE_RATE})")

        while stream.is_active():
            # 마이크에서 오디오 데이터 읽기
            pcm_data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
            # 큐에 데이터 넣기
            audio_q.put(pcm_data)

    except IOError as e:
        # 마이크 샘플레이트 문제일 가능성이 높음
        if e.errno == -9997:
             print("!!! [에러] 마이크가 16000Hz 샘플레이트를 지원하지 않습니다. !!!")
             print("arecord -D hw:1,0 --dump-hw-params 로 지원 샘플레이트를 확인하세요.")
        else:
             print(f"마이크 IO 에러 발생: {e}")
    except Exception as e:
        print(f"오디오 캡쳐 스레드에서 에러 발생: {e}")
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        if pa is not None:
            pa.terminate()
        print(">> 마이크 리소스 정리 완료.")


if __name__ == "__main__":
    # 이제 두 개의 스레드는 생산자-소비자 관계로 동작합니다.
    capture_thread = threading.Thread(target=audio_capture_thread)
    processor_thread = threading.Thread(target=wake_word_and_vosk_processor)

    capture_thread.start()
    processor_thread.start()

    capture_thread.join()
    processor_thread.join()
