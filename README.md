# sgs-skins · 武将皮肤图 CDN 仓库

独立存放三国杀武将图鉴的**皮肤大图**，供 App / 原页面通过 CDN 按需加载。

## 为什么单独一个仓

- 主数据仓库 `sgs-data` 当前 247 MB / 9313 文件，负责**文字数据 + 原页面骨架**，随版本 tag 热更新。
- 皮肤 12901 张 / 706.6 MB，若塞进主仓会到 954 MB，顶到 GitHub 推荐 1 GB 与 jsDelivr 1 GB 软上限，以后没有余量。
- 分开后两仓各自安全、各自打 tag、各自增量推送；改一句武将文案不需要重扫一万多张图。

## 目录结构

按主程序的**原 URL 路径平铺**，不做打包、不改文件名：

```
images/
├── gjf/sk/*.webp      1031 张   35.7 MB
├── hlsgs/sk/*.webp     752 张   69.2 MB
├── msgs/sk/*.webp     1519 张  107.2 MB
├── sgs/sk/*.webp      4214 张  167.0 MB
├── sgsol/sk/*.webp    4473 张  280.3 MB
└── wxmini/sk/*.webp    912 张   47.2 MB
manifest.json          版本摘要（不含逐文件列表，App 不按它下载）
tools/sync.py          单向同步脚本
```

路径与 `sgs-data/skins/*.json` 里的 `sk` 字段**一一对应**，例如
`images/gjf/sk/104.webp` → `https://gcore.jsdelivr.net/gh/liu2547259736/sgs-skins@main/images/gjf/sk/104.webp`。

## 为什么不压缩成 zip

抽样 300 张实测：webp 已是压缩格式，zip 默认压缩后**反而大 0.2%**，LZMA 大 1.6%。
打包还会触发 jsDelivr 单文件 50 MB 上限（sgsol 单版本就 280 MB 得分 6 卷），
并迫使客户端新增「查索引 → 下整卷 → 解压 → 缓存」逻辑，改一张图要重下整卷。
平铺后单张最大 0.21 MB、平均 56 KB，天然按文件粒度增量。

## CDN 用法

资源根（App 里配置，设置页可覆盖）：

```
https://gcore.jsdelivr.net/gh/liu2547259736/sgs-skins@main/
```

> 默认用 `gcore` 镜像：`cdn.jsdelivr.net` 在国内直连 TLS 握手失败
> （2026-11-12、11-16 实测 HTTP 000，挂代理才 200），gcore / testingcf 可直连。
> 图片是 `<img>` 单源直取、没有回退机会，所以 App 的默认源必须可直连。

原页面图片 URL 带 `?iv=N` 破缓存参数，壳做 302 重定向时必须原样保留 query。
需要固定版本时可用 tag：`https://gcore.jsdelivr.net/gh/liu2547259736/sgs-skins@skins-v2026.11.12/`。

## 同步

```bash
python tools/sync.py --check                    # 只看有没有变更
python tools/sync.py --commit --push --tag     # 完整发布
```

单向：主程序 `H:\AI\sgs-heroes\sgs-heroes-app\images\*\sk\` → 本仓。
**禁止反向写回主程序。** 无变更不产生空提交 / 空 tag。
自动同步由 `../data-repo/tools/auto_sync.py` 统一调度（与数据仓 tag 解耦）。

## 边界

- **语音**（26556 个 / 1621 MB）不在此仓，也不在 CDN 上 —— 超 1 GB 上限，仍留本地。
- 皮肤**不进 `sgs-data/manifest.json` 的 files 列表**：它是按需 HTTP 加载的静态资源，不下载到用户设备占 706 MB。
- Web 静态直出版没有服务端可做 302，需要部署侧把皮肤挂到同域 `images/` 下，或做 nginx rewrite。
