[中文](版本功能对照表.md) | **English**

# Y's Batch Toolkit — Feature Comparison (Lite / Advanced / Developer)

> Applicable to: Lite / Advanced / Developer authorization tiers; see each release page for version numbers.

> Verified item by item against each version's source (Lite / Developer = `gui.py`, Advanced = `src/*.rs`); not speculation.
> **Change**: v2 renames the former "Internal" column to "**Developer**"; Advanced and Developer are the **same Rust exe**,
> differing only in authorization tier: Advanced = standard activation code, Developer = developer authorization.
> Generated on: 2026-10-10

| Feature | Lite | Advanced | Developer |
|---|---|---|---|
| **Subtitle processing** | | | |
| One-click (auto troubleshooting + import localization, order 4→1→2→3→5) | ✓ | ✓ | ✓ |
| ZH csv split | ✓ | ✓ | ✓ |
| Localize subtitles / remove brackets / remove numbering | ✓ | ✓ | ✓ |
| Export VO text / vocabulary replacement / check errors | ✓ | ✓ | ✓ |
| **Logs & abort** | | | |
| Clear log | ✓ | ✓ | ✓ |
| Emergency abort (two confirmations, kills only the dubbing subprocess) | ✓ | ✓ | ✓ |
| **Paths / address bar** | | | |
| Source directory / output directory | ✓ | ✓ | ✓ |
| Dubbing folder / voice directory / output path | ✓ | ✓ | ✓ |
| Workspace directory derivation (VOtxt / VOerror / VOdub / translate / vocabulary) | ✓ | ✓ | ✓ |
| Compact mode | ✓ (on by default) | ✓ | ✓ |
| **Dubbing tools** | | | |
| Model dropdown (IndexTTS 2.5 / GPT-SoVITS v2Pro) | ✓ | ✓ | ✓ |
| Voice dropdown / preview · original / start dubbing | ✓ | ✓ | ✓ |
| List view (dubbing folder ↔ folder to be dubbed + refresh) | ✓ | ✓ (plus an extra "Refresh voices") | ✓ |
| Emotion sub-panel (emotion intensity / reference by original voice / eight directions) | ✓ | ✓ | ✓ |
| Select individual audio | ✓ | ✓ | ✓ |
| Persistent mode + close TTS | ✓ | ✓ | ✓ |
| Low-emotion second confirmation | ✓ | ✓ | ✓ |
| Open API | ✗ | ✓ | ✓ |
| ★ One-click dubbing | ✗ | ✓ | ✓ |
| **Automated flow** | | | |
| Automated flow sub-panel | ✗ | ✓ | ✓ |
| Status indicators (emotion / persistent / previous batch) | ✓ | ✓ | ✓ |
| Convert OGG (both `Auto\` and `原声\`) | ✗ | ✓ | ✓ |
| Write voices (two confirmations) | ✗ | ✓ | ✓ |
| Optimize for RON (character dropdown) | ✗ | ✓ | ✓ |
| **Unattended / monitoring** | | | |
| Unattended mode (batch by comparison table) | ✗ | ✗ | ✓ |
| Monitor (monitor.ps1 + 监视器.lnk) | ✗ | ✓ | ✓ |
| Monitor "duration" (session.json) | ✗ | ✗ | ✓ |
| **Less common tools** | | | |
| Find missing / extract untranslated / proofread VOtxt / merge CSV | ✗ | ✓ | ✓ |
| WAV to OGG / remove language suffix / VOerror dubbing | ✗ | ✓ | ✓ |
| **Original-voice cloning (Developer only)** | | | |
| Automated flow · original-voice cloning (orig_voice_clone) | ✗ | ✗ | ✓ |
| Dubbing tools · original-voice cloning (dub_clone) | ✗ | ✗ | ✓ |
| Unattended fallback cloning (unatt_clone) | ✗ | ✗ | ✓ |

## Notes

- **Lite**: a streamlined open-source version (GPL-3.0), without automated flow / unattended / less common tools / original-voice cloning.
- **Advanced ↔ Developer**: two authorization tiers of the same Rust exe; developer authorization additionally includes the following three items,
  and under non-developer authorization the related entries and buttons are not shown.
- **Developer version** adds three items over Advanced: **unattended mode (batch by comparison table)**, **original-voice cloning (three switches)**,
  and **monitor "duration" (session.json)**; in addition, "Convert OGG" covers both `Auto\` and `原声\` in the Developer version.
