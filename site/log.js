// site/log.js
// Edit-in-place loader + saver for /log
// Theme toggle: System -> Dark -> Light (persisted)

(function () {
	"use strict";

	const $ = (id) => document.getElementById(id);

	const payloadEl = $("payload");
	const msgEl = $("msg");
	const datePickEl = $("datePick");
	const loadedLabelEl = $("loadedLabel");

	const loadBtn = $("loadBtn");
	const todayBtn = $("todayBtn");
	const saveBtn = $("saveBtn");
	const saveGoBtn = $("saveGoBtn");

	const mergeChk = $("mergeChk");
	const overwriteChk = $("overwriteChk");

	const themeBtn = $("themeBtn");

	// -----------------------------
	// Theme (System/Dark/Light)
	// -----------------------------
	const THEME_KEY = "loseit_theme"; // "system" | "dark" | "light"

	function setTheme(mode) {
		// mode: "system" | "dark" | "light"
		if (mode !== "system" && mode !== "dark" && mode !== "light") {
			mode = "system";
		}

		if (mode === "system") {
			delete document.documentElement.dataset.theme;
		} else {
			document.documentElement.dataset.theme = mode;
		}

		localStorage.setItem(THEME_KEY, mode);
		updateThemeButton(mode);
	}

	function getTheme() {
		const v = localStorage.getItem(THEME_KEY);
		if (v === "dark" || v === "light" || v === "system") return v;
		return "system";
	}

	function updateThemeButton(mode) {
		if (!themeBtn) return;
		if (mode === "dark") themeBtn.textContent = "Theme: Dark";
		else if (mode === "light") themeBtn.textContent = "Theme: Light";
		else themeBtn.textContent = "Theme: System";
	}

	function cycleTheme() {
		const cur = getTheme();
		if (cur === "system") return setTheme("dark");
		if (cur === "dark") return setTheme("light");
		return setTheme("system");
	}

	// -----------------------------
	// UI helpers
	// -----------------------------
	function showMsg(text, ok) {
		if (!text) {
			msgEl.style.display = "none";
			msgEl.textContent = "";
			msgEl.className = "notice";
			return;
		}
		msgEl.style.display = "block";
		msgEl.textContent = text;
		msgEl.className = ok ? "notice ok" : "notice err";
	}

	function todayISO() {
		const d = new Date();
		const y = d.getFullYear();
		const m = String(d.getMonth() + 1).padStart(2, "0");
		const day = String(d.getDate()).padStart(2, "0");
		return `${y}-${m}-${day}`;
	}

	function getQueryDate() {
		const u = new URL(window.location.href);
		const qd = u.searchParams.get("date");
		if (qd && /^\d{4}-\d{2}-\d{2}$/.test(qd)) return qd;
		return "";
	}

	function setUrlDate(dateStr) {
		const u = new URL(window.location.href);
		if (dateStr) u.searchParams.set("date", dateStr);
		else u.searchParams.delete("date");
		history.replaceState(null, "", u.toString());
	}

	async function fetchEntry(dateStr) {
		const url = new URL("/api/entry", window.location.origin);
		if (dateStr) url.searchParams.set("date", dateStr);
		const resp = await fetch(url.toString(), { method: "GET" });
		if (!resp.ok) {
			const t = await resp.text();
			throw new Error(`Load failed (${resp.status}): ${t}`);
		}
		return await resp.json();
	}

	function safePretty(obj) {
		return JSON.stringify(obj, null, 2);
	}

	function parseEditorJSON() {
		const raw = (payloadEl.value || "").trim();
		if (!raw) throw new Error("Editor is empty.");
		try {
			const obj = JSON.parse(raw);
			if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
				throw new Error("Payload must be a single JSON object.");
			}
			return obj;
		} catch (e) {
			throw new Error(`Invalid JSON: ${e.message || e}`);
		}
	}

	async function saveEntry(goDashboard) {
		// If both checked, prefer merge (safer)
		let merge = !!mergeChk.checked;
		let overwrite = !!overwriteChk.checked;
		if (merge && overwrite) overwrite = false;

		const entry = parseEditorJSON();

		const resp = await fetch("/api/save", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ entry, merge, overwrite }),
		});

		let data;
		try {
			data = await resp.json();
		} catch {
			const t = await resp.text();
			throw new Error(`Save failed (${resp.status}): ${t}`);
		}

		if (!resp.ok || !data || data.ok !== true) {
			const err = (data && (data.error || data.message)) ? (data.error || data.message) : "Save failed.";
			throw new Error(err);
		}

		const dateStr = (data.date && typeof data.date === "string") ? data.date : "";
		if (dateStr) {
			datePickEl.value = dateStr;
			loadedLabelEl.textContent = `Loaded date: ${dateStr}`;
			setUrlDate(dateStr);
		}

		showMsg(data.message || "Saved.", true);

		if (goDashboard) {
			window.location.href = "/";
			return;
		}

		// Reload from server so editor stays in sync with merge results
		if (dateStr) {
			const fresh = await fetchEntry(dateStr);
			payloadEl.value = safePretty(fresh);
		}
	}

	async function loadDate(dateStr) {
		const d = dateStr && /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? dateStr : todayISO();
		showMsg("", false);
		payloadEl.value = "Loading...";
		const obj = await fetchEntry(d);
		payloadEl.value = safePretty(obj);
		datePickEl.value = d;
		loadedLabelEl.textContent = `Loaded date: ${d}`;
		setUrlDate(d);
	}

	// -----------------------------
	// Events
	// -----------------------------
	loadBtn.addEventListener("click", async () => {
		try {
			const d = (datePickEl.value || "").trim();
			await loadDate(d);
		} catch (e) {
			showMsg(e.message || String(e), false);
		}
	});

	todayBtn.addEventListener("click", async () => {
		try {
			await loadDate(todayISO());
		} catch (e) {
			showMsg(e.message || String(e), false);
		}
	});

	saveBtn.addEventListener("click", async () => {
		try {
			await saveEntry(false);
		} catch (e) {
			showMsg(e.message || String(e), false);
		}
	});

	saveGoBtn.addEventListener("click", async () => {
		try {
			await saveEntry(true);
		} catch (e) {
			showMsg(e.message || String(e), false);
		}
	});

	if (themeBtn) {
		themeBtn.addEventListener("click", () => {
			cycleTheme();
		});
	}

	// -----------------------------
	// Init
	// -----------------------------
	(async () => {
		try {
			// Apply stored theme
			setTheme(getTheme());

			const qd = getQueryDate();
			await loadDate(qd || todayISO());
		} catch (e) {
			showMsg(e.message || String(e), false);
		}
	})();
})();
