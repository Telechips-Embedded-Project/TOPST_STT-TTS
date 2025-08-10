#!/bin/sh

INPUT_TEXT_FILE=$1

if [ ! -f "$INPUT_TEXT_FILE" ]; then
    echo "Error: Input file not found at $INPUT_TEXT_FILE"
    exit 1
fi

TEXT_TO_SPEAK=$(cat "$INPUT_TEXT_FILE")

PIPER_APP="/home/root/TTS/piper/piper"
PIPER_MODEL="/home/root/TTS/piper/en_US-ryan-medium.onnx"
SPEAKER_DEVICE="plughw:0,0"

echo "Speaking directly via pipe: $TEXT_TO_SPEAK"

# --- 이 부분이 이 모든 문제의 최종 해결책입니다 ---
# 1. echo로 텍스트를 piper의 stdin으로 전달
# 2. piper는 --output_file - 옵션으로 오디오 데이터를 자신의 stdout으로 출력
# 3. aplay는 - 옵션으로 자신의 stdin으로 들어오는 오디오 데이터를 바로 재생
#    aplay에게 오디오 형식을 명시적으로 알려주어야 함
#    -f S16_LE (16bit signed little-endian), -r 22050 (rate), -c 1 (mono)
echo "$TEXT_TO_SPEAK" | $PIPER_APP --model $PIPER_MODEL --output_file - | aplay -D $SPEAKER_DEVICE -f S16_LE -r 22050 -c 1

# ---------------------------------------------------

echo "Playback finished. Exit code: $?"
