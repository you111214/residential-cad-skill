"""V1.0.1: create matching vector DXF and paper previews from confirmed JSON."""
import argparse
import json
import math
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font
from matplotlib.patches import Arc
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from validate_drawing import dimensions, distance, load_spec, validate

WIDTHS = {'WALL': 50, 'DOOR': 30, 'COLUMN': 35, 'DIM': 13, 'TEXT': 18, 'AUX': 9}


def font_for(text, custom=None):
    """Fail explicitly instead of silently exporting missing Chinese glyphs."""
    required = {ord(c) for c in text if not c.isspace()}
    candidates = [custom] if custom else []
    names = ['Microsoft YaHei', 'SimHei', 'SimSun', 'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'PingFang SC', 'Arial Unicode MS']
    for name in names:
        try:
            candidates.append(font_manager.findfont(name, fallback_to_default=False))
        except ValueError:
            pass
    candidates += font_manager.findSystemFonts()
    for path in dict.fromkeys(candidates):
        if not path:
            continue
        try:
            if required.issubset(FT2Font(path).get_charmap()):
                return font_manager.FontProperties(fname=path)
        except (OSError, RuntimeError):
            continue
    raise ValueError('缺少包含图纸文字的字体。请安装中文字体，或用 --font 指定中文 TTF/OTF/TTC 文件。')


def basis(w):
    a, b = w['start'], w['end']
    length = distance(a, b)
    u = ((b[0]-a[0])/length, (b[1]-a[1])/length)
    return u, (-u[1], u[0])


def shift(p, u, amount):
    return (p[0]+u[0]*amount, p[1]+u[1]*amount)


def wall_shape(w):
    return LineString([w['start'], w['end']]).buffer(w['thickness']/2, cap_style=2)


def joined_wall_shape(walls):
    """Fill the outer corner of perpendicular endpoint joins; keep free ends flat."""
    shapes = [wall_shape(w) for w in walls]
    for i, a in enumerate(walls):
        for b in walls[i+1:]:
            for a_end, a_other in ((a['start'], a['end']), (a['end'], a['start'])):
                for b_end, b_other in ((b['start'], b['end']), (b['end'], b['start'])):
                    if a_end != b_end:
                        continue  # No snapping or inference of unconnected walls.
                    p = a_end
                    la, lb = distance(p, a_other), distance(p, b_other)
                    u = ((a_other[0]-p[0])/la, (a_other[1]-p[1])/la)
                    v = ((b_other[0]-p[0])/lb, (b_other[1]-p[1])/lb)
                    if abs(u[0]*v[0] + u[1]*v[1]) > 1e-9:
                        continue  # Preserve existing handling of non-90-degree walls.
                    side = 1 if u[0]*v[1]-u[1]*v[0] > 0 else -1
                    outer_a = shift(p, (-u[1], u[0]), -side*a['thickness']/2)
                    outer_b = shift(p, (-v[1], v[0]), side*b['thickness']/2)
                    corner = (outer_a[0]+outer_b[0]-p[0], outer_a[1]+outer_b[1]-p[1])
                    shapes.append(Polygon([p, outer_a, corner, outer_b]))
    # Interior T/cross junctions are already continuous in the union of flat strips.
    return unary_union(shapes)


def create(spec, output, font_path=None):
    font = font_for(spec['title'] + ''.join(r['name'] for r in spec['rooms']) + '单位比例住宅测绘平面图', font_path)
    doc = ezdxf.new('R2000')
    doc.units = ezdxf.units.MM
    doc.header['$MEASUREMENT'] = 1
    for name, width in WIDTHS.items():
        doc.layers.new(name, dxfattribs={'color': 7, 'lineweight': width})
    doc.styles.new('CJK', dxfattribs={'font': Path(font.get_file()).name})
    msp = doc.modelspace()
    fig, ax = plt.subplots()
    ax.set_aspect('equal'); ax.axis('off')
    bounds = []
    all_points = [p for w in spec['walls'] for p in (w['start'], w['end'])]
    span = max(max(p[i] for p in all_points)-min(p[i] for p in all_points) for i in (0, 1))
    text_height = max(120, span/40)

    def line(a, b, layer):
        msp.add_line(a, b, dxfattribs={'layer': layer})
        ax.plot([a[0], b[0]], [a[1], b[1]], color='black', linewidth=WIDTHS[layer]/100*72/25.4)
        bounds.extend([a, b])

    def poly(points, layer):
        msp.add_lwpolyline(points, close=True, dxfattribs={'layer': layer})
        closed = list(points) + [points[0]]
        ax.plot([p[0] for p in closed], [p[1] for p in closed], color='black', linewidth=WIDTHS[layer]/100*72/25.4)
        bounds.extend(points)

    def label(p, text, height, layer='TEXT', rotation=0):
        msp.add_text(text, dxfattribs={'layer': layer, 'height': height, 'style': 'CJK', 'rotation': rotation}).set_placement(p, align=TextEntityAlignment.MIDDLE_CENTER)
        # Convert model text height to physical points after the viewport is fixed.
        artist = ax.text(*p, text, ha='center', va='center', rotation=rotation, fontproperties=font,
                         bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 1})
        bounds.extend([(p[0]-len(text)*height/2, p[1]-height), (p[0]+len(text)*height/2, p[1]+height)])
        artist._cad_height = height

    walls = {w['id']: w for w in spec['walls']}
    cuts = []
    for d in spec['doors']:
        w = walls[d['wall_id']]; u, n = basis(w)
        a = shift(w['start'], u, d['offset']); b = shift(a, u, d['width'])
        cuts.append(LineString([a, b]).buffer(w['thickness']/2+0.01, cap_style=2))
    wall_geometry = joined_wall_shape(spec['walls'])
    if cuts:
        wall_geometry = wall_geometry.difference(unary_union(cuts))
    polygons = [wall_geometry] if wall_geometry.geom_type == 'Polygon' else list(wall_geometry.geoms)
    for shape in polygons:
        poly(list(shape.exterior.coords)[:-1], 'WALL')
        for ring in shape.interiors:
            poly(list(ring.coords)[:-1], 'WALL')
    for d in spec['doors']:
        w = walls[d['wall_id']]; u, n = basis(w)
        side = 1 if d['swing_side'] == 'left' else -1
        low = shift(w['start'], u, d['offset'])
        hinge_center = low if d['hinge'] == 'start' else shift(low, u, d['width'])
        h = shift(hinge_center, n, side*w['thickness']/2)
        closed_u = u if d['hinge'] == 'start' else (-u[0], -u[1])
        closed = shift(h, closed_u, d['width'])
        opened = shift(h, n, side*d['width'])
        line(h, opened, 'DOOR')
        start_angle = math.degrees(math.atan2(closed_u[1], closed_u[0])) % 360
        end_angle = math.degrees(math.atan2(side*n[1], side*n[0])) % 360
        if (end_angle-start_angle) % 360 > 180:
            start_angle, end_angle = end_angle, start_angle
        msp.add_arc(h, d['width'], start_angle, end_angle, dxfattribs={'layer': 'DOOR'})
        ax.add_patch(Arc(h, 2*d['width'], 2*d['width'], theta1=start_angle, theta2=end_angle,
                         color='black', linewidth=WIDTHS['DOOR']/100*72/25.4))
        # Conservative extent includes arc even for oblique walls.
        bounds.extend([(h[0]-d['width'], h[1]-d['width']), (h[0]+d['width'], h[1]+d['width']), closed])
    for c in spec['columns']:
        x, y = c['origin']; w, h = c['width'], c['depth']
        poly([(x,y), (x+w,y), (x+w,y+h), (x,y+h)], 'COLUMN')
    for room in spec['rooms']:
        label(room['label_position'], room['name'], text_height)
    for d in dimensions(spec):
        a, b = d['start'], d['end']; length = distance(a, b)
        u = ((b[0]-a[0])/length, (b[1]-a[1])/length); n = (-u[1], u[0])
        aa, bb = shift(a, n, d['offset']), shift(b, n, d['offset'])
        line(a, shift(aa, n, math.copysign(text_height/4, d['offset'])), 'DIM')
        line(b, shift(bb, n, math.copysign(text_height/4, d['offset'])), 'DIM')
        line(aa, bb, 'DIM')
        tick = (u[0]+n[0], u[1]+n[1])
        for p in (aa, bb):
            line(shift(p, tick, -text_height/5), shift(p, tick, text_height/5), 'DIM')
        angle = math.degrees(math.atan2(u[1], u[0]))
        if angle > 90 or angle < -90:
            angle += 180
        mid = ((aa[0]+bb[0])/2, (aa[1]+bb[1])/2)
        label(shift(mid, n, text_height*.65), f'{d["value"]:g}', text_height*.75, 'DIM', angle)
    xmin = min(p[0] for p in bounds); xmax = max(p[0] for p in bounds)
    ymin = min(p[1] for p in bounds); ymax = max(p[1] for p in bounds)
    center_x = (xmin+xmax)/2
    label((center_x, ymax+text_height*2.5), spec['title'], text_height*1.4)
    label((center_x, ymin-text_height*2.5), '单位：mm | V1.0.1 | 比例见PDF页脚', text_height*.65)
    xmin = min(p[0] for p in bounds)-text_height; xmax = max(p[0] for p in bounds)+text_height
    ymin = min(p[1] for p in bounds)-text_height; ymax = max(p[1] for p in bounds)+text_height
    horizontal = xmax-xmin >= ymax-ymin
    pages = [(297,210), (420,297), (594,420)] if horizontal else [(210,297), (297,420), (420,594)]
    scale_choices = [20, 25, 50, 75, 100, 150, 200, 250, 500, 1000]
    selected = None
    for paper in pages:
        for scale in scale_choices:
            if (xmax-xmin)/scale <= paper[0]-30 and (ymax-ymin)/scale <= paper[1]-35:
                selected = (paper, scale); break
        if selected and selected[1] <= 100:
            break
    paper, scale = selected or (pages[-1], math.ceil(max((xmax-xmin)/(pages[-1][0]-30), (ymax-ymin)/(pages[-1][1]-35))))
    fig.set_size_inches(paper[0]/25.4, paper[1]/25.4)
    view_w, view_h = (paper[0]-30)*scale, (paper[1]-35)*scale
    cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
    ax.set_position([15/paper[0], 20/paper[1], (paper[0]-30)/paper[0], (paper[1]-35)/paper[1]])
    ax.set_xlim(cx-view_w/2, cx+view_w/2); ax.set_ylim(cy-view_h/2, cy+view_h/2)
    for artist in ax.texts:
        artist.set_fontsize(artist._cad_height/scale*72/25.4)
    fig.text(.5, .025, f'1:{scale}  |  {paper[0]} × {paper[1]} mm  |  PDF按100%打印；DXF模型1:1',
             ha='center', fontsize=8, fontproperties=font)
    output.mkdir(parents=True, exist_ok=True)
    base = output/'住宅测绘平面图'
    doc.set_modelspace_vport(height=view_h, center=(cx, cy))
    doc.saveas(base.with_suffix('.dxf'))
    fig.savefig(base.with_suffix('.pdf'))
    fig.savefig(base.with_suffix('.png'), dpi=200)
    plt.close(fig)
    (output/'drawing_spec.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description='生成住宅 CAD 平面图 V1.0.1')
    parser.add_argument('spec')
    parser.add_argument('--output', default='output', help='输出目录，默认 output')
    parser.add_argument('--font', help='指定支持中文的本地字体文件')
    args = parser.parse_args()
    try:
        spec = load_spec(args.spec)
        errors = validate(spec)
        if errors:
            for error in errors:
                print('[ERROR] '+error)
            return 1
        create(spec, Path(args.output), args.font)
    except (OSError, ValueError, RuntimeError) as exc:
        print('[ERROR] '+str(exc)); return 1
    print('[OK] 已生成 DXF、PDF、PNG 和 drawing_spec.json: '+str(Path(args.output).resolve()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
