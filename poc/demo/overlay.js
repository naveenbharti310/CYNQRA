/* Presentation layer for the recorded product demo. Injected by record_demo.js into the
   real running POC. It draws a pointer, captions, highlights, chapter cards and a
   browser window for the live product. It never changes what the product does. */
(() => {
  if (window.__demo || window.top !== window) return;
  const CSS = `
  #demo-layer{position:fixed;inset:0;pointer-events:none;z-index:2147483000;font-family:"IBM Plex Sans",system-ui,sans-serif}
  #demo-spots>div{position:fixed;border:3px solid #0F6B5C;border-radius:14px;box-shadow:0 0 0 7px rgba(15,107,92,.16),0 10px 30px rgba(15,107,92,.18);
    animation:dspot .5s cubic-bezier(.2,.8,.2,1) both}
  #demo-spots>div.amber{border-color:#9A4F00;box-shadow:0 0 0 7px rgba(154,79,0,.16),0 10px 30px rgba(154,79,0,.18)}
  #demo-spots>div.red{border-color:#A82820;box-shadow:0 0 0 7px rgba(168,40,32,.14),0 10px 30px rgba(168,40,32,.16)}
  @keyframes dspot{from{opacity:0;transform:scale(1.06)}to{opacity:1;transform:scale(1)}}
  #demo-caption{position:fixed;left:50%;bottom:34px;transform:translate(-50%,16px);opacity:0;transition:opacity .45s ease,transform .45s ease;
    max-width:1120px;background:rgba(27,29,31,.94);color:#fff;border-radius:16px;padding:15px 28px;font-size:22px;line-height:1.4;font-weight:500;
    box-shadow:0 18px 50px rgba(0,0,0,.22);display:flex;gap:16px;align-items:baseline;text-align:left}
  #demo-caption.on{opacity:1;transform:translate(-50%,0)}
  #demo-caption b{color:#8FD3C3;font-weight:600;font-size:15px;letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}
  #demo-card{position:fixed;inset:0;background:#F6F4EF;opacity:0;transition:opacity .6s ease;display:flex;align-items:center;justify-content:center;color:#1B1D1F}
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
  #demo-window{position:fixed;left:120px;right:120px;top:60px;bottom:120px;background:#fff;border-radius:14px;overflow:hidden;
    box-shadow:0 40px 120px rgba(0,0,0,.35),0 0 0 1px rgba(0,0,0,.08);transform:translateY(calc(100% + 220px));visibility:hidden;transition:transform .8s cubic-bezier(.2,.8,.2,1);
    display:flex;flex-direction:column;pointer-events:auto}
  #demo-window.on{transform:none;visibility:visible}
  #demo-window.off{visibility:visible}
  #demo-window .bar{height:48px;background:#EDEBE6;display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid #DDD8CD}
  #demo-window .dots{display:flex;gap:7px}#demo-window .dots i{width:12px;height:12px;border-radius:50%;background:#D5D0C5;display:block}
  #demo-window .url{flex:1;background:#fff;border-radius:8px;height:30px;display:flex;align-items:center;padding:0 14px;font:14px "IBM Plex Mono",monospace;color:#3E4140}
  #demo-window .url em{font-style:normal;color:#1E6F3B;margin-right:10px;font-family:"IBM Plex Sans",sans-serif;font-weight:600}
  #demo-window iframe{flex:1;border:0;width:100%}
  #demo-dim{position:fixed;inset:0;background:rgba(22,24,26,.38);opacity:0;transition:opacity .6s}
  #demo-dim.on{opacity:1}
  #demo-cursor{position:fixed;left:0;top:0;width:30px;height:30px;transform:translate(720px,860px);transition:transform .85s cubic-bezier(.22,.61,.36,1);
    filter:drop-shadow(0 3px 5px rgba(0,0,0,.35));opacity:1;transition-property:transform,opacity}
  #demo-cursor.gone{opacity:0}
  .demo-ripple{position:fixed;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;border:3px solid #0F6B5C;animation:drip .6s ease-out forwards}
  @keyframes drip{from{opacity:.9;transform:scale(.4)}to{opacity:0;transform:scale(2.6)}}`;

  const D = { x: 720, y: 860 };
  const el = (id) => document.getElementById(id);
  D.ensure = () => {
    if (el("demo-layer")) return;
    const st = document.createElement("style");
    st.textContent = CSS;
    document.head.append(st);
    const layer = document.createElement("div");
    layer.id = "demo-layer";
    layer.innerHTML = `<div id="demo-dim"></div><div id="demo-window"><div class="bar"><div class="dots"><i></i><i></i><i></i></div>
      <div class="url"><em>Live</em><span id="demo-url"></span></div></div><iframe id="demo-frame" title="Live product"></iframe></div>
      <div id="demo-spots"></div><div id="demo-caption"><span></span></div><div id="demo-card"></div>
      <svg id="demo-cursor" viewBox="0 0 24 24"><path d="M4 2l15 11.5-6.6 1.1 3.9 7.3-2.9 1.5-3.9-7.4L4 21z" fill="#1B1D1F" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    document.body.append(layer);
    el("demo-cursor").style.transform = `translate(${D.x}px,${D.y}px)`;
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
  D.caption = (text, label) => {
    D.ensure();
    const c = el("demo-caption");
    if (!text) { c.classList.remove("on"); return; }
    const swap = () => {
      c.innerHTML = (label ? `<b>${label}</b>` : "") + `<span>${text}</span>`;
      requestAnimationFrame(() => c.classList.add("on"));
    };
    if (c.classList.contains("on")) { c.classList.remove("on"); setTimeout(swap, 420); } else swap();
  };
  D.spots = (rects, tone) => {
    D.ensure();
    el("demo-spots").innerHTML = rects.map((r) =>
      `<div class="${tone || ""}" style="left:${r.x - 8}px;top:${r.y - 8}px;width:${r.w + 16}px;height:${r.h + 16}px"></div>`).join("");
  };
  D.clearSpots = () => { D.ensure(); el("demo-spots").innerHTML = ""; };
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
  D.openWindow = (url) => {
    D.ensure();
    el("demo-url").textContent = url.replace("http://", "");
    el("demo-frame").src = url;
    el("demo-dim").classList.add("on");
    el("demo-window").classList.add("on");
  };
  D.closeWindow = () => {
    el("demo-window").classList.add("off");
    el("demo-window").classList.remove("on");
    setTimeout(() => el("demo-window").classList.remove("off"), 900);
    el("demo-dim").classList.remove("on");
  };
  window.__demo = D;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", D.ensure);
  else D.ensure();
})();
