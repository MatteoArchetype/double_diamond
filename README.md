# Double Diamond Research Runtime

Double Diamond is a local research workspace for turning an open question into a traceable research decision.

It is designed for questions such as:

- How might AI change the work of middle-management insurance workers?
- How might healthcare change as a result of AI?
- What would make a school playground more usable during hot weather?

Start with a question, collect source material, retain the passages that matter, record what those passages support and where uncertainty remains. The workspace guides the research through the Double Diamond method and keeps the evidence, interpretations, decisions, and limits connected.

## What you can do

- Create a research case around any question.
- Search registered research publications through Crossref.
- Add sources you already know about and keep a shortlist for later review.
- Upload and retain research files locally, including PDFs, Word documents, text, Markdown, transcripts, video, and audio.
- Review a passage or short excerpt with its original location and surrounding context before using it as evidence.
- Mark invented material as synthetic so it cannot be confused with real-world evidence.
- Work through Discover, Define, Develop, and Deliver with explicit reviews between meaningful changes.
- Compare interpretations and alternatives rather than jumping from one source to a conclusion.
- Produce a readable report that retains evidence links, limitations, unknowns, and the next research questions.

## How the workflow fits together

| Phase | What you do | What you save |
| --- | --- | --- |
| **Discover** | Explore sources, perspectives, and gaps in what you know. | Reviewed evidence and observations. |
| **Define** | Decide which problem is worth addressing and what success would look like. | A bounded problem frame, linked interpretations, uncertainties, and criteria. |
| **Develop** | Compare possible explanations, responses, or directions. | Competing alternatives, proposed tests, assumptions, and limitations. |
| **Deliver** | Evaluate the available evidence against the criteria you defined. | An evaluation, decision, unresolved criteria, and next research where needed. |

The workspace does not silently approve sources, move a case between phases, or turn an interpretation into a confirmed result. You review evidence and explicitly decide when the research is ready to progress.

## First time using it

1. Launch the workspace using the instructions below.
2. Choose **Start a research case** and enter the question you want to explore.
3. In **Discover**, select **Find and review sources**.
4. Search Crossref, add a source link, or upload a research file.
5. Save a passage from the source with its page number, section, paragraph, or recording timestamp. Check the surrounding context before approving it.
6. Return to the Research tab to record what the evidence suggests and what you still need to learn.

Choose **Create practice case** on the home screen to inspect a completed example with clearly labelled invented evidence and simulated decisions.

## Source material and evidence

The app keeps a distinction between a source you may want to use and evidence that you have reviewed.

| Step | Meaning |
| --- | --- |
| **Find or save a source** | You have found something potentially relevant. It has not been used as evidence yet. |
| **Review a passage** | You select exact wording, record where it appears, check the context, and explain why it relates to the case. |
| **Approve and save source** | The reviewed passage becomes evidence available to the research case. |

Uploads stay in the local workspace. PDFs use embedded text for search. Scanned PDFs need OCR before their text can be searched. Video and audio can be retained with a timestamped WebVTT or SRT transcript. The app uses a supplied transcript when searching recordings.

## Install and start

You need Python 3.10 or later.

1. Clone this repository or choose **Code → Download ZIP** and extract it.
2. Open a terminal in the extracted project folder.
3. Run the commands for your system.

### macOS and Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m dd_research_runtime.local_app
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m dd_research_runtime.local_app
```

The final command opens the workspace in your browser and also prints the private local link in case you want to open it yourself. Leave the terminal running while you use the workspace. Run that final command again whenever you want to reopen it. The link changes each time the app starts, so an old bookmark will not work. To print the link without opening a browser, add `--no-browser` to the command.

On macOS, once the installation steps above are done, you can instead double-click `Start Research.command`. If macOS refuses to open it the first time, right-click the file and choose **Open**.

## Where your work is stored

Each installation creates a `research-workspace` folder beside the application, wherever you launch it from. It holds your research cases and the application’s local records. To keep them somewhere else, start the app with `--workspace /path/to/folder`. Keep the private link printed at launch to yourself while the workspace is running.

The workspace can create case checkpoints for the research record. Uploaded originals and attached transcripts, unsaved drafts, and saved source leads remain local and are not included. The Backups tab shows each case's on-disk size by category and the size of the research database included in its checkpoint.

Browser checkpoint transfers are limited to 32 MiB. For larger checkpoints, run the checkpoint CLI from the application folder. Replace `<workspace>` with the workspace path, `<case-id>` with the saved case's ID, and `<checkpoint.zip>` with a new file path. On macOS and Linux:

```sh
.venv/bin/python -m dd_research_runtime.checkpoint_cli create "<workspace>/<case-id>/research.sqlite" "<checkpoint.zip>"
.venv/bin/python -m dd_research_runtime.checkpoint_cli restore-case "<checkpoint.zip>" "<workspace>"
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m dd_research_runtime.checkpoint_cli create "<workspace>\<case-id>\research.sqlite" "<checkpoint.zip>"
.\.venv\Scripts\python.exe -m dd_research_runtime.checkpoint_cli restore-case "<checkpoint.zip>" "<workspace>"
```

`restore-case` verifies the checkpoint and adds it to the existing browser workspace as a separate case. It does not replace existing cases or renew historical approvals. Checkpoints contain plaintext research data; keep them private.

To print an operator-safe workspace health summary without opening the browser, run:

```sh
python3 -m dd_research_runtime.local_app --diagnostics --workspace /path/to/research-workspace
```

The summary includes case counts, workspace writability and storage usage. It does not include case titles, research content, absolute workspace paths or private launch tokens. The same summary can be downloaded from the Workspace home page.

## Run the tests

Use the same Python environment to install the test requirements and run the suite.

```sh
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python run_tests.py
```

## Licence

Copyright (c) 2026 Matteo. All rights reserved. The source is visible for reference only; see [LICENSE](LICENSE).
