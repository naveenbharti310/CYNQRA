"""A localhost server that speaks Ollama's native API. NOT a model and never a result.

It lets the tests run the laptop path end to end (model_adapter's Ollama provider, the CLI's
doctor, bench and run) without Ollama or a model: /api/version, /api/tags, /api/show and
/api/chat, with the same field names Ollama uses. Answers come from fake_model.answer; work
replies are sent back as file blocks, the layout local models are asked for.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fake_model

SLUG = {"slug.py": "import re\n\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n",
        "test_slug.py": ("import unittest\nfrom slug import slugify\n\n\nclass T(unittest.TestCase):\n"
                         "    def test_basic(self):\n        self.assertEqual(slugify('Hello World'), 'hello-world')\n\n"
                         "    def test_runs(self):\n        self.assertEqual(slugify('a  --  b'), 'a-b')\n\n"
                         "    def test_ends(self):\n        self.assertEqual(slugify('--x--'), 'x')\n\n"
                         "    def test_digits(self):\n        self.assertEqual(slugify('Room 42!'), 'room-42')\n")}


def as_blocks(reply: str) -> str:
    data = json.loads(re.search(r"\{.*\}", reply, re.S).group(0))
    files = data.pop("files", None)
    if not isinstance(files, dict):
        return json.dumps(data)
    return json.dumps(data) + "\n" + "".join(f"=== FILE: {k} ===\n{v.rstrip(chr(10))}\n=== END FILE ===\n"
                                             for k, v in files.items())


class FakeOllama:
    def __init__(self, models=("qwen3.6:35b",), mode: str = "ok", version: str = "0.34.4"):
        self.requests: list[dict] = []
        self.version = version
        self.models = list(models)
        self.mode = mode
        self.cut_tasks: set[str] = set()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/api/version":
                    return self._send(200, {"version": outer.version})
                if self.path == "/api/tags":
                    return self._send(200, {"models": [{"name": m, "model": m, "size": 14 * 1024 ** 3} for m in outer.models]})
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body})
                if self.path == "/api/show":
                    return self._send(200, {"capabilities": ["completion", "tools", "thinking"],
                                            "model_info": {"general.architecture": "qwen", "qwen.context_length": 262144}})
                if self.path != "/api/chat":
                    return self._send(404, {"error": "not found"})
                if body["model"] not in outer.models:
                    return self._send(404, {"error": f"model '{body['model']}' not found"})
                prompt = body["messages"][-1]["content"]
                if outer.mode == "length":
                    return self._send(200, {"message": {"role": "assistant", "content": '{"a": '}, "done": True,
                                            "done_reason": "length", "prompt_eval_count": 10, "eval_count": 99})
                if "slugify" in prompt:
                    text = json.dumps({"files": SLUG}) if body.get("format") else as_blocks(json.dumps({"files": SLUG}))
                elif '"sum": 2 + 3' in prompt:
                    text = '{"ok": true, "sum": 5}'
                else:
                    text = fake_model.answer(prompt)
                    if "=== FILE:" in prompt:
                        text = as_blocks(text)
                    cut = outer.cut_reply(prompt, text) if outer.mode == "cut" else None
                    if cut:
                        return self._send(200, {"model": body["model"], "message": {"role": "assistant", "content": cut},
                                                "done": True, "done_reason": "length",
                                                "prompt_eval_count": max(1, len(prompt) // 4), "eval_count": 8192})
                    if outer.mode == "cut" and "was cut off while writing" in prompt:
                        text = outer.only_the_cut_file(prompt, text)
                return self._send(200, {"model": body["model"], "message": {"role": "assistant", "content": text},
                                        "done": True, "done_reason": "stop",
                                        "prompt_eval_count": max(1, len(prompt) // 4),
                                        "eval_count": max(1, len(text) // 4)})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.host = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cut_reply(self, prompt: str, text: str) -> str | None:
        """mode "cut": the first code reply of each task stops halfway through its last file, like a local model at
        its output limit. The follow-up is answered with only the file that was cut, as the engine asks."""
        task = re.search(r"Task (t_\d+):", prompt)
        heads = list(re.finditer(r"^=== FILE: (.+?) ===$", text, re.M))
        if not task or len(heads) < 2 or task.group(1) in self.cut_tasks or "was cut off while writing" in prompt:
            return None
        self.cut_tasks.add(task.group(1))
        last = heads[-1]
        body = text[last.end():].split("=== END FILE ===")[0]
        return text[:last.end()] + body[: len(body) // 2]

    @staticmethod
    def only_the_cut_file(prompt: str, text: str) -> str:
        name = re.search(r"cut off while writing (\S+?), which", prompt).group(1)
        header = text.split("=== FILE:")[0]
        block = re.search(r"=== FILE: " + re.escape(name) + r" ===\n.*?=== END FILE ===\n", text, re.S)
        return header + (block.group(0) if block else "")

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
