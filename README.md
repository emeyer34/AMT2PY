## Table of Contents

- [Python NSNSD Acoustic Monitoring Toolbox (AMT)](#python-nsnsd-acoustic-monitoring-toolbox-amt)
- [Prepare your machine](#prepare-your-machine)
  - [Prerequisites](#prerequisites)
  - [One-time setup](#one-time-setup)
  - [Pulling updates](#pulling-updates)
- [Scripts](#scripts)
- [Sound Level Meters](#sound-level-meters)
- [Acknowledgments](#acknowledgments)

# Python NSNSD Acoustic Monitoring Toolbox (AMT)

This repository mirrors the **NSNSD Acoustic Monitoring Toolbox (AMT)** — originally a C# application used to process, visualize, and summarize acoustic data. These tools port core AMT workflows to **Python** for easier maintenance and updates.

This mostly replaces the [Type1-821envtools](https://github.com/emeyer34/Type1-821envtools) repository. That toolbox was meant to transition 821 and HOBO data into AMT, which required reformatting raw data before AMT could use it. **AMT2PY** avoids that extra step by:

1. Creating **NVSPL (NPS/Volpe Transportation Center Sound Pressure Level) files in Python** instead of inside AMT
2. Supporting more flexible wind-data merge (timestep and formatting) during NVSPL conversion

**Type 1 (821‑ENV) processing — start here:** **[`docs/821/pipeline.md`](docs/821/pipeline.md)**

Downloading field data from the SLM, wind logger, and Song Meter → [`docs/821/data-download.md`](docs/821/data-download.md).

**Legacy Model 831 workflow:** [`docs/831/README.md`](docs/831/README.md).

All **821** scripts open a **GUI** — nothing to edit in the code before running.

---

## Prepare your machine

### Prerequisites

1. **Python 3.9++** (Company Portal) - IMPORTANT: On DOI hosts, you may need to launch "Miniforge Prompt" (install miniforge from the company portal if you do not already have it) and run Python commands from there to work smoothly with AppLocker. This approach works as of 2026-09-22.
2. **Git** (Company Portal)
3. **Field data** downloaded and organized per [`docs/821/data-download.md`](docs/821/data-download.md) (then process with [`docs/821/pipeline.md`](docs/821/pipeline.md))

### One-time setup

1. Open **Git Bash** or Command Prompt and go where you want the repo:

```Shell
cd [path to the place where you would like to save the project]
```

2. Clone the repo and change to its directory:

```Shell
git clone https://github.com/emeyer34/AMT2PY.git
cd AMT2PY
```

3. Create and activate a virtual environment:

```Shell
python -m venv .venv
```

```Shell
# Command Prompt
.venv\Scripts\activate

# Git Bash
source .venv/Scripts/activate
```

4. Install required packages:

```Shell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. Now you're ready to proceed with the steps in [`docs/821/pipeline.md`](docs/821/pipeline.md)! With the environment active, you can run the data processing scripts, for example:

```Shell
python FeatherMC_combine.py
```

### Pulling updates

```Shell
cd [path where you have saved the project]
git pull
```

Re-run `pip install -r requirements.txt` with the virtual environment activated if dependencies (`requirements.txt`) changes.

---

## Scripts

| Script | Workflow | Detail |
|--------|----------|--------|
| `ld821_combine.py` | Merge G4 Time History CSVs | [`docs/821/pipeline.md`](docs/821/pipeline.md) · [`docs/821/ld821-combine.md`](docs/821/ld821-combine.md) |
| `FeatherMC_combine.py` | Combine Feather MC wind logger CSVs | [`docs/821/pipeline.md`](docs/821/pipeline.md) · [`docs/821/feathermc-combine.md`](docs/821/feathermc-combine.md) |
| `ld821_to_nvspl.py` | Combined G4 CSV → hourly NVSPL (optional wind merge) | [`docs/821/pipeline.md`](docs/821/pipeline.md) · [`docs/821/ld821-to-nvspl.md`](docs/821/ld821-to-nvspl.md) |
| `831Renamer.py` | Merge LD831 folders → `.831` | [`docs/831/renamer.md`](docs/831/renamer.md) |
| `831_to_NVSPL_external_wind_log.py` | `.831` → NVSPL (+ optional wind CSV) | [`docs/831/to-nvspl.md`](docs/831/to-nvspl.md) |

---

## Sound Level Meters

Both the **821‑ENV** and **Model 831** are [Larson Davis](https://www.larsondavis.com/Products/sound-level-meters) instruments with different download formats and software paths in this repo.

**821‑ENV** ([SoundExpert](https://www.larsondavis.com/Products/sound-level-meters/soundexpert-821env)) — NSNSD’s current **Type 1** system (G4 Utility, Feather MC wind, Song Meter audio). Follow **[`docs/821/pipeline.md`](docs/821/pipeline.md)**.

**Model 831** — [discontinued in 2022](https://www.larsondavis.com/product-support/announcements/sound-level-meter-model-831-discontinued); successor is SoundAdvisor 831C. See [`docs/831/README.md`](docs/831/README.md) when you still have `.831` logger data.

## Acknowledgments

- Original **AMT C#** implementation
- Larson Davis **LD831/LD821** data specifications
