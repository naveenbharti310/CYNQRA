# Cynqra product demo video

**What:** the scripts that record a video of the demo. **Why:** a two-minute video shows Cynqra to people who will not
run it. **How:** below. **Note:** the video and this script still show the earlier candidate-tracker demo; recording
a new video of the Bluedip demo is on the roadmap (docs/3_STATUS_AND_ROADMAP.md).

Cynqra_POC_demo.mp4 sits next to the project folder. It was 3 minutes 36 seconds,
1920 x 1080, 30 frames a second, silent with on screen captions. Every screen in it is the real POC doing the real work in demo
mode: the objective is structured, the organization runs, verification catches the
seeded defect, the PM clears the Blocker, policy denies the email, the release is built,
tested and deployed to a local URL, and the live product is used. Nothing is mocked up.
The only additions are a presentation layer (overlay.js): pointer, captions, highlights,
chapter cards and the window that shows the live product.

The script (record_demo.js) follows the current canonical flow: objective, workforce gate,
roadmap and budget gate, the work, delivery. The video beside the project folder was recorded
from the 26 September build, before the workforce gate and the dollar budget; re-record it with
`make_video.py` on a machine with ffmpeg. The storyboard below is the current script's.

## Storyboard

| Time | Chapter | What you see |
| --- | --- | --- |
| Chapter | What you see |
| --- | --- |
| Title | Type one objective. Approve a handful of decisions. Walk away with a live product. |
| 01 Objective | One messy sentence typed, seven fields out, two marked inferred, the dollar budget, decision 1 |
| 02 Workforce, roadmap and budget | Requirements and workstreams, the synthesized organization with the reason for each role (decision 2), a model for every worker, the roadmap and the budget in layers (decision 3) |
| 03 The organization works | Protocol tape, documents verified, product rule card anatomy (decision 4), defect caught and reworked, Blocker raised and cleared without the founder, merge card (decision 5), production deploy card with the denied email (decision 6) |
| 04 Live and handed over | Ten deployment stages, the live candidate tracker used, transition record, decision 7, export bundle, replay, company tiles |
| End | Seven founder decisions, tasks verified, product tests, workers synthesized, one defect caught, one Blocker cleared, one action stopped, ten stages |

## Make it again

Needs Node with Playwright and ffmpeg.

    python poc/demo/make_video.py

It starts a fresh POC on a free port with an empty data folder, drives it with
record_demo.js in headless Chromium, captures frames from the browser's screencast on the
real clock, and encodes poc/demo/out/Cynqra_POC_demo.mp4.
