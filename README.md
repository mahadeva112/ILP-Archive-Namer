# ILP Archive Namer

A local Windows app that produces **spec-compliant folder and file names** for
every category in *How to archive ILP content*, so nothing gets rejected by
Archives for a naming mistake.

It replaces the older single-page `Archieve code.html`, which covered only one
of the eight naming categories and validated nothing.

---

## Running it

**If Python 3.8+ is installed:** double-click

```
Run ILP Archive Namer.bat
```

It opens your browser and nothing else — the server runs behind the scenes with
no console window, and stops by itself a few seconds after you close the browser
tab. Nothing is installed, nothing goes on the network except the optional
YouTube title lookup, and the server listens on `127.0.0.1` only — no one else on
the network can reach it.

Add `--console` (or run the `.bat` from a terminal with it) to keep a visible
console window you can press Ctrl+C in.

**From a terminal:**

```bash
python server.py
```

Options: `--port 8737` to pin the port, `--no-open` to skip launching a browser,
`--no-auto-exit` to keep running after the browser tab closes.

Started from a terminal, the app keeps running until you press Ctrl+C. Started
with no console — `pythonw server.py`, the shortcut, or the `.exe` — it quits on
its own when the last browser tab closes, so it never lingers as an invisible
process. `--auto-exit` / `--no-auto-exit` override that either way.

**For a desktop icon you can pin**, double-click

```
Create Shortcut.bat
```

That puts an *ILP Archive Namer* shortcut with the app icon on your desktop and
in the Start menu. The shortcut targets `pythonw.exe` rather than the `.bat`,
because Windows only offers *Pin to taskbar* for shortcuts whose target is an
executable — and `pythonw` shows no console window. Close the browser tab to
stop the app.

Windows 10/11 blocks scripts from pinning things for you, so the last click is
manual: right-click the desktop shortcut → **Show more options → Pin to
taskbar**, or press Start, type `ILP Archive Namer`, right-click the result →
**Pin to Start**.

Add `-Console` (via `powershell -ExecutionPolicy Bypass -File ".\Create Shortcut.ps1" -Console`)
if you would rather have a minimised console window to press Ctrl+C in.

**To hand it to someone without Python**, build a single `.exe`:

```bash
pip install pyinstaller
```

then double-click `build_exe.bat`. The result is `dist\ILP-Archive-Namer.exe` —
one file, copy it anywhere, double-click, done. It is built `--noconsole`, so
it too shows only the browser and exits when the tab is closed.

**Updates.** Each time it starts, the app asks GitHub for the latest release
of `mahadeva112/ILP-Archive-Namer`. If it is newer, a bar at the top of the
page offers it. In the `.exe`, **Update now** downloads the release's
`ILP-Archive-Namer.exe`, checks its size and checksum, swaps it in for the
running file and restarts; the open tab reloads by itself. Run from Python,
the button opens the release page instead. With no internet, nothing is shown.
The update only works from 1.1.0 on: anyone still on 1.0.0 has to download
1.1.0 by hand once.

To publish an update: raise `__version__` in `namer/__init__.py`, write what
changed in `release-notes.txt` (shown under *What's new*), commit and push,
then double-click `release.bat`. It builds the `.exe` and creates the GitHub
release `v<version>` with it attached. It needs the GitHub CLI, signed in once
with `gh auth login`.

---

## What it does

**Create a name.** Pick one of the eight categories, fill the form, and get the
folder name plus every filename that belongs inside it. Paste a YouTube URL and
the video code and English title are pulled in automatically (title noise like
`| Sadhguru` and `#shorts` is trimmed, and you can edit the result). The app
tells you which NAS path the folder belongs in, per Appendix 2.

The name is shown in its labelled pieces rather than as one long string —
`SGYThin` / `xVbcVQApKig` / `A-Lesson-From-Guru-Nanak` / `09-Jul-2021`, each
captioned with the field that produced it. A swapped field or a wrongly cased
language code is then visible at a glance instead of having to be read
character by character. The pieces come from the builder itself, so the
breakdown can never disagree with the name that gets written to disk. Clicking
a piece jumps to the field behind it.

**Check an existing name.** Paste a folder name from the NAS. The app works out
which category it belongs to, breaks it into the same labelled pieces, and
flags every rule it breaks. Useful for auditing what is already archived.

A name that breaks the rules badly enough no longer matches its pattern at all
— which is exactly when you most need to be told what it was meant to be. So a
name that does not parse is read loosely: the app says which category it
*reads as* (never that it matches), marks the offending pieces, and reports
what is wrong with each, including the date, month and language-code formats
that a whole-string check cannot see.

Where the correction is unambiguous it offers one, built by the same engine
that generates new names, so it is guaranteed to pass. It is timid on purpose:
a video code copied from YouTube is never rewritten, an ambiguous date
(`03-10-2022` is either 3 Oct or 10 Mar) is left alone, and nothing is offered
unless the result validates clean. It is a suggestion to copy, never an
automatic rename.

**Create folder & add files.** Takes the name you just generated and builds it
on disk:

*Step 1 — create the folders.* Pick a destination (Browse opens a normal
Windows folder picker), preview exactly which folders would be created, then
create them. Running it twice is safe: existing folders and files are left
alone, and only what is missing gets added. Every run is recorded in
`history.jsonl` under `%LOCALAPPDATA%\ILP-Archive-Namer`; nothing extra is
left in the archive folder itself. A per-folder `manifest.json` (category,
fields, spec revision, every action taken) can be turned back on by setting
`"write_manifest": true` in `settings.json` next to that history file.

*Step 2 — add your files.* Point at the folder holding your finished wav /
docx / srt / mp4. Each file's role is guessed from its name and extension
(`Voice2 take.wav` → Voice 2, `render FB vertical.mp4` → Facebook MP4) and
every guess is a dropdown you can correct. **Dry run** shows precisely what
would be renamed and where, changing nothing. **Add files** then does it.

The safety behaviour is not optional:

- **Copy is the default.** Your originals stay where they are.
- **Move requires a separate tick-box** and is copy-then-verify-then-remove —
  the source is only deleted after the destination is confirmed byte-identical.
- **Nothing is ever overwritten** unless you explicitly choose *Replace*. The
  default on a name collision is to skip and tell you.
- **Nothing is ever deleted** other than a source file in confirmed move mode.
- A missing mandatory `Output*.mp4` is reported before you finish.
- A container mismatch (a `.mov` in the Output role) keeps the real extension
  and warns, rather than renaming it to `.mp4` and producing a broken file.
- Two files claiming the same role: the second is skipped and named, never
  silently dropped.

**History.** Every scaffold and ingest this machine has performed, logged to
`%LOCALAPPDATA%\ILP-Archive-Namer\history.jsonl`. If you generate a folder
name that was already archived from this machine, the app warns you before you
write it again.

**Reference.** Channel codes (Appendix 1), department codes, Indian language
codes, NAS destinations, and the naming rules — so nobody has to type a code
from memory. One search box covers every table, because nobody remembers which
of them a code lives in.

### Categories covered

| Spec | Category | Pattern |
|------|----------|---------|
| #1 | Dubbed YouTube (SGC / IFC) | `SGYThin_xVbcVQApKig_A-Lesson-From-Guru-Nanak_09-Jul-2021` |
| #2 | Other official Isha channel | `IECYThin_<code>_<Title>_07-Apr-2019` |
| #3 | Original currently unlisted | `SGLYThin_12-Mar-2021_<Title>_09-Jul-2021` |
| #4 | Department request | `IPC_How-To-Meditate_Tel_03-Oct-2022` |
| #5 | Sadhguru Exclusive | `SGEXhin0040_Realized-Beings-Ep-04-The-Rascal-Saint` |
| #6 | Instagram | `SGIGhin_CgTjVwqFBTQ_<Description>_07-Apr-2019` |
| #7 | Satsang (video / quote / guided meditation) | `Satsang-Jun-2022-Audio_GM_Chitshakti_Meditation-Peace_Tel` |
| — | Department backup | `Department-Backup-ILP-Sep-2021` |

---

## Layout

```
data/          the spec turned into data - edit these, not the code
  channels.json      Appendix 1 channel codes
  departments.json   department codes from "Video codes.png"
  languages.json     Indian language codes (ISO 639-2/B, 639-3 where needed)
  nas_routes.json    Appendix 2 NAS destinations
  template.json      the subfolder set from ARCHIVING TEMPLATE
namer/         the engine (all rules live here)
  slug.py            title -> hyphenated slug
  engine.py          the eight categories, validation, parsing
  fsops.py           scaffold, ingest, manifest, history
  registry.py        loads data/
web/           the UI (plain HTML/CSS/JS, no build step)
  index.html         the shell: five screens behind one rail
  styles.css         design tokens, dark and light
  app.js             renders the forms and whatever the engine returns
  mockup.html        static design mockup of the same UI, not served
assets/        app icon + the Pillow script that generated it
server.py      local stdlib HTTP server
mcp_server.py  MCP server: the engine as tools for Claude
tests/         golden tests
```

**When the archiving rules change, edit `data/*.json`.** Codes, NAS paths,
languages and the template folder set are all data. Only a change to a *naming
pattern* needs `namer/engine.py`.

---

## Using it from Claude (MCP)

`mcp_server.py` exposes the naming engine as an MCP server, so Claude Code or
Claude Desktop can build and check names with exactly the app's rules.
Standard library only, and every tool is read-only - nothing is created, moved
or renamed on disk.

| Tool | Does |
|---|---|
| `list_categories` | the eight categories, their fields, examples and NAS routes |
| `list_codes` | registered channel, department and language codes |
| `build_name` | folder name + inner file names for one item, with issues |
| `check_name` | checks an existing name; suggests a fix when it breaks a rule |
| `slugify_title` | English title -> hyphenated name slug |
| `lookup_video` | URL -> video code, platform, channel, and the YouTube title |

**Claude Code, in this folder:** `.mcp.json` already registers it. Open the
project, approve `ilp-archive-namer` when asked, and check it with `/mcp`.

**Claude Code, from anywhere:**

```bash
claude mcp add --scope user ilp-archive-namer -- python "D:\AI Automation\ILP-Archive-Namer\mcp_server.py"
```

**Claude Desktop:** add this to `claude_desktop_config.json` (Settings ->
Developer -> Edit Config) and restart:

```json
{
  "mcpServers": {
    "ilp-archive-namer": {
      "command": "python",
      "args": ["D:\\AI Automation\\ILP-Archive-Namer\\mcp_server.py"]
    }
  }
}
```

---

## Tests

```bash
python tests/run_all.py
```

- `test_golden.py` (101 checks) — every worked example printed in the spec, plus
  the naming rules, forbidden characters, the parser, the segment breakdown
  (which must always rebuild the name exactly), the loose reading of a broken
  name, the suggested corrections, and the error messages.
  **These are the contract**: if one fails, the tool is generating names
  Archives will reject.
- `test_fsops.py` (83 checks) — scaffold and ingest against real temp
  directories, including every destructive path: move refusing to run without
  confirmation, overwrite protection, conflict handling, duplicate roles,
  corrupt manifests, and path guards (drive roots, traversal, missing folders).

184 checks, all passing.

---

## Two things to confirm with Archives

These are genuine ambiguities in the source document, not bugs. The app takes
the reading that reproduces the spec's own examples, and says so in the UI.

1. **Channel prefix.** The spec says "3-digit channel code + 2-digit platform
   (YT)", but several Appendix 1 codes already contain the platform token
   (`SGYT`, `IFCYT`) while others do not (`IEC`, `IUC`). Taken literally,
   `SGYT` + `YT` would double it. The app stores an explicit `prefix_literal`
   per channel, which reproduces both published examples:
   `SGYT` → `SGYThin`, `IEC` → `IECYThin`. Confirm this is right for the
   channels with no example (`IUC`, `IFV`, `SOI`, `SGL`).

2. **Template subfolder names contain spaces** (`Video Output`,
   `Audio Project`, `Common files`) even though the naming rules forbid spaces.
   The app reproduces the shipped template verbatim. Confirm whether subfolder
   names are exempt from the no-spaces rule, or whether the template itself
   should be renamed.

Also: `IPC` appears in the spec's own category-#4 example but is not in the
department code screenshot. It is included in `departments.json` with a note.

---

## Not in this version

- **Bulk audit and rename** — point at a NAS directory and get a report of
  every non-conforming folder with a proposed fix, dry-run first. The
  groundwork is in place: `engine.parse_name()` already reverses a name back
  into its parts.
- **Media checks** — verify the WAV really is 24-bit/48 kHz mono, and the MP4
  really is an MP4, via `ffprobe`. Today a container mismatch is caught by
  extension only.
- **Shared history** — the duplicate-name check covers this machine only. A
  team-wide index would need somewhere shared to keep it.
- **Progress reporting on large copies** — a multi-GB master copies without a
  progress bar; the request simply takes as long as it takes.
