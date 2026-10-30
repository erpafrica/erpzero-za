// "Ask Barb": Barb the Bookkeeper's panel on every desk page. Questions go to the site
// (erpzero_za.barb.api.ask), which runs Barb's tools as this user; answers come back over realtime.
(() => {
	const PROMPTS = [
		"Prepare my VAT201 for the last tax period",
		"Why is this period a refund or a payment?",
		"Who owes us money, and who should I chase first?",
		"What's left to do before month end?",
	];
	const STYLE = `
	.barb-fab{position:fixed;right:20px;bottom:20px;z-index:1030;display:flex;align-items:center;gap:8px;padding:10px 16px 10px 10px;border:0;border-radius:999px;background:#B23A2E;color:#fff;font-weight:600;box-shadow:0 6px 20px rgba(0,0,0,.18);cursor:pointer}
	.barb-fab .barb-face,.barb-panel .barb-face{width:28px;height:28px;border-radius:50%;background:#C98B2B;color:#fff;display:grid;place-items:center;font-family:Georgia,serif;font-weight:700}
	.barb-panel{position:fixed;right:20px;bottom:20px;z-index:1031;width:400px;max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 100px);display:none;flex-direction:column;background:var(--card-bg,#fff);color:var(--text-color);border:1px solid var(--border-color);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.2);overflow:hidden}
	.barb-panel.open{display:flex}
	.barb-head{display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--border-color)}
	.barb-head b{display:block}.barb-head small{color:var(--text-muted)}
	.barb-head button{margin-left:auto;border:0;background:none;font-size:20px;color:var(--text-muted);cursor:pointer}
	.barb-body{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
	.barb-msg{padding:10px 12px;border-radius:10px;line-height:1.5;max-width:92%;overflow-wrap:anywhere}
	.barb-msg.user{align-self:flex-end;background:#B23A2E;color:#fff}
	.barb-msg.barb{align-self:flex-start;background:var(--subtle-fg,#f4efe6)}
	.barb-msg.barb table{font-size:12px;margin:6px 0}.barb-msg.barb td,.barb-msg.barb th{padding:2px 6px;border-bottom:1px solid var(--border-color)}
	.barb-msg.barb p:last-child{margin-bottom:0}
	.barb-msg.note{align-self:center;background:none;color:var(--text-muted);font-size:12px;padding:2px}
	.barb-prompts{display:flex;flex-direction:column;gap:6px}
	.barb-prompts button{text-align:left;border:1px solid var(--border-color);background:none;border-radius:8px;padding:8px 10px;cursor:pointer;color:var(--text-color)}
	.barb-foot{display:flex;gap:8px;padding:10px;border-top:1px solid var(--border-color)}
	.barb-foot textarea{flex:1;resize:none;border:1px solid var(--border-color);border-radius:8px;padding:8px;background:var(--control-bg);color:var(--text-color)}
	.barb-foot button{border:0;border-radius:8px;background:#B23A2E;color:#fff;padding:0 14px;font-weight:600}
	.barb-foot button:disabled{opacity:.5}
	.barb-small{font-size:11px;color:var(--text-muted);padding:0 14px 8px}`;

	let history = [];
	let running = null;
	let $panel;

	$(document).on("app_ready", init);

	async function init() {
		if ($panel || frappe.session.user === "Guest") return;
		const r = await frappe.xcall("erpzero_za.barb.api.status").catch(() => null);
		if (!r?.enabled) return;
		$("<style>").text(STYLE).appendTo("head");
		$(`<button class="barb-fab"><span class="barb-face">B</span>Ask Barb</button>`).appendTo("body").on("click", open);
		$panel = $(`
			<div class="barb-panel" role="dialog" aria-label="Barb the Bookkeeper">
				<div class="barb-head"><span class="barb-face">B</span><div><b>Barb the Bookkeeper</b><small>Drafts only. You check and submit.</small></div><button title="Close">×</button></div>
				<div class="barb-body"></div>
				<div class="barb-foot"><textarea rows="2" placeholder="Ask about your books…"></textarea><button>Ask</button></div>
				<div class="barb-small">Barb reads your books with your permissions. She never submits, pays, sends or files.</div>
			</div>`).appendTo("body");
		$panel.find(".barb-head button").on("click", () => $panel.removeClass("open"));
		$panel.find(".barb-foot button").on("click", send);
		$panel.find("textarea").on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				send();
			}
		});
		frappe.realtime.on("barb", onEvent);
		greet(r);
		// Demo guests came to meet Barb: open her once per session
		if (r.demo_guest && !sessionStorage.getItem("barb-opened")) {
			sessionStorage.setItem("barb-opened", "1");
			open();
		}
	}

	function open() {
		$panel.addClass("open");
		$panel.find("textarea").trigger("focus");
	}

	function greet(r) {
		const $body = $panel.find(".barb-body").empty();
		add("barb", `Hello ${frappe.boot.user.first_name || ""}. I'm Barb. Ask me about your books: VAT, debtors, reports, or the document you have open.`);
		if (r?.demo_guest) add("note", `Demo: ${r.questions_left} questions left today.`);
		const $p = $(`<div class="barb-prompts"></div>`).appendTo($body);
		PROMPTS.forEach((q) => $(`<button></button>`).text(q).appendTo($p).on("click", () => send(q)));
	}

	function add(who, text) {
		const $m = $(`<div class="barb-msg ${who}"></div>`);
		who === "barb" ? $m.html(frappe.markdown(text)) : $m.text(text);
		const $body = $panel.find(".barb-body").append($m);
		$body.scrollTop($body[0].scrollHeight);
		return $m;
	}

	async function send(preset) {
		const $t = $panel.find("textarea");
		const question = (typeof preset === "string" ? preset : $t.val()).trim();
		if (!question || running) return;
		$t.val("");
		$panel.find(".barb-prompts").remove();
		add("user", question);
		setBusy(true);
		const route = frappe.get_route();
		const onForm = route[0] === "Form";
		try {
			running = await frappe.xcall("erpzero_za.barb.api.ask", {
				question,
				history: JSON.stringify(history),
				doctype: onForm ? route[1] : null,
				docname: onForm ? route[2] : null,
			});
			history.push({ role: "user", content: question });
			add("note", "Barb is looking…").addClass("barb-status");
		} catch (e) {
			setBusy(false);
		}
	}

	function onEvent(data) {
		if (!running || data.log !== running) return;
		const $status = $panel.find(".barb-status").last();
		if (data.state === "working") {
			$status.text(`Barb is looking… (${data.tool.replace(/_/g, " ")})`);
			return;
		}
		$status.remove();
		if (data.state === "done") {
			add("barb", data.answer);
			history.push({ role: "assistant", content: data.answer });
		} else {
			add("note", data.error || "Barb couldn't answer that.");
		}
		running = null;
		setBusy(false);
	}

	function setBusy(on) {
		$panel.find(".barb-foot button").prop("disabled", on);
	}

	window.barb = { open: () => $panel && open() };
})();
