#!/usr/bin/env python3
"""
Generates a terminal-styled SVG that reframes real GitHub account stats
as a security-operations readout — e.g. commits become "payloads deployed",
closed issues become "vulnerabilities patched".

Data is pulled live from the GitHub REST + GraphQL APIs, so the numbers
are real, not decorative. Designed to run daily via
.github/workflows/terminal-card.yml, which commits the regenerated SVG
to an `output` branch and the profile README embeds it from there.

Env vars required:
    GH_USERNAME   - the GitHub username to report on
    GH_TOKEN      - a token with public read access (the default
                    GITHUB_TOKEN in Actions is sufficient)
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

USERNAME = os.environ.get("GH_USERNAME")
TOKEN = os.environ.get("GH_TOKEN")

if not USERNAME or not TOKEN:
    print("::error::GH_USERNAME and GH_TOKEN must both be set")
    sys.exit(1)

REST_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": USERNAME,
}


def rest_get(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com{path}", headers=REST_HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={**REST_HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_user_summary() -> dict:
    return rest_get(f"/users/{USERNAME}")


def get_total_stars() -> int:
    stars = 0
    page = 1
    while True:
        repos = rest_get(f"/users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
        if not repos:
            break
        stars += sum(r.get("stargazers_count", 0) for r in repos)
        if len(repos) < 100:
            break
        page += 1
    return stars


def get_year_contributions() -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalRepositoryContributions
        }
      }
    }
    """
    data = graphql(query, {"login": USERNAME})
    return data["data"]["user"]["contributionsCollection"]


def build_svg(stats: dict) -> str:
    lines = [
        f"root@{stats['username']}:~$ whoami",
        f"> {stats['bio'] or 'cybersecurity engineer'}",
        "",
        f"root@{stats['username']}:~$ scan --target=github-activity --deep",
        "[+] Initializing recon module...",
        "[+] Target acquired. Pulling telemetry...",
        "",
        f"[✓] Repositories compromised ......... {stats['public_repos']}",
        f"[✓] Payloads deployed (commits, 1y) ... {stats['commits']}",
        f"[✓] Vulnerabilities patched (issues) .. {stats['issues']}",
        f"[✓] Exploits reviewed (PRs) ........... {stats['prs']}",
        f"[✓] Bounty collected (stars) .......... {stats['stars']}",
        f"[✓] Recruits acquired (followers) ..... {stats['followers']}",
        "",
        f"[+] Operator active since {stats['member_since']}",
        "[+] Scan complete. No system exited clean.",
        "_",
    ]

    line_height = 20
    top_padding = 55
    width = 640
    height = top_padding + line_height * len(lines) + 25

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    text_elements = []
    for i, line in enumerate(lines[:-1]):  # all but the blinking cursor line
        y = top_padding + i * line_height
        color = "#00ff41"
        if line.startswith("root@"):
            color = "#58a6ff"
        elif line.startswith(">"):
            color = "#c9d1d9"
        elif line.startswith("[+]"):
            color = "#f0c674"
        elif line.startswith("[✓]"):
            color = "#00ff41"
        text_elements.append(
            f'<text x="20" y="{y}" font-family="Consolas, Monaco, monospace" '
            f'font-size="13" fill="{color}" xml:space="preserve">{esc(line)}</text>'
        )

    cursor_y = top_padding + (len(lines) - 1) * line_height
    cursor = f'''
    <rect x="20" y="{cursor_y - 11}" width="8" height="14" fill="#00ff41">
      <animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite" />
    </rect>'''

    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" rx="8" fill="#0d1117" stroke="#00ff41" stroke-width="1"/>
  <circle cx="20" cy="20" r="6" fill="#ff5f56"/>
  <circle cx="40" cy="20" r="6" fill="#ffbd2e"/>
  <circle cx="60" cy="20" r="6" fill="#27c93f"/>
  <text x="{width/2}" y="25" font-family="Consolas, Monaco, monospace" font-size="12" fill="#8b949e" text-anchor="middle">{esc(USERNAME)}@github — security-scan.sh</text>
  {''.join(text_elements)}
  {cursor}
</svg>'''
    return svg


def main():
    user = get_user_summary()
    contributions = get_year_contributions()
    stars = get_total_stars()

    created_at = datetime.strptime(user["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    stats = {
        "username": USERNAME,
        "bio": user.get("bio"),
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "commits": contributions.get("totalCommitContributions", 0),
        "issues": contributions.get("totalIssueContributions", 0),
        "prs": contributions.get("totalPullRequestContributions", 0),
        "stars": stars,
        "member_since": created_at.strftime("%Y"),
    }

    svg = build_svg(stats)

    os.makedirs("dist", exist_ok=True)
    with open("dist/terminal-card.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Generated dist/terminal-card.svg for {USERNAME}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
