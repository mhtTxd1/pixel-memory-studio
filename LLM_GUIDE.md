# 给其他 LLM 的接入与维护手册

适用版本：0.2.x。目标是让另一个 AI 助手能在新电脑部署、调用、排错或集成到情侣网站。代码是最终依据；若手册与代码不一致，先检查对应入口并修正文档，不臆造参数。

## 1. 一分钟理解项目

```text
人物照片（一个人的 1–4 张）
  → create_job → run_job → 审核原型及各组动作/方向 → approve(final)
  → avatar.json + spritesheet.png（可长期复用）

场景照片 / 文字 + 可选人物原型风格图
  → create_scene → run_scene
  → scene.json + background.png

可用场景 + 1–2 个最终审核通过的人物 + 时间线/字幕
  → create_movie（复制输入快照）→ render_movie（本地 FFmpeg）
  → memory.mp4 + poster.png + timeline.json
```

人物和背景由远程图像模型生成。视频是程序逐帧合成，不调用视频模型。已有背景/人物可反复渲染，不增加图像调用。默认 8 秒、24 fps、192 帧、无声，支持 2–15 秒、12/24/30 fps。

## 2. 文件地图与应修改的位置

| 需求 | 文件/入口 |
| --- | --- |
| 换模型、换 API 服务 | `pixel_avatar/provider.py` / `OpenAIProvider.generate` |
| 调整人物风格、动作提示词、帧数与时序 | `pixel_avatar/spec.py` |
| 人物任务创建、推进、审核、重试 | `pixel_avatar/pipeline.py` |
| 人物透明背景、分组、像素化、图集 | `pixel_avatar/imaging.py`；`vendor/` 是本地打包的处理代码 |
| 背景构图、风格、分辨率、像素程度 | `pixel_avatar/scenes.py` |
| 时间线、人物放置、字幕、视频编码 | `pixel_avatar/movie.py` |
| 人物 API、共享鉴权和执行队列 | `pixel_avatar/api.py` |
| 背景/视频 API | `pixel_avatar/media_api.py` |
| CLI | `pixel_avatar/cli.py`、`memory_cli.py` |
| 浏览器单独播放人物 | `pixel_avatar/web/player.js` |
| 开发工作台 | `pixel_avatar/web/index.html`、`memory.html` |
| 安装、Docker、配置示例 | `pyproject.toml`、`requirements.lock.txt`、`Dockerfile`、`compose.yaml`、`.env.example` |
| 自动测试与验证范围 | `tests/`、`VALIDATION.md` |

## 3. 在新电脑启动

先克隆仓库，进入克隆目录，不要把旧电脑上的 `D:\pet` 路径直接搬进代码。推荐 Python 3.12。

```text
git clone https://github.com/mhtTxd1/pixel-memory-studio.git
cd pixel-memory-studio
python -m venv .venv
```

激活虚拟环境：Windows PowerShell 用 `.venv\Scripts\Activate.ps1`；Linux/macOS 用 `source .venv/bin/activate`。然后：

```text
pip install -r requirements.lock.txt
pip install --no-deps -e .
pytest -q
```

运行测试不需要 API 密钥。需要真正生成时，在服务器环境中设置：

| 变量 | 意义 |
| --- | --- |
| `OPENAI_API_KEY` | 图像模型密钥，仅后端使用 |
| `AVATAR_SERVICE_TOKEN` | 访问本服务的独立令牌，至少 16 字符；不是 OpenAI 密钥 |
| `IMAGE_MODEL` | 默认 `gpt-image-1.5`；模型需支持本项目使用的接口 |
| `IMAGE_QUALITY` | 默认 `high` |
| `OPENAI_BASE_URL` | 可选兼容服务地址，需支持文生图与多参考图编辑 |
| `AVATAR_DATA_DIR` | HTTP 服务数据目录，默认相对当前工作目录的 `data` |
| `AVATAR_FONT_PATH` | 可选字幕字体路径；中文字幕需要中文字体 |
| `IMAGEIO_FFMPEG_EXE` | 可选 FFmpeg 路径，特殊平台使用 |

直接启动不会自动加载 `.env`；Docker Compose 会加载。CLI 的目录使用 `--root` 或显式 folder 参数，不读取 `AVATAR_DATA_DIR` 来改写默认目录。

```text
uvicorn pixel_avatar.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

`GET /health` 检查服务；浏览器 `/` 人物工作台，`/memory` 场景/视频工作台，`/docs` OpenAPI 文档。所有 `/v1` 接口要求 `Authorization: Bearer <AVATAR_SERVICE_TOKEN>`。不要把服务令牌嵌入面向终端用户的网页代码；由网站后端代理并检查人物/场景所属关系。

## 4. 人物状态机：不要自动跳过审核

人物每次 `run_job` 最多推进到下一处审核。固定生成顺序：

```text
base → idle → running-right → running-left → waving → jumping
→ failed → waiting → running → review → cardinals
→ look-row-9 → look-row-10 → final（仅组装与最终审核）
```

其中 `failed`、`running`、`review` 可能是动作名，也可能出现在任务状态或字段名中，需结合字段区分。动作 `running` 表示思考/工作，左右跑步分别叫 `running-right`、`running-left`。

| 任务状态 | 调用方下一步 |
| --- | --- |
| `created` | 显式调用 run |
| `running` 且 API `active=true` | 等待并轮询，不重复提交 |
| `needs_review` | 查看 `review` 指定的阶段；检查图像，approve 或 retry |
| `paused` | 审核/重置已完成，显式 run 继续 |
| `failed` | 查看私有 `job.json` 中错误，修复后继续或重试整组 |
| `ready` | 人物可用于视频，不能据此推断背景也可用 |

API 重启后可能保留 `running` 但 `active=false`；确认旧实例已经停止后可以继续。`active` 只存在于 HTTP 查询结果，不是持久化字段。HTTP run 返回 202 仅代表已入队，不代表完成；人物在待审核/完成时再次 HTTP run 会返回 409。

Python 最小调用：

```python
from pixel_avatar import create_job, run_job, approve

folder = create_job("data", ["person.jpg"], name="人物A", notes="保留短发与浅色衣服", pixel_block=2)
job = run_job(folder)  # 首次生成 base，可能产生费用
# 此处必须查看 folder/processed/base.png 并真实审核
approve(folder, "base", "已查看：发型衣服与照片一致，全身完整，风格合适")
job = run_job(folder)  # 推进到 idle；随后仍逐组检查
```

审核读取：原型/动作/方向 `processed/<stage>.png`；动作另有 `processed/<stage>.gif`。最终查看 `output/contact-sheet.png`、动作 GIF、播放器中的连续方向。首次完整流程需 13 次图像生成，另有最终组装，无自动审核循环。

审核重点：像不像本人、发型服装是否一致、肢体完整、动作可见、脚底/比例稳定、视线语义正确。原型通过不能代替全部方向通过。文字审核记录是保存证据的位置，不是自动视觉判断器。

## 5. 精灵图契约

- 8 列 × 11 行；每格 192×208；完整图集 1536×2288。
- 前九行动作帧数依次为 `6,8,8,4,5,8,6,6,6`，未使用格透明。
- 后两行各 8 个方向，共 16 格；索引 0 上、4 屏幕右、8 下、12 屏幕左，每步 22.5°顺时针。
- 方向不是身体朝向/走路方向。中性正脸来自 idle，不是第 0 个方向。
- 帧时间由 `avatar.json.animations[*].durations` 提供，不统一硬编码 fps。
- `pixel_block` 支持 1、2、4；默认 2，数值越大像素感越强。
- 浏览器中用最近邻绘制；现有 `AvatarPlayer` 提供 `play`、`lookAt`、`neutral`、`destroy`。

## 6. 场景与视频的状态、调用

场景和视频没有人物那样的逐组 approve：`created → running → ready`，失败为 `failed`。场景的 `ready` 仅表示处理完成，`visualReviewed=false` 明确表示程序没有证明视觉质量；请预览背景后使用。

```python
from pixel_avatar.scenes import create_scene, run_scene
from pixel_avatar.movie import create_movie, render_movie

scene = create_scene("data/scenes", description="傍晚公园，湖边开阔小路",
                     photo="park.jpg", style_avatar="data/已批准原型的人物ID")
run_scene(scene)

# 以下人物任务均须经过 final 审核，状态 ready
movie = create_movie("data/movies", scene,
                     ["data/人物A的ID", "data/人物B的ID"],
                     {"duration":8, "preset":"meet", "caption":"今天一起散步。"})
render_movie(movie)
```

场景 photo 或 description 至少提供一项，style_avatar 可省略。背景为单层、不含人物；风格原型用于约束画风，不作为背景角色。视频人物最多两个，顺序决定模板左右站位。重复传入同一人物也会按两名角色绘制，不是自动去重。

`create_movie` 复制输入快照，之后源人物/场景重试不会修改已有视频。换素材、字幕或时间线应新建视频任务。输出 `memory.mp4`、`poster.png`、`timeline.json`。时间线字段、动作模板、字幕字体见 `MEMORY.md` 与 `examples/memory-options.json`。

## 7. HTTP 完整操作顺序示例

下面是网站后端可运行的 Python/httpx 示例；准备一张 `person.jpg`，启动服务并设置服务令牌后使用。示例故意在每处人物视觉审核暂停，不能改成“收到 needs_review 就无条件批准”。

```python
import os
import time
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60,
                      headers={"Authorization": "Bearer " + os.environ["AVATAR_SERVICE_TOKEN"]})

def request(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

def wait(path, max_seconds=1200):
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        job = request("GET", path)
        if not job["active"]:
            if job["status"] == "failed":
                raise RuntimeError("Inspect the server's private job.json; do not blindly retry")
            return job
        time.sleep(3)
    raise TimeoutError("Task may still be running; query it again, do not create a duplicate")

with open("person.jpg", "rb") as image:
    avatar = request("POST", "/v1/avatars", data={"name":"人物A", "pixel_block":"2"},
                     files={"photos": ("person.jpg", image, "image/jpeg")})
avatar_path = "/v1/avatars/" + avatar["id"]
request("POST", avatar_path + "/run")
job = wait(avatar_path)
print(job["review"])  # base
# 下载并检查 GET {avatar_path}/files/base.png（同样带鉴权头）
# 实际检查通过后：
# request("POST", avatar_path + "/approve", json={"stage":"base", "note":"真实观察记录"})
# 然后 run/wait，逐组重复。最后 approve stage=final，人物才为 ready。
client.close()
```

拥有 ready 人物后，用相同鉴权客户端按下列次序调用：

1. `POST /v1/scenes`：multipart `description`，可选 `photo`、`style_avatar_id`、`aspect`、`pixel_block`。
2. `POST /v1/scenes/{id}/run`，然后 GET 轮询至 `ready`。
3. 预览 `GET /v1/scenes/{id}/files/background.png`。
4. `POST /v1/memories`，JSON 为 `{"scene_id":"真实场景ID","avatar_ids":["真实人物ID"],"options":{"duration":8,"preset":"meet"}}`。
5. `POST /v1/memories/{id}/run`，GET 轮询至 `ready`。
6. 下载 `GET /v1/memories/{id}/files/memory.mp4`。以上 ID 必须使用接口返回值，不要使用展示用占位符。

OpenAPI 以运行服务的 `/openapi.json` 为准，错误 401 表示令牌不正确，404 表示任务/文件不存在，409 常见于运行中或审核状态不适合当前动作，422 表示输入无效，429 表示队列已满。

## 8. 收费、恢复与重试

| 操作 | 是否可能调用收费模型 |
| --- | --- |
| 安装、测试、创建人物/场景/视频任务、查询、审核、重置 | 不调用 |
| 人物 run，当前组缺 raw 图 | 是 |
| 场景 run，缺 raw 图 | 是 |
| 已保存 raw 的重新处理、最终图集合成 | 不调用 |
| 视频 render | 不调用；消耗本地 CPU |

SDK 自动重试关闭。`attempt` 是发起调用的次数，不能据此精确推断账单；远端已成功而本地断线未保存时，下一次 run 可能再次收费。

| 问题 | 处理 |
| --- | --- |
| 未设置密钥/模型不可用 | 修复服务端配置，再运行原任务 |
| 图像已保存但处理失败 | 普通 run 会复用 raw；若 raw 本身不合格，需 retry 后再 run |
| 人物某组画错/裁切/方向反了 | `retry_stage(folder, stage, correction)` 或 `/retry`；重画整组 |
| 原型改了 | 重试 base，使所有后续结果失效 |
| 主方向或第一方向行改了 | 自动撤回依赖方向行；不要手工拼补单格 |
| 场景不好 | `retry_scene(folder, 新的完整描述)`，随后 run；照片与风格参考保留 |
| 视频编码失败 | 检查 `encoder.log` 与 `job.json`，修复 FFmpeg/字体后重跑 |
| 字幕太长 | 缩短字幕并创建新视频任务；最多三行，100 字符是输入上限而非排版保证 |
| 文件锁冲突 | 等待持有锁的操作结束；不要直接删除活跃锁 |
| 重启后显示 running | 检查旧进程已停、active=false，再显式 run |

场景重置不会更换参考照片；要换照片/人物风格参考应创建新场景。用户想改已经完成的视频时，也应新建视频任务，不在输出 MP4 上就地修改。

## 9. 数据目录、迁移与测试

```text
data/
  <人物ID>/job.json, references/, raw/, processed/, output/, history/
  scenes/<场景ID>/job.json, reference.png（可选）, style.png（可选）,
                   raw.png, background.png, scene.json, history/
  movies/<视频ID>/job.json, background.png, scene.json, actor-0/, actor-1/（可选）,
                   memory.mp4, poster.png, timeline.json, encoder.log
```

目录中的密钥不应存在；若排错时错误消息含敏感内容，不要复制到公开 issue。迁移用完整数据目录，单独重新设置密钥/服务令牌/字体环境变量。复制前停止写入，避免快照不完整。只迁移 `output` 可展示人物，但不能继续生成流程。

无收费回归命令：

```text
pytest -q
node tests/player.test.mjs
python scripts/package.py
```

目前验证过 Windows Python 3.12、模拟模型任务与真实 FFmpeg 编解码；Docker、其他平台与真实新图片的视觉质量没有因此自动通过。测试中出现的几何图块不是用户人物素材。

## 10. 可直接交给下一个 LLM 的任务说明

> 请先阅读本仓库 AGENTS.md、LLM_GUIDE.md、README.md 和 MEMORY.md。这个项目包含人物生成与微像素背景/8秒视频两个模块。请使用项目虚拟环境，检查已有任务和配置是否齐全，不要打印密钥；若仅开发或测试，使用模拟模型。人物需要逐阶段实际视觉审核，禁止自动填通过。请复用现有 API/状态机与图集约定，把模块接到我的网站后端，完成必要的用户鉴权和任务归属校验。遇到失败先读取任务状态并定位原因，再决定恢复或整组重试。最终说明你修改了什么、哪些测试通过、哪些真实生成效果尚未验证。
