"""Serve the static site (docs/) locally, optionally against a local nexus-design.

Pages link the hosted design system (https://doruirimescu.github.io/nexus-design/).
When a local clone of nexus-design is found, this server rewrites those links in
every HTML page to /__nexus-design/ and serves the clone there, so changes to the
design system can be previewed here before they are pushed. Nothing on disk changes.

    python scripts/serve_site.py                    # port 8080, ../nexus-design if present
    python scripts/serve_site.py --design ~/x/nexus-design
    python scripts/serve_site.py --hosted           # use the published design system

scripts/nexus.sh --start runs this for you.
"""
import argparse
import functools
import http.server
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTED = b"https://doruirimescu.github.io/nexus-design/"
LOCAL_PREFIX = "/__nexus-design/"


class Handler(http.server.SimpleHTTPRequestHandler):
    design: Path | None = None

    def end_headers(self):
        # Always revalidate, so an edit in either repo shows up on the next reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        if self.design and path.startswith(LOCAL_PREFIX):
            rel = path[len(LOCAL_PREFIX):].split("?", 1)[0].split("#", 1)[0]
            target = (self.design / rel).resolve()
            if self.design in target.parents or target == self.design:
                return str(target)
            return str(self.design / "__not_found__")
        return super().translate_path(path)

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir() and self.path.split("?", 1)[0].endswith("/"):
            path = path / "index.html"
        # nexus-design's own pages (gallery, template) link their files relatively.
        if not self.design or path.suffix != ".html" or not path.is_file() or self.design in path.resolve().parents:
            return super().send_head()
        body = path.read_bytes().replace(HOSTED, LOCAL_PREFIX.encode())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return io.BytesIO(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--design", type=Path, default=ROOT.parent / "nexus-design", help="local nexus-design clone")
    ap.add_argument("--hosted", action="store_true", help="don't use a local nexus-design")
    args = ap.parse_args()

    design = None if args.hosted else args.design.expanduser().resolve()
    if design and not (design / "nexus.css").is_file():
        design = None
    Handler.design = design
    print(f"Design system: {design or HOSTED.decode()}", flush=True)

    handler = functools.partial(Handler, directory=str(ROOT / "docs"))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving docs/ on http://localhost:{args.port}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
