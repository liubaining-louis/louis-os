FROM vllm/vllm-openai:latest

ENV MODEL_ID=Qwen/Qwen2.5-7B-Instruct \
    MAX_MODEL_LEN=8192 \
    GPU_MEMORY_UTILIZATION=0.90 \
    PORT=8080

COPY start.sh /opt/louis/start.sh
RUN chmod +x /opt/louis/start.sh

ENTRYPOINT ["/opt/louis/start.sh"]
