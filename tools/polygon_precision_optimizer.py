#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYGON精度优化器
专门解决POLYGON裁剪中的顶点重叠和边重叠导致的0.0重叠问题
"""

import logging
import re
from typing import List, Tuple, Dict, Any

import numpy as np
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree


class PolygonPrecisionOptimizer:
    """POLYGON精度优化器"""
    
    def __init__(self, precision_digits=12, tolerance=1e-12):
        """
        初始化优化器
        
        Args:
            precision_digits: 坐标精度位数
            tolerance: 几何容差
        """
        self.precision_digits = precision_digits
        self.tolerance = tolerance
        self.logger = logging.getLogger(__name__)
    
    def optimize_polygon_wkt(self, wkt_string: str) -> str:
        """
        优化POLYGON的WKT字符串，提高精度和稳定性
        
        Args:
            wkt_string: 原始WKT字符串
            
        Returns:
            str: 优化后的WKT字符串
        """
        try:
            # 提取坐标点
            coords = self._extract_coordinates(wkt_string)
            if not coords:
                return wkt_string
            
            # 优化坐标精度
            optimized_coords = self._optimize_coordinates(coords)
            
            # 移除重复点
            cleaned_coords = self._remove_duplicate_points(optimized_coords)
            
            # 确保多边形闭合
            closed_coords = self._ensure_polygon_closure(cleaned_coords)
            
            # 重构WKT字符串
            optimized_wkt = self._reconstruct_wkt(closed_coords)
            
            return optimized_wkt
            
        except Exception as e:
            self.logger.error(f"WKT优化失败: {e}")
            return wkt_string
    
    def analyze_polygon_overlap(self, wkt1: str, wkt2: str) -> Dict[str, Any]:
        """
        分析两个POLYGON的重叠情况
        
        Args:
            wkt1: 第一个POLYGON的WKT
            wkt2: 第二个POLYGON的WKT
            
        Returns:
            dict: 重叠分析结果
        """
        try:
            coords1 = self._extract_coordinates(wkt1)
            coords2 = self._extract_coordinates(wkt2)
            
            if not coords1 or not coords2:
                return {'error': '坐标提取失败'}
            
            # 分析顶点重叠
            vertex_overlaps = self._detect_vertex_overlaps(coords1, coords2)
            
            # 分析边重叠
            edge_overlaps = self._detect_edge_overlaps(coords1, coords2)
            
            # 计算边界框重叠
            bbox_overlap = self._calculate_bbox_overlap(coords1, coords2)
            
            return {
                'vertex_overlaps': vertex_overlaps,
                'edge_overlaps': edge_overlaps,
                'bbox_overlap': bbox_overlap,
                'has_potential_issues': len(vertex_overlaps) > 0 or len(edge_overlaps) > 0
            }
            
        except Exception as e:
            self.logger.error(f"重叠分析失败: {e}")
            return {'error': str(e)}
    
    def optimize_for_clipping(self, wkt1: str, wkt2: str) -> Tuple[str, str]:
        """
        为裁剪操作优化两个POLYGON
        
        Args:
            wkt1: 第一个POLYGON的WKT
            wkt2: 第二个POLYGON的WKT
            
        Returns:
            tuple: (优化后的wkt1, 优化后的wkt2)
        """
        try:
            # 分析重叠情况
            overlap_info = self.analyze_polygon_overlap(wkt1, wkt2)
            
            if overlap_info.get('has_potential_issues', False):
                # 有潜在问题，进行特殊优化
                optimized_wkt1 = self._apply_anti_overlap_optimization(wkt1)
                optimized_wkt2 = self._apply_anti_overlap_optimization(wkt2)
            else:
                # 标准优化
                optimized_wkt1 = self.optimize_polygon_wkt(wkt1)
                optimized_wkt2 = self.optimize_polygon_wkt(wkt2)
            
            return optimized_wkt1, optimized_wkt2
            
        except Exception as e:
            self.logger.error(f"裁剪优化失败: {e}")
            return wkt1, wkt2
    
    def _extract_coordinates(self, wkt_string: str) -> List[Tuple[float, float]]:
        """提取WKT中的坐标点，优先使用shapely解析"""
        try:
            geom = shapely_wkt.loads(wkt_string)
            if isinstance(geom, Polygon):
                return [(float(x), float(y)) for x, y in geom.exterior.coords]
            if hasattr(geom, "geoms"):  # MultiPolygon等
                first_polygon = next((g for g in geom.geoms if isinstance(g, Polygon)), None)
                if first_polygon is not None:
                    return [(float(x), float(y)) for x, y in first_polygon.exterior.coords]
        except Exception:
            # 回退到正则解析
            pass

        try:
            pattern = r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)'
            matches = re.findall(pattern, wkt_string)
            return [(float(x), float(y)) for x, y in matches]
        except Exception as e:
            self.logger.error(f"坐标提取失败: {e}")
            return []
    
    def _optimize_coordinates(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """使用NumPy向量化优化坐标精度"""
        if not coords:
            return []
        arr = np.round(np.asarray(coords, dtype=float), self.precision_digits)
        return [tuple(point) for point in arr.tolist()]
    
    def _remove_duplicate_points(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """移除重复的连续点"""
        if len(coords) <= 1:
            return coords
        
        arr = np.asarray(coords, dtype=float)
        if len(arr) <= 1:
            return coords

        deltas = np.linalg.norm(np.diff(arr, axis=0), axis=1)
        mask = np.concatenate(([True], deltas > self.tolerance))
        return [tuple(point) for point in arr[mask].tolist()]
    
    def _ensure_polygon_closure(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """确保多边形闭合"""
        if len(coords) < 3:
            return coords
        
        # 检查首尾点是否相同
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        
        return coords
    
    def _reconstruct_wkt(self, coords: List[Tuple[float, float]]) -> str:
        """重构WKT字符串"""
        if len(coords) < 4:  # 至少需要4个点（包括闭合点）
            raise ValueError("坐标点数量不足以构成有效多边形")
        
        coord_strings = []
        for x, y in coords:
            coord_strings.append(f"{x:.{self.precision_digits}f} {y:.{self.precision_digits}f}")
        
        return f"POLYGON (({', '.join(coord_strings)}))"
    
    def _detect_vertex_overlaps(self, coords1: List[Tuple[float, float]], 
                              coords2: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """检测顶点重叠"""
        if not coords1 or not coords2:
            return []

        points2 = [Point(x, y) for x, y in coords2]
        tree = STRtree(points2)
        geom_index_map = {id(geom): idx for idx, geom in enumerate(points2)}

        overlaps: List[Dict[str, Any]] = []
        for i, (x1, y1) in enumerate(coords1):
            point = Point(x1, y1)
            try:
                candidate_geoms = tree.query(point, predicate="dwithin", distance=self.tolerance)
            except TypeError:
                candidate_geoms = tree.query(point.buffer(self.tolerance))
            for geom in candidate_geoms:
                j = geom_index_map.get(id(geom))
                if j is None:
                    continue
                distance = point.distance(geom)
                if distance <= self.tolerance:
                    overlaps.append({
                        'poly1_vertex': i,
                        'poly2_vertex': j,
                        'coord1': (x1, y1),
                        'coord2': (geom.x, geom.y),
                        'distance': distance
                    })
        return overlaps
    
    def _detect_edge_overlaps(self, coords1: List[Tuple[float, float]], 
                            coords2: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """检测边重叠（简化版本）"""
        if len(coords1) < 2 or len(coords2) < 2:
            return []

        edges2 = [LineString([coords2[i], coords2[i + 1]]) for i in range(len(coords2) - 1)]
        tree = STRtree(edges2)
        geom_index_map = {id(geom): idx for idx, geom in enumerate(edges2)}

        overlaps: List[Dict[str, Any]] = []
        for i in range(len(coords1) - 1):
            edge_geom = LineString([coords1[i], coords1[i + 1]])
            try:
                candidate_edges = tree.query(edge_geom, predicate="dwithin", distance=self.tolerance)
            except TypeError:
                candidate_edges = tree.query(edge_geom.buffer(self.tolerance))

            for geom in candidate_edges:
                j = geom_index_map.get(id(geom))
                if j is None:
                    continue
                if edge_geom.distance(geom) <= self.tolerance:
                    overlaps.append({
                        'poly1_edge': i,
                        'poly2_edge': j,
                        'edge1': (coords1[i], coords1[i + 1]),
                        'edge2': tuple(geom.coords)
                    })
        return overlaps
    
    def _point_on_line_segment(self, point: Tuple[float, float], 
                              line_start: Tuple[float, float], 
                              line_end: Tuple[float, float]) -> bool:
        """检查点是否在线段上"""
        px, py = point
        x1, y1 = line_start
        x2, y2 = line_end
        
        # 计算点到线段的距离
        A = px - x1
        B = py - y1
        C = x2 - x1
        D = y2 - y1
        
        dot = A * C + B * D
        len_sq = C * C + D * D
        
        if len_sq == 0:  # 线段长度为0
            return ((px - x1)**2 + (py - y1)**2)**0.5 <= self.tolerance
        
        param = dot / len_sq
        
        if param < 0:
            xx, yy = x1, y1
        elif param > 1:
            xx, yy = x2, y2
        else:
            xx = x1 + param * C
            yy = y1 + param * D
        
        distance = ((px - xx)**2 + (py - yy)**2)**0.5
        return distance <= self.tolerance
    
    def _calculate_bbox_overlap(self, coords1: List[Tuple[float, float]], 
                               coords2: List[Tuple[float, float]]) -> Dict[str, float]:
        """计算边界框重叠"""
        # 计算边界框
        arr1 = np.asarray(coords1, dtype=float)
        arr2 = np.asarray(coords2, dtype=float)
        x1_min, y1_min = arr1.min(axis=0)
        x1_max, y1_max = arr1.max(axis=0)
        x2_min, y2_min = arr2.min(axis=0)
        x2_max, y2_max = arr2.max(axis=0)
        
        # 计算重叠区域
        overlap_x_min = max(x1_min, x2_min)
        overlap_x_max = min(x1_max, x2_max)
        overlap_y_min = max(y1_min, y2_min)
        overlap_y_max = min(y1_max, y2_max)
        
        if overlap_x_min < overlap_x_max and overlap_y_min < overlap_y_max:
            overlap_area = (overlap_x_max - overlap_x_min) * (overlap_y_max - overlap_y_min)
        else:
            overlap_area = 0.0
        
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        
        return {
            'overlap_area': overlap_area,
            'poly1_area': area1,
            'poly2_area': area2,
            'overlap_ratio1': overlap_area / area1 if area1 > 0 else 0,
            'overlap_ratio2': overlap_area / area2 if area2 > 0 else 0
        }
    
    def _apply_anti_overlap_optimization(self, wkt_string: str) -> str:
        """应用防重叠优化"""
        try:
            coords = self._extract_coordinates(wkt_string)
            if not coords:
                return wkt_string
            
            # 对有重叠问题的多边形进行微小的偏移
            offset = self.tolerance * 100  # 使用较大的偏移量
            
            optimized_coords = []
            for x, y in coords:
                # 添加微小的随机偏移来避免重叠
                import random
                random.seed(hash((x, y)) % 2147483647)  # 使用坐标作为种子确保一致性
                offset_x = (random.random() - 0.5) * offset
                offset_y = (random.random() - 0.5) * offset
                
                new_x = round(x + offset_x, self.precision_digits)
                new_y = round(y + offset_y, self.precision_digits)
                optimized_coords.append((new_x, new_y))
            
            # 移除重复点并确保闭合
            cleaned_coords = self._remove_duplicate_points(optimized_coords)
            closed_coords = self._ensure_polygon_closure(cleaned_coords)
            
            return self._reconstruct_wkt(closed_coords)
            
        except Exception as e:
            self.logger.error(f"防重叠优化失败: {e}")
            return wkt_string


def test_precision_optimizer():
    """测试精度优化器"""
    # 你提供的测试数据
    polygon1_wkt = "POLYGON ((111.91148257205967 21.81428867475205, 111.9062586542288 21.814253848633175, 111.90636313258541 21.809413018109908, 111.9095323094028 21.80885580020795, 111.91148257205967 21.81428867475205))"
    polygon2_wkt = "POLYGON ((111.91228357279373 21.812512542689554, 111.91242287726922 21.809796105417504, 111.90998504894814 21.810109540487357, 111.90998515997721 21.810117312522372, 111.91085288741212 21.81253455323389, 111.91228357279373 21.812512542689554))"
    
    # 创建优化器
    optimizer = PolygonPrecisionOptimizer(precision_digits=12, tolerance=1e-12)
    
    print("=== POLYGON精度优化测试 ===")
    
    # 分析重叠情况
    overlap_info = optimizer.analyze_polygon_overlap(polygon1_wkt, polygon2_wkt)
    print(f"重叠分析结果:")
    print(f"  顶点重叠数量: {len(overlap_info.get('vertex_overlaps', []))}")
    print(f"  边重叠数量: {len(overlap_info.get('edge_overlaps', []))}")
    print(f"  有潜在问题: {overlap_info.get('has_potential_issues', False)}")
    
    if 'bbox_overlap' in overlap_info:
        bbox = overlap_info['bbox_overlap']
        print(f"  边界框重叠面积: {bbox['overlap_area']:.12f}")
        print(f"  重叠比例1: {bbox['overlap_ratio1']:.6f}")
        print(f"  重叠比例2: {bbox['overlap_ratio2']:.6f}")
    
    # 优化多边形
    opt_wkt1, opt_wkt2 = optimizer.optimize_for_clipping(polygon1_wkt, polygon2_wkt)
    
    print(f"\n原始多边形1长度: {len(polygon1_wkt)}")
    print(f"优化后多边形1长度: {len(opt_wkt1)}")
    print(f"优化后多边形1: {opt_wkt1}")
    
    print(f"\n原始多边形2长度: {len(polygon2_wkt)}")
    print(f"优化后多边形2长度: {len(opt_wkt2)}")
    print(f"优化后多边形2: {opt_wkt2}")
    
    # 再次分析优化后的重叠情况
    opt_overlap_info = optimizer.analyze_polygon_overlap(opt_wkt1, opt_wkt2)
    print(f"\n优化后重叠分析:")
    print(f"  顶点重叠数量: {len(opt_overlap_info.get('vertex_overlaps', []))}")
    print(f"  边重叠数量: {len(opt_overlap_info.get('edge_overlaps', []))}")
    print(f"  有潜在问题: {opt_overlap_info.get('has_potential_issues', False)}")


if __name__ == "__main__":
    test_precision_optimizer()
