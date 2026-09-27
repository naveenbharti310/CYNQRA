#!/usr/bin/env python3
"""Build the browser version of the S1 paste pack.

Writes 03_pages/cynqra-s1-paste-pack.html: one copy button per prompt, one
reply box per item, and a button that saves every reply as s1_answers.json.
Put that file in spikes/s1/answers/ and run score_manual.py. The page holds
the prompts only. The expected answers never leave corpus.json.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_s1 import PROMPT_VERSION, load_corpus, prompt_for  # noqa: E402

OUT = HERE.parent.parent.parent / "03_pages" / "cynqra-s1-paste-pack.html"

STYLE = """
*{box-sizing:border-box}
:root{--ink:#2C2C2B;--muted:#6F6C67;--line:#E6E5E3;--soft:#F9F8F7;--panel:#fff;--tint:#F0EFED;--accent:#D5803B;--ok:#2F8A5B}
@media (prefers-color-scheme:dark){:root{--ink:#ECEAE6;--muted:#A8A49D;--line:#3A3936;--soft:#1C1B1A;--panel:#252422;--tint:#2E2D2A;--accent:#E0945A;--ok:#5CC08A}}
body{margin:0;padding:40px 16px 96px;background:var(--soft);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:28px;line-height:1.2;margin:0 0 6px}
.sub{color:var(--muted);margin:0 0 28px}
h2{font-size:19px;margin:36px 0 10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:0 0 16px}
.rule{background:var(--tint);border-left:3px solid var(--accent);border-radius:6px;padding:12px 16px;margin:0 0 10px}
.rule b{display:block}
.item{border:1px solid var(--line);border-radius:10px;background:var(--panel);margin:0 0 22px;overflow:hidden}
.head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;background:var(--tint);border-bottom:1px solid var(--line)}
.tag{font-weight:650}
.state{font-size:13px;color:var(--muted)}
.state.ok{color:var(--ok)}
pre{margin:0;padding:16px;white-space:pre-wrap;word-wrap:break-word;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.body{padding:12px 16px 16px;border-top:1px solid var(--line)}
label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
textarea,input[type=text]{width:100%;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding:10px;border:1px solid var(--line);border-radius:7px;background:var(--soft);color:var(--ink)}
textarea{min-height:120px;resize:vertical}
details{border-top:1px solid var(--line)}
summary{cursor:pointer;padding:10px 16px;color:var(--muted);font-size:14px}
button{font:600 13px/1 inherit;padding:9px 14px;border-radius:7px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
button:hover{background:var(--tint)}
button.primary{background:var(--ink);color:var(--soft);border-color:var(--ink)}
button.copied{border-color:var(--ok);color:var(--ok)}
.bar{position:sticky;bottom:0;background:var(--soft);border-top:1px solid var(--line);padding:12px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.foot{color:var(--muted);font-size:14px;margin-top:36px;border-top:1px solid var(--line);padding-top:16px}
code{background:var(--tint);padding:1px 5px;border-radius:4px;font-size:13px}
"""

SCRIPT = """
var KEY='cynqra_s1_%(ver)s';
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
function save(){var d={};document.querySelectorAll('[data-k]').forEach(function(el){d[el.dataset.k]=el.value});try{localStorage.setItem(KEY,JSON.stringify(d))}catch(e){}refresh()}
function refresh(){var n=0;document.querySelectorAll('textarea[data-main]').forEach(function(el){var s=document.getElementById('st_'+el.dataset.k);if(el.value.trim()){n++;s.textContent='Reply saved';s.className='state ok'}else{s.textContent='No reply yet';s.className='state'}});document.getElementById('count').textContent=n+' of %(n)d replies'}
function copyBlock(id,btn){var t=document.getElementById(id).innerText;function ok(){btn.textContent='Copied';btn.classList.add('copied');setTimeout(function(){btn.textContent='Copy';btn.classList.remove('copied')},1500)}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok,function(){manual()})}else{manual()}
function manual(){var r=document.createRange();r.selectNodeContents(document.getElementById(id));var s=window.getSelection();s.removeAllRanges();s.addRange(r);try{document.execCommand('copy');ok()}catch(e){btn.textContent='Select and copy'}}}
function download(){var d={prompt_version:'%(ver)s',model:document.getElementById('model').value.trim(),saved_at:new Date().toISOString(),answers:{}};document.querySelectorAll('textarea[data-k]').forEach(function(el){if(el.value.trim())d.answers[el.dataset.k]=el.value});var b=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='s1_answers.json';document.body.appendChild(a);a.click();a.remove()}
(function(){var d=load();document.querySelectorAll('[data-k]').forEach(function(el){if(d[el.dataset.k])el.value=d[el.dataset.k];el.addEventListener('input',save)});refresh()})();
"""


def main() -> int:
    corpus = load_corpus()
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Cynqra S1 paste pack</title><style>" + STYLE + "</style></head><body><div class='wrap'>",
        "<h1>S1 by hand</h1>",
        f"<p class='sub'>Prompt {html.escape(PROMPT_VERSION)}. Ten fresh chats, about an hour, no key and no install. "
        "This produces one of the two spike scores the M2 gate is waiting on. The bar is 8 of 10 and it does not move.</p>",
        "<div class='card'><b>Why this page replaced the 25 August one.</b> The old prompt told the model to leave "
        "unstated fields empty, and the scorer fails any empty field, so a model that obeyed would have scored zero. "
        "The ten objectives, the expected answers, the scorer and the bar are unchanged. No S1 answers existed yet, "
        "so no result is affected.</div>",
        "<h2>Rules that decide whether the score means anything</h2>",
        "<div class='rule'><b>A new chat every time.</b>Ten items, ten chats. A reused chat lets item four learn from item three.</div>",
        "<div class='rule'><b>Temporary or incognito chat, or memory off.</b>A model that remembers Cynqra or the candidate tracker is not a clean test.</div>",
        "<div class='rule'><b>Paste exactly, add nothing.</b>No hints, no context, no telling it what you hope to see.</div>",
        "<div class='rule'><b>Never tidy the reply.</b>Not a bracket, not a blank field, not a typo. Prose instead of JSON is a real failure and counts as one.</div>",
        "<div class='rule'><b>Retry only when the scorer says so.</b>Each item gets one retry, in a new chat, with the retry block under the item.</div>",
        "<h2>Which app and model</h2><div class='card'><label for='model'>For example: Claude app, Sonnet 5, temporary chat</label>",
        "<input type='text' id='model' data-k='model'></div>",
        "<h2>The ten items</h2>",
    ]
    for case in corpus:
        cid = case["id"]
        parts.append(
            f"<div class='item'><div class='head'><span class='tag'>{cid}</span>"
            f"<span class='state' id='st_{cid}'>No reply yet</span>"
            f"<button onclick=\"copyBlock('p_{cid}',this)\">Copy</button></div>"
            f"<pre id='p_{cid}'>{html.escape(prompt_for(case['messy']))}</pre>"
            f"<div class='body'><label for='r_{cid}'>Paste the whole reply for {cid} here, untouched</label>"
            f"<textarea id='r_{cid}' data-k='{cid}' data-main='1'></textarea></div>"
            f"<details><summary>Retry block for {cid}, only if the scorer says it failed</summary>"
            f"<div class='head'><span class='tag'>{cid} retry</span>"
            f"<button onclick=\"copyBlock('q_{cid}',this)\">Copy</button></div>"
            f"<pre id='q_{cid}'>{html.escape(prompt_for(case['messy'], retry=True))}</pre>"
            f"<div class='body'><label for='x_{cid}'>Retry reply for {cid}</label>"
            f"<textarea id='x_{cid}' data-k='{cid}_retry'></textarea></div></details></div>"
        )
    parts.append(
        "<div class='bar'><button class='primary' onclick='download()'>Save answers file</button>"
        "<span class='state' id='count'></span></div>"
        "<div class='foot'>Saving downloads <code>s1_answers.json</code>. Put it in "
        "<code>02_harness/spikes/s1/answers/</code>, then double click <code>RUN_M1.bat</code> and choose the "
        "hand pasted S1 option, or send the file to Claude. Replies also stay in this browser until you clear it. "
        "The expected answers were written on 24 August and are not in this page.</div>"
    )
    parts.append("<script>" + SCRIPT % {"ver": PROMPT_VERSION, "n": len(corpus)} + "</script></div></body></html>")
    OUT.write_text("".join(parts), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
