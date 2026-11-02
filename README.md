# wechat-mp-auto

把 Markdown 稿件自动推进微信公众号草稿箱。个人订阅号可用，每天跑一次，你只在手机上点一下群发。

## 能做到什么 / 做不到什么

| 环节 | 是否自动 |
| --- | --- |
| 选题 | 定时任务生成，人工过一眼 |
| 写稿、排版、封面 | 全自动 |
| 上传素材、写入草稿箱 | 全自动 |
| 群发 / 发布 | **个人订阅号必须手动**，微信 2025 年 7 月起回收了个人主体的发布接口 |

这是微信的权限规则，不是本工具的缺陷。企业或个体户认证号（300 元/年）才能全链路自动发布。

## 快速开始

```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 填凭证
copy .env.example .env      # 然后填写 WX_APPID 和 WX_APPSECRET

# 3. 自检（会告诉你 IP 白名单加哪一个）
python check.py

# 4. 生成封面（900x383，本地渲染，不依赖 AI）
python make_cover.py "文章标题" --sub "一句话副标题" --brand "猛虎传说的温暖角落" -o drafts/cover.png

# 5. 本地预览排版，不碰接口
python push.py drafts/示例稿件.md --dry-run

# 6. 正式推草稿
python push.py drafts/示例稿件.md --cover drafts/cover.png
```

## 稿件格式

Markdown 文件，开头可以用 `---` 写元信息，不写则自动取第一个 `# 标题` 和正文前 100 字作摘要。

```markdown
---
title: 文章标题
digest: 自定义摘要，最多 100 字
author: 欧尼酱
source_url: https://原文链接（可空）
---

## 正文从这里开始
```

正文里用相对路径引用的本地图片（`![](cover2.png)`）会自动上传到微信图床并替换链接。

## 文件说明

```
wxpub.py        接口封装 + Markdown 排版（token 缓存、素材上传、草稿写入）
push.py         命令行入口：稿件 → 草稿箱
check.py        接入自检：凭证、IP 白名单、草稿权限
make_cover.py   封面图生成（900×383，本地渲染）
make_diagram.py 讲解示意图生成（JSON 驱动的流程图 / 左右对比图）
drafts/         稿件、封面、论文配图、示意图定义
topics/         选题池与经验沉淀
styles/         风格档案（小白向写作标准与检查清单）
docs/           后台配置步骤
```

## 一篇稿件怎么来

以论文解读为例：

```bash
# 1. 抓论文原图和细节
curl -x http://127.0.0.1:7892 "https://arxiv.org/html/<id>" -o /tmp/p.html
# 从 <img src> 里挑图，下载到 drafts/assets/

# 2. 画讲解示意图
python make_diagram.py drafts/diagrams/pet.json -o drafts/assets/diag-pet.png

# 3. 出封面
python make_cover.py "标题" --sub "副标题" --brand "猛虎传说的温暖角落" -o drafts/cover.png

# 4. 本地预览 → 推草稿箱
python push.py drafts/2026-11-02-tango.md --dry-run
python push.py drafts/2026-11-02-tango.md --cover drafts/cover.png
```

取图、写稿、排版这三步由定时任务自动完成，人只负责最后在手机上点群发。

示意图用 JSON 描述，改文案不用动代码：

```json
{
  "title": "图的标题",
  "nodes": [
    {"title": "第一行", "sub": "第二行小字"},
    {"title": "重点节点", "sub": "带橙色底", "accent": true}
  ],
  "note": "底部说明"
}
```

讲「传统方法 vs 本文方法」时用左右对比布局，横向流程图摆不下这种对照：

```json
{
  "type": "compare",
  "title": "图的标题",
  "left":  {"label": "旧做法", "title": "一句话结论", "points": ["要点一", "要点二"]},
  "right": {"label": "新做法", "title": "一句话结论", "points": ["要点一"], "accent": true},
  "note": "底部说明"
}
```

## 写稿标准

见 `styles/风格档案.md`。目标读者是对 AI 有兴趣但不是从业者的人，每个术语第一次出现都要就地解释，数字后面要给参照系。交稿前对着文末检查清单过一遍。

## 常见报错

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `40164` | 调用 IP 不在白名单 | 把报错里的 IP 加进微信开发者平台的「API IP 白名单」 |
| `40125` | AppSecret 错 | 开发者平台「开发密钥」页重新生成，更新 `.env` |
| `40001` | token 失效 | 删掉 `.cache/` 再跑 |
| `48001` | 接口未授权 | 个人号没有永久素材权限，脚本会自动降级到临时素材，不用管 |
| `40007` | 封面临时素材过期 | 重新跑一次，临时素材只有 3 天 |

## 注意

- `.env` 已在 `.gitignore` 里，**不要**把 AppSecret 提交到仓库。
- 封面推荐 900×383（2.35:1），微信会按这个比例裁切。
- 正文超过 2 万字符会被接口拒绝，长文请拆篇。
