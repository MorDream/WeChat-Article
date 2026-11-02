"""接入自检：一条命令确认 AppID / AppSecret / IP 白名单 / 草稿接口是否都通了。

用法：python check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from wxpub import MPClient, WeChatError, load_env

ROOT = Path(__file__).resolve().parent


def main() -> int:
    env = ROOT / ".env"
    if not env.exists():
        print("没找到 .env")
        print(f"先把 .env.example 复制成 .env，填上 AppID 和 AppSecret：")
        print(f"  copy .env.example {env}")
        return 1

    load_env(env)
    appid = os.getenv("WX_APPID", "").strip()
    secret = os.getenv("WX_APPSECRET", "").strip()

    print("=" * 46)
    print("公众号接入自检")
    print("=" * 46)
    print(f"AppID：{appid[:6]}…{appid[-4:]}" if len(appid) > 10 else f"AppID：{appid or '(空)'}")
    print(f"AppSecret：{'已填写，长度 ' + str(len(secret)) if secret else '(空)'}")
    print("-" * 46)

    if not appid or not secret:
        print("请先在 .env 里补全这两项，AppID/AppSecret 到微信开发者平台「基础信息 / 开发密钥」核对")
        return 1

    client = MPClient(appid, secret, ROOT / ".cache")

    try:
        token = client.token(refresh=True)
        print(f"[OK] access_token：{token[:16]}…")
    except WeChatError as exc:
        print("[FAIL] 拿不到 access_token")
        print(f"       {exc}")
        if exc.errcode == 40164:
            print()
            print("照这个做：")
            print("  1. 打开 https://developers.weixin.qq.com 并登录")
            print("  2. 左侧「我的业务与服务」选中你的公众号")
            print("  3. 找到「API IP 白名单」，把上面提示里的 IP 加进去")
            print("  4. 保存后再跑一次本脚本")
        return 2

    ok = True
    try:
        drafts = client.list_drafts(count=5)
        print(f"[OK] 草稿箱接口：当前 {len(drafts)} 篇草稿")
        for item in drafts[:3]:
            title = item.get("content", {}).get("news_item", [{}])[0].get("title", "")
            print(f"       · {title}")
    except WeChatError as exc:
        ok = False
        print(f"[WARN] 草稿接口异常：{exc}")

    # 发表能力：接口调不了，但后台可能有按钮，得让用户知道点哪儿
    try:
        can_publish = client.publish_ability()
        print(f"[{'OK' if can_publish else 'WARN'}] 后台「发表」按钮：{'有，可在草稿箱手动点' if can_publish else '没有，只能群发'}")
    except WeChatError:
        can_publish = None
        print("[--] 发表能力：查询失败，不影响推草稿")

    print("-" * 46)
    if ok:
        print("结论：链路已通，可以开始推稿了。")
        print("下一步：python push.py drafts/示例稿件.md --cover 封面.png")
        print()
        print("注意：个人订阅号没有发表接口权限（48001），稿子只会进草稿箱。")
        if can_publish:
            print("      最后一步在后台点「发表」：电脑 mp.weixin.qq.com → 内容管理 → 草稿箱 → 选中 → 发表")
        else:
            print("      最后一步在后台点「群发」，会消耗当天 1 次群发额度。")
    else:
        print("结论：token 通了但草稿接口不通，把上面的报错发我，我按码定位。")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
