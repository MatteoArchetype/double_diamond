# Double Diamond Research Runtime

Double Diamond is a local research workspace. Create a case around your own question, collect and review evidence, and work through Discover, Define, Develop, and Deliver. You decide when to approve evidence and move between phases.

## Install and start

1. Get access to this private repository, then clone it or choose **Code → Download ZIP** and extract it.
2. Install Python 3.10 or later. Open a terminal in the project folder and run the commands for your system.

**macOS and Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m dd_research_runtime.local_app
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m dd_research_runtime.local_app
```

3. Open the private link printed in the terminal. Keep the terminal running while you use Double Diamond. Run the last command again whenever you want to reopen it.

## Start a case

Use **Start a research case** for your own question or **Create practice case** to explore the workflow with invented evidence. Your cases start fresh and are stored in the local `research-workspace` folder. The link printed in the terminal grants access to that running workspace. Keep it private.

Under **Sources**, you can search for registered publications through Crossref, save links for later, and review individual passages. You can upload PDF, DOCX, text, Markdown, WebVTT and SRT, plus MP4, MOV, WebM, MP3, M4A, WAV and OGG. PDF search uses embedded text. Scanned pages require OCR first. Recordings can be saved with an attached timestamped transcript for search. Case checkpoints exclude uploaded originals and attached transcripts.

## Run the tests

Use the same Python interpreter as above to install `requirements-test.txt` and run `run_tests.py`. For example, on macOS or Linux:

```sh
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python run_tests.py
```
