# Claude RPC

Shows what you're doing in Claude Code as Discord Rich Presence — the chat you're in, the model, the project, and how long you've been at it — with the Claude Code mascot as the image.

It runs quietly in the system tray and connects to Discord on its own. No window to keep open.

## Setup

1. Create an application at https://discord.com/developers/applications and name it **Claude Code** (that name shows after "Playing").
2. Run `ClaudeRPC.exe`. The settings page opens in your browser the first time.
3. Paste the Application ID. Done.

Open settings again any time from the tray icon (or run the exe again).

## Settings

- Show/hide model, chat, project folder, elapsed time
- Chat shows the session title or your latest message
- Idle timeout: presence clears when Claude Code hasn't been used for N minutes
- Custom image, hover text, and an optional button
- Start with Windows

Settings are stored in `%APPDATA%\claude-rpc\config.json`. The settings page is served only on `127.0.0.1:47823`.

## How it works

Claude Code writes each session to `~/.claude/projects/<project>/<session>.jsonl`. Claude RPC reads the most recently updated one every 5 seconds and sends the model, title, and last prompt to Discord over its local IPC pipe.

## Build

```
build.bat
```

Output: `dist\ClaudeRPC.exe`. Regenerate the logo with `python make_logo.py`.
