"""
k8sgpt-ui — airgap troubleshooting assistant for Helm / Kubernetes.

Two modes, one chat (context kept across both):
  1. Paste error  -> model explains + suggests fix.
  2. Scan cluster -> runs k8sgpt (detection only, JSON), feeds findings to model.

Runbooks are NOT injected automatically — browse them in the sidebar, or turn on
"Ground answers in runbooks" to let the model use the relevant ones as context.

Talks to a local Ollama for the model. k8sgpt runs as a subprocess (binary baked
into the image). No internet required at runtime.
"""

import json
import math
import os
import re
import subprocess
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

# --- config (env-overridable) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("MODEL", "qwen2.5-coder:7b")
# build-time version (set via APP_VERSION build-arg/env; blank in local dev)
APP_VERSION = os.environ.get("APP_VERSION", "").strip()
RUNBOOKS_DIR = Path(os.environ.get("RUNBOOKS_DIR", "/app/runbooks"))
# where an uploaded kubeconfig is written (writable, survives reruns within session)
UPLOAD_KUBECONFIG = os.environ.get("UPLOAD_KUBECONFIG", "/tmp/uploaded-kubeconfig")
# Ollama tuning: bigger context avoids 500s on long scans; keep_alive avoids reloads.
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
# cap how many past messages we resend each turn (bounds latency + context growth)
MAX_HISTORY = int(os.environ.get("MAX_HISTORY_MESSAGES", "16"))
# safety cap on the (already de-duplicated) scan text fed to the model. The full
# results are always shown in the chat; this only bounds the model input on huge
# clusters so a 7B model on CPU doesn't stall reading the prompt.
MAX_SCAN_CHARS = int(os.environ.get("MAX_SCAN_CHARS", "9000"))

SYSTEM_PROMPT = (
    "You are a Kubernetes and Helm troubleshooting assistant. "
    "A user gives you an error message or cluster findings. "
    "Identify the root cause and give concrete, copy-pasteable fix steps "
    "(kubectl / helm commands, manifest changes). Be concise. "
    "If runbook context is provided, prefer it. If unsure, say so and give "
    "the most likely fix plus how to confirm it. "
    "Do NOT paste whole runbooks back to the user; answer their question directly."
)


# ---------- kubeconfig discovery ----------
def kubeconfig_candidates():
    """Common kubeconfig locations, in priority order. $KUBECONFIG may be a list."""
    cands = []
    env = os.environ.get("KUBECONFIG", "")
    for p in env.split(os.pathsep):
        if p.strip():
            cands.append(p.strip())
    home = os.path.expanduser("~")
    cands += [
        os.path.join(home, ".kube", "config"),
        "/root/.kube/config",
        "/home/user/.kube/config",
        "/etc/kubernetes/admin.conf",
    ]
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def discovered_kubeconfig():
    """First existing kubeconfig among the common locations, else None."""
    for c in kubeconfig_candidates():
        if os.path.isfile(c):
            return c
    return None


def active_kubeconfig():
    """Uploaded kubeconfig wins; else the first discovered default. Returns path or None."""
    up = st.session_state.get("kubeconfig_path")
    if up and os.path.isfile(up):
        return up
    return discovered_kubeconfig()


# ---------- runbook retrieval (naive keyword match, airgap-friendly) ----------
def load_runbooks():
    docs = []
    if RUNBOOKS_DIR.is_dir():
        for p in sorted(RUNBOOKS_DIR.glob("*.md")):
            docs.append((p.name, p.read_text(encoding="utf-8", errors="ignore")))
    return docs


def _tokenize(text):
    return re.findall(r"[a-z0-9.-]{3,}", text.lower())


@st.cache_data(show_spinner=False)
def build_index(docs):
    """Tiny BM25 index over the runbooks. Pure-python, no deps, no network."""
    corpus = [(name, _tokenize(text)) for name, text in docs]
    n_docs = len(corpus)
    df = {}
    for _, toks in corpus:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    avgdl = (sum(len(toks) for _, toks in corpus) / n_docs) if n_docs else 0.0
    idf = {t: math.log(1 + (n_docs - c + 0.5) / (c + 0.5)) for t, c in df.items()}
    tfs = []
    for name, toks in corpus:
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        tfs.append((name, tf, len(toks)))
    return {"tfs": tfs, "idf": idf, "avgdl": avgdl}


def retrieve(query, docs, k=3, k1=1.5, b=0.75):
    """BM25 ranking of runbooks for a query. Returns [(score, name, text), ...].

    BM25 beats raw keyword counts: it discounts common words (idf) and normalises
    for doc length, so the right runbook surfaces instead of the longest one."""
    if not docs:
        return []
    index = build_index(docs)
    avgdl = index["avgdl"] or 1.0
    text_by_name = dict(docs)
    q = set(_tokenize(query))
    scored = []
    for name, tf, dl in index["tfs"]:
        score = 0.0
        for t in q:
            f = tf.get(t)
            if not f:
                continue
            idf = index["idf"].get(t, 0.0)
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            scored.append((score, name, text_by_name[name]))
    scored.sort(reverse=True)
    return scored[:k]


def runbook_context(query, docs):
    """Return (context_str, names) for the top runbooks, or ('', []) if none."""
    hits = retrieve(query, docs)
    if not hits:
        return "", []
    names = [n for _, n, _ in hits]
    ctx = "\n\n---\nRunbook context (reference only, do not echo verbatim):\n" + "\n\n".join(
        t for _, _, t in hits
    )
    return ctx, names


# ---------- ollama chat (streaming) ----------
def stream_chat(messages):
    """Yield content chunks from Ollama /api/chat. Raises RuntimeError with a useful
    message on HTTP errors (e.g. 500) instead of a bare status."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": NUM_CTX},
    }
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, stream=True, timeout=600)
    if resp.status_code != 200:
        try:
            msg = resp.json().get("error") or resp.text
        except Exception:
            msg = resp.text
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {msg.strip()[:500]}")
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line)
        if data.get("error"):
            raise RuntimeError(f"Ollama: {data['error']}")
        chunk = data.get("message", {}).get("content", "")
        if chunk:
            yield chunk


def ollama_up():
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).raise_for_status()
        return True
    except Exception:
        return False


# ---------- k8sgpt scan (detection only, no AI backend) ----------
def run_k8sgpt(namespaces=None):
    """Run k8sgpt analyze with JSON output.

    namespaces: None/empty -> whole cluster (all namespaces). A list -> run once per
    namespace and merge (k8sgpt's --namespace takes a single namespace), deduped by
    (kind, name).

    Returns (problems:list, raw:str, err:str). `err` carries stderr/diagnostics even
    when problems are found, so the UI can always surface it."""
    kubeconfig = active_kubeconfig()
    if not kubeconfig:
        return [], "", (
            "No kubeconfig found. Upload one in the sidebar, or mount it to a standard "
            "path (~/.kube/config, /root/.kube/config)."
        )

    base = ["k8sgpt", "analyze", "--output", "json", "--kubeconfig", kubeconfig]
    targets = namespaces if namespaces else [None]  # None -> all namespaces

    problems, raws, errs = [], [], []
    seen = set()
    for ns in targets:
        cmd = base + (["--namespace", ns] if ns else [])
        label = ns or "all"
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            return [], "", "k8sgpt binary not found in image."
        except subprocess.TimeoutExpired:
            errs.append(f"[{label}] k8sgpt timed out after 120s (cluster unreachable / token expired?).")
            continue

        out = proc.stdout.strip()
        stderr = proc.stderr.strip()
        if stderr:
            errs.append(f"[{label}] {stderr}")
        if not out:
            errs.append(f"[{label}] no output (exit {proc.returncode}).")
            continue
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            errs.append(f"[{label}] output was not valid JSON.")
            raws.append(out)
            continue
        raws.append(out)
        for r in data.get("results", []):
            key = (r.get("kind"), r.get("name"))
            if key in seen:
                continue
            seen.add(key)
            problems.append(r)

    return problems, "\n".join(raws), "\n".join(e for e in errs if e)


def findings_to_text(problems):
    """Full rendering for DISPLAY — every finding, every pod, nothing dropped."""
    if not problems:
        return "k8sgpt found no problems in the cluster."
    lines = []
    for r in problems:
        kind = r.get("kind", "?")
        name = r.get("name", "?")
        lines.append(f"### {kind}/{name}")
        for e in r.get("error", []):
            txt = e.get("Text") if isinstance(e, dict) else str(e)
            lines.append(f"- {txt}")
    return "\n".join(lines)


def findings_to_model_text(problems):
    """Compact rendering for the MODEL — collapses repeated per-pod errors (the same
    issue across replicas) into one line with a count. Keeps every DISTINCT issue, so
    nothing meaningful is lost, but the prompt is far smaller (faster on CPU)."""
    if not problems:
        return "k8sgpt found no problems in the cluster."
    out = []
    for r in problems:
        kind = r.get("kind", "?")
        name = r.get("name", "?")
        counts, order = {}, []
        for e in r.get("error", []):
            txt = e.get("Text") if isinstance(e, dict) else str(e)
            # strip replicaset+pod hash suffixes (e.g. -64d85cf868-587bw) so per-pod
            # duplicates of the same problem merge
            norm = re.sub(r"-[a-f0-9]{6,10}-[a-z0-9]{5}\b", "", txt).strip()
            if norm not in counts:
                counts[norm] = 0
                order.append(norm)
            counts[norm] += 1
        out.append(f"### {kind}/{name}")
        for norm in order:
            c = counts[norm]
            out.append(f"- {norm}" + (f"  (x{c})" if c > 1 else ""))
    return "\n".join(out)


# ---------- chat plumbing ----------
def ensure_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def visible_messages():
    return [m for m in st.session_state.messages if m["role"] != "system"]


def chat_to_markdown():
    """Render the current conversation as a self-contained markdown doc (a mini runbook)."""
    header = "# k8sgpt-ui — chat export"
    if APP_VERSION:
        header += f"\n\n_version {APP_VERSION}_"
    parts = [header, ""]
    for m in visible_messages():
        who = "🧑 **User**" if m["role"] == "user" else "🤖 **Assistant**"
        parts.append(f"## {who}\n\n{m['content']}\n")
    return "\n".join(parts)


def _latin1(s):
    """Core PDF fonts are latin-1 only; replace anything else so export never crashes."""
    return s.encode("latin-1", "replace").decode("latin-1")


def chat_to_pdf():
    """Render the current conversation as a simple PDF (lazy-imports fpdf2)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    w = pdf.epw  # full content width; w=0 is unreliable in fpdf2 2.7.9

    def block(text, size, style=""):
        # explicit left-align + return to left margin on the next line — without this,
        # fpdf2's default new_x=RIGHT pushes following lines to the right edge.
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(
            w, size * 0.5, _latin1(text),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L",
        )

    block("k8sgpt-ui - chat export", 16, "B")
    if APP_VERSION:
        block(f"version {APP_VERSION}", 10, "I")
    pdf.ln(3)
    for m in visible_messages():
        block("User" if m["role"] == "user" else "Assistant", 12, "B")
        block(m["content"], 11, "")
        pdf.ln(3)
    return bytes(pdf.output())


def trimmed_messages():
    """System prompt + the last MAX_HISTORY non-system messages. Bounds prompt size
    so long sessions don't overflow context or crawl."""
    msgs = st.session_state.messages
    system = [m for m in msgs if m["role"] == "system"][:1]
    rest = [m for m in msgs if m["role"] != "system"]
    return system + rest[-MAX_HISTORY:]


def _stream_into(box, sent):
    acc = ""
    for chunk in stream_chat(sent):
        acc += chunk
        box.markdown(acc)
    return acc


def send_to_model(user_content, display_content=None, extra_context=None):
    """Append clean user msg to history, stream assistant reply.

    `extra_context` (e.g. runbook text) is attached to THIS request only and is never
    stored in history — keeps the conversation lean and stops it being resent forever.
    """
    # If a previous generation was stopped mid-stream, its turn was left with a
    # dangling user message (the assistant reply is saved only after streaming
    # completes). Close it so the old question doesn't bleed into this new turn.
    msgs = st.session_state.messages
    if msgs and msgs[-1]["role"] == "user":
        msgs.append({"role": "assistant", "content": "_(response stopped)_"})

    st.session_state.messages.append({"role": "user", "content": user_content})
    with st.chat_message("user"):
        st.markdown(display_content or user_content)

    sent = trimmed_messages()
    if extra_context:
        last = sent[-1]
        sent = sent[:-1] + [{**last, "content": last["content"] + extra_context}]

    with st.chat_message("assistant"):
        box = st.empty()
        box.markdown("⏳ _thinking… (a large prompt can take a while on CPU)_")
        acc = ""
        try:
            acc = _stream_into(box, sent)
        except Exception:
            # one retry — covers cold model-load 500s and transient hiccups
            box.markdown("⏳ Model busy or loading — retrying once…")
            try:
                acc = _stream_into(box, sent)
            except Exception as e:
                acc = f"⚠️ Model error: {e}"
                box.markdown(acc)
    st.session_state.messages.append({"role": "assistant", "content": acc})


# ---------- UI ----------
st.set_page_config(
    page_title="k8sgpt-ui",
    page_icon="⎈",
    layout="wide",
    menu_items={"about": "k8sgpt-ui — airgap Helm / Kubernetes troubleshooting assistant."},
)
# Hide just the "Made with Streamlit" footer branding (keeps the menu + Settings).
st.markdown("<style>footer {visibility: hidden;}</style>", unsafe_allow_html=True)
# Remove ONLY the "Print" item from the hamburger menu while keeping Settings/About.
# Streamlit gives menu items no per-item id, so we match by label text via a tiny
# same-origin helper iframe (height 0) that reaches into the parent document.
components.html(
    """
    <script>
    const doc = window.parent.document;
    const REMOVE = ['Print'];   // add 'Record a screencast' here to drop that too
    function scrub() {
      doc.querySelectorAll('[data-testid="stActionButtonLabel"]').forEach(function (l) {
        if (REMOVE.includes(l.textContent.trim())) {
          const btn = l.closest('[data-testid="stActionButton"]');
          if (btn) btn.style.display = 'none';
        }
      });
    }
    new MutationObserver(scrub).observe(doc.body, {childList: true, subtree: true});
    scrub();
    </script>
    """,
    height=0,
)
ensure_state()
docs = load_runbooks()


@st.dialog("📖 Runbooks & docs", width="large")
def runbooks_dialog(all_docs):
    """Wide pop-up to browse and read runbooks comfortably (vs. the narrow sidebar)."""
    # Streamlit caps dialog width at "large" (~800px); widen it via CSS to ~90% viewport.
    st.markdown(
        "<style>div[role='dialog']{width:92vw !important;max-width:1500px !important;}</style>",
        unsafe_allow_html=True,
    )
    if not all_docs:
        st.info("No runbooks found.")
        return
    names = [n for n, _ in all_docs]
    sel = st.selectbox("Choose a runbook", names, key="rb_dialog_sel")
    st.divider()
    st.markdown(dict(all_docs).get(sel, ""))

with st.sidebar:
    ver = (
        f" <span style='font-size:0.45em;color:#888;vertical-align:middle;'>{APP_VERSION}</span>"
        if APP_VERSION
        else ""
    )
    st.markdown(f"<h1 style='margin-bottom:0'>⎈ k8sgpt-ui{ver}</h1>", unsafe_allow_html=True)
    st.caption("Airgap Helm / k8s troubleshooting")
    st.markdown(f"**Model:** `{MODEL}`")
    st.markdown(f"**Ollama:** {'🟢 up' if ollama_up() else '🔴 down'}")
    st.markdown(f"**Runbooks:** {len(docs)} loaded")
    st.divider()

    st.subheader("Kubeconfig")
    up = st.file_uploader(
        "Upload kubeconfig (overrides the default)",
        type=None,
        help="Used only by k8sgpt to read the cluster. If none is uploaded, common "
        "locations like ~/.kube/config are used automatically.",
    )
    if up is not None:
        with open(UPLOAD_KUBECONFIG, "wb") as f:
            f.write(up.getbuffer())
        os.chmod(UPLOAD_KUBECONFIG, 0o600)
        st.session_state.kubeconfig_path = UPLOAD_KUBECONFIG
        st.success(f"Loaded: {up.name}")

    active = active_kubeconfig()
    if active:
        src = "uploaded" if active == st.session_state.get("kubeconfig_path") else "auto-detected"
        st.caption(f"🟢 kubeconfig active ({src}): `{active}`")
    else:
        st.caption("⚪ no kubeconfig found — scan disabled, paste mode works")

    st.divider()

    st.subheader("Scan cluster")
    st.caption("Runs k8sgpt to auto-detect problems in the cluster (no error text needed).")
    scope = st.radio("Scope", ["All namespaces", "Specific namespace(s)"], key="scan_scope")
    ns_list = None
    if scope == "Specific namespace(s)":
        raw_ns = st.text_input(
            "Namespaces (comma-separated)",
            placeholder="default, kube-system, argocd",
            key="scan_ns",
            help="One or more namespaces. k8sgpt is run once per namespace and results merged.",
        )
        ns_list = [n.strip() for n in raw_ns.split(",") if n.strip()] or None

    if st.button("🔍 Scan with k8sgpt", use_container_width=True, disabled=active is None):
        if scope == "Specific namespace(s)" and not ns_list:
            st.warning("Enter at least one namespace, or choose 'All namespaces'.")
        else:
            scope_lbl = "all namespaces" if not ns_list else ", ".join(ns_list)
            with st.spinner(f"Running k8sgpt on {scope_lbl}..."):
                problems, raw, err = run_k8sgpt(ns_list)
            st.session_state.last_scan_raw = raw
            st.session_state.last_scan_err = err
            if not raw and err:
                # surface the real k8sgpt error in the chat (persistent + visible),
                # not just a transient sidebar message
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": (
                            f"🔴 **k8sgpt scan failed** ({scope_lbl}) — the cluster "
                            "could not be analyzed:\n\n"
                            f"```\n{err.strip()}\n```\n\n"
                            "Common cause: a kubeconfig / credentials problem — e.g. an "
                            "expired token, the wrong context, or an unreachable API server."
                        ),
                    }
                )
                st.rerun()
            else:
                st.session_state.pending_scan = {
                    "display": findings_to_text(problems),
                    "model": findings_to_model_text(problems),
                }
                st.success(f"Found {len(problems)} issue(s) in {scope_lbl}. See chat.")
                if err:
                    st.warning("k8sgpt reported warnings — see diagnostics below.")

    if st.session_state.get("last_scan_raw") or st.session_state.get("last_scan_err"):
        with st.expander("🛠️ Last scan diagnostics"):
            if st.session_state.get("last_scan_err"):
                st.caption("stderr / messages:")
                st.code(st.session_state["last_scan_err"])
            if st.session_state.get("last_scan_raw"):
                st.caption("raw k8sgpt JSON:")
                st.code(st.session_state["last_scan_raw"][:5000], language="json")

    st.divider()

    st.subheader("Runbooks")
    st.session_state.ground_runbooks = st.toggle(
        "Ground answers in runbooks",
        value=False,
        help="Off by default. When on, the most relevant runbook(s) are given to the "
        "model as background context for your question — they are not printed to chat.",
    )
    if st.button(f"📖 Open runbooks ({len(docs)})", use_container_width=True):
        runbooks_dialog(docs)

    st.divider()
    st.markdown("**Export chat**")
    has_chat = bool(visible_messages())
    exp_name = st.text_input("File name", value="k8sgpt-chat", key="export_name").strip() or "k8sgpt-chat"
    exp_fmt = st.radio("Format", ["Markdown (.md)", "PDF (.pdf)"], horizontal=True, key="export_fmt")
    if exp_fmt.startswith("PDF"):
        ext, mime = "pdf", "application/pdf"
        try:
            data = chat_to_pdf() if has_chat else b""
        except Exception as e:
            data = b""
            has_chat = False
            st.caption(f"⚠️ PDF export unavailable: {e}")
    else:
        ext, mime = "md", "text/markdown"
        data = chat_to_markdown() if has_chat else ""
    st.download_button(
        "⬇️ Download",
        data=data,
        file_name=f"{exp_name}.{ext}",
        mime=mime,
        use_container_width=True,
        disabled=not has_chat,
    )

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.rerun()

st.title("Helm / Kubernetes troubleshooter")

# replay history
for m in visible_messages():
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# handle a queued cluster scan
if "pending_scan" in st.session_state:
    pend = st.session_state.pop("pending_scan")
    summary = pend["display"]          # full, shown to the user
    model_summary = pend["model"]      # compact (de-duplicated), sent to the model
    truncated = False
    if len(model_summary) > MAX_SCAN_CHARS:
        model_summary = model_summary[:MAX_SCAN_CHARS]
        truncated = True
    prompt = (
        "k8sgpt scanned the cluster and reported these findings. "
        "Explain the root cause(s) and give fix steps.\n\n"
        f"{model_summary}"
    )
    extra, used = ("", [])
    if st.session_state.get("ground_runbooks"):
        extra, used = runbook_context(model_summary, docs)
    display = "🔍 **Cluster scan results:**\n\n" + summary
    if truncated:
        display += (
            "\n\n> ⚠️ Cluster is very large — even after de-duplication the findings "
            "exceeded the model's input budget, so only the first part was analyzed. "
            "All findings are shown above."
        )
    send_to_model(prompt, display_content=display, extra_context=extra or None)
    if used:
        st.caption("📖 Grounded in runbooks: " + ", ".join(used))

# chat input (paste-error mode)
if user_input := st.chat_input("Paste a Helm/k8s error, or ask a question..."):
    extra, used = ("", [])
    if st.session_state.get("ground_runbooks"):
        extra, used = runbook_context(user_input, docs)
    send_to_model(user_input, display_content=user_input, extra_context=extra or None)
    if used:
        st.caption("📖 Grounded in runbooks: " + ", ".join(used))
