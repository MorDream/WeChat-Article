"""微信公众平台接口封装 + Markdown 排版。

设计目标：
1. 只依赖标准库 + markdown，换台电脑也能直接跑。
2. 账号没有的权限（比如个人订阅号的发布接口）给出人话提示，而不是一串 errcode。
3. 排版结果全部用内联 style，因为公众号编辑器会丢掉 class。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.weixin.qq.com/cgi-bin/"

# 常见错误码翻译成人话
ERROR_HINTS = {
    40001: "access_token 无效，通常是 AppSecret 填错或已被重置，重新跑一次会刷新缓存",
    40013: "AppID 不正确，检查 .env 里的 WX_APPID",
    40125: "AppSecret 不正确，去微信开发者平台的「开发密钥」页重新生成",
    40164: "调用来源 IP 不在白名单。去微信开发者平台的「API IP 白名单」把报错里的 IP 加进去",
    48001: "该接口未授权。个人订阅号没有发表/群发接口权限，只能推到草稿箱，最后一步在后台手动点",
    45009: "接口调用超过当日限额，等第二天或降低频率",
    41005: "缺少媒体文件数据，通常是封面上传失败",
    40007: "media_id 无效或已过期（临时素材只有 3 天）",
}


class WeChatError(RuntimeError):
    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        hint = ERROR_HINTS.get(errcode, "")
        # 40164 的报错信息里带着真实出口 IP，直接抠出来
        ip_hint = ""
        m = re.search(r"invalid ip ([0-9a-fA-F.:]+)", errmsg or "")
        if m:
            ip_hint = f"\n  需要加入白名单的 IP：{m.group(1)}"
        super().__init__(f"[{errcode}] {errmsg}" + (f"\n  提示：{hint}" if hint else "") + ip_hint)


def _http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        return exc.read()


def _json(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8"))


def _check(obj: dict) -> dict:
    code = obj.get("errcode", 0)
    if code:
        raise WeChatError(code, obj.get("errmsg", ""))
    return obj


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")


def _multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = "----wxpub" + hashlib.md5(str(time.time()).encode()).hexdigest()
    body = bytearray()
    for key, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
    for key, path in files.items():
        path = Path(path)
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; '
            f'filename="{path.name}"\r\nContent-Type: {_guess_mime(path)}\r\n\r\n'
        ).encode()
        body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def load_env(path: str | Path = ".env") -> None:
    """极简 .env 读取，不覆盖已存在的环境变量。"""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class MPClient:
    def __init__(self, appid: str, secret: str, cache_dir: str | Path = ".cache"):
        if not appid or not secret:
            raise SystemExit("缺少 WX_APPID / WX_APPSECRET，请先复制 .env.example 为 .env 并填写")
        self.appid = appid
        self.secret = secret
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._token_file = self.cache / f"token_{appid[-6:]}.json"

    # ---------- 凭证 ----------

    def token(self, refresh: bool = False) -> str:
        if not refresh and self._token_file.exists():
            try:
                data = json.loads(self._token_file.read_text(encoding="utf-8"))
                if data.get("expires_at", 0) > time.time() + 120:
                    return data["access_token"]
            except (json.JSONDecodeError, KeyError):
                pass
        url = (
            f"{API_BASE}token?grant_type=client_credential"
            f"&appid={self.appid}&secret={self.secret}"
        )
        data = _check(_json(_http(url)))
        record = {
            "access_token": data["access_token"],
            "expires_at": time.time() + data.get("expires_in", 7200) - 300,
        }
        self._token_file.write_text(json.dumps(record), encoding="utf-8")
        return record["access_token"]

    def probe(self) -> dict:
        """自检：拿 token + 试读草稿数，确认账号到底有哪些权限。"""
        result = {"token": False, "draft": False, "detail": []}
        try:
            token = self.token(refresh=True)
            result["token"] = True
            result["detail"].append(f"access_token 获取成功（{token[:12]}…）")
        except WeChatError as exc:
            result["detail"].append(str(exc))
            return result
        try:
            body = json.dumps({"offset": 0, "count": 1, "no_content": 1}).encode()
            data = _check(_json(self._post("draft/batchget", body, token)))
            result["draft"] = True
            result["detail"].append(f"草稿箱接口可用，当前草稿 {data.get('total_count', 0)} 篇")
        except WeChatError as exc:
            result["detail"].append(str(exc))
        return result

    def _post(self, path: str, body: bytes, token: str, ctype: str = "application/json") -> bytes:
        url = f"{API_BASE}{path}?access_token={token}"
        return _http(url, data=body, headers={"Content-Type": ctype})

    # ---------- 素材 ----------

    def upload_cover(self, path: str | Path) -> tuple[str, str]:
        """上传封面，返回 (media_id, 用了哪个接口)。永久素材失败时自动降级到临时素材。"""
        path = Path(path)
        if not path.exists():
            raise SystemExit(f"封面文件不存在：{path}")
        token = self.token()
        body, ctype = _multipart({}, {"media": path})
        try:
            data = _check(_json(_http(
                f"{API_BASE}material/add_material?access_token={token}&type=thumb",
                data=body, headers={"Content-Type": ctype})))
            return data["media_id"], "永久素材"
        except WeChatError as exc:
            if exc.errcode not in (48001, 40007, 41005, 45009, -1):
                raise
            data = _check(_json(_http(
                f"{API_BASE}media/upload?access_token={token}&type=image",
                data=body, headers={"Content-Type": ctype})))
            return data["media_id"], "临时素材（3 天有效，当天用足够）"

    def upload_inline_image(self, path: str | Path) -> str:
        """上传正文内插图，返回微信图床 URL。"""
        path = Path(path)
        token = self.token()
        body, ctype = _multipart({}, {"media": path})
        data = _check(_json(_http(
            f"{API_BASE}media/uploadimg?access_token={token}",
            data=body, headers={"Content-Type": ctype})))
        return data["url"]

    # ---------- 草稿 & 发布 ----------

    def add_draft(self, article: dict) -> str:
        token = self.token()
        payload = {"articles": [article]}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        data = _check(_json(self._post("draft/add", body, token)))
        return data["media_id"]

    def list_drafts(self, count: int = 20) -> list[dict]:
        token = self.token()
        body = json.dumps({"offset": 0, "count": count, "no_content": 1}).encode()
        data = _check(_json(self._post("draft/batchget", body, token)))
        return data.get("item", [])

    def delete_draft(self, media_id: str) -> bool:
        """删除草稿。改稿重推时用来避免草稿箱里堆重复版本。"""
        token = self.token()
        body = json.dumps({"media_id": media_id}).encode()
        _check(_json(self._post("draft/delete", body, token)))
        return True

    def publish_ability(self) -> bool:
        """查询后台是否有「发表」按钮（is_open=1 表示有）。

        注意：这是后台功能的开关，和 freepublish/submit 接口权限是两回事。
        个人订阅号通常是后台能点、接口不给调。
        """
        token = self.token()
        body = _http(f"{API_BASE}draft/switch?checkbottom=1&access_token={token}",
                     data=b"{}", headers={"Content-Type": "application/json"})
        return bool(_check(_json(body)).get("is_open"))

    def submit_publish(self, media_id: str) -> str:
        """尝试直接发布。个人订阅号会被微信拒绝，属预期行为。"""
        token = self.token()
        body = json.dumps({"media_id": media_id}).encode()
        data = _check(_json(self._post("freepublish/submit", body, token)))
        return data.get("publish_id", "")


# ---------------------------------------------------------------- 排版 ----

DEFAULT_THEME = {
    "p": "margin:0 0 22px;font-size:15px;line-height:1.9;letter-spacing:.4px;color:#3f3f3f;text-align:justify;",
    "h1": "margin:36px 0 20px;font-size:22px;font-weight:600;line-height:1.5;color:#1a1a1a;",
    "h2": "margin:34px 0 18px;padding-left:10px;border-left:3px solid #d97757;font-size:19px;font-weight:600;line-height:1.5;color:#1a1a1a;",
    "h3": "margin:26px 0 14px;font-size:17px;font-weight:600;line-height:1.5;color:#1a1a1a;",
    "h4": "margin:22px 0 12px;font-size:15px;font-weight:600;color:#1a1a1a;",
    "blockquote": "margin:0 0 22px;padding:14px 16px;border-left:3px solid #e3e3e3;background:#fafafa;color:#8a8a8a;font-size:14px;line-height:1.85;",
    "ul": "margin:0 0 22px;padding-left:22px;",
    "ol": "margin:0 0 22px;padding-left:22px;",
    "li": "margin:0 0 10px;font-size:15px;line-height:1.9;letter-spacing:.4px;color:#3f3f3f;",
    "strong": "font-weight:600;color:#1a1a1a;",
    "em": "font-style:normal;color:#8a8a8a;",
    "a": "color:#576b95;text-decoration:none;border-bottom:1px solid #d6dce5;",
    "hr": "margin:34px 0;border:none;border-top:1px solid #eaeaea;",
    "img": "display:block;max-width:100%;margin:6px auto;border-radius:6px;",
    "pre": "margin:0 0 22px;padding:16px;background:#f7f7f5;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.7;color:#333;",
    "code": "font-family:Menlo,Consolas,monospace;background:#f2f2f0;padding:1px 4px;border-radius:3px;font-size:13px;color:#c7254e;",
    "table": "width:100%;border-collapse:collapse;margin:0 0 22px;font-size:14px;",
    "th": "border:1px solid #e8e8e8;padding:9px 10px;background:#f7f7f5;font-weight:600;color:#1a1a1a;text-align:left;",
    "td": "border:1px solid #e8e8e8;padding:9px 10px;color:#3f3f3f;",
}

AI_NOTICE = (
    "> 本文由 AI 辅助整理与撰写，人工核对后发布。"
)


def strip_front_matter(text: str) -> tuple[dict, str]:
    """解析可选的 --- 开头的简易元信息块。"""
    meta: dict[str, str] = {}
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            head = parts[0].lstrip("-").strip()
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            text = parts[1].lstrip("-").strip()
    return meta, text


def _apply_styles(html: str, theme: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        tag, attrs = match.group(1).lower(), match.group(2) or ""
        if tag not in theme or "style=" in attrs:
            return match.group(0)
        return f'<{tag}{attrs} style="{theme[tag]}">'

    return re.sub(r"<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)>", repl, html)


def _fix_nested(html: str) -> str:
    """修掉嵌套标签被父级样式盖掉的两个典型问题。"""
    # 1. 代码块里的 code 不应该再带行内代码的粉色背景
    html = re.sub(
        r"(<pre[^>]*>)\s*<code[^>]*>",
        r'\1<code style="font-family:Menlo,Consolas,monospace;background:none;padding:0;'
        r'color:#333;font-size:13px;">',
        html,
    )
    # 2. 引用块里的段落要继承引用的灰色小字，而不是正文样式
    quote_p = ("margin:0;font-size:14px;line-height:1.85;color:#8a8a8a;"
               "letter-spacing:.4px;text-align:justify;")

    def fix_quote(match: re.Match) -> str:
        inner = re.sub(r'<p style="[^"]*"', f'<p style="{quote_p}"', match.group(2))
        return match.group(1) + inner + match.group(3)

    return re.sub(r"(<blockquote[^>]*>)(.*?)(</blockquote>)", fix_quote, html, flags=re.S)


def _extract_plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).strip()


def markdown_to_html(text: str, disclosure: bool = True, theme: str = "default") -> tuple[str, dict]:
    """把 Markdown 稿件转成公众号可用的内联样式 HTML。返回 (html, 元信息)。"""
    try:
        import markdown as md
    except ImportError as exc:
        raise SystemExit("缺少 markdown 库，先执行：pip install -r requirements.txt") from exc

    meta, body = strip_front_matter(text)

    title = meta.get("title", "")
    if not title:
        m = re.match(r"\s*#\s+(.+)", body)
        if m:
            title = m.group(1).strip()
            body = body[m.end():]

    html = md.markdown(
        body,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    html = _apply_styles(html, DEFAULT_THEME)
    html = _fix_nested(html)

    if disclosure:
        notice = md.markdown(AI_NOTICE)
        notice = _fix_nested(_apply_styles(notice, DEFAULT_THEME))
        html = html + '<hr style="' + DEFAULT_THEME["hr"] + '">' + notice

    meta["title"] = title
    meta.setdefault("digest", meta.get("summary", "") or _extract_plain(html)[:100])
    return html, meta


def build_article(html: str, meta: dict, thumb_media_id: str, author: str = "") -> dict:
    title = meta.get("title", "未命名稿件")[:64]
    return {
        "title": title,
        "author": (meta.get("author") or author)[:8],
        "digest": meta.get("digest", "")[:100],
        "content": html,
        "content_source_url": meta.get("source_url", ""),
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
