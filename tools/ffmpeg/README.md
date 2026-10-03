# 项目本地媒体工具

此目录独立管理 FFmpeg/FFprobe 的 npm 依赖，不改变 Python package 或系统 PATH。
`package-lock.json` 固定依赖与下载完整性；`node_modules/` 不提交。

在仓库根目录安装：

```powershell
npm ci --prefix tools/ffmpeg --ignore-scripts --no-audit --no-fund
```

从 Node 获取实际可执行文件路径并验证：

```javascript
const { spawnSync } = require('node:child_process');
const ffmpeg = require('./tools/ffmpeg/node_modules/@ffmpeg-installer/ffmpeg').path;
const ffprobe = require('./tools/ffmpeg/node_modules/ffprobe-static').path;
for (const exe of [ffmpeg, ffprobe]) {
  const result = spawnSync(exe, ['-version'], { encoding: 'utf8' });
  if (result.error || result.status !== 0) throw result.error || new Error(result.stderr);
  console.log(exe, result.stdout.split(/\r?\n/)[0]);
}
```

HyperFrames 0.8.20 支持以下现有配置。在启动它的 Node 进程中传递
`env: { ...process.env, HYPERFRAMES_FFMPEG_PATH: ffmpeg, HYPERFRAMES_FFPROBE_PATH: ffprobe }`，
即可使用上述绝对路径。不要修改已批准 renderer package 或 FinalRenderRequest。

当前包提供 FFmpeg 2018 build 和 FFprobe 4.0.2；它们不是系统安装的 FFmpeg 9。
版本输出成功只证明工具可执行，最终媒体仍须通过正式 render、decode、Preview 对比和 QA gates。
