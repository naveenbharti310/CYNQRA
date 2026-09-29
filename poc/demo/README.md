# Cynqra product demo video

**What:** the scripts that record a video of the Bluedip demo. **Why:** a video shows Cynqra to people who will not
run it. **How:** below.

The video, Cynqra_POC_demo.mp4, is 4 minutes 28 seconds, 1920 x 1080, 30 frames a second, silent with on screen
captions. It was recorded on 29 September 2026. It is kept outside the repository because of its size (about 23 MB);
make it again with the command at the end. Every screen in it is the real software doing the real work in demo mode:
the idea is turned into a brief, the team is proposed, challenged and approved, the checks catch three mistakes, the
live product is used, and the Company Pack is handed over. The only additions are a presentation layer
(overlay.js): pointer, captions, highlights and chapter cards. The words the team writes come from the demo's script;
the code, the checks, the numbers and the deploy are real.

## Storyboard

| Chapter | What you see |
| --- | --- |
| Title | Describe what you want to build. Get it working in the real world, within your budget, without coordinating anyone. |
| 01 Your idea | The founder's words become a brief with the two guesses marked; a hard budget in dollars; what the founder brings |
| 02 What you'll get | The outcomes, the risks and the guesses the idea rests on; three cofounders and their teams, each seat with who asked for it, what it owns and what would be left undone without it; "Why this team" with its confidence; the independent challenge cutting a Security Expert that owned nothing and keeping the Designer; the lean team of ten beside the recommended thirteen; when each member starts; the budget. The founder approves the team, then the plan. |
| 03 The team at work | Everyone working at once; the forecast sent back after losing to last week's numbers; the CFO's value of a restaurant recomputed from its own figures and sent back; the rule on money brought to the founder; the Designer's screen sent back by the Chief Product Officer; a question answered by the Revenue Specialist; a test catching an estimate that ignored the owner's cap; the merge settled by the CTO, the founder told; going live brought to the founder |
| 04 It's live | Ten deployment stages; Bluedip used as the owner would: the day hour by hour, the recommended offers, the owner's 50% idea losing money after food cost and 20% earning it; the Company Pack: how you will know it worked, the numbers recomputed by the platform, the next steps only the founder can take; the founder accepts |
| 05 It keeps going | The founder's update, built from the record; what users said recorded for the next cycle |
| End | Times the founder was needed, work checked, mistakes caught, the seat cut, questions settled inside the team, the decision settled for the founder, tests in the live release, deployment stages |

## Make it again

Needs Node with Playwright and ffmpeg (a static build works: `pip install imageio-ffmpeg`, then put its binary on
the PATH as `ffmpeg`).

    python poc/demo/make_video.py

It starts a fresh Cynqra on a free port with an empty data folder, drives it with record_demo.js in headless
Chromium, captures frames from the browser's screencast on the real clock, and encodes
poc/demo/out/Cynqra_POC_demo.mp4. The live product opens in the same tab: Cynqra's own pages refuse to embed another
site, a protection the recording keeps.
