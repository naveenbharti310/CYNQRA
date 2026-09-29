/* Presentation layer for the recorded product demo. Injected by record_demo.js into the
   real running POC. It draws a pointer, captions, highlights, chapter cards and a veil
   for moving between screens, and it moves the page smoothly, like a camera. It never
   changes what the product does. */
(() => {
  if (window.__demo || window.top !== window) return;
  const PAPER = "#F6F4EF";
  // A page opened with the veil already down (a move to another page) starts covered, so its first paint never shows.
  const veiled = window.name === "demo-veil";
  if (veiled && document.documentElement) {
    const pre = document.createElement("style");
    pre.id = "demo-preveil";
    pre.textContent = `html::before{content:"";position:fixed;inset:0;background:${PAPER};z-index:2147482999}`;
    document.documentElement.append(pre);
  }
  const CSS = `
  #demo-layer{position:fixed;inset:0;pointer-events:none;z-index:2147483000;font-family:"IBM Plex Sans",system-ui,sans-serif}
  #demo-veil{position:fixed;inset:0;background:${PAPER};opacity:0;transition:opacity .3s ease}
  #demo-veil.on{opacity:1}
  /* where no fixed header covers the top edge of a scrolled page, the content fades into it instead of being cut */
  #demo-fade{position:fixed;left:0;right:0;top:0;height:30px;opacity:0;transition:opacity .25s}
  #demo-fade.on{opacity:1}
  #demo-spots>div{position:fixed;border:3px solid #0F6B5C;border-radius:14px;box-shadow:0 0 0 6px rgba(15,107,92,.14),0 10px 30px rgba(15,107,92,.16);
    animation:dspot .5s cubic-bezier(.2,.8,.2,1) both}
  #demo-spots>div.amber{border-color:#9A4F00;box-shadow:0 0 0 6px rgba(154,79,0,.14),0 10px 30px rgba(154,79,0,.16)}
  #demo-spots>div.red{border-color:#A82820;box-shadow:0 0 0 6px rgba(168,40,32,.12),0 10px 30px rgba(168,40,32,.14)}
  #demo-spots>div.out{animation:dspotout .3s ease both}
  @keyframes dspot{from{opacity:0;transform:scale(1.04)}to{opacity:1;transform:scale(1)}}
  @keyframes dspotout{to{opacity:0}}
  #demo-caption{position:fixed;left:50%;bottom:28px;transform:translate(-50%,14px);opacity:0;transition:opacity .4s ease,transform .4s ease;
    width:max-content;max-width:960px;background:rgba(27,29,31,.95);color:#fff;border-radius:14px;padding:14px 26px;font-size:21px;line-height:1.4;font-weight:500;
    box-shadow:0 18px 50px rgba(0,0,0,.22);display:flex;gap:16px;align-items:baseline;text-align:left}
  #demo-caption.on{opacity:1;transform:translate(-50%,0)}
  #demo-caption.top{bottom:auto;top:84px;transform:translate(-50%,-14px)}
  #demo-caption.top.on{transform:translate(-50%,0)}
  #demo-caption b{color:#8FD3C3;font-weight:600;font-size:14px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}
  /* the product's notices stay clear of the captions, and step aside while something is highlighted */
  .toasts{max-width:270px}
  body.demo-spotting .toasts{opacity:0;transition:opacity .3s}
  .guide-bar{visibility:hidden}
  /* room below the last thing on a page, inside its content, so the camera can lift anything clear of the caption
     band without scrolling past the app's own frame */
  .view,.wiz-body{padding-bottom:190px!important}
  body:not(:has(#app))::after{content:"";display:block;height:190px}
  #demo-card{position:fixed;inset:0;background:${PAPER};opacity:0;transition:opacity .6s ease;display:flex;align-items:center;justify-content:center;color:#1B1D1F}
  #demo-card.on{opacity:1}
  #demo-card.dark{background:#16181A;color:#F6F4EF}
  #demo-card .in{opacity:0;animation:dup .8s cubic-bezier(.2,.8,.2,1) forwards}
  @keyframes dup{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
  .dc-wrap{width:1100px;display:flex;flex-direction:column;gap:22px}
  .dc-word{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:132px;letter-spacing:-.03em;line-height:1}
  .dc-line{font-size:34px;line-height:1.3;font-weight:500}
  .dc-line i{font-style:normal;color:#0F6B5C}
  #demo-card.dark .dc-line i{color:#8FD3C3}
  .dc-foot{font-size:18px;color:#5B5E5C;margin-top:18px}
  #demo-card.dark .dc-foot{color:#A9ADA9}
  .dc-num{font-family:"IBM Plex Mono",monospace;font-size:22px;color:#0F6B5C;letter-spacing:.1em}
  .dc-chap{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:84px;letter-spacing:-.02em;line-height:1.05}
  .dc-bar{height:4px;width:0;background:#0F6B5C;border-radius:4px;animation:dbar 1.2s .2s cubic-bezier(.2,.8,.2,1) forwards}
  @keyframes dbar{to{width:180px}}
  .dc-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:10px}
  .dc-tile{background:#202326;border:1px solid #33373A;border-radius:16px;padding:20px 22px;display:flex;flex-direction:column;gap:6px}
  .dc-tile b{font-family:"IBM Plex Mono",monospace;font-size:44px;font-weight:500;color:#fff}
  .dc-tile span{font-size:17px;color:#C9CCC8;line-height:1.3}
  #demo-cursor{position:fixed;left:0;top:0;width:30px;height:30px;transform:translate(720px,860px);transition:transform .85s cubic-bezier(.22,.61,.36,1);
    filter:drop-shadow(0 3px 5px rgba(0,0,0,.35));opacity:1;transition-property:transform,opacity}
  #demo-cursor.gone{opacity:0}
  .demo-ripple{position:fixed;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;border:3px solid #0F6B5C;animation:drip .6s ease-out forwards}
  @keyframes drip{from{opacity:.9;transform:scale(.4)}to{opacity:0;transform:scale(2.6)}}`;

  const D = { x: 720, y: 860 };
  const el = (id) => document.getElementById(id);
  const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
  D.ensure = () => {
    if (el("demo-layer")) return;
    const st = document.createElement("style");
    st.textContent = CSS;
    document.head.append(st);
    const layer = document.createElement("div");
    layer.id = "demo-layer";
    layer.innerHTML = `<div id="demo-fade"></div><div id="demo-veil" class="${veiled ? "on" : ""}"></div><div id="demo-spots"></div><div id="demo-caption"><span></span></div><div id="demo-card"></div>
      <svg id="demo-cursor" viewBox="0 0 24 24"><path d="M4 2l15 11.5-6.6 1.1 3.9 7.3-2.9 1.5-3.9-7.4L4 21z" fill="#1B1D1F" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    document.body.append(layer);
    el("demo-cursor").style.transform = `translate(${D.x}px,${D.y}px)`;
    const pre = el("demo-preveil");
    if (pre) requestAnimationFrame(() => pre.remove());  // the layer's own veil has taken over
    const fade = () => {
      const f = el("demo-fade"), bg = getComputedStyle(document.body).backgroundColor;
      f.style.background = `linear-gradient(${bg}, ${bg.replace(/rgb\((.*)\)/, "rgba($1, 0)")})`;
      f.classList.toggle("on", window.scrollY > 2 && !document.querySelector("header.top"));
    };
    addEventListener("scroll", fade, { passive: true });
    setInterval(fade, 300);
  };
  D.cursor = (x, y, ms = 850) => {
    D.ensure();
    const c = el("demo-cursor");
    c.style.transitionDuration = ms + "ms";
    c.style.transform = `translate(${x - 4}px,${y - 2}px)`;
    D.x = x; D.y = y;
  };
  D.ripple = () => {
    const r = document.createElement("div");
    r.className = "demo-ripple";
    r.style.left = D.x + "px"; r.style.top = D.y + "px";
    el("demo-layer").append(r);
    setTimeout(() => r.remove(), 700);
  };
  D.caption = (text, label, pos) => {
    D.ensure();
    const c = el("demo-caption");
    if (!text) { c.classList.remove("on"); return; }
    const swap = () => {
      c.classList.toggle("top", pos === "top");
      c.innerHTML = (label ? `<b>${label}</b>` : "") + `<span>${text}</span>`;
      requestAnimationFrame(() => requestAnimationFrame(() => c.classList.add("on")));
    };
    if (c.classList.contains("on")) { c.classList.remove("on"); setTimeout(swap, 400); } else swap();
  };
  D.spots = (rects, tone) => {
    D.ensure();
    document.body.classList.add("demo-spotting");
    el("demo-spots").innerHTML = rects.map((r) =>
      `<div class="${tone || ""}" style="left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px"></div>`).join("");
  };
  D.clearSpots = () => {
    D.ensure();
    document.body.classList.remove("demo-spotting");
    const s = el("demo-spots");
    [...s.children].forEach((d) => d.classList.add("out"));
    setTimeout(() => { if (!document.body.classList.contains("demo-spotting")) s.innerHTML = ""; }, 320);
  };
  D.veil = (on) => {
    D.ensure();
    el("demo-veil").classList.toggle("on", !!on);
    // nothing to point at on a blank screen; a chapter card keeps it hidden until the card goes
    el("demo-cursor").classList.toggle("gone", !!on || el("demo-card").classList.contains("on"));
    if (!on) window.name = "";
  };
  /* The camera: scroll an element (or the page) to a position with an eased move, and resolve when it arrives. */
  D.scroll = (target, top, ms) => new Promise((done) => {
    const s = target || document.scrollingElement;
    const from = s.scrollTop, to = Math.max(0, Math.min(top, s.scrollHeight - s.clientHeight));
    if (Math.abs(to - from) < 2) return done(0);
    const dur = ms || Math.max(450, Math.min(1200, 300 + Math.abs(to - from) * 0.9));
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      s.scrollTop = from + (to - from) * ease(k);
      if (k < 1) requestAnimationFrame(step); else done(dur);
    };
    requestAnimationFrame(step);
  });
  D.card = (html, dark) => {
    D.ensure();
    const c = el("demo-card");
    c.className = dark ? "dark" : "";
    c.innerHTML = html;
    el("demo-cursor").classList.add("gone");
    requestAnimationFrame(() => requestAnimationFrame(() => c.classList.add("on")));
  };
  D.hideCard = () => { D.ensure(); el("demo-card").classList.remove("on"); el("demo-cursor").classList.remove("gone"); };
  D.countUp = () => {
    document.querySelectorAll("#demo-card [data-to]").forEach((b) => {
      const to = Number(b.dataset.to), dec = (b.dataset.to.split(".")[1] || "").length, t0 = performance.now(), dur = 1400;
      const tick = (t) => {
        const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
        b.textContent = (to * e).toFixed(dec) + (b.dataset.suffix || "");
        if (k < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  };
  window.__demo = D;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", D.ensure);
  else D.ensure();
})();
