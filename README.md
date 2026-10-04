# residential-cad-skill · V1.0.1

把住宅手绘测绘图整理成可在 LibreCAD 编辑的真实矢量 DXF，并同步生成 PDF、PNG。AI负责看图和提问，固定 Python 脚本负责绘图；不含自动OCR、模型调用、网页、数据库或云服务。

适合有实测尺寸的住宅平面测绘图，保留不规则外轮廓和错位墙体。第一版只做平面图，不含地砖、卫生间和厨房墙面深化。它是测绘整理工具，不能替代现场复测或专业施工设计审核。

V1.0.1 仅修复90°端点转角的厚墙轮廓连接；T形连接保持连续，不吸附或移动墙中心线。JSON数据格式版本仍为 `"1.0"`，原有数据可直接使用。

## 文件结构

```text
residential-cad-skill/
├─ README.md
├─ SKILL.md
├─ requirements.txt
├─ .gitignore
├─ scripts/
│  ├─ generate_drawing.py
│  └─ validate_drawing.py
├─ templates/
│  └─ drawing_spec.example.json
└─ examples/
   └─ README.md
```

## 安装

1. 安装 Python 3.10 或以上版本。Windows 安装时勾选“Add Python to PATH”。在终端运行 `python --version` 检查安装结果。
2. 下载本项目，在 `residential-cad-skill` 文件夹打开终端。Windows 可在文件夹地址栏输入 `powershell` 后回车。
3. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

   若 pip 对应的 Python 不一致，可用 `python -m pip install -r requirements.txt`。
4. 电脑需要中文字体。Windows 常见的微软雅黑、黑体通常可自动识别；Linux可安装 Noto Sans CJK，macOS可使用支持中文的字体文件。字体不随项目分发，脚本不会自动联网下载。

## 使用流程

1. 把原始手绘图和 `SKILL.md` 交给AI，同时提供本项目文件（Work可使用整个项目；普通聊天可上传SKILL、JSON模板和两个脚本）。要求AI先阅读SKILL。
2. AI整理 `drawing_spec.json`，无法确定的数据填 `null`、列出必要问题，并暂停。墙厚、门位、开门方向都不能靠猜。
3. 你确认尺寸和连接关系后，AI把 `confirmed` 改为 `true`，并清空 `unconfirmed_dimensions`。
4. 将确认后的 `drawing_spec.json` 放到项目根目录，运行：

   ```bash
   python scripts/validate_drawing.py drawing_spec.json
   python scripts/generate_drawing.py drawing_spec.json
   ```

5. 查看 `output` 文件夹中的：

   ```text
   住宅测绘平面图.dxf
   住宅测绘平面图.pdf
   住宅测绘平面图.png
   drawing_spec.json
   ```

生成命令本身也会校验，不必担心忘记先运行校验器。错误返回退出码1，成功返回0。重复使用同一输出目录会覆盖同名文件；不同住宅可指定 `--output output/住宅A`。

普通聊天如果不能运行Python，就下载JSON后在自己电脑运行以上命令。把文件上传给聊天并不等于永久安装Skill；每次新聊天重新提供SKILL即可。Work需要能读取项目文件、执行Python的环境。

标准调用：

```text
执行住宅CAD快速出图 Skill。

根据我上传的手绘住宅测绘图提取墙体、房间、门洞和尺寸。

先生成结构化 drawing_spec。
无法确认的尺寸不要猜，只询问必要问题。

我确认后，再生成可由 LibreCAD 编辑的 DXF，并同时输出 PDF 和 PNG。
```

## 先试一次示例

```bash
python scripts/validate_drawing.py templates/drawing_spec.example.json
python scripts/generate_drawing.py templates/drawing_spec.example.json --output output/example
```

示例为虚构两房空间，不是默认户型。更多说明见 `examples/README.md`。

## 如何填写 drawing_spec.json

复制模板后修改，或让AI严格按模板生成。JSON不能写注释；长度统一mm，坐标格式 `[x, y]`，x向右、y向上。原点可以任选，但全图必须一致。

| 字段 | 含义 |
| --- | --- |
| `version` / `unit` | 固定 `"1.0"` / `"mm"` |
| `title` | 图纸标题；输出文件名统一为住宅测绘平面图 |
| `coordinate_reference` | 固定 `"wall_centerline"`，墙坐标是中心线 |
| `confirmed` | 真实数据得到用户确认后才设为 `true` |
| `walls` | 每段含唯一 `id`、`start`、`end`、实测 `thickness`、`kind`（`exterior`外墙或`interior`内墙） |
| `rooms` | `name`、`label_position` 和 `dimensions`（至少一条已确认尺寸） |
| `doors` | 唯一 `id`、`wall_id`、`offset`、`width`、`hinge`、`swing_side` |
| `columns` | `origin`左下角、`width`横宽、`depth`纵深；无柱填 `[]` |
| `overall_dimensions` | 至少一条主要整体尺寸 |
| `unconfirmed_dimensions` | 未确认对象/尺寸/问题列表；全部确认后填 `[]` |

**墙坐标基准：**模板墙坐标是中心线，不是净墙面。若手绘标的是房间净宽，必须结合已确认墙厚换算中心线位置；不能直接把净宽当中心线间距。长墙可拆为相接短段，不能重复描述同一段墙。不支持用墙厚为0代替未知墙厚。

**门的定位：**沿对应墙 `start → end`，`offset` 是墙起点到门洞起点的距离；`width` 是洞宽。`hinge=start/end` 表示门洞起端/末端铰链。`swing_side=left/right` 是沿墙方向看的左/右侧，例如沿x正方向的墙，left是y正方向，right是y负方向。第一版单扇门统一开启90°，门叶绘在开启位置并附弧线。门洞需要避开其他墙/柱，不要跨越墙交点；在交点处拆段并核实。

**尺寸的填写：**房间和整体尺寸采用相同结构：

```json
{
  "start": [100, 3200],
  "end": [3050, 3200],
  "value": 2950,
  "offset": -300,
  "source": "用户明确标注的净宽"
}
```

端点必须对应实际测量基准；`value`为两点距离。`offset`是尺寸线相对端点连线的偏移，正值沿左法线，负值沿右法线。上述水平向右尺寸的负值向下偏移。调整offset只改变标注位置，不改变测量值。推导尺寸的source应写已知值和公式，例如“总跨度6000减两段2000、1500 = 2500，均为同一外边线基准”。

不能确定时：把相应值写 `null`，令 `confirmed=false`，并例如填：

```json
"unconfirmed_dimensions": [
  {"object": "W2", "field": "thickness", "question": "这段墙的实测厚度是多少mm？"}
]
```

校验器检查缺项、非有限坐标、墙长墙厚、门宽、门范围、同墙门洞重叠、门洞与其他墙柱相交、重叠共线墙、柱尺寸、尺寸端点与标注值冲突，以及null、unknown、待确认等。数值对比容差0.5mm，只用于检查浮点误差，**不会吸附、移动或修补坐标**。它不能判断AI是否读对房间连接关系，也不能代替所有复杂节点的人工复核。

## 图纸与 LibreCAD

在LibreCAD使用“文件 → 打开”，选择生成的DXF。DXF为R2000版本，模型单位mm、1:1，包含可编辑的线、闭合多段线、圆弧和文字。尺寸是可编辑线与文字，不是关联式尺寸对象。

| 图层 | 线宽mm | 用途 |
| --- | --- | --- |
| WALL | 0.50 | 厚墙轮廓 |
| DOOR | 0.30 | 门叶与开启弧 |
| COLUMN | 0.35 | 柱轮廓 |
| DIM | 0.13 | 尺寸线、引线、尺寸文字 |
| TEXT | 0.18 | 房间名称和标题 |
| AUX | 0.09 | 预留辅助线 |

启用线宽显示/打印预览可看出层级。PDF为矢量图，自动选A4/A3/A2、横竖方向和标准比例，页脚注明比例，按100%打印才对应该比例；PNG仅用于预览。PDF与DXF读取相同几何数据。各墙段厚度保留，输出墙轮廓统一使用WALL线宽。

## 常见问题

- **提示未确认尺寸：**先回答必要问题并核对数据，不能把null改成随意数值。真实图纸未确认前不能改confirmed为true。
- **尺寸冲突：**检查坐标基准和尺寸链，回到原图或询问用户，不要为了闭合强改测量值。
- **中文乱码或方框：**PDF/PNG找不到适用字体时脚本会停止，可运行 `python scripts/generate_drawing.py drawing_spec.json --font "C:\Windows\Fonts\msyh.ttc"`。LibreCAD字体系统可能与Matplotlib不同；如DXF中文不显示，在LibreCAD选择支持中文的字体，或安装对应字体后再开图。项目保留Unicode文字，不以图片替代。
- **文字碰墙：**修改房间label_position或尺寸offset后再运行；不要移动墙体改善排版。
- **不规则户型：**按实际端点填写斜墙/凹凸墙，不要转成矩形。多段共线墙要避免重叠。
- **窗户、双扇门或斜柱：**V1.0.1不支持这些对象，不能悄悄删除原图结构，先询问处理范围，后续版本再扩展。
- **没有门或柱：**显式填空数组，表示已确认没有，不表示不知道。
- **DXF没经过LibreCAD本机测试：**脚本使用基础DXF实体提高兼容性；首次在你的LibreCAD版本打开后复核字体、门弧和打印设置。

## 上传 GitHub

创建空仓库 `residential-cad-skill`，上传本目录内全部8个项目文件，保留scripts、templates、examples的目录结构，使README.md和SKILL.md位于仓库根目录。不要额外套一层同名文件夹。测试输出、真实住宅JSON和Python缓存不需上传，已在.gitignore排除。
