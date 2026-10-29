"""Bounded planar path planning and short-horizon motion extrapolation.

Plans are geometric simulation inputs. Predictions are constant-velocity fits,
not observations, calibrated uncertainty intervals or physical safety proofs.
"""
from __future__ import annotations
from copy import deepcopy
import heapq
import math
from .scene_edit import validate_document, stage_size
from .curves import Path


def number(value, name, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result) or low is not None and result < low or high is not None and result > high:
        raise ValueError(f"{name} is outside its supported range")
    return result


def xy(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be an X/Y pair")
    return [number(v, name, -10000, 10000) for v in value]


def segment_clear(a, b, obstacles):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    for x, y, radius in obstacles:
        fraction = max(0., min(1., ((x-a[0])*dx+(y-a[1])*dy)/length2)) if length2 else 0.
        distance2 = (a[0]+fraction*dx-x)**2 + (a[1]+fraction*dy-y)**2
        if distance2 <= radius * radius:
            return False
    return True


def _simplify(points, obstacles):
    result, index = [points[0]], 0
    while index < len(points)-1:
        target = len(points)-1
        while target > index+1 and not segment_clear(points[index], points[target], obstacles):
            target -= 1
        result.append(points[target]); index = target
    return result


def plan_object_path(scene, object_id, goal, *, resolution_m=.5, clearance_m=.1,
                     smooth=True, maximum_expansions=20000):
    document = validate_document(scene)
    stage, objects = document['stage_metres'], document['objects']
    selected = next((o for o in objects if o.get('id', o.get('object_id')) == object_id), None)
    if selected is None:
        raise ValueError('object_id is not in this scene')
    if not selected['waypoints']:
        raise ValueError('place the object before planning')
    if selected.get('category') == 'shelf' or number(selected.get('speed', 0), 'speed', 0, 8) <= 0:
        raise ValueError('planning requires a moving object with a positive speed')
    step = number(resolution_m, 'resolution_m', .25, 2)
    clearance = number(clearance_m, 'clearance_m', 0, 2)
    if not isinstance(smooth, bool):
        raise ValueError('smooth must be boolean')
    if isinstance(maximum_expansions, bool) or not isinstance(maximum_expansions, int) or not 1 <= maximum_expansions <= 40000:
        raise ValueError('invalid planning work budget')
    radius = number(selected.get('radius', .5), 'radius', 0, 10)
    start, goal = selected['waypoints'][0], xy(goal, 'goal')
    low, high = [radius, radius], [stage[0]-radius, stage[1]-radius]
    def inside(p): return all(low[a] <= p[a] <= high[a] for a in (0, 1))
    if not inside(start) or not inside(goal):
        raise ValueError('start and goal must fit the floor including the object radius')
    obstacles = []
    moving_others = 0
    for obj in objects:
        if obj is selected or not obj['waypoints']:
            continue
        static = len(obj['waypoints']) == 1 or obj.get('speed', 0) == 0
        if static:
            point = obj['waypoints'][0]
            obstacles.append((point[0], point[1], radius + obj.get('radius', .5) + clearance))
        else:
            moving_others += 1
    if not segment_clear(start, start, obstacles) or not segment_clear(goal, goal, obstacles):
        raise ValueError('start or goal overlaps an inflated static obstacle')
    expansions = 0
    if start == goal:
        points = [list(start)]
    elif segment_clear(start, goal, obstacles):
        points = [list(start), list(goal)]
    else:
        axes = []
        for a in (0, 1):
            count = math.floor((high[a]-low[a])/step)
            axis = [low[a]+i*step for i in range(count+1)]
            if axis[-1] < high[a]-1e-9: axis.append(high[a])
            axes.append(axis)
        if len(axes[0])*len(axes[1]) > 60000:
            raise ValueError('planning grid exceeds the work budget; use a coarser resolution')
        begin, end = (-1, -1), (-2, -2)
        def point(key):
            return start if key == begin else goal if key == end else [axes[0][key[0]], axes[1][key[1]]]
        def neighbours(key):
            p = point(key)
            if key == begin:
                ix, iy = (min(range(len(axes[a])), key=lambda i: abs(axes[a][i]-start[a])) for a in (0, 1))
                candidates = [(x, y) for x in range(max(0, ix-1), min(len(axes[0]), ix+2))
                              for y in range(max(0, iy-1), min(len(axes[1]), iy+2))]
            else:
                candidates = [(key[0]+dx, key[1]+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                              if (dx or dy) and 0 <= key[0]+dx < len(axes[0]) and 0 <= key[1]+dy < len(axes[1])]
                if math.dist(p, goal) <= step*1.5: candidates.append(end)
            return [(target, math.dist(p, point(target))) for target in candidates
                    if segment_clear(p, point(target), obstacles)]
        queue = [(math.dist(start, goal), 0., begin)]
        costs, parents = {begin: 0.}, {}
        reached = False
        while queue:
            _, cost, key = heapq.heappop(queue)
            if cost != costs[key]: continue
            if key == end: reached = True; break
            expansions += 1
            if expansions > maximum_expansions:
                raise ValueError('planning expansion budget exceeded; no path was applied')
            for target, distance in neighbours(key):
                candidate = cost + distance
                if candidate < costs.get(target, math.inf):
                    costs[target], parents[target] = candidate, key
                    heapq.heappush(queue, (candidate+math.dist(point(target), goal), candidate, target))
        if not reached:
            raise ValueError('no path found at this grid resolution')
        reverse, key = [goal], end
        while key != begin:
            key = parents[key]; reverse.append(point(key))
        points = _simplify(list(reversed(reverse)), obstacles)
    if len(points) > 24:
        raise ValueError('route exceeds the scene waypoint budget')
    curve, warnings = 'straight', []
    if smooth and len(points) >= 3:
        samples = [[p.x, p.y] for p in Path(points, 'smooth', False).points]
        if all(inside(p) for p in samples) and all(segment_clear(a, b, obstacles) for a, b in zip(samples, samples[1:])):
            curve = 'smooth'
        else:
            warnings.append('Smooth interpolation cut the allowed corridor; validated straight segments were retained.')
    selected['waypoints'], selected['curve'], selected['mode'] = points, curve, 'stop'
    selected['path_source'] = 'DETERMINISTIC_PLAN'
    warnings.append('Only static disk obstacles are reserved. This is not collision avoidance for other moving actors or physical safety validation.')
    return {'scene': document, 'object_id': object_id, 'algorithm': 'astar_static_disks',
            'source': 'DETERMINISTIC_PLAN', 'expansions': expansions, 'static_obstacles': len(obstacles),
            'unreserved_moving_actors': moving_others, 'clearance_m': clearance, 'warnings': warnings}


def predict_track(points, *, horizon_s=3., step_s=.25, space='world', stage_metres=None,
                  radius=0., maximum_speed=100.):
    """Fit the latest 20 observations in centred time; no future points are read."""
    horizon = number(horizon_s, 'horizon_s', .1, 30)
    step = number(step_s, 'step_s', .05, 5)
    maximum = number(maximum_speed, 'maximum_speed', .01, 1000)
    if space not in ('world', 'pixel'):
        raise ValueError('space must be world or pixel')
    if not isinstance(points, list) or not 3 <= len(points) <= 5000:
        raise ValueError('prediction requires 3..5000 timestamped observations')
    clean, last = [], -math.inf
    for row in points:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError('observations must be [time_seconds, x, y]')
        t, x, y = [number(v, 'observation', -1e15, 1e15) for v in row]
        if t <= last: raise ValueError('observation times must be strictly increasing')
        last = t; clean.append((t, x, y))
    clean = clean[-20:]
    cutoff = clean[-1][0]
    times = [row[0]-cutoff for row in clean]
    if times[-1]-times[0] < .05:
        raise ValueError('observation time span is too short')
    mean = sum(times)/len(times)
    denominator = sum((t-mean)**2 for t in times)
    velocities, intercepts = [], []
    for axis in (1, 2):
        centre = sum(row[axis] for row in clean)/len(clean)
        velocity = sum((t-mean)*(row[axis]-centre) for t, row in zip(times, clean))/denominator
        velocities.append(velocity); intercepts.append(centre-velocity*mean)
    speed = math.hypot(*velocities)
    if speed > maximum:
        raise ValueError('fitted speed exceeds the configured limit; check units and timestamps')
    residual = math.sqrt(sum(sum((row[a+1]-(intercepts[a]+velocities[a]*t))**2 for a in (0,1))
                             for t, row in zip(times, clean))/len(clean))
    count = math.ceil(horizon/step)
    if count > 300: raise ValueError('prediction exceeds the sample budget')
    # Anchor at the last actual observation: the displayed trajectory never jumps
    # from the object to the fitted intercept at the handoff.
    origin = [clean[-1][1], clean[-1][2]]
    offsets = [min(horizon, i*step) for i in range(count+1)]
    predicted = [[cutoff+t, origin[0]+velocities[0]*t, origin[1]+velocities[1]*t] for t in offsets]
    staged, boundary_time = None, None
    if stage_metres is not None:
        if space != 'world': raise ValueError('pixel predictions cannot be placed on a metre-space floor without calibration')
        stage = stage_size(stage_metres); r = number(radius, 'radius', 0, min(stage)/2)
        if any(not r <= origin[a] <= stage[a]-r for a in (0,1)):
            raise ValueError('last observation is outside the floor')
        hits = [(stage[a]-r-origin[a])/velocities[a] if velocities[a] > 0
                else (r-origin[a])/velocities[a] for a in (0,1) if velocities[a] != 0]
        boundary_time = min([horizon]+hits)
        staged = [[cutoff+t, origin[0]+velocities[0]*min(t,boundary_time),
                   origin[1]+velocities[1]*min(t,boundary_time)] for t in offsets]
    return {'algorithm': 'constant_velocity_least_squares', 'source': 'PREDICTED', 'time_unit': 'seconds',
            'space': space, 'fit_observations': len(clean), 'input_cutoff': cutoff,
            'velocity': velocities, 'fit_rmse': residual, 'points': predicted, 'staged_points': staged,
            'boundary_hold_after_s': boundary_time if boundary_time is not None and boundary_time < horizon else None,
            'warnings': ['Constant velocity can fail under turns, occlusion or acceleration. Fit RMSE is not a calibrated prediction interval.',
                         'A staged boundary hold is a display constraint, not predicted braking.']}
