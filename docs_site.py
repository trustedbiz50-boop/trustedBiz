"""docs_site.py — the TrustedBiz documentation (home, search, and one page per topic).
Every statement here describes something that works today; planned features are
labelled 'coming soon' and live on the 'What works today' page."""
import re

from flask import render_template, request, abort

import hosting

_SECTIONS = ["Get started", "Projects", "Apps", "Reference"]

_PAGES = [
 ("quickstart-static", "Get started", "Quickstart: a static site",
  "Put index.html in a ZIP, upload it, and your site is live in seconds.",
  """<p>A static site is plain HTML, CSS and JavaScript. You can have it live in about a minute, from a phone.</p>
<ol><li>Put <code>index.html</code> at the top of a ZIP. Other pages (like <code>about.html</code>) go next to it.</li>
<li>Open your dashboard, choose <b>New project</b>, give it a name and pick the ZIP.</li>
<li>Press <b>Deploy</b>. Your site goes live at <code>yourname.trustedbiz.co.ug</code>.</li></ol>
<p>Local CSS, JavaScript, small images and fonts are embedded for you, and links like <code>about.html</code> are converted automatically. Built with React or Vite? Run the build on your computer and zip the <code>dist/</code> or <code>build/</code> folder.</p>
<p>Your first project is free. See <a href="/docs/plans">Free and Paid plans</a>.</p>"""),
 ("quickstart-git", "Get started", "Quickstart: deploy from GitHub or GitLab",
  "Connect an account, pick a repository, and every push deploys.",
  """<p>Public repositories need no login: open <b>New project → Import from Git</b>, paste the link, and deploy. To deploy private repositories and get automatic deploys on every push, connect your account.</p>
<ol><li>Open <b>Import from Git</b> and choose <b>Connect</b> next to GitHub or GitLab.</li>
<li>Pick a repository and press <b>Deploy</b>.</li>
<li>TrustedBiz installs a webhook, so every push to your branch redeploys the project.</li></ol>
<p>The repository goes through the same checks as a ZIP upload. If a deploy fails, your previous version stays live and the reason appears under <b>Events</b>. Repositories larger than 8 MB as a ZIP are refused: remove large media files first.</p>
<p>See <a href="/docs/deploy-hooks">Deploy hooks and auto-deploy</a> to change the branch or deploy a sub-folder.</p>"""),
 ("plans", "Projects", "Free and Paid plans", "What each plan includes, and how renewal works.",
  """<div class="scroll-x"><table class="tbl"><thead><tr><th></th><th>Free</th><th>Paid</th></tr></thead><tbody>
<tr><td>Price</td><td>UGX 0</td><td>UGX {{ monthly }} per month or UGX {{ yearly }} per year, per project</td></tr>
<tr><td>Projects</td><td>1 free project</td><td>Upgrade any project</td></tr>
<tr><td>Address</td><td>yourname.trustedbiz.co.ug</td><td>Your own domain too</td></tr>
<tr><td>Staying live</td><td>Open your dashboard at least every {{ renew }} days</td><td>Always on</td></tr>
<tr><td>Maintenance mode</td><td>No</td><td>Yes</td></tr>
<tr><td>Apps (when app hosting launches)</td><td>Sleep after {{ sleep }} minutes without visits. Temporary storage.</td><td>Always on, persistent storage</td></tr></tbody></table></div>
<h2>How the Free plan stays live</h2>
<p>Opening your dashboard renews every Free project for another {{ renew }} days. If you don't open it in that time, the project pauses and visitors see a paused page. Opening the dashboard brings it straight back. We send a reminder a week before.</p>
<h2>Upgrading</h2>
<p>Open the project, go to <b>Settings → Plan</b>, enter your mobile money number and choose <b>Upgrade to Paid</b>. You pay by MTN or Airtel Money on WhatsApp, and we switch the plan on when we see the payment. If a Paid project stays unpaid after a grace period it can be suspended.</p>"""),
 ("custom-domains", "Projects", "Custom domains", "Point a domain you own at your project (Paid plan).",
  """<p>Custom domains are part of the <a href="/docs/plans">Paid plan</a>.</p>
<ol><li>Open the project, then <b>Settings → Custom domains</b>, and add your domain.</li>
<li>At your domain provider, add a <b>CNAME</b> record pointing your domain to <code>trustedbiz.co.ug</code>.</li>
<li>Wait for DNS to update (up to 24 hours), then press <b>Verify DNS</b>. TrustedBiz checks the domain over HTTPS before marking it live.</li></ol>
<p>Remove a domain any time from the same section.</p>"""),
 ("rollbacks", "Projects", "Snapshots and rollbacks", "Go back to an earlier version in one click.",
  """<p>A snapshot of your static site is saved every time its content changes. The last 5 are kept. Open the project, go to <b>Events</b>, and press <b>Rollback</b> next to the version you want. Your current version stays in the snapshots, so you can roll forward again.</p>
<p>Snapshots apply to static sites. For apps, deploy the earlier ZIP or commit again.</p>"""),
 ("deploy-hooks", "Projects", "Deploy hooks and auto-deploy", "Branch, root directory, webhooks and your private deploy URL.",
  """<p>Projects imported from Git have these controls under <b>Settings → Build and deploy</b>:</p>
<ul><li><b>Branch:</b> the branch that gets deployed.</li>
<li><b>Root directory:</b> deploy only a folder of the repository (for example <code>dist</code>).</li>
<li><b>Auto-deploy:</b> redeploy on every push to the branch. Turn it off to deploy only when you choose.</li>
<li><b>Deploy hook:</b> a private URL that triggers a deploy when it is requested. Use it from a build pipeline or a scheduled job. Keep it secret, and use <b>Regenerate hook</b> if it leaks.</li></ul>
<p>Public repositories imported by link can't install a webhook, but the deploy hook and <b>Manual deploy → Deploy latest commit</b> still work.</p>"""),
 ("env-vars", "Projects", "Environment variables", "Give your app settings and secrets without putting them in your code.",
  """<p>Environment variables are for apps. Open a Python or Node project, choose the <b>Environment</b> tab and add a name and value. Values are encrypted when stored and never shown again after you save them. They are passed to your app when it runs.</p>
<p>App hosting has not launched yet, so your app isn't running today. Add the variables now and they will be ready at launch. Never put secrets in your ZIP or repository.</p>"""),
 ("maintenance", "Projects", "Maintenance mode", "Show a maintenance page while you work (Paid plan).",
  """<p>Turn on maintenance mode under <b>Settings → Maintenance mode</b>. Visitors see a maintenance page instead of your project. If you set a custom maintenance page, visitors are sent to that link instead. You can still manage the project from your dashboard.</p>"""),
 ("pause-delete", "Projects", "Pause and delete", "Take a project offline, or remove it for good.",
  """<p><b>Pause</b> takes a project offline without deleting anything. Visitors see a paused page, and you can resume any time from <b>Settings → Danger zone</b>.</p>
<p><b>Delete</b> permanently removes the project, its snapshots, stored files and variables, and its Git webhook. This can't be undone. Download anything you need first. The Free plan allows one free project, so deleting it lets you create another.</p>"""),
 ("apps", "Apps", "Python and Node apps", "What you can upload today, and what happens at launch.",
  """<p><b>Today:</b> you can upload a Python or Node app as a ZIP or from Git. TrustedBiz detects it, validates it and stores it safely. Its address shows a "coming online soon" page.</p>
<p><b>At launch:</b> stored apps start running automatically, with your environment variables. Free apps sleep after {{ sleep }} minutes without visits and wake on the next visit; Paid apps are always on.</p>
<ul><li><b>Python:</b> include <code>requirements.txt</code> and an entry such as <code>app.py</code>. A <code>Procfile</code> line like <code>web: gunicorn app:app</code> tells us how to start it.</li>
<li><b>Node:</b> include <code>package.json</code> with a <code>start</code> script.</li>
<li>Keep out <code>.env</code> files, virtual environments and <code>node_modules</code>. Bundles are limited to 5 MB.</li></ul>"""),
 ("config", "Apps", "trustedbiz.yaml", "Optional config file, read and validated on upload.",
  """<pre>name: my-app
type: web
runtime: python
build: pip install -r requirements.txt
start: gunicorn app:app
env:
  - DATABASE_URL
  - SECRET_KEY</pre>
<p><code>env</code> lists variable <b>names</b> only. Never put secret values in this file; set them on the <b>Environment</b> tab. Unknown keys are ignored with a warning.</p>"""),
 ("limits", "Reference", "Limits", "Size and file limits for uploads and repositories.",
  """<ul><li>ZIP or repository: up to 8 MB, 600 files, 40 pages.</li>
<li>Each embedded image or font: up to 400 KB. All embedded files together: 3 MB. Host bigger media elsewhere (for example Cloudinary) and link to it.</li>
<li>Only top-level pages are published. Pages in sub-folders are skipped for now.</li>
<li>App bundles: up to 5 MB. Up to 50 environment variables per project.</li>
<li>One Free project per account.</li></ul>"""),
 ("security", "Reference", "Sign-in and security", "Google, GitHub, email, and two-factor login.",
  """<p>You can log in with email and password, with Google, or with GitHub. If you sign in with Google or GitHub using an email that already has an account, the two are linked, but only when the provider confirms that email is yours.</p>
<p>Turn on two-factor login under <b>Account → Security</b>. It also applies when you sign in with Google or GitHub.</p>
<p>Git access tokens and environment variables are encrypted before they are stored. Disconnect a Git provider any time from <b>Account → Connected accounts</b>.</p>"""),
 ("troubleshooting", "Reference", "Troubleshooting", "Common problems and what to do.",
  """<h2>"No index.html found"</h2><p>The ZIP needs <code>index.html</code> at the top. If your files are inside a folder in the ZIP, TrustedBiz looks one level down for GitHub-style ZIPs, but not deeper. Re-zip the contents, not the folder.</p>
<h2>"Must be built first"</h2><p>The ZIP looks like unbuilt React or Vite source. Run the build locally and upload the <code>dist/</code> or <code>build/</code> folder.</p>
<h2>"The Free plan includes 1 project"</h2><p>Upgrade your existing project to Paid, or delete it, then try again.</p>
<h2>A Git deploy failed</h2><p>Open the project's <b>Events</b> tab for the reason. Your previous version stays live. Common causes: the branch name is wrong, the root directory doesn't exist, or the repository is over 8 MB.</p>
<h2>My project says paused</h2><p>Free projects pause if the dashboard isn't opened for {{ renew }} days. Open your dashboard to bring it back. If you paused it yourself, resume it in <b>Settings → Danger zone</b>.</p>"""),
]

_BY_SLUG = {p[0]: p for p in _PAGES}


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def init_docs(app, deps):
    ctx = lambda: {"monthly": "{:,}".format(deps["HOSTING_FEE_MONTHLY"]), "yearly": "{:,}".format(deps["HOSTING_FEE_YEARLY"]),
                   "renew": hosting.FREE_RENEW_DAYS, "sleep": hosting.FREE_APP_SLEEP_MINUTES}

    def render_body(html):
        from flask import render_template_string
        return render_template_string(html, **ctx())

    def sections():
        out = []
        for sec in _SECTIONS:
            items = [{"slug": s, "title": t, "summary": sm} for (s, se, t, sm, _b) in _PAGES if se == sec]
            items.append  # keep order
            if sec == "Reference":
                items.append({"slug": "roadmap", "title": "What works today", "summary": "Every feature, marked Live or Coming soon."})
            out.append({"name": sec, "items": items})
        return out

    @app.route("/docs")
    def docs_home():
        q = (request.args.get("q") or "").strip()[:80]
        results = []
        if q:
            words = [w for w in re.split(r"\s+", q.lower()) if w]
            for (slug, sec, title, summary, body) in _PAGES:
                hay = (title + " " + summary + " " + _text(body)).lower()
                score = sum(hay.count(w) + (5 if w in title.lower() else 0) for w in words)
                if all(w in hay for w in words):
                    results.append((score, {"slug": slug, "title": title, "summary": summary, "section": sec}))
            results = [r for _s, r in sorted(results, key=lambda x: -x[0])]
        return render_template("docs.html", mode="results" if q else "home", q=q, results=results, sections=sections(),
                               current_user=deps["get_current_user"]())

    @app.route("/docs/<slug>")
    def docs_page(slug):
        if slug == "roadmap":
            rows = "".join(
                f'<tr><td><b>{n}</b><br><span style="font-size:12.5px">{note}</span></td><td><span class="tag {s}">{"Live" if s == "live" else "Coming soon"}</span></td></tr>'
                for n, s, note in hosting._FEATURES)
            body = f'<p>We only mark something Live when it works today.</p><div class="scroll-x"><table class="tbl"><tbody>{rows}</tbody></table></div>'
            page = ("roadmap", "Reference", "What works today", "", body)
            html = body
        else:
            page = _BY_SLUG.get(slug)
            if not page:
                abort(404)
            html = render_body(page[4])
        slugs = [p[0] for p in _PAGES] + ["roadmap"]
        idx = slugs.index(page[0])
        nxt = slugs[idx + 1] if idx + 1 < len(slugs) else None
        prv = slugs[idx - 1] if idx > 0 else None
        title_of = lambda s: "What works today" if s == "roadmap" else _BY_SLUG[s][2]
        return render_template("docs.html", mode="page", page={"slug": page[0], "title": page[2], "section": page[1], "html": html},
                               sections=sections(), prev=({"slug": prv, "title": title_of(prv)} if prv else None),
                               next=({"slug": nxt, "title": title_of(nxt)} if nxt else None), q="", results=[],
                               current_user=deps["get_current_user"]())
