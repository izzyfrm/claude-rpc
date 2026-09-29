@echo off
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --name ClaudeRPC --icon assets/logo.ico --add-data "settings.html;." --add-data "assets/logo.ico;assets" claude_rpc.py
echo Built dist\ClaudeRPC.exe
