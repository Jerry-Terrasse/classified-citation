from shapely import geometry

Rect = tuple[float, float, float, float]
Point = tuple[float, float]

def dot_in_rect(rect: Rect, dot: Point, dis: float = 0.0):
    rect_ext = (rect[0] - dis, rect[1] - dis, rect[2] + dis, rect[3] + dis)
    return geometry.box(*rect_ext).contains(geometry.Point(*dot))

def contains(big_rect: Rect, small_rect: Rect, threshold: float = 0.7):
    # big_rect = [x0, y0, x1, y1]
    # small_rect = [x0, y0, x1, y1]
    overlap = geometry.box(*big_rect).intersection(geometry.box(*small_rect)).area
    ratio = overlap / geometry.box(*small_rect).area
    return ratio >= threshold

def overlap(rect1: Rect, rect2: Rect) -> float:
    # rect = [x0, y0, x1, y1]
    return geometry.box(*rect1).intersection(geometry.box(*rect2)).area

def area(rect: Rect) -> float:
    # rect = [x0, y0, x1, y1]
    return (rect[2] - rect[0]) * (rect[3] - rect[1])
    # return geometry.box(*rect).area # too slow