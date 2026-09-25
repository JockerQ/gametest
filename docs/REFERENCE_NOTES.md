# Reference notes — Evil Tower (reference only)

The brief names Evil Tower as a *reference* for the central-tower defence loop. Evil Cats
uses none of its assets, code, names, interface layouts or audio. This file separates
what was **actually observed** from what is **assumed** or taken from the brief.

## What I could access (2026-09-25, cloud session)

| Source | Result |
|---|---|
| YouTube video `wiRAEMLcGbk` | **Not accessed.** The session's network policy blocked `www.youtube.com` (HTTP 403 from the egress proxy, and the web-fetch tool reported `EGRESS_BLOCKED`). **I did not watch any footage.** |
| Google Play listing `com.aurecas.eviltower` | **Not accessed.** `play.google.com` blocked the same way. **I did not see the official screenshots.** |
| Third-party mirrors (mwm.ai, CrazyGames) | Blocked (`EGRESS_BLOCKED`). |
| Web search result summaries (text only) | Accessible. See below. |

## Observed (text from web-search result summaries only)

Search for `"Evil Tower" Aurecas tower defense game android` returned listing summaries
stating, in paraphrase:

* It is described as a "medieval idle tower defense" game mixing tower-defence strategy
  with roguelike decisions, by developer Aurecas; title "Evil Tower - Idle Defense TD".
* The player is a wizard lord of a tower using a crystal's power to defend against
  opposing kingdoms.
* Players place **automated weapon stations** on their tower; between battles resources
  go to **permanent upgrades** and there are **temporary run-specific perks**.
* It advertises **action buttons for special powers**, station customisation and waves of
  fantasy enemies.
* Listed as available on Android (7.0+) and browser, content rating note "Mild Fantasy
  Violence".

These are second-hand summaries, not first-hand inspection. No visual or timing detail
was observed.

## Not observed → taken from the Evil Cats brief instead

Everything about layout, battlefield camera, HUD placement, number of stations, wave
structure, timings, economy formulas, enemy types, bosses and art direction comes from
the Evil Cats specification (the user's brief), **not** from the reference. In particular
I made no assumptions about how Evil Tower's interface looks, and nothing was reproduced
from it.

## How to let a future session inspect the reference

Allow `www.youtube.com` and `play.google.com` in the cloud environment's **Network
access** settings (environment menu in the session title bar → Edit). Even then, the
web-fetch tool reads page text; watching video frames would require a video-analysis
service, which I did not use (it may consume paid credits and needs your approval).
