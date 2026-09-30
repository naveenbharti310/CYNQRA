# Cynqra product demo video

**What:** the scripts that record a video of the Bluedip demo. **Why:** a video shows Cynqra to people who will not
run it. **How:** below.

The video, Cynqra_POC_demo.mp4, is about 6 minutes 10 seconds long and follows the seven
steps of the journey, 1920 x 1080, 30 frames a second, silent with on screen captions. It was recorded on 30 September
2026. It is kept outside the repository because of its size; make it again with the command at the end. Every screen in it is the real software doing the real work in demo mode: the
idea becomes a brief, the plan and organisation are approved, the founder defines themselves, the team and budget are
approved, the checks catch mistakes, the live product is used, and the founder audits it and accepts it. The words the
team writes come from the demo's script; the code, the checks, the numbers and the deploy are real.

The only additions are a presentation layer (overlay.js), which never changes what the product does:

- a pointer, captions, highlights and chapter cards;
- a camera: the page moves with an eased scroll, never a jump, and stops where the top edge falls between lines of
  text; where no fixed header covers that edge, the content fades into it;
- a short fade between screens and between pages, so no half drawn screen is ever shown;
- room below the last thing on a page, so anything can be lifted clear of the captions.

How it is shown:

- Every highlight is framed before it is drawn and sits fully above the caption band. The recording lists any
  highlight that would be cut, and a clean recording lists none.
- Every click target is brought clear of the captions first.
- A caption stays up for a second and a half plus about 200 words a minute, and a long stretch of work carries a
  caption saying what the team is doing meanwhile.
- A click that leaves a screen fades it first, so the next screen never shows before its step card; the fade carries
  over to the live product, which runs on its own port.
- In step 5 the team works at its own pace. A watcher holds the work the instant each moment happens (a piece of
  work sent back, a decision for the founder, a merge settled), so the screen shows it as it happens, not a step later. The
  team goes on when the moment has been explained.

## Storyboard

| Chapter | What you see |
| --- | --- |
| Title | You bring the vision. Cynqra creates the organisation that can build it. |
| Step 1: Describe the idea | The founder's words become a brief with the two guesses marked, and a hard budget in dollars |
| Step 2: Approve the plan | What the founder will get and the capabilities it takes; the proposed organisation, three named AI cofounders and their teams, every member named; the estimated budget. The founder approves the plan. |
| Step 3: Define yourself | The founder's background; an area the founder leads gets no AI cofounder. This founder is not technical, so all three stay. |
| Step 4: Approve the team and budget | The budget, the timeline and the organisation, each person with the AI best suited to their work, and what happens if one cannot do it: a new person takes the seat. The founder approves. |
| Step 5: Watch it being built | Everyone working at once; the data scientist's forecast, by name, sent back after losing to last week's numbers; the rule on money brought to the founder; a test catching an estimate that ignored the owner's cap; the merge settled by the AI CTO, by name, the founder told; a question asked instead of guessed, answered inside the team; going live brought to the founder, and a message outside the company stopped by the rules |
| Step 6: Receive the working product | The product live; Bluedip used as the owner would: the day hour by hour, the owner's 50% idea losing money after food cost and 20% earning it |
| Step 7: Audit and refine | Every requirement checked against the original objective; where to ask for a rework; the founder accepts |
| End | Times the founder was needed, requirements met, mistakes caught, tests in the live release |

## Make it again

Needs Node with Playwright and ffmpeg (a static build works: `pip install imageio-ffmpeg`, then put its binary on
the PATH as `ffmpeg`).

    python poc/demo/make_video.py

It starts a fresh Cynqra on a free port with an empty data folder, drives it with record_demo.js in headless
Chromium, captures frames from the browser's screencast on the real clock, and encodes
poc/demo/out/Cynqra_POC_demo.mp4. Beside it, beats.json lists every caption, highlight and caught moment with its
time, to check the video frame by frame. The live product opens in the same tab: Cynqra's own pages refuse to embed
another site, a protection the recording keeps.
