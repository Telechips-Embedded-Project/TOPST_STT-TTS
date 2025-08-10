#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <alsa/asoundlib.h>
#include <cjson/cJSON.h>

#define WAV_HEADER_SIZE 44
#define BUFFER_SIZE 4096

// JSON 추출 함수
char* extract_json(const char* input) {
    static char buf[1024];
        memset(buf, 0, sizeof(buf));
        char temp[1024];
        int j = 0;
        for (int i = 0; input[i] && j < sizeof(temp) - 1; ++i) {
                if (input[i] == '`' || input[i] == '\n' || input[i] == '\r' || input[i] == '\t') continue;
                temp[j++] = input[i];
        }
        temp[j] = '\0';
        const char* start = strchr(temp, '{');
        const char* end = strrchr(temp, '}');
        if (!start || !end || end <= start) return NULL;
        size_t len = end - start + 1;
        if (len >= sizeof(buf)) len = sizeof(buf) - 1;
        strncpy(buf, start, len);
        buf[len] = '\0';
        return buf;
}

void run_piper(const char* text) {
    char cmd[2048];
    const char* temp_input_file = "/tmp/tts_input.txt";

    // JSON 파싱
    const char* cleaned_json = extract_json(text);
    if (!cleaned_json) { printf("[ERROR] Invalid JSON format\n"); return; }
    cJSON* root = cJSON_Parse(cleaned_json);
    if (!root) { printf("[ERROR] JSON parsing failed\n"); return; }
    cJSON* comm = cJSON_GetObjectItemCaseSensitive(root, "Comment");
    const char* com_text = cJSON_IsString(comm) ? comm->valuestring : "";
    printf("[JSON RESULT COM] : %s\n", com_text);

    FILE* fp = fopen(temp_input_file, "w");
    if (fp == NULL) {
        perror("Failed to open temp input file");
        cJSON_Delete(root); // 에러 발생 시에도 메모리 해제
        return;
    }
    fprintf(fp, "%s", com_text);
    fflush(fp);
    int fd = fileno(fp);
    fsync(fd);
    fclose(fp);

    // --- com_text 변수를 모두 사용한 뒤 여기서 메모리 해제. ---
    cJSON_Delete(root);
    // -----------------------------------------------------------------

    snprintf(cmd, sizeof(cmd), "/home/root/TTS/run_tts.sh %s", temp_input_file);

    printf("Executing command: %s\n", cmd);
    system(cmd);
    printf("Shell script finished.\n");

    remove(temp_input_file);
}


int main(void) {
    const char* json_input1 = "```json\n"
        "{\n"
        "  \"Command\": \"Speak\",\n"
        "  \"Comment\": \"Success, This is the final working version.\"\n"
        "}\n"
        "```";

    printf("Starting TTS test program with direct ALSA playback.\n\n");
    run_piper(json_input1);
    printf("\nTTS test finished.\n");
    return 0;
}
