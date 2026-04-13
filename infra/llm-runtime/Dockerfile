FROM ollama/ollama:0.11.4

COPY start.sh /usr/local/bin/start-ollama.sh
RUN chmod +x /usr/local/bin/start-ollama.sh

EXPOSE 11434

ENTRYPOINT ["/usr/local/bin/start-ollama.sh"]
