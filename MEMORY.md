# 微像素背景与 8 秒 2D 视频

这部分与现有人物生成器共用一套 Python 环境、API 服务和密钥。背景可独立生成，也可以将其与 1–2 个已通过最终检查的人物组合成短视频。此次交付程序，没有调用真实图像 API 生成新素材。

## 做到什么

输入一张场景照片、一段场景文字，或两者一起，生成微像素背景。可附加已批准的人物原型作为**风格参考**：背景采用相似轮廓、色板、简化阴影和像素颗粒。提示词要求不把人物画进背景，并在前景留出落脚区域。生成背景后仍应目视确认风格与构图；模型无法保证每次完全匹配。

背景与已有透明人物精灵图经过本地合成，输出默认 **8 秒、24 fps、192 帧、H.264/yuv420p MP4**，可在网页或手机播放；附封面 PNG 与时间线 JSON。视频是静态背景上的人物逐帧动画与移动，可添加一句文字记录，默认无声。没有视频生成模型调用；背景通常只需一次图像调用，复用背景后可以反复本地合成。

画面尺寸：横屏 1280×720、竖屏 720×1280、方形 960×960。默认 2 像素网格，可改 4 获得更明显像素感。背景使用固定 96 色调色板；视频合成后统一画面网格，字幕单独渲染以保证可读。竖屏双人会按可用宽度缩小，避免挤在一起。

## 运行

按 README 安装/升级（`pip install -e ".[test]"`），配置原来的环境变量，再启动同一个服务：

```text
uvicorn pixel_avatar.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

打开 http://127.0.0.1:8000/memory ：

1. 填服务令牌、场景照片/描述，可填一个已批准原型的人物 ID 作为风格参考。
2. 创建任务，然后点击“生成背景”。完成后预览背景。
3. 填一个或两个人物 ID（状态必须为 `ready`），选动作模板和字幕。
4. 创建视频任务，点击“合成视频”，完成后播放或下载 MP4。

三个动作模板：

| 模板 | 8 秒中的动作安排 |
| --- | --- |
| `meet` 相遇 | 0–2.4 秒走近，2.4–5.6 秒挥手，5.6–8 秒互相看向对方 |
| `celebrate` 庆祝 | 走近 → 跳跃 → 对视 |
| `quiet` 陪伴 | 并排站立，持续待机呼吸/眨眼 |

单人模板最后恢复待机。已有跑步帧用于移动，因此实际步态是现有人物的跑步节奏；需要慢走应另增对应动作素材。

## CLI：不接前端也可使用

```text
pixel-memory scene-create --description "傍晚公园，暖色路灯和湖，前景是开阔小路" --style-avatar data/<人物ID>
pixel-memory scene-run data/scenes/<场景ID>

# 图片输入，可同时补充文字
pixel-memory scene-create --photo park.jpg --description "保留湖与树，暖色夕阳" --aspect landscape

pixel-memory movie-create --scene data/scenes/<场景ID> --avatar data/<人物A> --avatar data/<人物B> --caption "今天又一起走过了这条小路。" --preset meet
pixel-memory render data/movies/<视频ID>
pixel-memory status data/movies/<视频ID>

# 修改不满意的场景，再运行 scene-run；会再次调用图像模型
pixel-memory scene-retry data/scenes/<场景ID> "保留湖面，让下方20%的路面更开阔，去掉人物"
```

输出：`data/scenes/<ID>/background.png`、`scene.json`；`data/movies/<ID>/memory.mp4`、`poster.png`、`timeline.json`。CLI 返回的文件夹路径可直接用于下一步。

## Python 模块

```python
from pixel_avatar.scenes import create_scene, run_scene
from pixel_avatar.movie import create_movie, render_movie

scene = create_scene("data/scenes", description="夜晚温暖的小咖啡馆，前景开阔",
                     photo="cafe.jpg", style_avatar="data/人物A的ID", pixel_block=2)
run_scene(scene)  # 调用图像 API；无照片和风格图时走文生图，有图时走多图编辑

movie = create_movie("data/movies", scene, ["data/人物A的ID", "data/人物B的ID"],
                     {"caption":"今天一起喝了喜欢的咖啡。", "preset":"quiet"})
render_movie(movie)  # 本地 FFmpeg 编码，不调用模型
```

图像 API 按官方接口实现：[文生图](https://developers.openai.com/api/reference/python/resources/images/methods/generate)、[多图编辑](https://developers.openai.com/api/reference/python/resources/images/methods/edit)。沿用 `OPENAI_API_KEY`、`IMAGE_MODEL` 和可选 `OPENAI_BASE_URL`；替换服务时需同时支持这两个接口。

## HTTP 接口

仍使用 `Authorization: Bearer <AVATAR_SERVICE_TOKEN>`，仅供你的网站后端调用。终端用户登录、素材所属关系与配额由你的网站负责。

| 接口 | 参数/作用 |
| --- | --- |
| `POST /v1/scenes` | multipart：`description`、可选 `photo`、可选 `style_avatar_id`、`aspect`、`pixel_block`；创建后不自动收费 |
| `POST /v1/scenes/{id}/run` | 异步生成，202；只有这里调用图像 API |
| `GET /v1/scenes/{id}` | `status` 与 `active` |
| `POST /v1/scenes/{id}/retry` | JSON `{"description":"新的完整场景描述"}`，撤回背景结果，保留历史；随后显式 run |
| `GET /v1/scenes/{id}/files/background.png` | 获取背景，另支持 `scene.json` |
| `POST /v1/memories` | 创建视频任务，见下例 |
| `POST /v1/memories/{id}/run` | 异步本地合成，202 |
| `GET /v1/memories/{id}` | 状态、`progress`（0–1）、`active`、成功后的尺寸/帧数 |
| `GET /v1/memories/{id}/files/memory.mp4` | 下载/播放视频，另支持 `poster.png`、`timeline.json` |

创建视频的 JSON：

```json
{
  "scene_id":"场景ID",
  "avatar_ids":["人物A的ID","人物B的ID"],
  "options":{
    "duration":8,
    "fps":24,
    "preset":"meet",
    "caption":"今天，我们又一起走过了这条小路。",
    "ground_y":0.84,
    "actor_height":0.31
  }
}
```

人物 ID 与场景 ID 都是实际返回的 32 位十六进制 ID。`ground_y` 是落脚位置/画面高度；如果背景地面不在默认位置，可改 0.55–0.95。`actor_height` 是人物可见高度/画面高度，范围 0.15–0.38；双人竖屏还受宽度上限约束。

## 自定义动作、站位与视线

向 `options.tracks` 传每个人的一条时间线，覆盖模板。CLI 可用 `--options examples/memory-options.json`。每条时间线最多 24 段，按时间升序排列，段之间不能重叠，不能超过视频长度；时间空档会隐藏该人物。

```json
{
  "duration":8,
  "tracks":[
    [
      {"start":0,"end":3,"action":"running-right","x":0.2,"to_x":0.4},
      {"start":3,"end":6,"action":"waving","x":0.4},
      {"start":6,"end":8,"action":"idle","x":0.4,"gaze":4}
    ],
    [
      {"start":0,"end":3,"action":"running-left","x":0.8,"to_x":0.6},
      {"start":3,"end":6,"action":"jumping","x":0.6},
      {"start":6,"end":8,"action":"idle","x":0.6,"gaze":12}
    ]
  ]
}
```

`x` 与 `to_x` 是画面宽度比例，0.12–0.88，指定 `to_x` 后在该段线性移动。`gaze` 为 0–15 的视线格索引：0 上、4 右、8 下、12 左；填写时该段使用视线静态姿态，不同时播放动作。省略则根据原动作帧时长循环。人物位置以中性姿态脚底为锚点，保留跳跃帧的高度变化。

## 可迁移性、失败恢复与边界

- 输入场景和人物在创建视频时复制成快照。此后重做原背景或人物，不会改变这条视频；要使用新版素材需创建新视频任务。
- 复制整个 `data` 即可迁移任务；没有本机绝对素材路径。已保存的场景 raw 图在恢复时不会再次调用模型。渲染失败/中断后执行 run，会从头重编码，只有完成的视频才能下载。
- `imageio-ffmpeg` 在常见平台的 wheel 中附带 FFmpeg。特殊架构可安装系统 FFmpeg（需 libx264）并设置 `IMAGEIO_FFMPEG_EXE`。不需要 GPU。
- 中文字幕需要字体。Windows/macOS 会寻找常见中文字体，Docker 安装 Noto CJK；其他主机设置 `AVATAR_FONT_PATH`。字幕过长（超过三行）会明确失败，不静默截断。字幕不满意可缩短文字后新建视频。
- 单实例与原人物服务共用两条工作线程和队列上限。大规模上线仍需外部持久队列、用户权限与存储策略。
- 当前背景为单层静态图，没有天气粒子、场景内物体独立动画或前后遮挡关系。人物会绘制在背景上层；请优先使用开阔前景。没有自动生成拥抱、接吻等新交互动作，也没有音轨。
- 本次实测涵盖模拟背景与几何人物的真实 8 秒 MP4 编码/解码。未对新照片实际调用模型，不能以程序测试代替画风/相似度的视觉验收。
