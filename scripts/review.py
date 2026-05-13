import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a senior code reviewer. Review the provided code and flag:
- Bugs and logic errors
- Security vulnerabilities
- Performance issues
- Style and maintainability concerns
- Missing error handling

Output in markdown with clear sections (## Summary, ## Issues, ## Suggestions).
Be concise and actionable. If the code looks good, say so briefly."""


def review_file(path: str) -> str:
    content = Path(path).read_text(encoding="utf-8", errors="ignore")

    if len(content) > 50000:
        return f"_Skipped `{path}`: file too large (>50KB)_\n"

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Review this file: `{path}`\n\n```\n{content}\n```"
        }]
    )
    return msg.content[0].text


def main():
    files = [f for f in sys.argv[1].split() if f.strip() and Path(f).exists()]
    if not files:
        print("No files to review.", file=sys.stderr)
        return

    reviews_dir = Path("reviews")
    reviews_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    for f in files:
        safe_name = f.replace("/", "_").replace("\\", "_")
        out_path = reviews_dir / f"{timestamp}_{safe_name}.md"

        review_body = review_file(f)
        out_path.write_text(
            f"# Review: `{f}`\n\n"
            f"_Generated: {datetime.now(timezone.utc).isoformat()}_\n\n"
            f"---\n\n"
            f"{review_body}\n",
            encoding="utf-8"
        )
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
