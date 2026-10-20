# 情侣网站微像素工具包 · 人物、背景与八秒视频

**交给其他 LLM：先读 [AGENTS.md](AGENTS.md) 与 [LLM_GUIDE.md](LLM_GUIDE.md)。** 后者包含架构、状态机、代码入口、调用示例、收费边界和排错流程。背景/视频详细用法见 [MEMORY.md](MEMORY.md)。

## 在另一台电脑使用

此仓库包含两个配套模块：`pixel-avatar`（人物生成）和 `pixel-memory`（背景生成与视频合成）。推荐 Python 3.12。

```text
git clone https://github.com/mhtTxd1/pixel-memory-studio.git
cd pixel-memory-studio
python -m venv .venv
```

Windows PowerShell 执行 `.venv\Scripts\Activate.ps1`；Linux/macOS 执行 `source .venv/bin/activate`。然后：

```text
pip install -r requirements.lock.txt
pip install --no-deps -e .
```

按下文设置 API 密钥及服务令牌，启动服务后访问 `/`（人物）与 `/memory`（背景和视频）。私有仓库需在另一台电脑登录同一个 GitHub 账号或被授权的账号。已有任务需单独迁移 `data` 文件夹；GitHub 仅保存程序，不含照片、生成结果或密钥。

可迁移的 Python 模块、HTTP 服务与原生 JavaScript 播放器。沿用之前女友宠物成功示例的布局与分阶段生成方法，风格改为轻像素。**本次交付程序，不包含新人物生成结果。**

## 生成内容

- 同一个人的 1–4 张照片 → 一张统一人物原型。情侣双方分别创建任务。
- 9 组动作：待机、向右跑、向左跑、挥手、跳跃、难过、等待、思考、观察。
- 16 个视线方向：从向上开始，每 22.5° 顺时针一格。不是身体 16 朝向行走动画。
- 透明 PNG / WebP 精灵图（1536×2288）、`avatar.json`、动作 GIF、带标签检查图。
- 像素程度：`pixel_block=2` 默认轻像素（96×104 逻辑网格放大两倍）；`4` 更明显；`1` 只依靠模型生成的像素风。

0.2 新增场景生成与视频模块：图片/文字 → 微像素背景 → 人物动作时间线 → 约 8 秒 MP4。打开 `/memory` 使用背景与视频工作台；完整说明见 [MEMORY.md](MEMORY.md)。支持相遇、庆祝、安静陪伴三个动作模板与自定义时间线，尚不包含从任意日记自动理解并生成复杂剧情、配音或新人物动作。

## 快速启动（Python 3.11+）

```powershell
# 先进入克隆后的 pixel-memory-studio 目录，或 ZIP 解压后的 pixel-avatar 目录
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[test]"
$env:OPENAI_API_KEY="你的 API 密钥"
$env:AVATAR_SERVICE_TOKEN="至少16位的随机服务令牌"
uvicorn pixel_avatar.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Linux/macOS 使用 `source .venv/bin/activate`，并用 `export OPENAI_API_KEY=...` 等设置变量。直接启动不自动读取 `.env`，Docker Compose 会读取。

若要固定为交付测试版本，先执行 `pip install -r requirements.lock.txt`，再执行 `pip install --no-deps -e .`。锁文件不包含本机绝对路径。

打开 http://127.0.0.1:8000 ，填入服务令牌即可使用开发工作台；接口文档在 `/docs`。创建任务只保存照片，点击“生成 / 继续”才调用模型。

没有 API 密钥也可以安装、运行测试、创建任务。真正生成需具备相应模型访问权限。默认 `gpt-image-1.5`，可通过 `IMAGE_MODEL`、`IMAGE_QUALITY`、`OPENAI_BASE_URL` 配置。兼容服务必须支持多参考图编辑和 base64 图像返回，不能只支持文生图。

## 生成与检查流程

1. 创建人物任务，上传同一个人的清晰照片，填写希望保留的发型、衣着等特征。
2. 生成 `base`，检查人物像不像、风格是否合适；通过后才继续。
3. 依次生成并检查 9 组动作。每组都引用同一张原型，不把一组动作硬变换成另一组。
4. 检查 `cardinals` 的上、右、下、左；然后依次检查 `look-row-9` 和 `look-row-10`。后一行还引用前一行保持衔接。
5. 检查完整精灵图与动画，批准 `final` 后状态变为 `ready`。

每阶段在 `needs_review` 停下。检查页要求填写观察记录：五官/服装一致、完整无裁切、动作含可见变化、视线方向正确、比例稳定。像素网格转换可能丢失很细的五官；不满意可改小像素块或重试原型。程序只检查分组和几何，不能自动证明“长得像”或方向语义正确。

一轮完整素材有 13 次图像生成调用，失败重试会增加。SDK 自动重试已关闭。中断后已保存的阶段不重复生成；若远端已收费而本地尚未保存就断线，重跑该阶段仍可能再次收费。

失败时先查看私有 `data/<id>/job.json` 的错误。缺少密钥/网络失败可直接继续；分组或画面问题用“重置当前组”填写纠正意见，然后继续。重试 `base` 会使全部下游失效；重试主方向会使两个方向行失效；重试前八方向会使后八方向失效；普通动作仅重做自身。旧文件存入 `history`，最终输出会撤回，避免误用旧版。

## HTTP 集成

所有 `/v1` 接口使用 `Authorization: Bearer <AVATAR_SERVICE_TOKEN>`。这是后端之间的服务令牌，不应分发给网站终端用户。你的网站后端负责用户登录、角色所属检查、上传限流和把生成素材保存到自己的私有对象存储或授权 CDN。

| 接口 | 用途 |
| --- | --- |
| `POST /v1/avatars` | multipart：`photos`（可重复）、`name`、`notes`、`pixel_block` |
| `GET /v1/avatars/{id}` | 状态、当前阶段、是否仍在执行 |
| `POST /v1/avatars/{id}/run` | 异步开始/继续，返回 202 |
| `POST /v1/avatars/{id}/approve` | JSON：`{"stage":"base","note":"人物发型服装一致，完整无裁切"}` |
| `POST /v1/avatars/{id}/retry` | JSON：`{"stage":"look-row-9","note":"90度必须朝屏幕右侧"}` |
| `GET /v1/avatars/{id}/files/{name}` | 获取授权检查图/素材 |

状态流：`created → running → needs_review → paused → … → needs_review(final) → ready`；异常进入 `failed`。`active` 是当前进程的队列/执行状态。重启后任务状态文件可能仍显示 `running`，但 `active=false`，可以显式继续。服务不在重启时自动触发收费请求。

只有 `status=ready` 才应在正式网站发布素材；文件接口也允许读取尚在检查中的中间产物，供工作台预览。

## Python / CLI 集成

```python
from pixel_avatar import create_job, run_job, approve

folder = create_job("data", ["person.jpg"], name="她", notes="保留短发和粉色裙子", pixel_block=2)
job = run_job(folder)  # 首次仅生成原型；后续每次推进到下一处审核
# 检查 folder/processed/base.png 之后：
approve(folder, "base", "人物特征和服装正确，像素感合适")
job = run_job(folder)
```

```text
pixel-avatar create person.jpg --name 她 --pixel-block 2
pixel-avatar run data/<返回的ID>
pixel-avatar status data/<ID>
pixel-avatar approve data/<ID> base "已检查五官、服装与完整轮廓"
pixel-avatar retry data/<ID> waving "手要有明显挥动，不能有漂浮特效"
```

替换模型：实现 `generate(prompt: str, refs: list[Path], stage: str) -> PIL.Image.Image`，传给 `run_job(folder, provider=你的适配器)`。服务可用 `create_app(provider_factory=...)` 注入。无需修改精灵图格式或前端。

## 在你的网站中播放

把 `pixel_avatar/web/player.js` 拷入前端项目，输出素材按同一人物存放：

```javascript
import { AvatarPlayer } from './player.js';
const manifest = await fetch('/assets/person-a/avatar.json').then(r => r.json());
const image = new Image();
image.src = '/assets/person-a/spritesheet.png';
await image.decode();
const avatar = new AvatarPlayer(document.querySelector('canvas'), image, manifest);
avatar.play('waving');
avatar.lookAt(100, -40); // 相对人物中心的指针坐标：x右为正，y下为正
avatar.neutral();       // 回到当前动作
// 组件卸载时：avatar.destroy();
```

第二个人用第二个 canvas 和实例。后续日记模块可选择 `waving`、`jumping` 等动作并安排时间线；它们共享同一人物资产，无需每天重生角色。

## Docker 与迁移

```text
cp .env.example .env
# 编辑密钥和随机服务令牌
docker compose up --build -d
```

服务默认仅映射本机 8000 端口。容器使用非 root 用户，数据在 `avatar-data` 命名卷。迁移需要：源代码/镜像、整个数据目录（含 `job.json`、references、raw、processed 等）和目标主机独立配置的密钥。任务文件内部没有原机器绝对路径，复制完整任务目录后可继续。

Docker 卷可用你现有的卷备份工具导出/还原；也可改为挂载可写的主机目录。不要只迁移最终图后期待断点续跑。Windows、Linux、macOS 均可本地安装，主机无需 Codex、技能目录或 GPU；图像推理由远程 API 提供。

这是单实例后端组件：仅启动一个 uvicorn worker，两条后台线程，最多 8 个排队/执行任务。文件锁防止同一任务并发写入。跨主机扩容需要接入持久队列与共享任务存储；当前版本未实现分布式调度。公网部署在你的鉴权网关后，配置请求体上限（建议 45 MB）、速率限制和 HTTPS。原照片不通过文件接口暴露。

## 测试

```text
pytest -q
node tests/player.test.mjs
```

自动测试使用几何测试夹具和模拟模型，覆盖流程、重试、断点续跑、透明布局、上传与鉴权，不调用真实图像 API。真实照片的像素风质量与相似度需要首次接入模型时验收。原示例仅作为实现依据，不随包分发。

已执行的验证及未覆盖项见 `VALIDATION.md`。运行 `python scripts/package.py` 可重新生成不包含原照片、密钥或虚拟环境的可迁移源码 ZIP。
