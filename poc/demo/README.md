# Cynqra product demo video

Cynqra_POC_demo.mp4 sits next to the project folder. It is 3 minutes 36 seconds,
1920 x 1080, 30 frames a second, silent with on screen captions. Every screen in it is the real POC doing the real work in demo
mode: the objective is structured, the organization runs, verification catches the
seeded defect, the PM clears the Blocker, policy denies the email, the release is built,
tested and deployed to a local URL, and the live product is used. Nothing is mocked up.
The only additions are a presentation layer (overlay.js): pointer, captions, highlights,
chapter cards and the window that shows the live product.

## Storyboard

| Time | Chapter | What you see |
| --- | --- | --- |
| 0:00 | Title | Type one objective. Approve a handful of decisions. Walk away with a live product. |
| 0:08 | 01 Objective | One messy sentence typed, seven fields out, two marked inferred, budget cap, decision 1 |
| 0:38 | 02 Organization and plan | Fixed team, Verification Service outside it, six tasks with platform set risk, decision 2 |
| 0:56 | 03 The organization works | Protocol tape, spec verified, product rule card anatomy, decision 3, defect caught and reworked, Blocker raised and cleared without the founder, merge card, decision 4, production deploy card with the denied email, decision 5 |
| 2:20 | 04 Live and handed over | Ten deployment stages, the live candidate tracker used (flagged, stuck, filter), transition record, decision 6, export bundle, replay 8 of 8, company tiles |
| 3:26 | End | Six founder decisions, 6 of 6 tasks verified, 16 product tests, 68 of 120 work units, one defect caught, one Blocker cleared, one action stopped, ten stages |

## Make it again

Needs Node with Playwright and ffmpeg.

    python poc/demo/make_video.py

It starts a fresh POC on a free port with an empty data folder, drives it with
record_demo.js in headless Chromium, captures frames from the browser's screencast on the
real clock, and encodes poc/demo/out/Cynqra_POC_demo.mp4.
