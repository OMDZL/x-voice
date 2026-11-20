# x-voice

> **Unofficial.** x-voice is an independent hobby project. It is not affiliated with, endorsed by, or supported by xAI. Grok Bot is a trademark of its owner. x-voice automates the Grok Bot desktop app on your own PC; check Grok Bot's terms before relying on it.

Starting a voice chat with a Grok Bot on my PC always takes a manual click: open the app, find the right bot, and press the voice button. That defeats the point of talking hands-free. Grok Bot has no documented hotkey, command, or link that starts a voice chat, so there's no built-in way to trigger one by voice. x-voice fills that gap with a small local app that listens for a wake phrase entirely on my PC, without recording or sending any audio, then opens a dedicated voice bot and starts the call.

You do not install Python. You download the app, run it, and fill in the settings window.

## Before you use it

- **Early, AI-built hobby project.** I built x-voice with AI coding tools and use it daily, but it has been tested on one PC. Use it at your own risk. There is no warranty (see the [MIT License](LICENSE)) and no promise of support.
- **Anyone can say the wake phrase.** A TV, a video, or someone on a call saying it can start a voice chat, and Grok Bot will then hear your room. Raise **How sure**, use **Pause**, or pick a less common phrase if that matters to you.
- **Grok Bot updates may break it.** x-voice depends on Grok Bot's link and button names, which can change without notice. If something no longer matches, x-voice clicks nothing and says why in the status line.

## Download and run

The app is a folder with `x-voice.exe` inside. The rest of the folder is part of the app. Leave those files next to the exe.

1. Open this repository's **Releases** page. Under **Assets** in the latest release, download **x-voice-windows.zip**. That is the app. Ignore the two **Source code** files: GitHub adds them to every release automatically, and they will not run.
2. Right-click **x-voice-windows.zip** and choose **Extract All**. You get a folder named `x-voice`.
3. Open that folder and double-click **x-voice.exe**. Do not move the exe out of the folder.

### Newest build (optional)

Every change to `main` is also built on GitHub Actions. Those builds can be newer than the latest release, and they need a GitHub sign-in to download.

1. Sign in to GitHub, open this repository, and click **Actions**.
2. Click **Build Windows app** on the left, then the latest run with a green check.
3. At the bottom, under **Artifacts**, download **x-voice-windows**.
4. GitHub wraps that download in a zip of its own, so extract it twice: once to get `x-voice-windows.zip`, then that zip to get the `x-voice` folder.

### If Windows says it protected your PC

The app is not signed, so SmartScreen warns the first time.

1. Click **More info**.
2. Click **Run anyway**.

That warning is Windows being careful about a new program. It is the same exe built by this repository's GitHub Actions. Only download x-voice from this repository's Actions or Releases pages, never from a copy someone sends you.

## Settings window

The window opens the first time, because the bot id is not filled in yet. Set:

- **Wake phrase.** It starts on **Computer**. That model also hears "hey computer". The other built-in phrases are still in the list, including hey jarvis. **Custom wake word file (.onnx)…** lets you pick a file on this PC. x-voice checks it and copies it into `%APPDATA%\x-voice\models`. It does not download the file.
- **Grok Bot id.** The id of the bot that x-voice should open. The quickest way to get it is to ask your voice bot in Grok Bot: "What is your bot ID?", then copy and paste the answer. If x-voice later says Grok Bot did not switch to the voice bot, get the id from the share link instead: click the bot's name, choose **Share**, then **Copy link**, and paste the whole link. x-voice keeps the id and drops the rest of the link.
- **Microphone.** **Windows default**, or pick one from the list. **Refresh** updates the list. **Test mic** shows a short level meter. Nothing from that test is saved.
- **How sure.** This is the sensitivity slider. A higher number means x-voice must be more sure before it starts a call, so a television or someone saying the word in passing starts fewer calls. A lower number makes it easier to trigger, and also easier to trigger by mistake. Computer is a common word, so a new install starts at **0.75**, and the score has to stay that high for three moments in a row (about a quarter of a second). The other phrases start at **0.50** and can trigger on one moment. After you pick a phrase, you can still move the slider, then click **Save**. If Computer starts when you did not say it, move How sure up, toward 0.85 or 0.90. If it misses you, move it down a little, toward 0.60.
- **Cooldown.** Seconds to wait after a call, or after a click that did not start one. The starting value is 10.
- **Play a chime** when the phrase is accepted.
- **Show in the system tray.** Off until you turn it on.
- **Start with Windows.** Off until you turn it on. It adds a startup entry for your Windows user only. It does not ask for an administrator password.

Click **Save**. Listening starts when the bot id is filled in. Change any of these later and click **Save** again. You do not download the app again.

If the saved settings file cannot be read, x-voice opens with the default settings, keeps the old file as `config.toml.invalid` next to it, and says so in the status line.

**Pause** stops listening and releases the microphone. **Resume** starts again. **Quit** closes x-voice.

### Tray

Turn on **Show in the system tray** and click **Save**. The icon sits by the clock.

- The tooltip says whether x-voice is listening or paused.
- Right-click the icon for **Open settings**, **Pause listening** or **Resume listening**, and **Quit**.
- Closing the window leaves x-voice running in the tray.

With the tray turned off, closing the window quits.

### Microphone permission

Windows has a switch called **Let desktop apps access your microphone**. If x-voice cannot open the microphone, or the test meter stays empty because Windows is sending silence, the window says so and shows **Open microphone settings**. That button opens the Windows privacy page. Turn the switch on, then click **Test mic** again.

If the microphone you picked is unplugged, x-voice switches to the **Windows default** and tells you in the status line.

## What it does while it listens

x-voice keeps a short stretch of audio in memory, scores it, and drops it. It does not write a recording, keep a transcript, or use the network. The wake-word files are already inside the app folder.

When the phrase is accepted, x-voice opens your bot with a Grok Bot link that carries the word `x-voice`. Grok Bot ignores a link with no text, so the word is needed. Grok Bot switches to that bot and puts the word in its message box. Sometimes it first asks **Add Message for …?**. x-voice presses **Confirm** only when that box shows `x-voice`, and never ticks **Don't show again**. Seeing exactly `x-voice` in the message box is how x-voice knows your voice bot is on screen. It then removes that word and clicks **Start voice chat**. If the word never arrives, or the box holds anything else, x-voice clicks nothing. It only touches the Grok Bot window. If that window or that button is missing, it says so and does nothing else. If a voice chat is already running, it does not click **End** and it does not start a second call. If the voice bot's message box already holds your own text, x-voice leaves it alone, says so in the status line, and does not start a call. Listening stays off until the call ends, then the cooldown runs.

Grok Bot needs to be installed and signed in. The first time, Windows may also ask to allow the microphone. Choose **Yes**.

## For development

This section is for changing the program. The download above is the way to use x-voice.

The supported toolchain is 64-bit Python 3.11 on 64-bit Windows 10 or 11. From the project folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --require-hashes -r requirements.lock
python -m xvoice.setup_models
python -m xvoice
```

`python -m xvoice` opens the same settings window. Settings still go to `%APPDATA%\x-voice\config.toml`.

Useful commands:

- `python -m xvoice --console --config config.toml` runs in the terminal. Copy `config.example.toml` to `config.toml` first.
- `python -m xvoice --list-mics` prints input devices.
- `python -m xvoice --self-test` loads the hey jarvis and Computer models and the settings file, then exits. It does not open the microphone.
- `python -m pytest` runs the unit tests. Install `requirements-dev.txt` first.

`python -m xvoice.setup_models` is the only command that downloads anything. The running app does not. The Windows build does that download on the build machine and packs the model files into the zip.

The build is a folder, not a single file. onnxruntime's DLLs are unreliable inside a one-file exe. GitHub Actions on `windows-latest` runs `x-voice.spec` with Python 3.11, zips `dist\x-voice`, uploads the artifact, and runs `x-voice.exe --self-test`. Pushing a version tag such as `v0.2.0` or `0.2.0` also attaches that zip to a GitHub Release.

## License

x-voice's code and icon are under the [MIT License](LICENSE). The Windows download also bundles third-party models and libraries under their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The bundled openWakeWord phrase models (hey Jarvis, Alexa and others) are **non-commercial** (CC BY-NC-SA 4.0). The default "Computer" model is MIT.
