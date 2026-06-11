"""Quick connectivity check — writes result to connectivity_result.txt."""
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "connectivity_result.txt"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8213322562:AAHiCG068sysLORWj7X0fKyQOw8F62epBB0")
PROXY = os.environ.get("TELEGRAM_PROXY", "").strip() or None


def main() -> None:
    lines: list[str] = []
    try:
        import httpx

        kwargs: dict = {"timeout": 30}
        if PROXY:
            kwargs["proxy"] = PROXY
            lines.append(f"proxy={PROXY}")

        r = httpx.get("https://api.telegram.org", **kwargs)
        lines.append(f"api.telegram.org status={r.status_code}")

        r2 = httpx.get(f"https://api.telegram.org/bot{TOKEN}/getMe", **kwargs)
        lines.append(f"getMe status={r2.status_code} body={r2.text[:200]}")
        lines.append("RESULT=OK" if r2.status_code == 200 else "RESULT=FAIL")
    except Exception as e:
        lines.append(f"RESULT=FAIL error={type(e).__name__}: {e}")
        if not PROXY:
            lines.append("HINT: set TELEGRAM_PROXY=socks5://127.0.0.1:1080 if blocked")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
    sys.exit(0 if "RESULT=OK" in OUT.read_text(encoding="utf-8") else 1)
