# Third-party notices

x-voice's own code is under the MIT License in `LICENSE`. The Windows download
also contains the third-party files and libraries listed here, under their own
licenses.

## Wake-word models

### "Computer" model

`computer_v2.onnx`, from the Home Assistant Wake Word Collection by Florian
Wartner, under the MIT License. The full notice is in
`third_party/wakewords/LICENSE.txt`.

### openWakeWord pre-trained models

The Windows download includes these model files from the openWakeWord project
by David Scripka (release v0.5.1):

- `melspectrogram.onnx`, `embedding_model.onnx` (shared audio features)
- `hey_jarvis_v0.1.onnx`, `alexa_v0.1.onnx`, `hey_mycroft_v0.1.onnx`,
  `hey_rhasspy_v0.1.onnx`, `timer_v0.1.onnx`, `weather_v0.1.onnx`

The openWakeWord project publishes its pre-trained models under the Creative
Commons Attribution-NonCommercial-ShareAlike 4.0 International license
(CC BY-NC-SA 4.0): https://creativecommons.org/licenses/by-nc-sa/4.0/

Under that license these models may not be used for commercial purposes.
x-voice is free and non-commercial. If you reuse x-voice commercially, use the
"Computer" model or a wake word you trained yourself, and remove these files.
Source: https://github.com/dscripka/openWakeWord

## Libraries

The download bundles Python 3.11, Tcl/Tk, and these open-source libraries.
Licenses are as published on PyPI for the pinned versions in
`requirements.lock`. Each library's source is available from PyPI and its
project page.

| Library | License |
|---|---|
| openWakeWord 0.6.0 (code) | Apache-2.0 |
| ONNX Runtime 1.32.0 | MIT |
| NumPy 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| SciPy 1.17.1 | BSD-3-Clause |
| scikit-learn 1.9.1, joblib 1.6.0, threadpoolctl 3.8.0 | BSD-3-Clause |
| sounddevice 0.5.6 (with PortAudio) | MIT |
| pywinauto 0.6.9 | BSD-3-Clause |
| pywin32 312 | PSF |
| comtypes 1.5.0 | MIT |
| pystray 0.19.5 | LGPL-3.0 (source: https://github.com/moses-palmer/pystray) |
| Pillow 13.0.0 | MIT-CMU |
| protobuf 7.36.2 | BSD-3-Clause |
| flatbuffers 25.12.19, requests 2.34.2 | Apache-2.0 |
| tqdm 4.70.1 | MPL-2.0 AND MIT |
| cffi 2.1.1 | MIT-0 |
| six 1.17.0 | MIT |
| Python 3.11, Tcl/Tk 8.6 | PSF-2.0; Tcl/Tk license |

pystray is included unmodified as a separate library. Under the LGPL you may
replace it with your own build: install a different pystray and rebuild with
`x-voice.spec`, as described in the README's development section.

## Icon

The x-voice icon is original artwork by the project owner, included under the
same MIT License as the code.
