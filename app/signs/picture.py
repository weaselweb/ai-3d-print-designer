"""Trace an uploaded image into extrudable shapes for signs. Works well on
simple, high-contrast cartoon/clip-art style images with clear subjects/colour
blocks -- not photos. Two modes:

- Single-colour silhouette: one outline of the whole subject.
- Multi-colour: colour-clusters the image and traces each non-background
  colour region separately, each paired with its own detected colour.

Either way, only outer silhouettes are followed -- internal details/holes
(like an eye) are not punched out.
"""
from __future__ import annotations

import cadquery as cq
import cv2
import numpy as np


class PictureTraceError(RuntimeError):
    pass


def _contours_from_mask(mask: np.ndarray, min_area_frac: float) -> list[list[tuple[float, float]]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape
    min_area = min_area_frac * w * h
    polygons = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            continue
        eps = 0.01 * cv2.arcLength(c, True)
        simplified = cv2.approxPolyDP(c, eps, True)
        if len(simplified) >= 3:
            polygons.append([(float(pt[0][0]), float(pt[0][1])) for pt in simplified])
    return polygons


def _decode(image_bytes: bytes, flag: int):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, flag)
    if img is None:
        raise PictureTraceError("Could not read that image file.")
    return img


def _trace_polygons(image_bytes: bytes, min_area_frac: float = 0.002) -> list[list[tuple[float, float]]]:
    img = _decode(image_bytes, cv2.IMREAD_GRAYSCALE)
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if np.count_nonzero(binary) > binary.size / 2:
        binary = cv2.bitwise_not(binary)
    polygons = _contours_from_mask(binary, min_area_frac)
    if not polygons:
        raise PictureTraceError("No shape found in that image -- try one with a clearer subject.")
    return polygons


def _rgb_to_hex(rgb) -> str:
    r, g, b = (int(max(0, min(255, c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _trace_multicolor(
    image_bytes: bytes, max_colors: int = 6, min_area_frac: float = 0.004
) -> list[tuple[list[list[tuple[float, float]]], str]]:
    cv2.setRNGSeed(42)  # kmeans init is otherwise randomized -- keep repeat traces of the same image stable
    img = _decode(image_bytes, cv2.IMREAD_COLOR)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    samples = img_rgb.reshape(-1, 3).astype(np.float32)
    k = max(2, min(max_colors, 8))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(samples, k, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    labels = labels.reshape(h, w)

    corners = [int(labels[0, 0]), int(labels[0, w - 1]), int(labels[h - 1, 0]), int(labels[h - 1, w - 1])]
    background_label = max(set(corners), key=corners.count)

    kernel = np.ones((3, 3), np.uint8)
    results = []
    for cluster_id in range(k):
        if cluster_id == background_label:
            continue
        mask = np.where(labels == cluster_id, 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        polygons = _contours_from_mask(mask, min_area_frac)
        if polygons:
            results.append((polygons, _rgb_to_hex(centers[cluster_id])))

    if not results:
        raise PictureTraceError(
            "No distinct colour regions found -- try an image with clearer colour blocks."
        )
    return results


def _polygons_to_solid(
    polygons: list[list[tuple[float, float]]], cx: float, cy: float, scale: float, height: float
) -> cq.Workplane:
    result = None
    for poly in polygons:
        # Image rows increase downward; CAD Y increases upward -- flip Y.
        pts = [((x - cx) * scale, -(y - cy) * scale) for x, y in poly]
        wp = cq.Workplane("XY").moveTo(*pts[0])
        for pt in pts[1:]:
            wp = wp.lineTo(*pt)
        solid = wp.close().extrude(height)
        result = solid if result is None else result.union(solid)
    return result


def build_picture_shape(image_bytes: bytes, size_mm: float, height: float) -> cq.Workplane:
    """Single-colour silhouette, scaled to size_mm on its longest side and
    centred on the origin."""
    polygons = _trace_polygons(image_bytes)
    all_pts = [pt for poly in polygons for pt in poly]
    xs, ys = [pt[0] for pt in all_pts], [pt[1] for pt in all_pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    scale = size_mm / (max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0)
    return _polygons_to_solid(polygons, cx, cy, scale, height)


def build_picture_bodies(
    image_bytes: bytes, size_mm: float, height: float, max_colors: int = 6
) -> list[tuple[cq.Workplane, str]]:
    """Multi-colour version: one solid per detected colour region, all
    consistently scaled/centred together against the combined bounds, each
    paired with its detected hex colour."""
    regions = _trace_multicolor(image_bytes, max_colors=max_colors)
    all_pts = [pt for polygons, _ in regions for poly in polygons for pt in poly]
    xs, ys = [pt[0] for pt in all_pts], [pt[1] for pt in all_pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    scale = size_mm / (max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0)
    return [(_polygons_to_solid(polygons, cx, cy, scale, height), color) for polygons, color in regions]
