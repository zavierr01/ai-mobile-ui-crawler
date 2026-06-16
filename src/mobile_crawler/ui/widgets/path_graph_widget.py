"""Path graph widget for OmniParser Sweep mode.

Renders the navigation graph discovered during a sweep crawl:
  - Nodes  = unique screens (identified by screen_signature)
  - Edges  = directed arrows (from_signature -> to_signature, labelled by element tapped)

Data is read from `omni_sweep_edges` and `step_logs` (for thumbnail screenshots).

The widget can be refreshed at any time; during a live crawl the caller should
call refresh(run_id) periodically.
"""

import logging
import math
import os
import sqlite3
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Layout constants
_NODE_W = 160
_NODE_H = 110
_THUMB_H = 64
_H_GAP = 60
_V_GAP = 50
_ARROW_SIZE = 10
_ROOT_COLOR = QColor("#2e7d32")
_NODE_COLOR = QColor("#1565c0")
_NODE_BG = QColor("#1e1e2e")
_NODE_BORDER = QColor("#444466")
_EDGE_COLOR = QColor("#aaaacc")
_TEXT_COLOR = QColor("#e0e0f0")
_LABEL_COLOR = QColor("#ffcc44")


class _ScreenNode(QGraphicsItem):
    """A node representing one unique screen in the path graph."""

    def __init__(
        self,
        signature: str,
        short_label: str,
        thumbnail_path: Optional[str],
        is_root: bool,
        bboxes: Optional[List[Tuple[int, int, int, int]]] = None,
    ):
        super().__init__()
        self.signature = signature
        self.short_label = short_label
        self.is_root = is_root
        self._pixmap: Optional[QPixmap] = None

        if thumbnail_path and os.path.isfile(thumbnail_path):
            raw = QPixmap(thumbnail_path)
            if not raw.isNull():
                scaled = raw.scaledToHeight(_THUMB_H, Qt.TransformationMode.SmoothTransformation)
                if bboxes:
                    # Draw bbox overlays scaled to the thumbnail dimensions.
                    orig_w = raw.width()
                    orig_h = raw.height()
                    thumb_w = scaled.width()
                    thumb_h = scaled.height()
                    from PySide6.QtGui import QPainter as _QP
                    painter = _QP(scaled)
                    painter.setRenderHint(_QP.RenderHint.Antialiasing)
                    for (x1, y1, x2, y2) in bboxes:
                        sx = thumb_w / orig_w if orig_w else 1
                        sy = thumb_h / orig_h if orig_h else 1
                        painter.setPen(QPen(QColor("#4fc3f7"), max(1, int(thumb_w / 80))))
                        painter.setBrush(QBrush(QColor(79, 195, 247, 30)))
                        painter.drawRect(
                            int(x1 * sx), int(y1 * sy),
                            max(1, int((x2 - x1) * sx)), max(1, int((y2 - y1) * sy)),
                        )
                    painter.end()
                self._pixmap = scaled

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setToolTip(signature)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, _NODE_W, _NODE_H)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_color = _ROOT_COLOR if self.is_root else _NODE_BORDER
        if self.isSelected():
            border_color = QColor("#ffaa00")

        painter.setBrush(QBrush(_NODE_BG))
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(0, 0, _NODE_W, _NODE_H, 8, 8)

        y = 4
        if self._pixmap:
            px_x = (_NODE_W - self._pixmap.width()) // 2
            painter.drawPixmap(px_x, y, self._pixmap)
            y += _THUMB_H + 4
        else:
            # Placeholder box
            painter.setBrush(QBrush(QColor("#2a2a3e")))
            painter.setPen(QPen(QColor("#444466"), 1))
            painter.drawRect(4, y, _NODE_W - 8, _THUMB_H)
            painter.setPen(QPen(QColor("#666688")))
            painter.setFont(QFont("monospace", 8))
            painter.drawText(
                QRectF(4, y, _NODE_W - 8, _THUMB_H),
                Qt.AlignmentFlag.AlignCenter,
                "No screenshot",
            )
            y += _THUMB_H + 4

        painter.setPen(QPen(_TEXT_COLOR))
        painter.setFont(QFont("monospace", 7, QFont.Weight.Bold if self.is_root else QFont.Weight.Normal))
        painter.drawText(
            QRectF(4, y, _NODE_W - 8, _NODE_H - y - 4),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self.short_label,
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().update()
        return super().itemChange(change, value)


class PathGraphScene(QGraphicsScene):
    """Scene that owns the node/edge items and can redraw edges on update."""

    def __init__(self):
        super().__init__()
        # Each edge: (src_node, dst_node, label, bbox_pixmap_or_None)
        self._edges: List[Tuple[_ScreenNode, _ScreenNode, str, Optional[QPixmap]]] = []

    def set_edges(self, edges: List[Tuple[_ScreenNode, _ScreenNode, str, Optional[QPixmap]]]) -> None:
        self._edges = edges
        self.update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor("#12121e"))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Count parallel edges (same src+dst pair) to offset them.
        pair_counts: Dict[tuple, int] = {}
        pair_index: Dict[int, int] = {}
        for i, (src, dst, label, _) in enumerate(self._edges):
            key = (id(src), id(dst))
            pair_index[i] = pair_counts.get(key, 0)
            pair_counts[key] = pair_counts.get(key, 0) + 1
        for i, (src_node, dst_node, label, bbox_thumb) in enumerate(self._edges):
            key = (id(src_node), id(dst_node))
            self._draw_edge(painter, src_node, dst_node, label, bbox_thumb,
                            offset_index=pair_index[i], total=pair_counts[key])

    def _draw_edge(
        self,
        painter: QPainter,
        src: _ScreenNode,
        dst: _ScreenNode,
        label: str,
        bbox_thumb: Optional[QPixmap],
        offset_index: int = 0,
        total: int = 1,
    ) -> None:
        src_center = src.mapToScene(QPointF(_NODE_W / 2, _NODE_H / 2))
        dst_center = dst.mapToScene(QPointF(_NODE_W / 2, _NODE_H / 2))

        src_pt = self._border_point(src_center, dst_center, src)
        dst_pt = self._border_point(dst_center, src_center, dst)

        # Offset parallel edges perpendicularly so they don't overlap.
        if total > 1:
            dx = dst_pt.x() - src_pt.x()
            dy = dst_pt.y() - src_pt.y()
            length = math.hypot(dx, dy) or 1
            perp_x = -dy / length
            perp_y = dx / length
            step = 8
            shift = (offset_index - (total - 1) / 2) * step
            src_pt = QPointF(src_pt.x() + perp_x * shift, src_pt.y() + perp_y * shift)
            dst_pt = QPointF(dst_pt.x() + perp_x * shift, dst_pt.y() + perp_y * shift)

        pen = QPen(_EDGE_COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(src_pt, dst_pt)

        self._draw_arrowhead(painter, src_pt, dst_pt)

        mid = QPointF((src_pt.x() + dst_pt.x()) / 2, (src_pt.y() + dst_pt.y()) / 2)

        # Draw clicked-bbox thumbnail above the midpoint if available.
        if bbox_thumb and not bbox_thumb.isNull():
            tx = int(mid.x() - bbox_thumb.width() / 2)
            ty = int(mid.y() - bbox_thumb.height() - 4)
            painter.drawPixmap(tx, ty, bbox_thumb)
        elif label:
            painter.setPen(QPen(_LABEL_COLOR))
            painter.setFont(QFont("sans-serif", 7))
            short = label[:24] + "…" if len(label) > 24 else label
            painter.drawText(mid + QPointF(4, -4), short)

    def _border_point(
        self, from_center: QPointF, to_center: QPointF, node: _ScreenNode
    ) -> QPointF:
        dx = to_center.x() - from_center.x()
        dy = to_center.y() - from_center.y()
        length = math.hypot(dx, dy) or 1
        dx /= length
        dy /= length

        # Walk from center toward edge
        cx, cy = from_center.x(), from_center.y()
        hw, hh = _NODE_W / 2, _NODE_H / 2
        if abs(dx) < 1e-9:
            t = hh / abs(dy)
        elif abs(dy) < 1e-9:
            t = hw / abs(dx)
        else:
            t = min(hw / abs(dx), hh / abs(dy))

        return QPointF(cx + dx * t, cy + dy * t)

    def _draw_arrowhead(
        self, painter: QPainter, src: QPointF, dst: QPointF
    ) -> None:
        dx = dst.x() - src.x()
        dy = dst.y() - src.y()
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length

        p1 = QPointF(
            dst.x() - _ARROW_SIZE * ux + _ARROW_SIZE * 0.4 * (-uy),
            dst.y() - _ARROW_SIZE * uy + _ARROW_SIZE * 0.4 * ux,
        )
        p2 = QPointF(
            dst.x() - _ARROW_SIZE * ux - _ARROW_SIZE * 0.4 * (-uy),
            dst.y() - _ARROW_SIZE * uy - _ARROW_SIZE * 0.4 * ux,
        )
        painter.setBrush(QBrush(_EDGE_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([dst, p1, p2]))


class PathGraphWidget(QWidget):
    """Full widget: a QGraphicsView containing the path graph, plus a status label."""

    def __init__(self, db_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._current_run_id: Optional[int] = None
        self._nodes: Dict[str, _ScreenNode] = {}

        self._scene = PathGraphScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.wheelEvent = self._wheel_zoom

        self._status = QLabel("No crawl selected — select a run or start an OmniParser Sweep crawl.")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")

        reset_zoom_btn = QPushButton("Reset Zoom")
        reset_zoom_btn.setFixedHeight(26)
        reset_zoom_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        reset_zoom_btn.clicked.connect(self._reset_zoom)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 0)
        toolbar.addStretch()
        toolbar.addWidget(reset_zoom_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._status)

        # Auto-refresh timer for live crawls
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._auto_refresh)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_live_refresh(self, run_id: int) -> None:
        self._current_run_id = run_id
        self._timer.start()
        self.refresh(run_id)

    def stop_live_refresh(self) -> None:
        self._timer.stop()

    def refresh(self, run_id: int) -> None:
        self._current_run_id = run_id
        edges_raw = self._load_edges(run_id)
        thumbnails = self._load_thumbnails(run_id)
        bboxes = self._load_bboxes(run_id)
        self._rebuild(edges_raw, thumbnails, bboxes, run_id)

    def set_db_path(self, db_path: str) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _auto_refresh(self) -> None:
        if self._current_run_id is not None:
            self.refresh(self._current_run_id)

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        if not self._db_path or not os.path.isfile(self._db_path):
            # Try default location
            try:
                from mobile_crawler.config import get_app_data_dir
                default = get_app_data_dir() / "crawler.db"
                if default.is_file():
                    conn = sqlite3.connect(str(default))
                    conn.row_factory = sqlite3.Row
                    return conn
            except Exception:
                pass
            return None
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_edges(self, run_id: int) -> List[Dict]:
        conn = self._get_connection()
        if not conn:
            return []
        try:
            rows = conn.execute(
                "SELECT from_signature, to_signature, group_label, "
                "step_number, from_bbox_json, to_screenshot_path "
                "FROM omni_sweep_edges WHERE run_id=? "
                "ORDER BY step_number",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug(f"PathGraph: failed to load edges: {e}")
            return []
        finally:
            conn.close()

    def _load_thumbnails(self, run_id: int) -> Dict[str, str]:
        """Return {screen_signature -> screenshot path} for all known screens."""
        conn = self._get_connection()
        if not conn:
            return {}
        try:
            result: Dict[str, str] = {}

            # Destination screens: use to_screenshot_path stored on each edge (first arrival wins).
            edge_rows = conn.execute(
                "SELECT to_signature, MIN(to_screenshot_path) AS path "
                "FROM omni_sweep_edges "
                "WHERE run_id=? AND to_screenshot_path IS NOT NULL "
                "GROUP BY to_signature",
                (run_id,),
            ).fetchall()
            for row in edge_rows:
                if row["path"]:
                    result[row["to_signature"]] = row["path"]

            # Source screens: match omni_scan step logs to element_groups order.
            scan_rows = conn.execute(
                "SELECT step_number, screenshot_path FROM step_logs "
                "WHERE run_id=? AND action_type='omni_scan' AND screenshot_path IS NOT NULL "
                "ORDER BY step_number",
                (run_id,),
            ).fetchall()
            sig_rows = conn.execute(
                "SELECT DISTINCT screen_signature FROM element_groups "
                "WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
            for i, sig_row in enumerate(sig_rows):
                sig = sig_row["screen_signature"]
                if sig not in result and i < len(scan_rows) and scan_rows[i]["screenshot_path"]:
                    result[sig] = scan_rows[i]["screenshot_path"]

            return result
        except Exception as e:
            logger.debug(f"PathGraph: failed to load thumbnails: {e}")
            return {}
        finally:
            conn.close()

    def _load_bboxes(self, run_id: int) -> Dict[str, List[Tuple[int, int, int, int]]]:
        """Return {screen_signature -> list of pixel bboxes} from element_groups."""
        conn = self._get_connection()
        if not conn:
            return {}
        try:
            import json as _json
            rows = conn.execute(
                "SELECT screen_signature, bbox_json FROM element_groups WHERE run_id=?",
                (run_id,),
            ).fetchall()
            result: Dict[str, List[Tuple[int, int, int, int]]] = {}
            for row in rows:
                try:
                    d = _json.loads(row["bbox_json"])
                    tl = d["top_left"]
                    br = d["bottom_right"]
                    bbox = (int(tl[0]), int(tl[1]), int(br[0]), int(br[1]))
                    result.setdefault(row["screen_signature"], []).append(bbox)
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.debug(f"PathGraph: failed to load bboxes: {e}")
            return {}
        finally:
            conn.close()

    def _rebuild(
        self,
        edges_raw: List[Dict],
        thumbnails: Dict[str, str],
        bboxes: Dict[str, List[Tuple[int, int, int, int]]],
        run_id: int,
    ) -> None:
        if not edges_raw:
            self._scene.clear()
            self._nodes.clear()
            self._scene.set_edges([])
            self._status.setText(
                f"Run #{run_id}: no navigation edges recorded yet "
                "(only available in OmniParser Sweep mode)."
            )
            return

        # Collect all unique signatures preserving order of appearance.
        seen: Dict[str, int] = {}
        for row in edges_raw:
            seen.setdefault(row["from_signature"], len(seen))
            seen.setdefault(row["to_signature"], len(seen))

        # Determine root (first from_signature ever seen).
        root_sig = edges_raw[0]["from_signature"]

        # BFS-level assignment for layout.
        levels: Dict[str, int] = {root_sig: 0}
        queue = [root_sig]
        adj: Dict[str, List[str]] = {s: [] for s in seen}
        for row in edges_raw:
            adj[row["from_signature"]].append(row["to_signature"])
        head = 0
        while head < len(queue):
            sig = queue[head]
            head += 1
            for nb in adj.get(sig, []):
                if nb not in levels:
                    levels[nb] = levels[sig] + 1
                    queue.append(nb)
        # Anything unreachable from root gets level = max + 1
        max_level = max(levels.values(), default=0)
        for sig in seen:
            if sig not in levels:
                levels[sig] = max_level + 1

        # Group by level, assign column positions.
        level_counts: Dict[int, int] = {}
        level_index: Dict[str, int] = {}
        for sig in sorted(seen, key=lambda s: (levels.get(s, 0), seen[s])):
            lv = levels.get(sig, 0)
            level_index[sig] = level_counts.get(lv, 0)
            level_counts[lv] = level_counts.get(lv, 0) + 1

        # Build positions: columns = levels (x), rows within level (y).
        positions: Dict[str, QPointF] = {}
        for sig in seen:
            lv = levels.get(sig, 0)
            col_idx = level_index[sig]
            total_in_level = level_counts.get(lv, 1)
            x = lv * (_NODE_W + _H_GAP)
            y = (col_idx - (total_in_level - 1) / 2) * (_NODE_H + _V_GAP)
            positions[sig] = QPointF(x, y)

        # Only rebuild nodes if signatures changed.
        new_sigs = set(seen)
        old_sigs = set(self._nodes)

        # Remove stale nodes.
        for sig in old_sigs - new_sigs:
            node = self._nodes.pop(sig)
            self._scene.removeItem(node)

        # Add new nodes.
        for sig in new_sigs - old_sigs:
            is_root = sig == root_sig
            short = self._shorten_signature(sig)
            thumb = thumbnails.get(sig)
            node = _ScreenNode(sig, short, thumb, is_root, bboxes.get(sig))
            node.setPos(positions[sig])
            self._scene.addItem(node)
            self._nodes[sig] = node

        # Reposition existing nodes (only if not moved by user — approximate check).
        for sig, node in self._nodes.items():
            if sig in positions:
                target = positions[sig]
                cur = node.pos()
                # Only auto-position if very close to a grid position or newly added.
                if abs(cur.x() - target.x()) < 2 and abs(cur.y() - target.y()) < 2:
                    node.setPos(target)

        # Build edge list.
        edge_items = []
        for row in edges_raw:
            src = self._nodes.get(row["from_signature"])
            dst = self._nodes.get(row["to_signature"])
            if src and dst and src is not dst:
                bbox_thumb = self._make_bbox_thumb(
                    thumbnails.get(row["from_signature"]),
                    row.get("from_bbox_json"),
                )
                edge_items.append((src, dst, row.get("group_label") or "", bbox_thumb))

        self._scene.set_edges(edge_items)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        n_nodes = len(self._nodes)
        n_edges = len(edges_raw)
        self._status.setText(
            f"Run #{run_id} — {n_nodes} screen(s), {n_edges} navigation edge(s)  "
            "· Scroll to zoom · Drag nodes to rearrange"
        )

    @staticmethod
    def _shorten_signature(sig: str) -> str:
        parts = sig.split("/")
        if len(parts) >= 2:
            activity = parts[1].split(".")[-1] if "." in parts[1] else parts[1]
            suffix = parts[2][:8] if len(parts) > 2 else ""
            return f"{activity}_\n{suffix}" if suffix else f"{activity}"
        return sig[:20]

    @staticmethod
    def _make_bbox_thumb(
        screenshot_path: Optional[str],
        bbox_json: Optional[str],
        thumb_h: int = 36,
    ) -> Optional[QPixmap]:
        """Crop the clicked bbox from the source screenshot and return a small pixmap."""
        if not screenshot_path or not bbox_json or not os.path.isfile(screenshot_path):
            return None
        try:
            import json as _json
            coords = _json.loads(bbox_json)
            x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
            if x2 <= x1 or y2 <= y1:
                return None
            raw = QPixmap(screenshot_path)
            if raw.isNull():
                return None
            # Add padding around the bbox for context.
            pad = 8
            crop = raw.copy(max(0, x1 - pad), max(0, y1 - pad), (x2 - x1) + pad * 2, (y2 - y1) + pad * 2)
            if crop.isNull():
                return None
            scaled = crop.scaledToHeight(thumb_h, Qt.TransformationMode.SmoothTransformation)
            # Draw a highlight border on the cropped region.
            from PySide6.QtGui import QPainter as _QP
            painter = _QP(scaled)
            painter.setPen(QPen(QColor("#ff5722"), 2))
            painter.drawRect(pad, pad, int((x2 - x1) * thumb_h / max(1, y2 - y1 + pad * 2)), thumb_h - pad * 2)
            painter.end()
            return scaled
        except Exception:
            return None

    def _reset_zoom(self) -> None:
        self._view.resetTransform()
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _wheel_zoom(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._view.scale(factor, factor)
