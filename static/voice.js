/*
 * Sanjeevani voice chat - mic button inside the existing chat widget.
 * Uses the page's own elements: #voiceBtn (mic), #chatMessages, #userInput. No new CSS, no layout change.
 * Talks to POST /api/chat-voice (same login session as /api/chat).
 *
 * Click mic -> speak -> it stops by itself when you stop talking -> reply shows in chat AND is spoken.
 * Click mic again while it is listening = send now; while the bot is speaking = stop the voice.
 *
 * Capture: mic -> AudioContext -> PCM frames -> 16 kHz mono WAV, built in-memory the moment you stop talking
 * (no MediaRecorder / decodeAudioData / OfflineAudioContext round trip, so no extra delay and no decode failures).
 */
(function () {
  const btn = document.getElementById("voiceBtn");
  const chatMessages = document.getElementById("chatMessages");
  const userInput = document.getElementById("userInput");
  if (!btn || !chatMessages) return;

  const API = "/api/chat-voice";
  const SILENCE_MS = 700;      // stop this long after speech ends
  const MAX_MS = 15000;
  const NO_SPEECH_MS = 6000;
  const PRE_ROLL_MS = 300;     // keep this much audio before the first detected speech (first word is never cut)
  const TAIL_KEEP_MS = 250;    // of the trailing silence only this much is uploaded (smaller upload, faster STT)
  const OUT_RATE = 16000;
  const FRAME = 2048;          // samples per audio callback
  const placeholder = userInput ? userInput.placeholder : "";

  // same markup as the page's own appendMessage()
  function addMessage(sender, html) {
    const d = document.createElement("div");
    d.className = "message " + sender;
    d.innerHTML = html;
    chatMessages.appendChild(d);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return d;
  }
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  const ICON = { idle: "🎤", listening: "⏺", thinking: "⏳", speaking: "🔊" };
  function setState(s) {
    state = s;
    btn.textContent = ICON[s];
    if (userInput) userInput.placeholder = s === "listening" ? "Listening... boliye" : placeholder;
  }

  let stream, ctx, proc, rec, state = "idle", cancelled = false, startAborted = false;

  // ---------- capture with silence detection ----------
  async function startListening() {
    if (state !== "idle") return;
    setState("listening");                 // show it at once; also blocks a 2nd click while the permission prompt is open
    startAborted = false;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (e) {
      setState("idle");
      return alert("Microphone permission chahiye.");
    }
    if (startAborted) {                    // user clicked again while the mic was still opening
      stream.getTracks().forEach((t) => t.stop());
      return setState("idle");
    }

    ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") await ctx.resume();   // created after an await -> browser may keep it suspended (silent input)
    if (startAborted) {                    // clicked again while the audio engine was starting
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
      return setState("idle");
    }
    const rate = ctx.sampleRate;
    const frameMs = (FRAME / rate) * 1000;
    const src = ctx.createMediaStreamSource(stream);
    proc = ctx.createScriptProcessor(FRAME, 1, 1);
    const mute = ctx.createGain(); mute.gain.value = 0;   // the graph must reach the speakers for the callback to fire; gain 0 = silent
    src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);

    const t0 = performance.now();
    const calibFrames = Math.max(2, Math.round(200 / frameMs));      // first ~200 ms = background noise
    rec = {
      frames: [], rate, heard: false, firstVoiceIdx: 0, tailUnvoiced: 0, peakAll: 0,
      preFrames: Math.ceil(PRE_ROLL_MS / frameMs), tailFrames: Math.ceil(TAIL_KEEP_MS / frameMs),
    };
    let lastVoice = t0, nf = null, n = 0;                            // nf = noise floor

    proc.onaudioprocess = (e) => {
      if (!proc) return;
      const x = e.inputBuffer.getChannelData(0);
      let sum = 0, pk = 0;
      for (let i = 0; i < x.length; i++) { const v = x[i]; sum += v * v; const a = v < 0 ? -v : v; if (a > pk) pk = a; }
      const rms = Math.sqrt(sum / x.length);
      const now = performance.now();
      if (pk > rec.peakAll) rec.peakAll = pk;
      rec.frames.push(new Float32Array(x));

      // Noise floor = QUIETEST of the first frames (capped). Using the loudest one (old code) made your own first word
      // the "noise", so the threshold became too high and speech was never detected.
      n++;
      if (n <= calibFrames) {
        nf = nf === null ? Math.min(rms, 0.015) : Math.min(nf, rms);
        rec.tailUnvoiced++;
        return;
      }
      const threshold = Math.min(0.05, Math.max(0.010, nf * 3));
      if (window.VOICE_DEBUG) console.log("[voice] rms", rms.toFixed(4), "thr", threshold.toFixed(4));
      if (rms > threshold) {
        if (!rec.heard) { rec.heard = true; rec.firstVoiceIdx = rec.frames.length - 1; }
        lastVoice = now;
        rec.tailUnvoiced = 0;
      } else {
        rec.tailUnvoiced++;
        if (!rec.heard) nf = nf * 0.95 + Math.min(rms, 0.015) * 0.05;   // follow slow background changes
      }

      if (rec.heard && now - lastVoice > SILENCE_MS) stopListening();
      else if (!rec.heard && now - t0 > NO_SPEECH_MS) stopListening();   // detector heard nothing -> still send what was recorded (checked below)
      else if (now - t0 > MAX_MS) stopListening();
    };
  }

  function stopListening(cancel) {
    cancelled = !!cancel;
    if (!proc) { startAborted = true; return; }   // mic is still opening
    const p = proc, c = ctx, s = stream, r = rec;
    proc = null;                                  // guards against a 2nd call from the next audio callback
    p.onaudioprocess = null;
    try { p.disconnect(); } catch (e) { /* already disconnected */ }
    s && s.getTracks().forEach((t) => t.stop());
    c && c.close();
    if (cancelled) return setState("idle");
    onRecorded(r);
  }

  // ---------- 16 kHz mono WAV, built from the captured PCM (instant) ----------
  function buildWav(r) {
    let fr = r.frames;
    if (r.heard) {                                                    // drop silence before the speech (keep a short pre-roll) and most of the trailing silence
      fr = fr.slice(Math.max(0, r.firstVoiceIdx - r.preFrames));
      const cut = r.tailUnvoiced - r.tailFrames;
      if (cut > 0) fr = fr.slice(0, Math.max(1, fr.length - cut));
    }
    let len = 0;
    for (const f of fr) len += f.length;
    const all = new Float32Array(len);
    let o = 0;
    for (const f of fr) { all.set(f, o); o += f.length; }

    let pcm = all;                                                    // box-filter downsample to 16 kHz
    if (r.rate !== OUT_RATE) {
      const ratio = r.rate / OUT_RATE;
      const m = Math.max(1, Math.floor(all.length / ratio));
      pcm = new Float32Array(m);
      for (let i = 0; i < m; i++) {
        const s = Math.floor(i * ratio), e = Math.min(all.length, Math.max(s + 1, Math.floor((i + 1) * ratio)));
        let sum = 0;
        for (let j = s; j < e; j++) sum += all[j];
        pcm[i] = sum / (e - s);
      }
    }

    let peak = 0;
    for (let i = 0; i < pcm.length; i++) { const a = Math.abs(pcm[i]); if (a > peak) peak = a; }
    if (peak > 0.004 && peak < 0.25) {                                // quiet mic -> lift it so the speech model hears it clearly
      const g = Math.min(8, 0.5 / peak);
      for (let i = 0; i < pcm.length; i++) pcm[i] *= g;
    }

    const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const w = (off, s) => [...s].forEach((c, i) => out.setUint8(off + i, c.charCodeAt(0)));
    w(0, "RIFF"); out.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVEfmt ");
    out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true);
    out.setUint32(24, OUT_RATE, true); out.setUint32(28, OUT_RATE * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
    w(36, "data"); out.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) {
      const s = Math.max(-1, Math.min(1, pcm[i]));
      out.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    const wavBlob = new Blob([out], { type: "audio/wav" });
    wavBlob.peak = r.peakAll;                                         // peak of what the mic really delivered (before any lifting)
    wavBlob.seconds = pcm.length / OUT_RATE;
    return wavBlob;
  }

  // ---------- playback queue (chunks arrive while the first one is already playing) ----------
  let queue = [], playing = null, streamDone = true;
  function stopPlayback() {
    queue = [];
    if (playing) { playing.pause(); playing = null; }
  }
  function enqueue(b64) { queue.push(b64); if (!playing) playNext(); }
  function playNext() {
    const next = queue.shift();
    if (!next) {
      playing = null;
      if (streamDone) setState("idle");
      return;
    }
    playing = new Audio("data:audio/wav;base64," + next);
    playing.onended = playNext;
    playing.onerror = playNext;
    setState("speaking");
    playing.play().catch(playNext);
  }

  // ---------- send + read NDJSON stream ----------
  async function onRecorded(r) {
    setState("thinking");
    const loadingMsg = addMessage("bot", "Thinking...");
    const tStop = performance.now();                      // end of your speech
    try {
      const wav = buildWav(r);
      if (window.VOICE_DEBUG) console.log("[voice] recorded peak", wav.peak, "bytes", wav.size, "seconds", wav.seconds.toFixed(2));
      if (wav.peak < 0.004) {      // recording is really silent -> mic problem, not a speech problem
        loadingMsg.remove();
        addMessage("bot", "Mic se awaaz record nahi hui. Browser (address bar ke mic icon) aur Windows Sound > Input me sahi mic select/unmute karein, phir dobara try karein.");
        return setState("idle");
      }
      const fd = new FormData();
      fd.append("audio", wav, "voice.wav");
      const res = await fetch(API, { method: "POST", body: fd, credentials: "same-origin" });
      if (!(res.headers.get("content-type") || "").includes("ndjson")) {
        const j = await res.json();
        loadingMsg.remove();
        addMessage("bot", j.reply || "Voice me error aaya.");
        return setState("idle");
      }
      streamDone = false;
      let gotText = false, gotAudio = false;
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const m = JSON.parse(line);
          if (m.type === "text") {
            if (!gotText) { gotText = true; console.log("[voice] you stopped talking -> reply text: " + Math.round(performance.now() - tStop) + " ms"); }
            loadingMsg.remove(); addMessage("user", esc(m.transcript)); addMessage("bot", m.reply);
          }
          else if (m.type === "audio") {
            if (!gotAudio) { gotAudio = true; console.log("[voice] you stopped talking -> first audio: " + Math.round(performance.now() - tStop) + " ms"); }
            enqueue(m.b64);
          }
          else if (m.type === "audio_error") console.warn(m.message);
          else if (m.type === "done") console.log("[voice timing]", m.timing);
        }
      }
    } catch (e) {
      console.error(e);
      loadingMsg.remove();
      addMessage("bot", "Voice me problem aayi, kripya dobara try karein.");
    } finally {
      streamDone = true;
      loadingMsg.remove();
      if (!playing) setState("idle");
    }
  }

  btn.addEventListener("click", () => {
    if (state === "idle") startListening();
    else if (state === "listening") stopListening();
    else if (state === "speaking") { stopPlayback(); streamDone = true; setState("idle"); }
  });
  setState("idle");
})();