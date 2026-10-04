"""V1.0: validate the explicit, millimetre drawing contract; never repair geometry."""
import argparse
import json
import math
import sys
from pathlib import Path

TOL = 0.5  # Numeric comparison tolerance, never a snapping distance.


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def point(v):
    return isinstance(v, list) and len(v) == 2 and all(number(x) for x in v)


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def dimensions(spec):
    yield from spec.get('overall_dimensions', [])
    for room in spec.get('rooms', []):
        yield from room.get('dimensions', [])


def validate(spec):
    errors = []
    if not isinstance(spec, dict):
        return ['JSON 顶层必须是对象。']

    def unresolved(v):
        if v is None:
            return True
        if isinstance(v, str):
            return not v.strip() or any(s in v.lower() for s in ('unknown', '待确认', '未确认', 'tbd', '?'))
        if isinstance(v, list):
            return any(unresolved(x) for x in v)
        if isinstance(v, dict):
            return any(unresolved(x) for x in v.values())
        return False

    if unresolved(spec) or spec.get('unconfirmed_dimensions') != [] or spec.get('confirmed') is not True:
        errors.append('存在未确认尺寸，禁止生成最终图纸。')
    if any(spec.get(k) for k in ('windows', 'furniture')):
        errors.append('V1.0 不支持窗户或家具，请先明确处理范围。')
    if spec.get('unit') != 'mm':
        errors.append('单位必须为 mm。')
    if spec.get('version') != '1.0':
        errors.append('version 必须为 1.0。')
    if not isinstance(spec.get('title'), str) or not spec['title'].strip():
        errors.append('缺少图纸标题。')
    if spec.get('coordinate_reference') != 'wall_centerline':
        errors.append('coordinate_reference 必须为 wall_centerline。')
    for key in ('walls', 'doors', 'columns', 'rooms', 'overall_dimensions', 'unconfirmed_dimensions'):
        if not isinstance(spec.get(key), list):
            errors.append(f'{key} 必须是数组（无对象时填 []）。')
    if errors and any(not isinstance(spec.get(k), list) for k in ('walls', 'doors', 'columns', 'rooms', 'overall_dimensions')):
        return errors
    if not spec['walls'] or not spec['rooms'] or not spec['overall_dimensions']:
        errors.append('至少需要墙段、房间和主要整体尺寸。')
    walls = {}
    for w in spec['walls']:
        if not isinstance(w, dict):
            errors.append('墙段必须是对象。')
            continue
        wid = w.get('id')
        if not isinstance(wid, str) or not wid or wid in walls:
            errors.append('墙段 id 缺失或重复。')
            continue
        if not point(w.get('start')) or not point(w.get('end')):
            errors.append(f'{wid}: 墙段坐标不合法。')
            continue
        if distance(w['start'], w['end']) <= TOL or not number(w.get('thickness')) or w['thickness'] <= 0:
            errors.append(f'{wid}: 墙长或墙厚不合法。')
            continue
        if w.get('kind') not in ('exterior', 'interior'):
            errors.append(f'{wid}: kind 必须为 exterior/interior。')
        walls[wid] = w
    intervals = {}
    ids = set()
    for d in spec['doors']:
        if not isinstance(d, dict):
            errors.append('门必须是对象。')
            continue
        did = d.get('id')
        if not isinstance(did, str) or not did or did in ids:
            errors.append('门 id 缺失或重复。')
        else:
            ids.add(did)
        wall_id = d.get('wall_id')
        w = walls.get(wall_id) if isinstance(wall_id, str) else None
        if w is None:
            errors.append(f'{did}: 对应墙段不存在。')
            continue
        width, offset = d.get('width'), d.get('offset')
        if not number(width) or width <= 0 or not number(offset) or offset < 0:
            errors.append(f'{did}: 门宽必须大于0，offset 必须大于等于0。')
            continue
        end = offset + width
        if end > distance(w['start'], w['end']) + TOL:
            errors.append(f'{did}: 门洞超出对应墙段范围。')
        if d.get('hinge') not in ('start', 'end') or d.get('swing_side') not in ('left', 'right'):
            errors.append(f'{did}: 缺少合法铰链位置或开门方向。')
        for a, b in intervals.setdefault(d['wall_id'], []):
            if min(end, b) - max(offset, a) > TOL:
                errors.append(f'{did}: 门洞与同墙其他门洞重叠。')
        intervals[d['wall_id']].append((offset, end))
    for c in spec['columns']:
        if not isinstance(c, dict) or not point(c.get('origin')) or any(not number(c.get(k)) or c[k] <= 0 for k in ('width', 'depth')):
            errors.append('柱坐标或宽深不合法。')
    for room in spec['rooms']:
        if not isinstance(room, dict):
            errors.append('房间必须是对象。')
            continue
        if not isinstance(room.get('name'), str) or not point(room.get('label_position')):
            errors.append('房间名称或文字位置缺失。')
        if not isinstance(room.get('dimensions'), list) or not room['dimensions']:
            errors.append('房间至少需要一条已确认尺寸。')
    if errors:
        return errors
    for dim in dimensions(spec):
        if not isinstance(dim, dict) or not point(dim.get('start')) or not point(dim.get('end')):
            errors.append('尺寸测量端点缺失或不合法。')
            continue
        value = dim.get('value')
        if not number(value) or value <= 0 or not number(dim.get('offset')) or abs(dim['offset']) <= TOL:
            errors.append('尺寸值必须大于0，尺寸偏移必须为非零数。')
            continue
        if abs(distance(dim['start'], dim['end']) - value) > TOL:
            errors.append(f'明显尺寸冲突：标注 {value}，端点距离 {distance(dim["start"], dim["end"]):.3f}。')
        if not isinstance(dim.get('source'), str):
            errors.append('尺寸缺少 source（测量值或可靠尺寸链说明）。')
    # Do not allow duplicate/overlapping collinear wall descriptions.
    ws = list(walls.values())
    for i, a in enumerate(ws):
        ax, ay = a['start']; bx, by = a['end']
        length = distance(a['start'], a['end']); ux, uy = (bx-ax)/length, (by-ay)/length
        for b in ws[i+1:]:
            projections = []
            for x, y in (b['start'], b['end']):
                if abs((x-ax)*uy - (y-ay)*ux) > TOL:
                    break
                projections.append((x-ax)*ux + (y-ay)*uy)
            if len(projections) == 2 and min(length, max(projections)) - max(0, min(projections)) > TOL:
                errors.append(f'{a["id"]}/{b["id"]}: 同一直线墙段重叠，请拆分或去重。')
    # Opening subtraction must not silently remove another wall or a column.
    if not errors:
        from shapely.geometry import LineString, box
        for d in spec['doors']:
            w = walls[d['wall_id']]
            length = distance(w['start'], w['end'])
            ux = (w['end'][0]-w['start'][0])/length
            uy = (w['end'][1]-w['start'][1])/length
            a = [w['start'][0]+ux*d['offset'], w['start'][1]+uy*d['offset']]
            b = [a[0]+ux*d['width'], a[1]+uy*d['width']]
            cut = LineString([a,b]).buffer(w['thickness']/2, cap_style=2)
            for other in walls.values():
                if other['id'] == w['id']:
                    continue
                shape = LineString([other['start'],other['end']]).buffer(other['thickness']/2, cap_style=2)
                if cut.intersection(shape).area > TOL*TOL:
                    errors.append(f'{d["id"]}: 门洞与其他墙体相交，请复核门位或拆分墙段。')
            for c in spec['columns']:
                x,y = c['origin']
                if cut.intersection(box(x,y,x+c['width'],y+c['depth'])).area > TOL*TOL:
                    errors.append(f'{d["id"]}: 门洞与柱重叠。')
    return errors


def load_spec(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='校验住宅 CAD 数据，失败返回退出码1。')
    parser.add_argument('spec', help='drawing_spec.json 路径')
    args = parser.parse_args()
    try:
        errors = validate(load_spec(args.spec))
    except (OSError, ValueError) as exc:
        errors = [f'无法读取 JSON: {exc}']
    for error in errors:
        print('[ERROR] ' + error)
    if errors:
        return 1
    print('[OK] 数据检查通过，可以生成图纸。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
