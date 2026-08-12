# LD 831 workflow

**Larson Davis Model 831** — earlier LD sound level meter (manufacturer [discontinued the 831 in 2022](https://www.larsondavis.com/product-support/announcements/sound-level-meter-model-831-discontinued); replacement line is SoundAdvisor 831C). These tools process classic `.831` logger downloads (`OverAll` / `SLog` / `THist`). For NSNSD’s current **821‑ENV** Type 1 deployments, see [`../821/pipeline.md`](../821/pipeline.md).

Two command-line tools: merge logger folders into `.831` files, then convert to NVSPL. Setup: [`README.md`](../../README.md) → *Prepare your machine*.

| Script | Doc |
|--------|-----|
| `831Renamer.py` | [`renamer.md`](renamer.md) |
| `831_to_NVSPL_external_wind_log.py` | [`to-nvspl.md`](to-nvspl.md) |

## Typical order

1. Run **`831Renamer.py`** on a folder tree containing `OverAll` / `SLog` / `THist` subfolders → `SPL_<SITE>_<timestamp>.831` files.
2. Edit paths in **`831_to_NVSPL_external_wind_log.py`**, then run it → hourly NVSPL `.txt` files.
