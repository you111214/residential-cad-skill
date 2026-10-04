# 示例 · V1.0.1

示例数据位于 `../templates/drawing_spec.example.json`。这是一套虚构的矩形两房空间，只演示格式，与任何用户住宅无关。

在项目根目录运行：

```bash
python scripts/validate_drawing.py templates/drawing_spec.example.json
python scripts/generate_drawing.py templates/drawing_spec.example.json --output output/example
```

会得到 DXF、PDF、PNG 和确认后的 JSON。示例 `confirmed=true` 仅用于脚本演示；处理真实手绘图必须先得到用户确认。

图上6400×4400为外墙外边线跨度；6200×4200为墙中心线跨度；房间一2950为净宽。房间二纵向3600是到柱底边的局部净尺寸，不能当作完整房间长度。由此演示不能混用测量基准。

输出文件默认被 `.gitignore` 排除，避免把真实住宅数据提交到 GitHub。
