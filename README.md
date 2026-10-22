# KingofThieves-TAS-ENG

TAS (*tool-assisted speedrun*) tool for **King of Thieves**, played on the
**MEmu** Android emulator, on Windows.

You place the jumps of a run on a timeline. The tool replays them to the exact
frame, and you shift by one frame, replay, start again, until the run gets
through. It attaches to the game with [Frida](https://frida.re) to read the
hero's position and control the game's time, and it taps into the game through
adb.

> **Usage rule: only on your own base, never against another player's.**
>
> Personal project, not affiliated with ZeptoLab. Use it at your own risk.

*Version française : <https://github.com/Ant6508/KOT_TAS>.*

## What you need

- Windows 10 or 11, 64-bit.
- An internet connection, for the installation and the first launch.
- About 3 GB of disk space (MEmu and the game).

## Installation

Allow half an hour. Each step ends with a check: only move on to the next one
if it passes.

### 1. MEmu

1. Download MEmu from <https://www.memuplay.com> and install it with the
   default options.
2. Launch MEmu and wait for the Android home screen.
3. Open MEmu's **Settings** (gear icon in the right-hand bar):
   - **Engine** tab: turn on **Root mode**;
   - **Display** tab: pick the resolution **1600 × 900** (preset or custom
     resolution), DPI **300**.
4. Save, then restart MEmu when it offers to.

Why: the tool needs root rights on the emulator to run frida-server there,
and it taps the center of a 1600 × 900 screen, the only resolution it has been
tested on.

**Check:** after the restart, MEmu's settings still show Root mode on and
1600 × 900.

### 2. King of Thieves 2.84.1

1. In MEmu, open the **Play Store**, sign in with a Google account and install
   **King of Thieves**.
2. Launch the game once, up to your base, so it finishes downloading its data.

**Check:** in MEmu, Android *Settings* → *Apps* → *King of Thieves*: the
version shown must be **2.84.1**.

The tool is tied to this exact version (versionCode 4755794): it reads the
game's memory at addresses recorded on 2.84. With any other version, it refuses
to start rather than read garbage. If the Play Store installs a newer version,
the tool won't work until those addresses have been updated (see
[Limitations](#limitations)).

### 3. Python

1. Download the Python Windows installer from
   <https://www.python.org/downloads/windows/>: version 3.10 or newer (the
   tool is tested on 3.14).
2. Run the installer. **On the first screen, tick "Add python.exe to
   PATH"**, then click *Install Now*.
3. If you go through *Customize installation*, keep **"tcl/tk and IDLE"**
   ticked: the workshop window needs it.

**Check:** open a **new** terminal (Start menu, type `PowerShell`, Enter) and
type:

```
python --version
```

It must answer `Python 3.x.y` with x equal to 10 or more. If it opens the
Microsoft Store or says the command isn't found, the "Add python.exe to PATH"
box wasn't ticked: run the installer again, choose *Modify*, then *Next*, tick
**"Add Python to environment variables"** and confirm. Then open a new
terminal.

### 4. Get the project

Either:

- **Without Git**: on <https://github.com/Ant6508/KingofThieves-TAS-ENG>,
  green **Code** button → **Download ZIP**. Right-click the downloaded file →
  *Extract All…*. The ZIP contains a `KingofThieves-TAS-ENG-main` folder:
  that's the project folder. Put it wherever you like, for example
  `C:\KingofThieves-TAS-ENG`.
- **With Git** (<https://git-scm.com/download/win>), handier to get updates:

  ```
  git clone https://github.com/Ant6508/KingofThieves-TAS-ENG C:\KingofThieves-TAS-ENG
  ```

All the following commands are typed in a terminal opened **in the project
folder**:

```
cd C:\KingofThieves-TAS-ENG
```

**Check:** `dir` lists, among others, `controller`, `scripts` and
`pyproject.toml`.

### 5. Python environment

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The first command creates a Python of the project's own, in `.venv`. The
second installs Frida 17.18.0 and pytest into it. All the project's commands
then call **this** Python, `.venv\Scripts\python.exe`, without activation: no
need for `Activate.ps1`, which PowerShell often blocks.

**Check:** the last line printed starts with `Successfully installed` and
mentions `frida-17.18.0`.

### 6. Check the installation

```
.venv\Scripts\python.exe -m pytest -q
```

**Check:** the last line says `N passed`, with no `failed` or `error`. These
tests touch neither the game nor MEmu: they check that the project is complete
and that Python is properly installed.

### 7. First launch

1. Launch MEmu, then King of Thieves, up to your base.
2. In the terminal:

   ```
   .venv\Scripts\python.exe scripts\atelier.py
   ```

   The **TAS Workshop** window opens.
3. Click **▶ Try (relaunch)**. The tool relaunches the game and attaches to
   it.

   **The very first time**, it first installs frida-server on MEmu, the small
   program through which Frida reads the game: the terminal prints
   `frida-server missing: downloading...`, then the tool copies it into MEmu
   and starts it. Allow a minute. The following times, it's immediate.
4. When the window tells you to navigate to the starting screen, bring the
   game back to the starting screen of the run in your base, then click
   **Ready**.

The tool finds the `adb` shipped with MEmu on its own: no need to install the
Android SDK.

**Check:** after **Ready**, the run plays out in MEmu and the workshop's
timeline fills up. If an error message shows up, see
[Troubleshooting](#troubleshooting).

## Usage

### The workshop: placing a run

```
.venv\Scripts\python.exe scripts\atelier.py
.venv\Scripts\python.exe scripts\atelier.py films\my_run.json
```

A window to put next to MEmu. The banner always says the state of the movie
and why: **Draft** (jumps changed since the last try), **Tried** (trace up to
date since a relaunch, ready to freeze), **Frozen** (saved, read-only). Each
try relaunches the game; you navigate to the starting screen and click
**Ready**. A frozen movie is replayed twice in a row: **Replay** (with
relaunch), then **Replay again** (without).

To look at the game at a precise frame, set the marker then
**⏸ Breakpoint at marker**: Try, +10 and Play to the end stop there, and Play
to the end moves on to the next breakpoint. A breakpoint isn't part of the
movie. While a run is playing, **⏸ Pause** freezes the game where it is (to
within a second).

Your movies are saved in `films\`: they replay **your** base, and stay with
you (the folder is ignored by git).

### The keyboard editor and the brute force

```
.venv\Scripts\python.exe scripts\tas.py
.venv\Scripts\python.exe scripts\tas.py --film=films\my_run.json --label="my base"
```

The old console editor. The key help is shown at launch: F1 starts a session
(game relaunch), F2 replays quickly, F3 validates with a relaunch, **F4 finds
on its own a pair of jumps that reaches the target** (brute force), F5 saves.

### The autoclicker

Taps a fixed point at a regular interval. It only goes through adb, without
Frida.

```
.venv\Scripts\python.exe scripts\autoclic.py X Y --intervalle 0.2 --taps 100
.venv\Scripts\python.exe scripts\autoclic.py X Y --intervalle 0.2 --duree 120
```

- `X Y`: the point, in **Android screen** coordinates (1600 × 900), not MEmu
  window ones: in the window, subtract 33 px vertically (the tab bar).
- `--intervalle`: seconds between two taps. An adb tap already takes about
  0.15 s: **0.2 s** is the recommended rate.
- A limit is **mandatory**: `--taps N` (number of taps), `--duree S`
  (seconds), or both.
- **Ctrl+C** stops it at any time; it always prints its summary.

### Replaying a movie and checking it matches

A try takes two commands, because navigating in the game is manual:

```
.venv\Scripts\python.exe scripts\rejeu.py films\my_run.json --relance
.venv\Scripts\python.exe scripts\rejeu.py films\my_run.json
```

The first one relaunches the game; you navigate to the starting screen. The
second one replays the movie and says whether the replay is identical to the
recording. On a movie's very first try, add `--ecrire` to the second command:
it stores the reference fingerprint in the movie, and the following tries are
compared against it.

### Several MEmu instances

With a single instance open, the tool finds it on its own. With several, it
refuses to guess and lists the devices. Pick the instance **in the same
terminal, before launching**:

```
$env:KOT_SERIAL="127.0.0.1:21503"
.venv\Scripts\python.exe scripts\atelier.py
```

The first MEmu instance answers on `127.0.0.1:21503`, the second on
`127.0.0.1:21513`, and so on (+10 per instance). The variable only holds for
that terminal; to clear it: `Remove-Item Env:KOT_SERIAL`.

### Updating

With Git: `git pull` in the project folder. With the ZIP: download the new ZIP
and replace the files, keeping your `films` folder. Either way, then run again:

```
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `python` isn't recognized, or the Microsoft Store opens | Python isn't in the PATH | Step 3: run the installer again, *Modify*, "Add Python to environment variables", then open a new terminal |
| `frida X is installed, but the tool expects 17.18.0` | Another version of Frida was installed in `.venv` | `.venv\Scripts\python.exe -m pip install "frida==17.18.0"` |
| `adb not found (...)` | MEmu isn't installed, or installed in a way the tool doesn't recognize | Install MEmu (step 1). Otherwise, add the folder containing `adb.exe` to the PATH (in MEmu's folder, `MEmu` subfolder) |
| `no adb device connected: launch MEmu.` | MEmu is closed, or not started yet | Launch MEmu, wait for the home screen, try again |
| `several adb devices connected (...)` | Several MEmu instances are open | Close the ones you don't use, or set `KOT_SERIAL` (see [Several MEmu instances](#several-memu-instances)) |
| `unexpected game version: ...` | King of Thieves isn't on 2.84.1 | The tool only works with 2.84.1 (see [Limitations](#limitations)) |
| `com.zeptolab.thieves.google isn't running. Launch the game in MEmu.` | The game is closed | Launch King of Thieves in MEmu |
| `frida-server 17.18.0 missing and could not be downloaded` | No internet, or GitHub unreachable | Check your connection and try again. Otherwise, follow the message's instructions: download the archive by hand, unpack it with 7-Zip, put the file where it says |
| `attach failed after 15 tries`, with `frida-server` or `closed` in the last error | frida-server doesn't start: Root mode off, or an old frida-server of another version left in MEmu | Check Root mode (step 1). Otherwise, restart MEmu then, in a terminal, `& "C:\Program Files\Microvirt\MEmu\adb.exe" shell rm /data/local/tmp/frida-server` (adjust the path if MEmu is installed elsewhere): the tool will reinstall the right version |
| `the agent refuses to start. Missing symbols or invalid offsets` | Right after a relaunch, that's normal: the tool retries on its own. If it persists, the game isn't exactly 2.84.1 | Check the game version (step 2) |
| The step 6 tests fail | Incomplete installation | Redo step 5, then step 6 |

## Limitations

- **King of Thieves 2.84.1 only.** The tool reads the game's memory at addresses
  recorded on this version; with every game update, they have to be found
  again.
- **MEmu on Windows only, at 1600 × 900.**
- The interface and messages are in English, but the code itself (names,
  comments, docstrings) is in French.
- The code comments often refer to `NOTES.md`: that's the author's reverse
  engineering notebook, which isn't published.

## License

MIT: see [LICENSE](LICENSE).
