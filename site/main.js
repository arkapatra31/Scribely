// Scribely website interactions. Plain JS, no dependencies.
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ---------- reveal on scroll ---------- */
  const revealer = new IntersectionObserver(
    (entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); revealer.unobserve(e.target); }
    }),
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
  );
  $$(".reveal").forEach((el) => revealer.observe(el));

  /* ---------- nav ---------- */
  const nav = $(".nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 20);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- hero: 3D tilt following the pointer ---------- */
  const stage = $("[data-tilt]");
  const app = $(".app");
  if (stage && !reduceMotion && window.matchMedia("(pointer: fine)").matches) {
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      app.style.setProperty("--ry", `${(-9 + x * 10).toFixed(2)}deg`);
      app.style.setProperty("--rx", `${(5 - y * 8).toFixed(2)}deg`);
    });
    stage.addEventListener("pointerleave", () => {
      app.style.removeProperty("--ry");
      app.style.removeProperty("--rx");
    });
  }

  /* ---------- hero: the app demo ---------- */
  const LINES = [
    [0, "Today we're building a retrieval-augmented generation pipeline on Amazon Bedrock."],
    [4, "First, we split our documents into chunks and turn each chunk into an embedding."],
    [9, "Those vectors go into a vector store, here OpenSearch Serverless."],
    [15, "At query time we embed the question and retrieve the closest chunks."],
    [21, "The retrieved context goes into the prompt, so the model answers from our data."],
    [27, "That grounding keeps hallucinations down and answers up to date."],
  ];
  const transcript = $("#demoTranscript");
  const timerEl = $("#demoTimer");
  const meter = $$("#demoMeter i");
  const tabs = $$(".app-tabs span");
  const sumBtn = $(".app-sum");
  const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  let seconds = 0;
  let listening = true;
  let heroVisible = true;
  new IntersectionObserver(([e]) => { heroVisible = e.isIntersecting; }).observe(app);

  function addLine(t, text, partial = false) {
    const li = document.createElement("li");
    if (partial) li.className = "partial";
    li.innerHTML = `<time>${clock(t)}</time><span></span>`;
    li.lastChild.textContent = text;
    transcript.append(li);
    while (transcript.children.length > 7) transcript.firstChild.remove();
    return li;
  }

  function setTab(name) {
    tabs.forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
    app.classList.toggle("notes", name === "n");
  }

  if (reduceMotion) {
    LINES.slice(0, 5).forEach(([t, text]) => addLine(t, text));
    timerEl.textContent = "0:31";
    meter.forEach((m, i) => { m.style.height = `${40 + i * 12}%`; });
  } else {
    // Timer + level meter
    setInterval(() => {
      if (!listening || !heroVisible) return;
      seconds += 1;
      timerEl.textContent = clock(seconds);
    }, 1000);
    let phase = 0;
    setInterval(() => {
      if (!heroVisible) return;
      phase += 0.35;
      meter.forEach((m, i) => {
        const level = listening ? 0.35 + 0.65 * Math.abs(Math.sin(phase + i * 0.9) * Math.random()) : 0;
        m.style.height = `${25 + 75 * level}%`;
        m.style.opacity = 0.35 + 0.65 * level;
      });
    }, 120);

    (async function loop() {
      for (;;) {
        transcript.textContent = "";
        setTab("t");
        app.classList.remove("summarize");
        listening = true;
        seconds = 0;
        timerEl.textContent = "0:00";
        await sleep(600);
        for (const [t, text] of LINES) {
          // A live partial that grows word by word, then becomes final.
          const words = text.split(" ");
          const li = addLine(t, "", true);
          for (let i = 1; i <= words.length; i += 2) {
            li.lastChild.textContent = words.slice(0, i).join(" ");
            await sleep(170);
          }
          li.classList.remove("partial");
          li.lastChild.textContent = text;
          await sleep(650);
        }
        listening = false;
        await sleep(500);
        app.classList.add("summarize");
        await sleep(1100);
        sumBtn.classList.add("press");
        await sleep(180);
        sumBtn.classList.remove("press");
        await sleep(700);
        setTab("n");
        await sleep(6500);
      }
    })();
  }

  /* ---------- story: steps drive the sticky stage ---------- */
  const stageCard = $(".stage-card");
  const steps = $$(".step");
  let activeStep = 0;
  const setStep = (n) => {
    activeStep = n;
    stageCard.dataset.active = String(n);
    steps.forEach((s) => s.classList.toggle("active", Number(s.dataset.step) === n));
  };
  setStep(0);
  // A step becomes active when it crosses the middle band of the viewport.
  const stepObserver = new IntersectionObserver(
    (entries) => entries.forEach((e) => { if (e.isIntersecting) setStep(Number(e.target.dataset.step)); }),
    { rootMargin: "-45% 0px -45% 0px" },
  );
  steps.forEach((s) => stepObserver.observe(s));

  /* ---------- story: live waveform ---------- */
  const canvas = $("#wave");
  const ctx = canvas.getContext("2d");
  let waveVisible = false;
  new IntersectionObserver(([e]) => { waveVisible = e.isIntersecting; }).observe(canvas);
  function drawWave(t) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const bars = Math.floor(w / 7);
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#b8a6ff"); grad.addColorStop(0.5, "#8b85ff"); grad.addColorStop(1, "#6ee7f9");
    ctx.fillStyle = grad;
    for (let i = 0; i < bars; i++) {
      const x = i * 7;
      // Speech-like envelope: syllables (fast) inside words (slow), drifting left.
      const p = i * 0.16 - t * 0.003;
      const env = 0.2 + 0.8 * Math.abs(Math.sin(p * 0.42)) * (0.65 + 0.35 * Math.sin(p * 0.11 + 1));
      const syl = 0.3 + 0.7 * Math.abs(Math.sin(p * 2.1) * Math.cos(p * 1.3 + Math.sin(p * 0.7)));
      const edge = Math.sin((i / bars) * Math.PI) ** 0.6;
      const amp = Math.max(0.03, env * syl * edge) * h * 0.46;
      ctx.globalAlpha = 0.35 + 0.65 * (amp / (h * 0.46));
      ctx.beginPath();
      ctx.roundRect(x, h / 2 - amp, 4, amp * 2, 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  if (reduceMotion) {
    requestAnimationFrame(() => drawWave(4000));
  } else {
    const frame = (t) => {
      if (waveVisible && activeStep === 0) drawWave(t);
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  /* ---------- story: restructure chips cycle ---------- */
  const chips = $$(".styles-row .chip");
  if (!reduceMotion) {
    let c = 0;
    setInterval(() => {
      if (activeStep !== 3) return;
      c = (c + 1) % chips.length;
      chips.forEach((ch, i) => ch.classList.toggle("on", i === c));
    }, 1600);
  }

  /* ---------- features: languages ---------- */
  const hello = $("#hello");
  const HELLOS = ["Hello", "Bonjour", "Hola", "Hallo", "Ciao", "Olá", "Merhaba", "Hej", "Cześć", "Xin chào"];
  if (!reduceMotion) {
    let h = 0;
    setInterval(async () => {
      hello.classList.add("out");
      await sleep(450);
      h = (h + 1) % HELLOS.length;
      hello.textContent = HELLOS[h];
      hello.classList.remove("out");
    }, 1800);
  }

  /* ---------- features: search typing ---------- */
  const searchArt = $(".search-art");
  const typed = $("#searchType");
  if (reduceMotion) {
    typed.textContent = "embedding";
    searchArt.classList.add("found");
  } else {
    (async function typeLoop() {
      for (;;) {
        searchArt.classList.remove("found");
        typed.textContent = "";
        await sleep(900);
        for (const ch of "embedding") { typed.textContent += ch; await sleep(110); }
        await sleep(250);
        searchArt.classList.add("found");
        await sleep(3200);
      }
    })();
  }

  /* ---------- features: spotlight follows the pointer ---------- */
  $$(".card").forEach((card) => {
    card.addEventListener("pointermove", (e) => {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${e.clientX - r.left}px`);
      card.style.setProperty("--my", `${e.clientY - r.top}px`);
    });
  });

  /* ---------- get started: OS tabs + copy ---------- */
  const osTabs = $$(".tabs button");
  const terms = $$(".term");
  const select = (os) => {
    osTabs.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.os === os)));
    terms.forEach((t) => { t.hidden = t.dataset.os !== os; });
  };
  osTabs.forEach((b) => b.addEventListener("click", () => select(b.dataset.os)));
  if (/Win/.test(navigator.platform || navigator.userAgent)) select("win");

  const copyBtn = $(".copy");
  copyBtn.addEventListener("click", async () => {
    const term = terms.find((t) => !t.hidden);
    const text = term.innerText
      .split("\n")
      .filter((l) => !l.trim().startsWith("#"))
      .map((l) => l.replace(/^\s*[$>]\s?/, ""))
      .join("\n")
      .trim();
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "Copied";
    } catch {
      copyBtn.textContent = "Select & copy";
    }
    copyBtn.classList.add("done");
    setTimeout(() => { copyBtn.textContent = "Copy"; copyBtn.classList.remove("done"); }, 1800);
  });
})();
