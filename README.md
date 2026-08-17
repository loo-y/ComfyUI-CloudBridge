# ComfyUI-CloudBridge

[English](#english) · [中文](#中文)

## English

ComfyUI-CloudBridge is a ComfyUI custom node pack for cloud AI providers. Each
provider and operation is exposed as a separate node instead of being combined
into one large provider selector.

The first release includes:

- **☁️ Kie.ai · Seedream 5 Lite · Image to Image**
- Up to 14 input images, including frames expanded from ComfyUI IMAGE batches
- Kie file upload, asynchronous task polling, and automatic result download
- `IMAGE`, `task_id`, and JSON `result_urls` outputs

### Installation

Clone the repository into ComfyUI's `custom_nodes` directory and install its
requirements with the Python environment used by ComfyUI:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/loo-y/ComfyUI-CloudBridge.git
cd ComfyUI-CloudBridge
python -m pip install -r requirements.txt
```

Restart ComfyUI, then find the node under `CloudBridge → Kie.ai` or search for
`Seedream 5 Lite`.

### API key

The recommended configuration is the `KIE_API_KEY` environment variable:

```bash
export KIE_API_KEY="your-kie-api-key"
```

On Windows PowerShell for the current session:

```powershell
$env:KIE_API_KEY = "your-kie-api-key"
```

You can also enter the key in the node. Values entered in a node are stored in
the workflow JSON and may be exposed when the workflow is shared. When both are
present, `KIE_API_KEY` takes precedence.

### Node controls

| Input | Description |
| --- | --- |
| `image_1` | Required first reference image. |
| `image_2`–`image_14` | Optional additional reference images. IMAGE batches are expanded in order. |
| `prompt` | Edit instruction, 3–3000 characters. |
| `aspect_ratio` | Kie-supported output aspect ratio. |
| `quality` | `basic` (2K), `high` (3K), or `ultra` (4K). |
| `output_format` | PNG or JPEG result request. |
| `nsfw_checker` | Enables Kie's content checker. |
| `regenerate` | Off: identical inputs can reuse ComfyUI cache. On: every Queue creates a new billable Kie task. |

Input images are uploaded through Kie's official file upload API. PNG is used
when it fits Kie's 10 MB input limit; larger images are converted to a
high-quality JPEG. Uploaded files and generated URLs are temporary, while the
downloaded output remains in the ComfyUI workflow as an IMAGE value.

The ComfyUI console logs the Kie task ID, each polled task state, elapsed time,
and the remote progress percentage when Kie provides one. Seedream may omit a
percentage; in that case the state and elapsed time still confirm activity.

### Development

Run the offline test suite without a Kie API key:

```bash
python -m unittest discover -s tests -t . -v
```

Live API tests are intentionally not run automatically because they consume
Kie credits.

## 中文

ComfyUI-CloudBridge 是一个连接云端 AI 服务的 ComfyUI 自定义节点包。不同供应商和不同操作会显示为独立节点，而不是全部塞进一个供应商选择大节点。

首个版本包含：

- **☁️ Kie.ai · Seedream 5 Lite · Image to Image**
- 最多 14 张输入图片，并可按顺序展开 ComfyUI IMAGE batch
- 自动完成 Kie 文件上传、异步任务轮询和结果下载
- 输出 `IMAGE`、`task_id` 和 JSON 格式的 `result_urls`

### 安装

将仓库克隆到 ComfyUI 的 `custom_nodes` 目录，并使用 ComfyUI 自己的 Python 环境安装依赖：

```bash
cd /path/to/ComfyUI/custom_nodes
git clone git@github.com:loo-y/ComfyUI-CloudBridge.git
cd ComfyUI-CloudBridge
python -m pip install -r requirements.txt
```

重启 ComfyUI 后，可在 `CloudBridge → Kie.ai` 分类中找到节点，也可以搜索 `Seedream 5 Lite`。

### API Key

推荐使用环境变量 `KIE_API_KEY`：

```powershell
$env:KIE_API_KEY = "你的-Kie-API-Key"
```

也可以直接在节点中填写，但节点输入会保存在工作流 JSON 中，分享工作流时可能泄露。两者同时存在时，环境变量优先。

### 使用说明

| 输入 | 说明 |
| --- | --- |
| `image_1` | 必填的第一张参考图。 |
| `image_2`–`image_14` | 可选参考图；IMAGE batch 会按顺序展开。 |
| `prompt` | 3–3000 字符的编辑指令。 |
| `aspect_ratio` | Kie 支持的输出比例。 |
| `quality` | `basic`（2K）、`high`（3K）或 `ultra`（4K）。 |
| `output_format` | 请求 PNG 或 JPEG 结果。 |
| `nsfw_checker` | 是否启用 Kie 内容检查。 |
| `regenerate` | 关闭时相同输入可复用缓存；打开后每次 Queue 都会新建可能扣费的 Kie 任务。 |

输入图片会通过 Kie 官方上传接口发送。10 MB 以内优先使用无损 PNG，超过后自动转换为高质量 JPEG。上传文件和远程结果链接都是临时资源，下载后的结果则作为 ComfyUI IMAGE 继续在工作流中使用。

ComfyUI 控制台会显示 Kie 任务 ID、每次查询得到的任务状态、已等待时间，以及 Kie 返回进度时的百分比。Seedream 可能不返回百分比，此时仍会持续显示状态和耗时。

### 开发测试

无需 Kie API Key 即可运行离线测试：

```bash
python -m unittest discover -s tests -t . -v
```

真实 API 测试会消耗 Kie 积分，因此不会自动运行。

## License

[MIT](LICENSE)
