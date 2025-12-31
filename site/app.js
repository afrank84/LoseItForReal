(function () {
	"use strict";

	// ----------------------------------------
	// Theme (System/Dark/Light) shared with /log
	// ----------------------------------------
	const THEME_KEY = "loseit_theme"; // "system" | "dark" | "light"
	const themeBtn = document.getElementById("themeBtn");

	function setTheme(mode) {
		if (mode !== "system" && mode !== "dark" && mode !== "light") mode = "system";

		if (mode === "system") {
			delete document.documentElement.dataset.theme;
		} else {
			document.documentElement.dataset.theme = mode;
		}

		localStorage.setItem(THEME_KEY, mode);

		if (themeBtn) {
			themeBtn.textContent =
				mode === "dark" ? "Theme: Dark" :
					mode === "light" ? "Theme: Light" :
						"Theme: System";
		}
	}

	function getTheme() {
		const v = localStorage.getItem(THEME_KEY);
		return (v === "dark" || v === "light" || v === "system") ? v : "system";
	}

	function cycleTheme() {
		const cur = getTheme();
		if (cur === "system") setTheme("dark");
		else if (cur === "dark") setTheme("light");
		else setTheme("system");

		// Redraw chart with new colors
		if (window.__dashboard_redraw) window.__dashboard_redraw();
	}

	// Apply stored theme immediately
	setTheme(getTheme());
	if (themeBtn) themeBtn.addEventListener("click", cycleTheme);

	// Helper to read CSS variables for chart colors
	function cssVar(name, fallback) {
		const v = getComputedStyle(document.documentElement).getPropertyValue(name);
		const t = (v || "").trim();
		return t || fallback;
	}

	function parseJsonl(text) {
		const out = [];
		const lines = text.split("\n");
		for (const line of lines) {
			const t = line.trim();
			if (!t) continue;
			try {
				out.push(JSON.parse(t));
			} catch (e) {
				out.push({ date: "UNKNOWN", _corrupt: true, raw: t });
			}
		}
		return out;
	}

	function getKcal(entry) {
		const est = entry.estimates || {};
		const v = est.total_kcal;
		if (typeof v === "number") return Math.round(v);

		// fallback: sum meal kcal keys if present
		const keys = ["breakfast_kcal", "lunch_kcal", "dinner_kcal", "snacks_kcal"];
		let total = 0;
		let any = false;
		for (const k of keys) {
			if (typeof est[k] === "number") {
				total += est[k];
				any = true;
			}
		}
		return any ? Math.round(total) : null;
	}

	function rollingAvg(values, windowSize) {
		const out = new Array(values.length).fill(null);
		for (let i = 0; i < values.length; i++) {
			let sum = 0;
			let count = 0;
			for (let j = i - windowSize + 1; j <= i; j++) {
				if (j < 0) continue;
				const v = values[j];
				if (typeof v === "number") {
					sum += v;
					count += 1;
				}
			}
			if (count === windowSize) {
				out[i] = sum / windowSize;
			}
		}
		return out;
	}

	function byDateAsc(a, b) {
		return String(a.date).localeCompare(String(b.date));
	}

	function esc(s) {
		return String(s || "").replace(/[&<>"']/g, (c) => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
		}[c]));
	}

	function drawChart(svg, xs, ys, ysAvg) {
		const w = svg.clientWidth || 900;
		const h = svg.clientHeight || 220;
		svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
		while (svg.firstChild) svg.removeChild(svg.firstChild);

		// Theme-aware colors (fall back to reasonable defaults)
		const axisStroke = cssVar("--muted", "#9ca3af");
		const gridStroke = cssVar("--border", "#e5e7eb");
		const labelFill = cssVar("--muted", "#6b7280");
		const dailyStroke = cssVar("--text", "#111827");
		const avgStroke = cssVar("--accent", "#2563eb");

		// padding
		const padL = 48, padR = 12, padT = 12, padB = 28;
		const plotW = w - padL - padR;
		const plotH = h - padT - padB;

		const points = ys.filter(v => typeof v === "number");
		const avgPoints = ysAvg.filter(v => typeof v === "number");
		const all = points.concat(avgPoints);
		const minY = all.length ? Math.min(...all) : 0;
		const maxY = all.length ? Math.max(...all) : 1;

		const yMin = Math.floor(minY / 100) * 100;
		const yMax = Math.ceil(maxY / 100) * 100 + 1;

		function xScale(i) {
			if (xs.length <= 1) return padL + plotW / 2;
			return padL + (i / (xs.length - 1)) * plotW;
		}
		function yScale(v) {
			const t = (v - yMin) / (yMax - yMin);
			return padT + (1 - t) * plotH;
		}

		// axes
		const axis = document.createElementNS("http://www.w3.org/2000/svg", "path");
		axis.setAttribute("d", `M${padL},${padT} V${padT + plotH} H${padL + plotW}`);
		axis.setAttribute("fill", "none");
		axis.setAttribute("stroke", axisStroke);
		axis.setAttribute("stroke-width", "1");
		svg.appendChild(axis);

		// y ticks (5)
		const ticks = 5;
		for (let i = 0; i <= ticks; i++) {
			const v = yMin + (i / ticks) * (yMax - yMin);
			const y = yScale(v);

			const grid = document.createElementNS("http://www.w3.org/2000/svg", "path");
			grid.setAttribute("d", `M${padL},${y} H${padL + plotW}`);
			grid.setAttribute("stroke", gridStroke);
			grid.setAttribute("stroke-width", "1");
			svg.appendChild(grid);

			const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
			label.textContent = String(Math.round(v));
			label.setAttribute("x", String(8));
			label.setAttribute("y", String(y + 4));
			label.setAttribute("font-size", "12");
			label.setAttribute("fill", labelFill);
			svg.appendChild(label);
		}

		function pathFrom(series) {
			let d = "";
			for (let i = 0; i < series.length; i++) {
				const v = series[i];
				if (typeof v !== "number") continue;
				const x = xScale(i);
				const y = yScale(v);
				d += (d ? " L" : "M") + x + "," + y;
			}
			return d;
		}

		// daily line
		const p1 = document.createElementNS("http://www.w3.org/2000/svg", "path");
		p1.setAttribute("d", pathFrom(ys));
		p1.setAttribute("fill", "none");
		p1.setAttribute("stroke", dailyStroke);
		p1.setAttribute("stroke-width", "2");
		svg.appendChild(p1);

		// 7-day avg line
		const p2 = document.createElementNS("http://www.w3.org/2000/svg", "path");
		p2.setAttribute("d", pathFrom(ysAvg));
		p2.setAttribute("fill", "none");
		p2.setAttribute("stroke", avgStroke);
		p2.setAttribute("stroke-width", "3");
		svg.appendChild(p2);

		// x labels (start/mid/end)
		const idxs = [0, Math.floor((xs.length - 1) / 2), xs.length - 1]
			.filter((v, i, a) => a.indexOf(v) === i);

		for (const idx of idxs) {
			if (idx < 0 || idx >= xs.length) continue;
			const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
			t.textContent = xs[idx];
			t.setAttribute("x", String(xScale(idx)));
			t.setAttribute("y", String(padT + plotH + 20));
			t.setAttribute("text-anchor", "middle");
			t.setAttribute("font-size", "12");
			t.setAttribute("fill", labelFill);
			svg.appendChild(t);
		}
	}

	function renderDetail(entry) {
		const el = document.getElementById("detail");
		if (!entry) {
			el.innerHTML = "";
			document.getElementById("detailHint").textContent =
				"Click a day from the table to see what you ate and the estimate breakdown.";
			return;
		}
		document.getElementById("detailHint").textContent = "";

		const mealsText = entry.meals_text || {};
		const est = entry.estimates || {};
		const kcal = getKcal(entry);

		function mealBlock(label, key) {
			const txt = mealsText[key] || "";
			if (!txt.trim()) return "";
			return `<h3 style="margin:12px 0 6px 0;">${esc(label)}</h3><div class="mono">${esc(txt)}</div>`;
		}

		const estRows = [];
		for (const k of ["breakfast_kcal", "lunch_kcal", "dinner_kcal", "snacks_kcal", "total_kcal", "protein_g", "weight_lb"]) {
			if (typeof est[k] === "number") {
				estRows.push(`<tr><td>${esc(k)}</td><td>${esc(est[k])}</td></tr>`);
			}
		}

		el.innerHTML = `
      <div class="small"><b>Date:</b> ${esc(entry.date || "")}</div>
      <div class="small"><b>Kcal:</b> ${kcal === null ? "n/a" : esc(kcal)}</div>
      <div class="small"><b>Day type:</b> ${esc(entry.day_type || "")}</div>
      <div class="small"><b>Source:</b> ${esc(entry.source || "")}</div>
      ${entry.notes ? `<h3 style="margin:12px 0 6px 0;">Notes</h3><div class="mono">${esc(entry.notes)}</div>` : ""}

      ${mealBlock("Breakfast", "breakfast")}
      ${mealBlock("Lunch", "lunch")}
      ${mealBlock("Dinner", "dinner")}
      ${mealBlock("Snacks", "snacks")}

      ${estRows.length ? `
        <h3 style="margin:12px 0 6px 0;">Estimates</h3>
        <table class="table">
          <thead><tr><th>Field</th><th>Value</th></tr></thead>
          <tbody>${estRows.join("")}</tbody>
        </table>
      ` : ""}
    `;
	}

	function renderDays(entries) {
		const tbody = document.getElementById("daysTbody");
		tbody.innerHTML = "";

		for (const e of entries) {
			const kcal = getKcal(e);
			const notes = (e.notes || "").split("\n")[0];
			const tr = document.createElement("tr");
			tr.innerHTML = `
        <td><a href="#" data-date="${esc(e.date || "")}">${esc(e.date || "")}</a></td>
        <td>${kcal === null ? "n/a" : esc(kcal)}</td>
        <td>${esc(e.day_type || "")}</td>
        <td class="small">${esc(notes)}</td>
      `;
			tbody.appendChild(tr);
		}

		tbody.querySelectorAll("a[data-date]").forEach(a => {
			a.addEventListener("click", (ev) => {
				ev.preventDefault();
				const date = a.getAttribute("data-date");
				const entry = entries.find(x => String(x.date) === String(date));
				renderDetail(entry);
			});
		});
	}

	function renderKpis(entries) {
		const kpis = document.getElementById("kpis");
		const kcalSeries = entries.map(getKcal);
		const last = entries.length ? entries[entries.length - 1] : null;
		const lastKcal = last ? getKcal(last) : null;

		// 7-day average on last available point
		const avg7 = rollingAvg(kcalSeries, 7);
		const lastAvg7 = avg7.length ? avg7[avg7.length - 1] : null;

		// average of last 14 (simple)
		const last14 = kcalSeries.slice(-14).filter(v => typeof v === "number");
		const avg14 = last14.length ? (last14.reduce((a, b) => a + b, 0) / last14.length) : null;

		const daysLogged = kcalSeries.filter(v => typeof v === "number").length;

		kpis.innerHTML = `
      <div><div class="muted small">Days logged</div><div class="big">${daysLogged}</div></div>
      <div><div class="muted small">Latest day kcal</div><div class="big">${lastKcal === null ? "n/a" : Math.round(lastKcal)}</div></div>
      <div><div class="muted small">7-day rolling avg</div><div class="big">${lastAvg7 === null ? "n/a" : Math.round(lastAvg7)}</div></div>
      <div><div class="muted small">Last 14-day avg</div><div class="big">${avg14 === null ? "n/a" : Math.round(avg14)}</div></div>
    `;
	}

	async function load() {
		const status = document.getElementById("status");
		status.textContent = "Loading entries.jsonl...";
		let text = "";
		try {
			const resp = await fetch("/data/entries.jsonl", { cache: "no-store" });
			if (!resp.ok) throw new Error("HTTP " + resp.status);
			text = await resp.text();
		} catch (e) {
			status.textContent = "Failed to load /data/entries.jsonl. Start the local server and reload.";
			return;
		}

		// Fix: parseJsonl marks corrupt lines with _corrupt, not _corrupt_line
		let entries = parseJsonl(text).filter(e => e && !e._corrupt);
		entries = entries.filter(e => e && typeof e.date === "string");
		entries.sort(byDateAsc);

		status.textContent = `Loaded ${entries.length} entries.`;

		const chart = document.getElementById("chart");

		function redraw(currentEntries) {
			const xs = currentEntries.map(e => e.date);
			const ys = currentEntries.map(getKcal);
			const ysAvg = rollingAvg(ys, 7);
			drawChart(chart, xs, ys, ysAvg);
		}

		// Expose a redraw hook so theme changes can re-color the SVG
		window.__dashboard_redraw = function () {
			redraw(entries);
		};

		renderKpis(entries);
		redraw(entries);
		renderDays(entries);
		renderDetail(null);

		// Filter controls
		document.getElementById("applyFilter").addEventListener("click", () => {
			const mode = document.getElementById("filterType").value;
			const th = parseInt(document.getElementById("threshold").value || "0", 10);

			let filtered = entries.slice();
			if (mode === "over") {
				filtered = filtered.filter(e => {
					const k = getKcal(e);
					return typeof k === "number" && k > th;
				});
			} else if (mode === "under") {
				filtered = filtered.filter(e => {
					const k = getKcal(e);
					return typeof k === "number" && k < th;
				});
			}

			redraw(filtered);
			renderDays(filtered);
			renderDetail(null);
			status.textContent = `Showing ${filtered.length} entries (filter: ${mode}).`;
		});
	}

	load();
})();
