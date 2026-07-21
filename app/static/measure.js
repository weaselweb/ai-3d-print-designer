// Interactive scale + measurement over an uploaded photo. Plain script (no modules).
(function () {
  const app = document.getElementById("measure-app");
  if (!app) return;
  const captureId = app.dataset.captureId;
  const canvas = document.getElementById("canvas");
  const ctx = canvas.getContext("2d");

  const refSelect = document.getElementById("ref-select");
  const customFields = document.getElementById("custom-fields");
  const customName = document.getElementById("custom-name");
  const customMm = document.getElementById("custom-mm");
  const measureName = document.getElementById("measure-name");
  const btnCalibrate = document.getElementById("btn-calibrate");
  const scaleStatus = document.getElementById("scale-status");
  const measInput = document.getElementById("meas-name");
  const btnMeasure = document.getElementById("btn-measure");
  const measList = document.getElementById("meas-list");
  const btnGenerate = document.getElementById("btn-generate");
  const genStatus = document.getElementById("gen-status");
  const description = document.getElementById("description");

  const img = new Image();
  let mode = null;            // 'calibrate' | 'measure' | null
  let pending = [];           // points awaiting a pair
  let calSeg = null;          // {p1,p2}
  let mmPerPx = null;
  let measurements = [];      // {name, mm, p1, p2}

  img.onload = function () {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    redraw();
  };
  img.src = app.dataset.imageUrl;

  function currentRefMm() {
    const opt = refSelect.options[refSelect.selectedIndex];
    if (opt.dataset.custom === "1") return parseFloat(customMm.value) || 0;
    return parseFloat(opt.dataset.mm) || 0;
  }

  refSelect.addEventListener("change", function () {
    const opt = refSelect.options[refSelect.selectedIndex];
    customFields.classList.toggle("d-none", opt.dataset.custom !== "1");
    measureName.textContent = opt.dataset.measure || "known dimension";
  });

  function dist(a, b) { return Math.hypot(b[0] - a[0], b[1] - a[1]); }

  function toImageCoords(e) {
    const r = canvas.getBoundingClientRect();
    return [(e.clientX - r.left) * (canvas.width / r.width),
            (e.clientY - r.top) * (canvas.height / r.height)];
  }

  btnCalibrate.addEventListener("click", function () {
    if (currentRefMm() <= 0) { scaleStatus.textContent = "Enter the reference length first."; return; }
    mode = "calibrate"; pending = [];
    scaleStatus.innerHTML = "Click point <b>1</b> of the reference…";
  });

  btnMeasure.addEventListener("click", function () {
    if (mmPerPx === null) return;
    if (!measInput.value.trim()) { measInput.focus(); return; }
    mode = "measure"; pending = [];
    genStatus.textContent = 'Click the 2 points of "' + measInput.value.trim() + '"…';
  });

  canvas.addEventListener("click", function (e) {
    if (!mode) return;
    pending.push(toImageCoords(e));
    if (pending.length === 1) {
      if (mode === "calibrate") scaleStatus.innerHTML = "Click point <b>2</b> of the reference…";
    } else if (pending.length === 2) {
      if (mode === "calibrate") finishCalibration();
      else finishMeasurement();
      pending = []; mode = null;
    }
    redraw();
  });

  function finishCalibration() {
    const refMm = currentRefMm();
    const px = dist(pending[0], pending[1]);
    if (px <= 0) { scaleStatus.textContent = "Points too close — try again."; return; }
    mmPerPx = refMm / px;
    calSeg = { p1: pending[0], p2: pending[1] };
    const opt = refSelect.options[refSelect.selectedIndex];
    const acc = px / Math.hypot(canvas.width, canvas.height);
    const hint = acc < 0.15 ? "low (reference small in frame)" : acc < 0.30 ? "ok" : "good";
    scaleStatus.innerHTML = "Scale set: <b>" + mmPerPx.toFixed(4) + "</b> mm/px · " +
      (opt.dataset.custom === "1" ? (customName.value || "custom") : opt.text.split(" —")[0]) +
      " · accuracy " + hint;
    btnMeasure.disabled = false;
  }

  function finishMeasurement() {
    const mm = +(dist(pending[0], pending[1]) * mmPerPx).toFixed(2);
    const name = measInput.value.trim() || ("dimension " + (measurements.length + 1));
    measurements.push({ name: name, mm: mm, p1: pending[0], p2: pending[1] });
    measInput.value = "";
    renderList();
    btnGenerate.disabled = false;
    genStatus.textContent = "";
  }

  function renderList() {
    measList.innerHTML = "";
    measurements.forEach(function (m, i) {
      const li = document.createElement("li");
      li.className = "list-group-item bg-transparent d-flex justify-content-between align-items-center px-0";
      li.innerHTML = '<span><span class="fw-semibold">' + m.name + '</span> — ' + m.mm +
        ' mm</span><button class="btn btn-sm btn-outline-danger py-0">×</button>';
      li.querySelector("button").onclick = function () {
        measurements.splice(i, 1); renderList(); redraw();
        btnGenerate.disabled = measurements.length === 0;
      };
      measList.appendChild(li);
    });
  }

  function drawSeg(p1, p2, color, label) {
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = Math.max(2, canvas.width / 400);
    ctx.beginPath(); ctx.moveTo(p1[0], p1[1]); ctx.lineTo(p2[0], p2[1]); ctx.stroke();
    [p1, p2].forEach(function (p) { ctx.beginPath(); ctx.arc(p[0], p[1], ctx.lineWidth * 1.6, 0, 7); ctx.fill(); });
    if (label) {
      const mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
      ctx.font = Math.max(14, canvas.width / 45) + "px sans-serif";
      ctx.fillStyle = "#000"; ctx.fillRect(mx + 4, my - 18, ctx.measureText(label).width + 8, 22);
      ctx.fillStyle = color; ctx.fillText(label, mx + 8, my - 2);
    }
  }

  function redraw() {
    ctx.drawImage(img, 0, 0);
    if (calSeg) drawSeg(calSeg.p1, calSeg.p2, "#ffd400", "ref");
    measurements.forEach(function (m) { drawSeg(m.p1, m.p2, "#22d3ee", m.name + " " + m.mm + "mm"); });
    ctx.fillStyle = "#ff4d4d";
    pending.forEach(function (p) { ctx.beginPath(); ctx.arc(p[0], p[1], Math.max(3, canvas.width / 250), 0, 7); ctx.fill(); });
  }

  btnGenerate.addEventListener("click", function () {
    const opt = refSelect.options[refSelect.selectedIndex];
    btnGenerate.disabled = true;
    genStatus.textContent = "Generating — this can take up to a minute…";
    fetch("/capture/" + captureId + "/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reference_label: opt.dataset.custom === "1" ? (customName.value || "custom") : opt.text,
        reference_mm: currentRefMm(),
        mm_per_px: mmPerPx,
        measurements: measurements,
        description: description.value,
      }),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j.design_url) { window.location = res.j.design_url; }
        else { genStatus.textContent = "Error: " + (res.j.error || "generation failed"); btnGenerate.disabled = false; }
      })
      .catch(function (err) { genStatus.textContent = "Error: " + err; btnGenerate.disabled = false; });
  });
})();
