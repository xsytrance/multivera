#!/bin/bash
cd /home/xsyvps/.openclaw/workspace/multivera
source .venv/bin/activate
export TELEGRAM_BOT_TOKEN
export OLLAMA_HOST=100.94.216.114:11434
export OLLAMA_MODEL=llama3.1:8b
python hackermouth_telegram_bot.py
