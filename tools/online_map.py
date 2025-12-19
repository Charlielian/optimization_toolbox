# -*- coding: utf-8 -*-
"""
在线地图功能 - 优化百宝箱工具集
基于 Streamlit + Folium + GeoPandas 的交互式地图可视化工具

功能特性：
- 支持百度/高德地图底图
- GPKG 格式空间图层上传与渲染
- SQLite 空间数据库（WKT/WKB字段）加载
- 图层样式自定义
- 坐标系自动转换（WGS84 -> BD09/GCJ02）
- 交互式弹窗和图层控制
"""

import logging
import math
import os
import tempfile
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium import plugins
from folium.plugins import Draw, Fullscreen, MeasureControl
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import sqlite3
from shapely import wkt, wkb
from shapely.geometry import Point, LineString, Polygon, MultiLineString, MultiPolygon
from pyproj import Transformer
import json
import tempfile
import os

logger = logging.getLogger(__name__)


def add_bing_tile_layer(map_obj, tiles_url='http://ecn.t3.tiles.virtualearth.net/tiles/a{q}.jpeg?g=1', 
                       attr='Bing Maps', max_zoom=19, min_zoom=1):
    """
    为地图添加 Bing Maps 瓦片图层（使用 QuadKey 格式）
    
    Args:
        map_obj: folium.Map 对象
        tiles_url: 瓦片 URL 模板（包含 {q} 占位符）
        attr: 地图属性信息
        max_zoom: 最大缩放级别
        min_zoom: 最小缩放级别
    """
    # 获取地图对象的名称
    map_name = map_obj.get_name()
    
    # 转义 JavaScript 字符串中的特殊字符
    tiles_url_escaped = tiles_url.replace("'", "\\'")
    attr_escaped = attr.replace("'", "\\'")
    
    # 使用 MacroElement 注入 JavaScript
    from folium import Element
    
    bing_js = f"""
    <script>
    (function() {{
        // QuadKey 转换函数
        function tileToQuadKey(x, y, z) {{
            var quadkey = "";
            for (var i = z; i > 0; i--) {{
                var digit = 0;
                var mask = 1 << (i - 1);
                if ((x & mask) != 0) digit += 1;
                if ((y & mask) != 0) digit += 2;
                quadkey += digit.toString();
            }}
            return quadkey;
        }}
        
        // 获取地图对象
        var map = {map_name};
        
        // 创建自定义的 TileLayer
        var BingTileLayer = L.TileLayer.extend({{
            getTileUrl: function(coords) {{
                var quadkey = tileToQuadKey(coords.x, coords.y, coords.z);
                return '{tiles_url_escaped}'.replace('{{q}}', quadkey);
            }}
        }});
        
        var bingLayer = new BingTileLayer('', {{
            attribution: '{attr_escaped}',
            maxZoom: {max_zoom},
            minZoom: {min_zoom}
        }});
        
        bingLayer.addTo(map);
    }})();
    </script>
    """
    
    # 添加脚本到地图
    element = Element(bing_js)
    map_obj.get_root().html.add_child(element)


class CoordinateConverter:
    """坐标系转换工具类"""
    
    # 坐标转换参数（用于百度/高德坐标系转换）
    PI = 3.1415926535897932384626
    X_PI = 3.14159265358979324 * 3000.0 / 180.0
    
    @staticmethod
    def out_of_china(lng, lat):
        """
        判断坐标是否在中国境外（境外坐标无需转换，直接返回原坐标）
        
        Args:
            lng: 经度
            lat: 纬度
            
        Returns:
            True（境外）/False（境内）
        """
        if lng < 72.004 or lng > 137.8347:
            return True
        if lat < 0.8293 or lat > 55.8271:
            return True
        return False
    
    @staticmethod
    def wgs84_to_gcj02(lng, lat):
        """
        将WGS84坐标转换为GCJ02坐标（高德坐标）
        
        Args:
            lng: WGS84经度
            lat: WGS84纬度
            
        Returns:
            转换后的GCJ02经纬度（元组：(gcj_lng, gcj_lat)）
        """
        if CoordinateConverter.out_of_china(lng, lat):
            return lng, lat
        
        a = 6378245.0
        ee = 0.00669342162296594323
        
        # 计算经纬度相对于中心点的偏移
        x = lng - 105.0
        y = lat - 35.0
        
        # 计算纬度偏移量
        dLat = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        dLat += (20.0 * math.sin(6.0 * x * CoordinateConverter.PI) + 20.0 * math.sin(2.0 * x * CoordinateConverter.PI)) * 2.0 / 3.0
        dLat += (20.0 * math.sin(y * CoordinateConverter.PI) + 40.0 * math.sin(y / 3.0 * CoordinateConverter.PI)) * 2.0 / 3.0
        dLat += (160.0 * math.sin(y / 12.0 * CoordinateConverter.PI) + 320.0 * math.sin(y * CoordinateConverter.PI / 30.0)) * 2.0 / 3.0
        
        # 计算经度偏移量
        dLon = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        dLon += (20.0 * math.sin(6.0 * x * CoordinateConverter.PI) + 20.0 * math.sin(2.0 * x * CoordinateConverter.PI)) * 2.0 / 3.0
        dLon += (20.0 * math.sin(x * CoordinateConverter.PI) + 40.0 * math.sin(x / 3.0 * CoordinateConverter.PI)) * 2.0 / 3.0
        dLon += (150.0 * math.sin(x / 12.0 * CoordinateConverter.PI) + 300.0 * math.sin(x / 30.0 * CoordinateConverter.PI)) * 2.0 / 3.0
        
        # 计算辅助变量
        radLat = lat * CoordinateConverter.PI / 180.0
        magic = math.sin(radLat)
        magic = 1 - ee * magic * magic
        sqrtMagic = math.sqrt(magic)
        
        # 转换偏移量为经纬度差
        dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * CoordinateConverter.PI)
        dLon = (dLon * 180.0) / (a / sqrtMagic * math.cos(radLat) * CoordinateConverter.PI)
        
        # 计算最终GCJ02坐标
        gcjLat = lat + dLat
        gcjLon = lng + dLon
        
        return gcjLon, gcjLat
    
    @staticmethod
    def gcj02_to_bd09(lon, lat):
        """
        GCJ02坐标系转BD09坐标系（百度地图）
        
        Args:
            lon: 经度
            lat: 纬度
            
        Returns:
            (lon, lat) 转换后的坐标
        """
        z = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * CoordinateConverter.X_PI)
        theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * CoordinateConverter.X_PI)
        bd_lon = z * math.cos(theta) + 0.0065
        bd_lat = z * math.sin(theta) + 0.006
        return bd_lon, bd_lat
    
    @staticmethod
    def wgs84_to_bd09(lon, lat):
        """
        WGS84坐标系转BD09坐标系（百度地图）
        
        Args:
            lon: 经度
            lat: 纬度
            
        Returns:
            (lon, lat) 转换后的坐标
        """
        gcj_lon, gcj_lat = CoordinateConverter.wgs84_to_gcj02(lon, lat)
        return CoordinateConverter.gcj02_to_bd09(gcj_lon, gcj_lat)


class OnlineMap:
    """在线地图功能主类"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        # 从 session_state 恢复图层，如果不存在则初始化
        if 'layers' not in st.session_state:
            st.session_state['layers'] = {}
        self.layers = st.session_state['layers']  # 存储加载的图层
    
    @staticmethod
    def calculate_sector_beam(row):
        """
        计算扇区波瓣角度
        
        Args:
            row: 包含 site_type, zhishi, pinduan 的字典或 Series
            
        Returns:
            float: 扇区波瓣角度（度）
        """
        site_type = str(row.get('site_type', '') or '').strip()
        zhishi = str(row.get('zhishi', '') or '').strip()
        pinduan = str(row.get('pinduan', '') or '').strip()
        
        if site_type == '室分':
            return 359.0
        elif zhishi == '5G':
            if '700M' in pinduan:
                return 40.0
            elif '2.6G' in pinduan:
                return 65.0
            elif '4.9G' in pinduan:
                return 70.0
        elif zhishi == '4G':
            if 'FDD900' in pinduan:
                return 30.0
            elif 'FDD1800' in pinduan:
                return 50.0
            elif 'F' in pinduan:
                return 45.0
            elif 'D' in pinduan:
                return 60.0
            elif 'A' in pinduan:
                return 55.0
        
        return 40.0  # 默认值
    
    @staticmethod
    def calculate_sector_radius(row):
        """
        计算扇区半径（米）
        
        Args:
            row: 包含 site_type, zhishi, pinduan 的字典或 Series
            
        Returns:
            float: 扇区半径（米）
        """
        site_type = str(row.get('site_type', '') or '').strip()
        zhishi = str(row.get('zhishi', '') or '').strip()
        pinduan = str(row.get('pinduan', '') or '').strip()
        
        if site_type == '室分':
            return 30.0
        elif zhishi == '5G':
            if '700M' in pinduan:
                return 50.0
            elif '2.6G' in pinduan:
                return 40.0
            elif '4.9G' in pinduan:
                return 30.0
        elif zhishi == '4G':
            if 'FDD900' in pinduan:
                return 47.0
            elif 'FDD1800' in pinduan:
                return 43.0
            elif 'F' in pinduan:
                return 39.0
            elif 'D' in pinduan:
                return 42.0
            elif 'A' in pinduan:
                return 38.0
        
        return 40.0  # 默认值
    
    @staticmethod
    def create_sector_polygon(center_lon, center_lat, azimuth, beam_width, radius_meters, num_points=32):
        """
        创建扇形多边形
        
        Args:
            center_lon: 中心点经度
            center_lat: 中心点纬度
            azimuth: 方位角（度，0-360，正北为0，顺时针）
            beam_width: 波瓣宽度（度）
            radius_meters: 半径（米）
            num_points: 圆弧上的点数（用于平滑扇形边界）
            
        Returns:
            Polygon: 扇形多边形
        """
        try:
            # 地球半径（米）
            EARTH_RADIUS = 6371000.0
            
            # 将方位角转换为弧度（地理坐标系：0度为正北，顺时针）
            # 数学坐标系：0度为正东，逆时针
            # 转换：地理方位角 -> 数学角度 = 90 - 方位角（逆时针）
            azimuth_rad = math.radians(90.0 - azimuth)
            half_beam_rad = math.radians(beam_width / 2.0)
            
            # 计算左边界和右边界的角度（从中心看，左边界和右边界）
            # 注意：这里左边界是方位角减去一半波瓣，右边界是方位角加上一半波瓣
            left_angle = azimuth_rad - half_beam_rad
            right_angle = azimuth_rad + half_beam_rad
            
            # 使用大圆距离公式计算扇区边界点（考虑地球曲率）
            # 地球半径（米）
            EARTH_RADIUS_M = 6371000.0
            
            # 将中心点转换为弧度
            center_lat_rad = math.radians(center_lat)
            center_lon_rad = math.radians(center_lon)
            
            # 计算半径对应的角度（弧度）
            # 使用公式：角度 = 弧长 / 半径
            radius_rad = radius_meters / EARTH_RADIUS_M
            
            # 生成扇形边界点
            points = []
            
            # 添加中心点
            points.append((center_lon, center_lat))
            
            # 辅助函数：根据方位角和距离计算目标点坐标
            def calculate_destination_point(lon_rad, lat_rad, bearing_rad, distance_rad):
                """
                使用大圆距离公式计算目标点坐标
                
                Args:
                    lon_rad: 起点经度（弧度）
                    lat_rad: 起点纬度（弧度）
                    bearing_rad: 方位角（弧度，从正北顺时针）
                    distance_rad: 距离（弧度）
                
                Returns:
                    (目标经度, 目标纬度) 元组（度）
                """
                # 地理方位角转数学角度（从正北顺时针转为从正东逆时针）
                # 地理方位角：0度=正北，90度=正东，180度=正南，270度=正西
                # 数学角度：0度=正东，90度=正北，180度=正西，270度=正南
                # 转换：数学角度 = 90 - 地理方位角
                math_bearing = math.pi / 2.0 - bearing_rad
                
                # 计算目标点纬度
                dest_lat_rad = math.asin(
                    math.sin(lat_rad) * math.cos(distance_rad) +
                    math.cos(lat_rad) * math.sin(distance_rad) * math.cos(math_bearing)
                )
                
                # 计算目标点经度
                dest_lon_rad = lon_rad + math.atan2(
                    math.sin(math_bearing) * math.sin(distance_rad) * math.cos(lat_rad),
                    math.cos(distance_rad) - math.sin(lat_rad) * math.sin(dest_lat_rad)
                )
                
                return (math.degrees(dest_lon_rad), math.degrees(dest_lat_rad))
            
            # 计算左边界点（方位角 - 波瓣/2）
            left_bearing_rad = math.radians(azimuth - beam_width / 2.0)
            left_lon, left_lat = calculate_destination_point(
                center_lon_rad, center_lat_rad, left_bearing_rad, radius_rad
            )
            points.append((left_lon, left_lat))
            
            # 添加圆弧上的点（从左边界到右边界）
            right_bearing_rad = math.radians(azimuth + beam_width / 2.0)
            for i in range(num_points + 1):
                # 计算当前角度（从左边界到右边界）
                bearing_deg = azimuth - beam_width / 2.0 + (beam_width * i / num_points)
                bearing_rad = math.radians(bearing_deg)
                
                lon, lat = calculate_destination_point(
                    center_lon_rad, center_lat_rad, bearing_rad, radius_rad
                )
                points.append((lon, lat))
            
            # 闭合多边形（回到中心点）
            points.append((center_lon, center_lat))
            
            # 创建多边形
            polygon = Polygon(points)
            
            # 验证多边形有效性
            if not polygon.is_valid:
                # 尝试修复无效的多边形
                polygon = polygon.buffer(0)
            
            return polygon
            
        except Exception as e:
            logger.warning(f"创建扇形失败: {e}, 中心点: ({center_lon}, {center_lat}), 方位角: {azimuth}, 波瓣: {beam_width}, 半径: {radius_meters}")
            return None
        
    def render(self):
        """渲染在线地图界面"""
        st.title("🗺️ 在线地图功能")
        st.caption("基于 Folium + GeoPandas 的交互式空间数据可视化")
        
        # 侧边栏配置
        with st.sidebar:
            st.header("⚙️ 地图配置")
            
            # 底图选择（默认使用 GEO 卫星底图）
            basemap_type = st.selectbox(
                "选择底图类型",
                [
                    "GEO卫星地图",
                    "高德地图（普通）",
                    "高德地图（瓦片）",
                    "百度地图（普通）",
                    "百度地图（瓦片）",
                    "Google地图",
                    "Google卫星地图",
                    "OpenStreetMap",
                    "GMCC地图",
                    "Bing地图",
                ],
                index=0
            )
            
            # 底图使用说明
            if basemap_type.startswith("Google"):
                st.info("⚠️ Google 地图仅在境外/特殊网络环境下可用，境内普通网络可能显示空白。Google 地图使用 WGS84 坐标系，无需坐标转换。")
            elif basemap_type.startswith("GEO"):
                st.info("ℹ️ GEO 卫星底图基于 Google 瓦片镜像服务，使用 WGS84 坐标系，无需坐标转换。")
            
            # 初始中心点和缩放级别（如果已加载图层，使用图层中心点）
            if 'map_center_lat' in st.session_state and 'map_center_lon' in st.session_state:
                default_lat = st.session_state['map_center_lat']
                default_lon = st.session_state['map_center_lon']
            else:
                default_lat = 21.85919070
                default_lon = 111.97884194
            
            col1, col2 = st.columns(2)
            with col1:
                init_lat = st.number_input("初始纬度", value=default_lat, format="%.6f")
            with col2:
                init_lon = st.number_input("初始经度", value=default_lon, format="%.6f")
            
            zoom_level = st.slider("缩放级别", min_value=1, max_value=18, value=10)
            
            st.markdown("---")
            st.header("📍 经纬度定位")
            st.caption("输入经纬度快速定位到指定位置")
            
            # 定位输入框
            col1, col2 = st.columns(2)
            with col1:
                locate_lat = st.number_input(
                    "纬度", 
                    value=default_lat, 
                    format="%.6f",
                    key="locate_lat_input",
                    help="输入要定位的纬度（-90 到 90）"
                )
            with col2:
                locate_lon = st.number_input(
                    "经度", 
                    value=default_lon, 
                    format="%.6f",
                    key="locate_lon_input",
                    help="输入要定位的经度（-180 到 180）"
                )
            
            # 定位按钮
            if st.button("📍 定位", type="primary", key="locate_button", use_container_width=True):
                # 验证经纬度范围
                if -90 <= locate_lat <= 90 and -180 <= locate_lon <= 180:
                    # 保存定位信息到 session_state
                    st.session_state['locate_lat'] = locate_lat
                    st.session_state['locate_lon'] = locate_lon
                    st.session_state['locate_zoom'] = 15  # 定位时使用较大的缩放级别
                    # 更新地图中心点
                    st.session_state['map_center_lat'] = locate_lat
                    st.session_state['map_center_lon'] = locate_lon
                    st.session_state['map_auto_zoom'] = 15
                    st.success(f"✅ 已定位到: 纬度 {locate_lat:.6f}, 经度 {locate_lon:.6f}")
                    st.rerun()
                else:
                    st.error("❌ 经纬度范围无效！纬度应在 -90 到 90 之间，经度应在 -180 到 180 之间。")
            
            # 清除定位标记按钮
            if 'locate_lat' in st.session_state and 'locate_lon' in st.session_state:
                if st.button("🗑️ 清除定位标记", key="clear_locate_button", use_container_width=True):
                    if 'locate_lat' in st.session_state:
                        del st.session_state['locate_lat']
                    if 'locate_lon' in st.session_state:
                        del st.session_state['locate_lon']
                    st.success("✅ 已清除定位标记")
                    st.rerun()
            
            st.markdown("---")
            st.header("📂 数据加载")
            
            # 数据源选择
            data_source = st.radio(
                "选择数据源",
                ["上传 GPKG 文件", "加载 SQLite 空间数据库"],
                index=0
            )
        
        # 主内容区域
        if data_source == "上传 GPKG 文件":
            self._render_gpkg_upload(basemap_type, init_lat, init_lon, zoom_level)
        else:
            self._render_sqlite_loader(basemap_type, init_lat, init_lon, zoom_level)
    
    def _render_gpkg_upload(self, basemap_type, init_lat, init_lon, zoom_level):
        """渲染 GPKG 文件上传界面"""
        st.header("📤 上传 GPKG 文件")
        st.info("💡 **说明**: 支持上传 GPKG 格式的空间数据文件，系统将自动解析点/线/面要素并在地图上渲染。")
        
        uploaded_file = st.file_uploader(
            "选择 GPKG 文件",
            type=['gpkg'],
            help="支持 GeoPackage 格式的空间数据文件",
            key="gpkg_file_uploader"
        )
        
        if uploaded_file:
            # 使用 session_state 缓存已读取的数据，避免重复读取导致无限刷新
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            cache_key = f"gpkg_cache_{file_id}"
            
            # 检查缓存
            if cache_key in st.session_state:
                gdf = st.session_state[cache_key]
                logger.debug(f"使用缓存的 GPKG 数据: {uploaded_file.name}")
            else:
                tmp_file_path = None
                try:
                    # 保存上传的文件到临时目录
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.gpkg') as tmp_file:
                        tmp_file.write(uploaded_file.read())
                        tmp_file_path = tmp_file.name
                    
                    # 读取 GPKG 文件
                    gdf = None
                    with st.spinner("正在读取 GPKG 文件..."):
                        try:
                            gdf = gpd.read_file(tmp_file_path)
                            # 缓存读取的数据
                            st.session_state[cache_key] = gdf
                            logger.info(f"GPKG 文件已缓存: {uploaded_file.name}")
                        except Exception as e:
                            st.error(f"❌ 读取文件失败: {str(e)}")
                            logger.error(f"读取 GPKG 文件失败: {str(e)}", exc_info=True)
                            # 清理临时文件
                            if tmp_file_path and os.path.exists(tmp_file_path):
                                try:
                                    os.unlink(tmp_file_path)
                                except:
                                    pass
                            return
                    
                    # 清理临时文件
                    if tmp_file_path and os.path.exists(tmp_file_path):
                        try:
                            os.unlink(tmp_file_path)
                        except:
                            pass
                    
                    if gdf is None or len(gdf) == 0:
                        st.warning("⚠️ 文件读取成功，但未包含有效数据")
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                        return
                except Exception as e:
                    st.error(f"❌ 处理文件失败: {str(e)}")
                    logger.error(f"处理 GPKG 文件失败: {str(e)}", exc_info=True)
                    return
            
            st.success(f"✅ 文件读取成功！共 {len(gdf):,} 个要素")
            
            # 显示文件信息（优化性能，避免处理大量数据时卡顿）
            with st.expander("📊 数据信息", expanded=False):
                try:
                    st.write(f"**要素数量**: {len(gdf):,}")
                    # 优化：只获取前几种几何类型，避免处理全部数据
                    geom_types = gdf.geometry.type.unique()[:5].tolist()
                    if len(gdf.geometry.type.unique()) > 5:
                        geom_types.append("...")
                    st.write(f"**几何类型**: {geom_types}")
                    st.write(f"**坐标系**: {gdf.crs if gdf.crs else '未定义'}")
                    st.write(f"**属性字段**: {', '.join(gdf.columns.tolist()[:10])}")
                    if len(gdf.columns) > 10:
                        st.write(f"*（共 {len(gdf.columns)} 个字段，仅显示前10个）*")
                    
                    # 显示数据预览（限制行数）
                    # 注意：Streamlit 无法直接显示 geometry 列，需要先移除或转换
                    # 使用缓存避免每次渲染都重新处理
                    preview_cache_key = f"gpkg_preview_{file_id}"
                    if preview_cache_key in st.session_state:
                        preview_df = st.session_state[preview_cache_key]
                        logger.debug("使用缓存的数据预览")
                    else:
                        preview_rows = min(10, len(gdf))
                        preview_df = gdf.head(preview_rows).copy()
                        # 将 geometry 列转换为简单的字符串描述，避免 WKT 转换导致的内存问题
                        if 'geometry' in preview_df.columns:
                            try:
                                # 安全地转换 geometry 列 - 只显示类型和基本信息，不转换完整 WKT
                                def safe_geom_info(geom):
                                    try:
                                        if geom is None:
                                            return "None"
                                        if geom.is_empty:
                                            return "Empty"
                                        # 只返回几何类型和基本信息，不转换完整 WKT
                                        geom_type = geom.geom_type
                                        if geom_type == 'Point':
                                            return f"{geom_type}"
                                        elif geom_type == 'LineString':
                                            try:
                                                coords_count = len(list(geom.coords))
                                                return f"{geom_type}({coords_count} points)"
                                            except:
                                                return f"{geom_type}"
                                        elif geom_type == 'Polygon':
                                            try:
                                                coords_count = len(geom.exterior.coords)
                                                return f"{geom_type}({coords_count} points)"
                                            except:
                                                return f"{geom_type}"
                                        elif geom_type == 'MultiPolygon':
                                            try:
                                                geom_count = len(geom.geoms)
                                                return f"{geom_type}({geom_count} parts)"
                                            except:
                                                return f"{geom_type}"
                                        elif geom_type == 'MultiLineString':
                                            try:
                                                geom_count = len(geom.geoms)
                                                return f"{geom_type}({geom_count} parts)"
                                            except:
                                                return f"{geom_type}"
                                        elif geom_type == 'MultiPoint':
                                            try:
                                                geom_count = len(geom.geoms)
                                                return f"{geom_type}({geom_count} points)"
                                            except:
                                                return f"{geom_type}"
                                        else:
                                            return geom_type
                                    except Exception as e:
                                        logger.warning(f"获取几何信息失败: {str(e)}")
                                        return "Unknown"
                                # 先复制数据，然后转换 geometry 列
                                preview_df = preview_df.copy()
                                preview_df['geometry'] = preview_df['geometry'].apply(safe_geom_info)
                                # 缓存处理后的预览数据
                                st.session_state[preview_cache_key] = preview_df
                                logger.info("✅ geometry 列转换成功（使用简化信息）")
                            except Exception as e:
                                # 如果转换失败，直接删除 geometry 列
                                logger.warning(f"转换 geometry 列失败: {str(e)}")
                                preview_df = preview_df.drop(columns=['geometry'])
                                st.session_state[preview_cache_key] = preview_df
                    try:
                        st.dataframe(preview_df, use_container_width=True)
                    except Exception as e:
                        st.warning(f"⚠️ 显示数据预览失败: {str(e)}")
                        logger.warning(f"显示数据预览失败: {str(e)}")
                except Exception as e:
                    st.warning(f"⚠️ 显示数据信息时出错: {str(e)}")
                    logger.warning(f"显示数据信息时出错: {str(e)}")
            
            # 图层样式配置
            st.subheader("🎨 图层样式配置")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                fill_color = st.color_picker("填充颜色", value="#3388ff", key="fill_color")
                fill_opacity = st.slider("填充透明度", 0.0, 1.0, 0.5, key="fill_opacity")
            
            with col2:
                line_color = st.color_picker("线条颜色", value="#000000", key="line_color")
                line_width = st.slider("线条宽度", 1, 10, 2, key="line_width")
            
            with col3:
                point_radius = st.slider("点要素大小", 1, 20, 5, key="point_radius")
                point_color = st.color_picker("点要素颜色", value="#ff0000", key="point_color")
            
            # 图层名称
            layer_name = st.text_input("图层名称", value=uploaded_file.name.replace('.gpkg', ''), key="layer_name")
            
            # 坐标系转换选项
            st.subheader("🔄 坐标系转换")
            convert_coords = st.checkbox("自动转换坐标系（WGS84 -> 百度/高德）", value=True)
            
            # 渲染选项
            st.subheader("⚙️ 渲染选项")
            render_all = st.checkbox(
                "全量渲染所有要素（不推荐，可能影响性能）", 
                value=False,
                help="默认情况下，超过1000个要素的图层仅渲染前1000个以提升性能。勾选此选项将渲染所有要素，但可能导致页面卡顿。"
            )
            
            if st.button("🗺️ 加载到地图", type="primary"):
                with st.spinner("正在加载图层到地图..."):
                    try:
                        # 验证数据有效性
                        if gdf is None or len(gdf) == 0:
                            st.error("❌ 无法加载空图层")
                            return
                        
                        # 存储图层数据
                        # 使用深拷贝确保存储的是原始数据的副本，避免后续转换操作影响原始数据
                        layer_key = f"layer_{len(self.layers)}"
                        self.layers[layer_key] = {
                            'gdf': gdf.copy(deep=True),  # 深拷贝，确保存储原始数据
                            'name': layer_name,
                            'fill_color': fill_color,
                            'fill_opacity': fill_opacity,
                            'line_color': line_color,
                            'line_width': line_width,
                            'point_radius': point_radius,
                            'point_color': point_color,
                            'convert_coords': convert_coords,
                            'render_all': render_all
                        }
                        st.session_state['layers'] = self.layers
                        
                        # 将新图层添加到顺序列表的末尾
                        if 'layer_order' not in st.session_state:
                            st.session_state['layer_order'] = []
                        st.session_state['layer_order'].append(layer_key)
                        
                        # 计算所有图层的合并边界并更新地图中心点（只在加载图层时计算一次）
                        try:
                            all_bounds = []
                            for layer_data in self.layers.values():
                                layer_gdf = layer_data['gdf']
                                bounds = layer_gdf.total_bounds
                                if bounds is not None and len(bounds) == 4:
                                    all_bounds.append(bounds)
                            
                            if all_bounds:
                                # 计算所有图层的合并边界
                                minx = min(b[0] for b in all_bounds)
                                miny = min(b[1] for b in all_bounds)
                                maxx = max(b[2] for b in all_bounds)
                                maxy = max(b[3] for b in all_bounds)
                                
                                # 更新中心点
                                center_lat = (miny + maxy) / 2
                                center_lon = (minx + maxx) / 2
                                
                                # 根据边界范围自动调整缩放级别
                                lat_range = maxy - miny
                                lon_range = maxx - minx
                                max_range = max(lat_range, lon_range)
                                
                                # 根据范围估算合适的缩放级别
                                if max_range > 10:
                                    auto_zoom = 5
                                elif max_range > 5:
                                    auto_zoom = 6
                                elif max_range > 2:
                                    auto_zoom = 7
                                elif max_range > 1:
                                    auto_zoom = 8
                                elif max_range > 0.5:
                                    auto_zoom = 9
                                elif max_range > 0.2:
                                    auto_zoom = 10
                                elif max_range > 0.1:
                                    auto_zoom = 11
                                elif max_range > 0.05:
                                    auto_zoom = 12
                                else:
                                    auto_zoom = 13
                                
                                # 保存地图中心点和缩放级别（只在值真正变化时才更新，避免浮点数精度导致的微小变化）
                                # 使用四舍五入到6位小数来避免浮点数精度问题
                                center_lat_rounded = round(center_lat, 6)
                                center_lon_rounded = round(center_lon, 6)
                                
                                # 只在值真正变化时才更新（避免微小变化导致无限刷新）
                                should_update = True
                                if 'map_center_lat' in st.session_state and 'map_center_lon' in st.session_state:
                                    old_lat = round(st.session_state['map_center_lat'], 6)
                                    old_lon = round(st.session_state['map_center_lon'], 6)
                                    if abs(center_lat_rounded - old_lat) < 0.0001 and abs(center_lon_rounded - old_lon) < 0.0001:
                                        should_update = False
                                
                                if should_update:
                                    st.session_state['map_center_lat'] = center_lat_rounded
                                    st.session_state['map_center_lon'] = center_lon_rounded
                                    st.session_state['map_auto_zoom'] = auto_zoom
                                    logger.info(f"自动调整地图中心: ({center_lat_rounded}, {center_lon_rounded}), 缩放级别: {auto_zoom}")
                                else:
                                    logger.debug(f"地图中心点未变化，跳过更新")
                        except Exception as e:
                            logger.warning(f"计算图层边界失败: {str(e)}")
                        
                        st.success(f"✅ 图层 '{layer_name}' 已加载")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 加载图层失败: {str(e)}")
                        logger.error(f"加载图层失败: {str(e)}", exc_info=True)
                        import traceback
                        logger.error(traceback.format_exc())
                # 文件会在会话结束时自动清理
        
        # 显示地图（只有在有图层时才渲染，避免空地图导致卡顿）
        if 'layers' in st.session_state and st.session_state['layers']:
            self._render_map(basemap_type, init_lat, init_lon, zoom_level)
        else:
            st.info("💡 请先上传并加载图层数据，地图将在加载图层后显示。")
    
    def _render_sqlite_loader(self, basemap_type, init_lat, init_lon, zoom_level):
        """渲染 SQLite 空间数据库加载界面"""
        st.header("💾 加载 SQLite 空间数据库")
        st.info("💡 **说明**: 支持从 SQLite 数据库中加载包含 WKT/WKB 格式的空间表。")

        # 数据库来源：上传文件 或 使用内置 optimization_toolbox.db
        db_source = st.radio(
            "选择数据库来源",
            ["上传 SQLite 数据库文件", "使用内置 optimization_toolbox.db（工程参数表）"],
            index=0,
            key="sqlite_db_source"
        )

        # 选项一：上传任意 SQLite 空间数据库（原有逻辑）
        uploaded_db = None
        if db_source == "上传 SQLite 数据库文件":
            uploaded_db = st.file_uploader(
                "选择 SQLite 数据库文件",
                type=['db', 'sqlite', 'sqlite3'],
                help="支持 SQLite 数据库文件",
                key="sqlite_file_uploader"
            )
        else:
            st.info("📌 当前使用的是内置数据库 `optimization_toolbox.db` 中的 `engineering_params` 工参表，经纬度字段为 `lon`/`lat`。")

        # 选项二：直接从内置 optimization_toolbox.db 的 engineering_params 表加载点要素
        if db_source == "使用内置 optimization_toolbox.db（工程参数表）":
            self._render_internal_engineering_layer(basemap_type, init_lat, init_lon, zoom_level)
            return

        if uploaded_db:
            # 使用 session_state 缓存数据库连接和表信息，避免重复读取
            db_id = f"{uploaded_db.name}_{uploaded_db.size}"
            db_cache_key = f"sqlite_db_{db_id}"
            tables_cache_key = f"sqlite_tables_{db_id}"
            
            # 检查缓存
            if db_cache_key in st.session_state and tables_cache_key in st.session_state:
                tmp_file_path = st.session_state[db_cache_key]
                tables = st.session_state[tables_cache_key]
                conn = sqlite3.connect(tmp_file_path)
                logger.debug(f"使用缓存的 SQLite 数据库: {uploaded_db.name}")
            else:
                try:
                    # 保存上传的文件到临时目录
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
                        tmp_file.write(uploaded_db.read())
                        tmp_file_path = tmp_file.name
                    
                    # 连接数据库
                    conn = sqlite3.connect(tmp_file_path)
                    
                    # 获取所有表名
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    
                    # 缓存数据库路径和表信息
                    st.session_state[db_cache_key] = tmp_file_path
                    st.session_state[tables_cache_key] = tables
                    logger.info(f"SQLite 数据库已缓存: {uploaded_db.name}")
                    
                    if not tables:
                        st.warning("⚠️ 数据库中没有找到表")
                        conn.close()
                        return
                except Exception as e:
                    st.error(f"❌ 读取数据库失败: {str(e)}")
                    logger.error(f"读取 SQLite 数据库失败: {str(e)}", exc_info=True)
                    return
            
            st.success(f"✅ 数据库连接成功！找到 {len(tables)} 个表")
            
            # 选择表
            selected_table = st.selectbox("选择空间表", tables)
            
            if selected_table:
                # 获取表的列信息
                cursor.execute(f"PRAGMA table_info({selected_table})")
                columns = cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                st.write(f"**表列**: {', '.join(column_names)}")
                
                # 选择空间字段
                geom_column = st.selectbox(
                    "选择空间字段（WKT/WKB）",
                    column_names,
                    help="选择包含 WKT 或 WKB 格式几何数据的列"
                )
                
                # 选择其他属性字段（用于弹窗显示）
                attr_columns = st.multiselect(
                    "选择属性字段（用于弹窗显示）",
                    [col for col in column_names if col != geom_column],
                    help="选择要在弹窗中显示的属性字段"
                )
                
                # 限制查询数量
                limit = st.number_input("限制查询数量", min_value=1, max_value=100000, value=1000, step=100)
                
                if st.button("🔍 查询数据", type="primary"):
                    with st.spinner("正在查询数据..."):
                        # 查询数据
                        query = f"SELECT * FROM {selected_table} LIMIT {limit}"
                        df = pd.read_sql_query(query, conn)
                        
                        # 解析空间字段
                        geometries = []
                        for idx, row in df.iterrows():
                            geom_str = row[geom_column]
                            if geom_str:
                                try:
                                    # 尝试解析 WKT
                                    if isinstance(geom_str, str):
                                        geom = wkt.loads(geom_str)
                                    else:
                                        # 尝试解析 WKB
                                        geom = wkb.loads(geom_str)
                                    geometries.append(geom)
                                except:
                                    geometries.append(None)
                            else:
                                geometries.append(None)
                        
                        # 创建 GeoDataFrame
                        gdf = gpd.GeoDataFrame(df, geometry=geometries, crs='EPSG:4326')
                        gdf = gdf[gdf.geometry.notna()]  # 过滤掉无效几何
                        
                        st.success(f"✅ 查询成功！共 {len(gdf):,} 个有效要素")
                        
                        # 显示数据预览
                        with st.expander("📊 数据预览", expanded=False):
                            # Streamlit 无法直接显示 geometry 列，需要转换为字符串
                            preview_df = gdf.head(10).copy()
                            if 'geometry' in preview_df.columns:
                                try:
                                    # 使用简化的几何信息，避免 WKT 转换导致的内存问题
                                    def safe_geom_info(geom):
                                        try:
                                            if geom is None:
                                                return "None"
                                            if geom.is_empty:
                                                return "Empty"
                                            geom_type = geom.geom_type
                                            if geom_type == 'Point':
                                                return f"{geom_type}"
                                            elif geom_type == 'LineString':
                                                try:
                                                    coords_count = len(list(geom.coords))
                                                    return f"{geom_type}({coords_count} points)"
                                                except:
                                                    return f"{geom_type}"
                                            elif geom_type == 'Polygon':
                                                try:
                                                    coords_count = len(geom.exterior.coords)
                                                    return f"{geom_type}({coords_count} points)"
                                                except:
                                                    return f"{geom_type}"
                                            elif geom_type == 'MultiPolygon':
                                                try:
                                                    geom_count = len(geom.geoms)
                                                    return f"{geom_type}({geom_count} parts)"
                                                except:
                                                    return f"{geom_type}"
                                            elif geom_type == 'MultiLineString':
                                                try:
                                                    geom_count = len(geom.geoms)
                                                    return f"{geom_type}({geom_count} parts)"
                                                except:
                                                    return f"{geom_type}"
                                            elif geom_type == 'MultiPoint':
                                                try:
                                                    geom_count = len(geom.geoms)
                                                    return f"{geom_type}({geom_count} points)"
                                                except:
                                                    return f"{geom_type}"
                                            else:
                                                return geom_type
                                        except Exception:
                                            return "Unknown"
                                    # 先复制数据，然后转换 geometry 列
                                    preview_df = preview_df.copy()
                                    preview_df['geometry'] = preview_df['geometry'].apply(safe_geom_info)
                                except Exception as e:
                                    logger.warning(f"转换 geometry 列失败: {str(e)}")
                                    preview_df = preview_df.drop(columns=['geometry'])
                            try:
                                st.dataframe(preview_df, use_container_width=True)
                            except Exception as e:
                                st.warning(f"⚠️ 显示数据预览失败: {str(e)}")
                                logger.warning(f"显示数据预览失败: {str(e)}")
                        
                        # 图层样式配置
                        st.subheader("🎨 图层样式配置")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            fill_color = st.color_picker("填充颜色", value="#3388ff", key="fill_color_sqlite")
                            fill_opacity = st.slider("填充透明度", 0.0, 1.0, 0.5, key="fill_opacity_sqlite")
                        
                        with col2:
                            line_color = st.color_picker("线条颜色", value="#000000", key="line_color_sqlite")
                            line_width = st.slider("线条宽度", 1, 10, 2, key="line_width_sqlite")
                        
                        with col3:
                            point_radius = st.slider("点要素大小", 1, 20, 5, key="point_radius_sqlite")
                            point_color = st.color_picker("点要素颜色", value="#ff0000", key="point_color_sqlite")
                        
                        # 图层名称
                        layer_name = st.text_input("图层名称", value=selected_table, key="layer_name_sqlite")
                        
                        # 坐标系转换选项
                        st.subheader("🔄 坐标系转换")
                        convert_coords = st.checkbox("自动转换坐标系（WGS84 -> 百度/高德）", value=True, key="convert_coords_sqlite")
                        
                        # 渲染选项
                        st.subheader("⚙️ 渲染选项")
                        render_all = st.checkbox(
                            "全量渲染所有要素（不推荐，可能影响性能）", 
                            value=False,
                            key="render_all_sqlite",
                            help="默认情况下，超过1000个要素的图层仅渲染前1000个以提升性能。勾选此选项将渲染所有要素，但可能导致页面卡顿。"
                        )
                        
                        if st.button("🗺️ 加载到地图", type="primary", key="load_sqlite"):
                            # 存储图层数据
                            # 使用深拷贝确保存储的是原始数据的副本，避免后续转换操作影响原始数据
                            layer_key = f"layer_{len(self.layers)}"
                            self.layers[layer_key] = {
                                'gdf': gdf.copy(deep=True),  # 深拷贝，确保存储原始数据
                                'name': layer_name,
                                'fill_color': fill_color,
                                'fill_opacity': fill_opacity,
                                'line_color': line_color,
                                'line_width': line_width,
                                'point_radius': point_radius,
                                'point_color': point_color,
                                'convert_coords': convert_coords,
                                'attr_columns': attr_columns,
                                'render_all': render_all
                            }
                            st.session_state['layers'] = self.layers
                            
                            # 将新图层添加到顺序列表的末尾
                            if 'layer_order' not in st.session_state:
                                st.session_state['layer_order'] = []
                            st.session_state['layer_order'].append(layer_key)
                            
                            # 计算所有图层的合并边界并更新地图中心点（只在加载图层时计算一次）
                            try:
                                all_bounds = []
                                for layer_data in self.layers.values():
                                    layer_gdf = layer_data['gdf']
                                    bounds = layer_gdf.total_bounds
                                    if bounds is not None and len(bounds) == 4:
                                        all_bounds.append(bounds)
                                
                                if all_bounds:
                                    # 计算所有图层的合并边界
                                    minx = min(b[0] for b in all_bounds)
                                    miny = min(b[1] for b in all_bounds)
                                    maxx = max(b[2] for b in all_bounds)
                                    maxy = max(b[3] for b in all_bounds)
                                    
                                    # 更新中心点
                                    center_lat = (miny + maxy) / 2
                                    center_lon = (minx + maxx) / 2
                                    
                                    # 根据边界范围自动调整缩放级别
                                    lat_range = maxy - miny
                                    lon_range = maxx - minx
                                    max_range = max(lat_range, lon_range)
                                    
                                    # 根据范围估算合适的缩放级别
                                    if max_range > 10:
                                        auto_zoom = 5
                                    elif max_range > 5:
                                        auto_zoom = 6
                                    elif max_range > 2:
                                        auto_zoom = 7
                                    elif max_range > 1:
                                        auto_zoom = 8
                                    elif max_range > 0.5:
                                        auto_zoom = 9
                                    elif max_range > 0.2:
                                        auto_zoom = 10
                                    elif max_range > 0.1:
                                        auto_zoom = 11
                                    elif max_range > 0.05:
                                        auto_zoom = 12
                                    else:
                                        auto_zoom = 13
                                    
                                    # 保存地图中心点和缩放级别（只在值真正变化时才更新，避免浮点数精度导致的微小变化）
                                    # 使用四舍五入到6位小数来避免浮点数精度问题
                                    center_lat_rounded = round(center_lat, 6)
                                    center_lon_rounded = round(center_lon, 6)
                                    
                                    # 只在值真正变化时才更新（避免微小变化导致无限刷新）
                                    should_update = True
                                    if 'map_center_lat' in st.session_state and 'map_center_lon' in st.session_state:
                                        old_lat = round(st.session_state['map_center_lat'], 6)
                                        old_lon = round(st.session_state['map_center_lon'], 6)
                                        if abs(center_lat_rounded - old_lat) < 0.0001 and abs(center_lon_rounded - old_lon) < 0.0001:
                                            should_update = False
                                    
                                    if should_update:
                                        st.session_state['map_center_lat'] = center_lat_rounded
                                        st.session_state['map_center_lon'] = center_lon_rounded
                                        st.session_state['map_auto_zoom'] = auto_zoom
                                        logger.info(f"自动调整地图中心: ({center_lat_rounded}, {center_lon_rounded}), 缩放级别: {auto_zoom}")
                                    else:
                                        logger.debug(f"地图中心点未变化，跳过更新")
                            except Exception as e:
                                logger.warning(f"计算图层边界失败: {str(e)}")
                            
                            st.success(f"✅ 图层 '{layer_name}' 已加载")
                            st.rerun()
                
                conn.close()
                
                # 清理临时文件
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
        
        # 显示地图
        self._render_map(basemap_type, init_lat, init_lon, zoom_level)
    
    def _render_internal_engineering_layer(self, basemap_type, init_lat, init_lon, zoom_level):
        """
        从内置 optimization_toolbox.db 的 engineering_params 表加载工参点图层或扇区图层
        使用经纬度字段 lon/lat 作为点坐标
        """
        from database import DatabaseManager

        st.subheader("📌 内置工参图层（engineering_params）")
        st.caption("直接从内置数据库 `optimization_toolbox.db` 的 `engineering_params` 表读取数据并加载到地图。")

        # 选择图层类型
        layer_type = st.radio(
            "选择图层类型",
            ["点图层", "扇区图层"],
            index=0,
            key="internal_eng_layer_type",
            help="点图层：显示工参点位置；扇区图层：显示扇区覆盖范围（按制式分为不同图层）"
        )

        # 选择简单过滤条件
        col1, col2 = st.columns(2)
        with col1:
            system_filter = st.multiselect(
                "制式过滤（zhishi）",
                options=["4G", "5G"],
                default=[],
                help="为空则不过滤"
            )
        with col2:
            if layer_type == "点图层":
                limit = st.number_input(
                    "最多加载点数量",
                    min_value=100,
                    max_value=100000,
                    value=5000,
                    step=500,
                    help="为保证性能，建议控制在 1 万点以内"
                )
            else:
                limit = st.number_input(
                    "最多加载扇区数量",
                    min_value=100,
                    max_value=50000,
                    value=5000,
                    step=500,
                    help="为保证性能，建议控制在 5 万扇区以内"
                )

        # 图层样式
        st.subheader("🎨 图层样式配置")
        col1, col2, col3 = st.columns(3)
        with col1:
            point_radius = st.slider("点要素大小", 1, 20, 6, key="point_radius_internal_eng")
            point_color = st.color_picker("点要素颜色", value="#ff0000", key="point_color_internal_eng")
        with col2:
            line_color = st.color_picker("轮廓颜色（备用）", value="#000000", key="line_color_internal_eng")
            line_width = st.slider("轮廓宽度（备用）", 1, 10, 2, key="line_width_internal_eng")
        with col3:
            fill_color = st.color_picker("填充颜色（备用）", value="#3388ff", key="fill_color_internal_eng")
            fill_opacity = st.slider("填充透明度（备用）", 0.0, 1.0, 0.5, key="fill_opacity_internal_eng")

        layer_name = st.text_input(
            "图层名称",
            value="内置工参点（engineering_params）",
            key="layer_name_internal_eng"
        )

        st.subheader("🔄 坐标系转换")
        convert_coords = st.checkbox(
            "自动转换坐标系（WGS84 -> 百度/高德）",
            value=True,
            key="convert_coords_internal_eng"
        )

        # 选择弹窗中展示的字段（在加载数据前选择）
        st.subheader("📊 属性字段配置")
        st.caption("选择在地图弹窗中显示的属性字段")
        # 预定义的可用字段列表（基于engineering_params表结构）
        available_columns = ["cgi", "celname", "zhishi", "pinduan", "phy_name", 
                            "ant_dir", "antenna_name", "ant_height", "lon", "lat"]
        default_popup_cols = ["cgi", "celname", "zhishi", "pinduan", "phy_name"]
        attr_columns = st.multiselect(
            "选择属性字段（弹窗展示）",
            options=available_columns,
            default=default_popup_cols,
            key="attr_cols_internal_eng",
            help="选择要在点击地图上的点时显示的属性字段"
        )

        # 点击按钮执行查询并加载到地图
        button_text = "🗺️ 从内置数据库加载扇区图层" if layer_type == "扇区图层" else "🗺️ 从内置数据库加载工参点"
        if st.button(button_text, type="primary", key="load_internal_eng_points"):
            try:
                # 优先使用传入的 db_manager，否则创建一个新的
                db_manager = self.db_manager or DatabaseManager()

                # 构造 SQL（扇区图层需要更多字段）
                if layer_type == "扇区图层":
                    base_sql = """
                        SELECT 
                            cgi,
                            celname,
                            lon,
                            lat,
                            zhishi,
                            pinduan,
                            phy_name,
                            ant_dir,
                            antenna_name,
                            ant_height,
                            site_type
                        FROM engineering_params
                        WHERE lon IS NOT NULL AND lat IS NOT NULL
                        AND ant_dir IS NOT NULL
                    """
                else:
                    base_sql = """
                        SELECT 
                            cgi,
                            celname,
                            lon,
                            lat,
                            zhishi,
                            pinduan,
                            phy_name,
                            ant_dir,
                            antenna_name,
                            ant_height
                        FROM engineering_params
                        WHERE lon IS NOT NULL AND lat IS NOT NULL
                    """
                
                params = []
                if system_filter:
                    placeholders = ",".join(["?"] * len(system_filter))
                    base_sql += f" AND zhishi IN ({placeholders})"
                    params.extend(system_filter)
                base_sql += " LIMIT ?"
                params.append(int(limit))

                spinner_text = "正在从内置数据库读取扇区数据..." if layer_type == "扇区图层" else "正在从内置数据库读取工参点数据..."
                with st.spinner(spinner_text):
                    df = db_manager.get_dataframe(base_sql, tuple(params))

                if df is None or df.empty:
                    st.warning("⚠️ 未查询到有效数据（lon/lat 为空或过滤条件过严）。")
                    return

                    # 处理经纬度字段
                try:
                    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
                    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
                    # 验证经纬度范围
                    df = df.dropna(subset=["lon", "lat"])
                    df = df[(df["lon"] >= -180) & (df["lon"] <= 180) & 
                           (df["lat"] >= -90) & (df["lat"] <= 90)]
                except Exception as e:
                    st.error(f"❌ 处理经纬度字段失败: {e}")
                    return

                if df.empty:
                    st.warning("⚠️ 经纬度转换后没有有效数据。请检查 engineering_params 表中的 lon 和 lat 字段。")
                    return
                
                # 显示数据统计信息
                st.info(f"📊 数据统计: 有效记录 {len(df):,} 条")

                if layer_type == "扇区图层":
                    # 生成扇区图层
                    st.info(f"📊 开始处理 {len(df):,} 条记录...")
                    
                    # 处理方位角
                    df["ant_dir"] = pd.to_numeric(df["ant_dir"], errors="coerce")
                    df_before = len(df)
                    df = df.dropna(subset=["ant_dir"])
                    df_after = len(df)
                    
                    if df_before > df_after:
                        st.warning(f"⚠️ 过滤掉 {df_before - df_after} 条无方位角的记录。")
                    
                    if df.empty:
                        st.error("❌ 方位角数据无效，无法生成扇区图层。请确保 engineering_params 表中的 ant_dir 字段有有效数据。")
                        return
                    
                    st.info(f"✅ 有效记录数: {len(df):,} 条")
                    
                    # 计算扇区参数
                    with st.spinner("正在计算扇区参数（波瓣角度和半径）..."):
                        df["beam"] = df.apply(self.calculate_sector_beam, axis=1)
                        df["radius"] = df.apply(self.calculate_sector_radius, axis=1)
                        st.info(f"📐 扇区参数计算完成，平均波瓣角度: {df['beam'].mean():.1f}度，平均半径: {df['radius'].mean():.1f}米")
                    
                    # 生成扇形几何
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    geometries = []
                    valid_indices = []
                    error_count = 0
                    
                    total_rows = len(df)
                    for idx, (row_idx, row) in enumerate(df.iterrows()):
                        if idx % 100 == 0:
                            progress = (idx + 1) / total_rows
                            safe_progress = min(1.0, max(0.0, progress))
                            progress_bar.progress(safe_progress)
                            status_text.text(f"正在生成扇区几何: {idx + 1}/{total_rows} ({int(safe_progress*100)}%)")
                        
                        try:
                            sector = self.create_sector_polygon(
                                row["lon"],
                                row["lat"],
                                row["ant_dir"],
                                row["beam"],
                                row["radius"]
                            )
                            if sector is not None and not sector.is_empty:
                                geometries.append(sector)
                                valid_indices.append(row_idx)
                            else:
                                error_count += 1
                        except Exception as e:
                            error_count += 1
                            if error_count <= 5:  # 只显示前5个错误
                                logger.warning(f"生成扇区失败 (CGI: {row.get('cgi', 'unknown')}): {e}")
                            continue
                    
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ 扇区几何生成完成")
                    
                    if error_count > 0:
                        st.warning(f"⚠️ 有 {error_count} 个扇区生成失败，已跳过。")
                    
                    if not geometries:
                        st.error("❌ 无法生成任何扇区几何。可能的原因：\n"
                                "1. 方位角数据异常\n"
                                "2. 经纬度数据异常\n"
                                "3. 扇区参数计算错误\n"
                                "请检查 engineering_params 表中的数据。")
                        return
                    
                    # 创建 GeoDataFrame（只包含有效的扇区）
                    df_valid = df.loc[valid_indices].copy()
                    gdf = gpd.GeoDataFrame(df_valid, geometry=geometries, crs="EPSG:4326")
                    
                    st.success(f"✅ 已从内置数据库生成 {len(gdf):,} 个扇区（成功率: {len(gdf)/total_rows*100:.1f}%）。")
                    
                    # 按制式分组创建不同的图层
                    if "layer_order" not in st.session_state:
                        st.session_state["layer_order"] = []
                    
                    # 获取所有制式
                    zhishi_list = []
                    if "zhishi" in gdf.columns:
                        zhishi_list = [z for z in gdf["zhishi"].unique().tolist() 
                                     if pd.notna(z) and str(z).strip() != '']
                    
                    if not zhishi_list:
                        st.warning("⚠️ 未找到有效的制式信息（zhishi字段），将创建单一图层。")
                        zhishi_list = ["未知"]
                    
                    layers_created = 0
                    for zhishi_val in zhishi_list:
                        # 筛选该制式的扇区
                        if zhishi_val == "未知":
                            gdf_subset = gdf.copy()
                        else:
                            gdf_subset = gdf[gdf["zhishi"] == zhishi_val].copy()
                        
                        if len(gdf_subset) == 0:
                            continue
                        
                        # 为不同制式设置不同颜色
                        if zhishi_val == "5G":
                            layer_color = "#ff0000"  # 红色
                        elif zhishi_val == "4G":
                            layer_color = "#0000ff"  # 蓝色
                        else:
                            layer_color = fill_color
                        
                        layer_key = f"layer_{len(self.layers)}"
                        layer_name_zhishi = f"{layer_name} - {zhishi_val}" if zhishi_val != "未知" else layer_name
                        
                        self.layers[layer_key] = {
                            "gdf": gdf_subset.copy(deep=True),
                            "name": layer_name_zhishi,
                            "fill_color": layer_color,
                            "fill_opacity": fill_opacity,
                            "line_color": line_color,
                            "line_width": line_width,
                            "point_radius": point_radius,
                            "point_color": point_color,
                            "convert_coords": convert_coords,
                            "attr_columns": attr_columns,
                            "render_all": True
                        }
                        st.session_state["layer_order"].append(layer_key)
                        layers_created += 1
                        st.info(f"  ✓ 已创建 {zhishi_val} 图层: {len(gdf_subset):,} 个扇区")
                    
                    if layers_created == 0:
                        st.error("❌ 未能创建任何图层，请检查数据。")
                        return
                    
                    st.session_state["layers"] = self.layers
                    
                    # 更新地图中心
                    try:
                        bounds = gdf.total_bounds
                        if bounds is not None and len(bounds) == 4:
                            minx, miny, maxx, maxy = bounds
                            center_lat = (miny + maxy) / 2
                            center_lon = (minx + maxx) / 2
                            lat_range = maxy - miny
                            lon_range = maxx - minx
                            max_range = max(lat_range, lon_range)

                            if max_range > 10:
                                auto_zoom = 5
                            elif max_range > 5:
                                auto_zoom = 6
                            elif max_range > 2:
                                auto_zoom = 7
                            elif max_range > 1:
                                auto_zoom = 8
                            elif max_range > 0.5:
                                auto_zoom = 9
                            elif max_range > 0.2:
                                auto_zoom = 10
                            elif max_range > 0.1:
                                auto_zoom = 11
                            elif max_range > 0.05:
                                auto_zoom = 12
                            else:
                                auto_zoom = 13

                            st.session_state["map_center_lat"] = round(center_lat, 6)
                            st.session_state["map_center_lon"] = round(center_lon, 6)
                            st.session_state["map_auto_zoom"] = auto_zoom
                    except Exception as e:
                        logger.warning(f"根据扇区更新地图中心失败: {e}")
                    
                        st.success(f"✅ 扇区图层已加载到地图（共 {len(zhishi_list)} 个制式图层）。")
                    
                else:
                    # 生成点图层（原有逻辑）
                    gdf = gpd.GeoDataFrame(
                        df,
                        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
                        crs="EPSG:4326"
                    )

                    st.success(f"✅ 已从内置数据库加载 {len(gdf):,} 个工参点。")

                    # 存储图层数据
                    layer_key = f"layer_{len(self.layers)}"
                    self.layers[layer_key] = {
                        "gdf": gdf.copy(deep=True),
                        "name": layer_name,
                        "fill_color": fill_color,
                        "fill_opacity": fill_opacity,
                        "line_color": line_color,
                        "line_width": line_width,
                        "point_radius": point_radius,
                        "point_color": point_color,
                        "convert_coords": convert_coords,
                        "attr_columns": attr_columns,
                        "render_all": True  # 内置点图层通常数据量有限，默认全量渲染
                    }
                    st.session_state["layers"] = self.layers

                    # 维护图层顺序
                    if "layer_order" not in st.session_state:
                        st.session_state["layer_order"] = []
                    st.session_state["layer_order"].append(layer_key)

                    # 根据该图层更新地图中心和缩放
                    try:
                        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
                        if bounds is not None and len(bounds) == 4:
                            minx, miny, maxx, maxy = bounds
                            center_lat = (miny + maxy) / 2
                            center_lon = (minx + maxx) / 2
                            lat_range = maxy - miny
                            lon_range = maxx - minx
                            max_range = max(lat_range, lon_range)

                            if max_range > 10:
                                auto_zoom = 5
                            elif max_range > 5:
                                auto_zoom = 6
                            elif max_range > 2:
                                auto_zoom = 7
                            elif max_range > 1:
                                auto_zoom = 8
                            elif max_range > 0.5:
                                auto_zoom = 9
                            elif max_range > 0.2:
                                auto_zoom = 10
                            elif max_range > 0.1:
                                auto_zoom = 11
                            elif max_range > 0.05:
                                auto_zoom = 12
                            else:
                                auto_zoom = 13

                            st.session_state["map_center_lat"] = round(center_lat, 6)
                            st.session_state["map_center_lon"] = round(center_lon, 6)
                            st.session_state["map_auto_zoom"] = auto_zoom
                    except Exception as e:
                        logger.warning(f"根据工参点更新地图中心失败: {e}")

                    st.success(f"✅ 图层 '{layer_name}' 已加载到地图。")

                st.rerun()

            except Exception as e:
                error_msg = "加载扇区图层失败" if layer_type == "扇区图层" else "加载工参点失败"
                st.error(f"❌ 从内置数据库{error_msg}: {e}")
                logger.error(f"加载内置工程参数图层失败: {e}", exc_info=True)
                import traceback
                st.error(f"详细错误信息:\n```\n{traceback.format_exc()}\n```")
                logger.error(traceback.format_exc())
        
        # 显示地图（如果有图层）
        if 'layers' in st.session_state and st.session_state['layers']:
            self._render_map(basemap_type, init_lat, init_lon, zoom_level)
        else:
            st.info("💡 请先加载图层数据，地图将在加载图层后显示。")
    
    def _render_map(self, basemap_type, init_lat, init_lon, zoom_level):
        """渲染地图"""
        st.markdown("---")
        st.subheader("🗺️ 地图视图")
        
        # 快速定位输入框
        with st.container():
            st.markdown("**📍 快速定位**")
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            
            with col1:
                quick_lat = st.text_input(
                    "纬度",
                    value="",
                    key="quick_lat_input",
                    placeholder="例如: 21.85919070",
                    help="输入纬度（-90 到 90）"
                )
            
            with col2:
                quick_lon = st.text_input(
                    "经度",
                    value="",
                    key="quick_lon_input",
                    placeholder="例如: 111.97884194",
                    help="输入经度（-180 到 180）"
                )
            
            with col3:
                if st.button("📍 定位", key="quick_locate_button", use_container_width=True):
                    try:
                        if quick_lat and quick_lon:
                            lat = float(quick_lat.strip())
                            lon = float(quick_lon.strip())
                            
                            # 验证经纬度范围
                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                # 保存定位信息到 session_state
                                st.session_state['locate_lat'] = lat
                                st.session_state['locate_lon'] = lon
                                # 更新地图中心点
                                st.session_state['map_center_lat'] = lat
                                st.session_state['map_center_lon'] = lon
                                st.session_state['map_auto_zoom'] = 15
                                st.success(f"✅ 已定位到: 纬度 {lat:.6f}, 经度 {lon:.6f}")
                                st.rerun()
                            else:
                                st.error("❌ 经纬度范围无效！纬度应在 -90 到 90 之间，经度应在 -180 到 180 之间。")
                        else:
                            st.warning("⚠️ 请输入纬度和经度")
                    except ValueError:
                        st.error("❌ 请输入有效的数字格式")
            
            with col4:
                if 'locate_lat' in st.session_state and 'locate_lon' in st.session_state:
                    if st.button("🗑️ 清除", key="quick_clear_button", use_container_width=True):
                        if 'locate_lat' in st.session_state:
                            del st.session_state['locate_lat']
                        if 'locate_lon' in st.session_state:
                            del st.session_state['locate_lon']
                        st.success("✅ 已清除定位标记")
                        st.rerun()
        
        st.markdown("---")
        
        # 图层控制
        if 'layers' in st.session_state and st.session_state['layers']:
            st.write("**已加载图层**:")
            
            # 初始化图层顺序（如果不存在）
            if 'layer_order' not in st.session_state:
                st.session_state['layer_order'] = list(st.session_state['layers'].keys())
            
            # 确保图层顺序包含所有图层（处理新增图层的情况）
            current_layers = set(st.session_state['layers'].keys())
            current_order = set(st.session_state['layer_order'])
            if current_layers != current_order:
                # 添加新图层到顺序列表的末尾
                for layer_key in current_layers:
                    if layer_key not in st.session_state['layer_order']:
                        st.session_state['layer_order'].append(layer_key)
                # 移除已删除的图层
                st.session_state['layer_order'] = [
                    k for k in st.session_state['layer_order'] 
                    if k in current_layers
                ]
            
            # 按照顺序显示图层
            layer_order = st.session_state['layer_order']
            for idx, layer_key in enumerate(layer_order):
                if layer_key not in st.session_state['layers']:
                    continue
                    
                layer_data = st.session_state['layers'][layer_key]
                
                # 创建列布局：图层信息、上移、下移、置顶、置底、删除
                col1, col2, col3, col4, col5, col6 = st.columns([4, 1, 1, 1, 1, 1])
                
                with col1:
                    # 显示图层序号和名称
                    st.write(f"**{idx + 1}.** {layer_data['name']} ({len(layer_data['gdf']):,} 个要素)")
                
                with col2:
                    # 上移按钮（第一个图层不能上移）
                    if idx > 0:
                        if st.button("⬆️", key=f"up_{idx}_{layer_key}", help="上移一层"):
                            # 交换当前图层和上一个图层的位置
                            st.session_state['layer_order'][idx], st.session_state['layer_order'][idx - 1] = \
                                st.session_state['layer_order'][idx - 1], st.session_state['layer_order'][idx]
                            st.rerun()
                    else:
                        st.write("")  # 占位，保持对齐
                
                with col3:
                    # 下移按钮（最后一个图层不能下移）
                    if idx < len(layer_order) - 1:
                        if st.button("⬇️", key=f"down_{idx}_{layer_key}", help="下移一层"):
                            # 交换当前图层和下一个图层的位置
                            st.session_state['layer_order'][idx], st.session_state['layer_order'][idx + 1] = \
                                st.session_state['layer_order'][idx + 1], st.session_state['layer_order'][idx]
                            st.rerun()
                    else:
                        st.write("")  # 占位，保持对齐
                
                with col4:
                    # 置顶按钮（第一个图层不能置顶）
                    if idx > 0:
                        if st.button("🔝", key=f"top_{idx}_{layer_key}", help="置顶"):
                            # 将图层移到最前面
                            st.session_state['layer_order'].pop(idx)
                            st.session_state['layer_order'].insert(0, layer_key)
                            st.rerun()
                    else:
                        st.write("")  # 占位，保持对齐
                
                with col5:
                    # 置底按钮（最后一个图层不能置底）
                    if idx < len(layer_order) - 1:
                        if st.button("🔽", key=f"bottom_{idx}_{layer_key}", help="置底"):
                            # 将图层移到最后面
                            st.session_state['layer_order'].pop(idx)
                            st.session_state['layer_order'].append(layer_key)
                            st.rerun()
                    else:
                        st.write("")  # 占位，保持对齐
                
                with col6:
                    # 删除按钮
                    if st.button("🗑️", key=f"del_{idx}_{layer_key}", help="删除图层"):
                        del st.session_state['layers'][layer_key]
                        # 从顺序列表中移除
                        if layer_key in st.session_state['layer_order']:
                            st.session_state['layer_order'].remove(layer_key)
                        
                        # 删除图层后，重新计算所有图层的合并边界
                        if st.session_state['layers']:
                            try:
                                all_bounds = []
                                for layer_data in st.session_state['layers'].values():
                                    layer_gdf = layer_data['gdf']
                                    bounds = layer_gdf.total_bounds
                                    if bounds is not None and len(bounds) == 4:
                                        all_bounds.append(bounds)
                                
                                if all_bounds:
                                    minx = min(b[0] for b in all_bounds)
                                    miny = min(b[1] for b in all_bounds)
                                    maxx = max(b[2] for b in all_bounds)
                                    maxy = max(b[3] for b in all_bounds)
                                    center_lat = (miny + maxy) / 2
                                    center_lon = (minx + maxx) / 2
                                    lat_range = maxy - miny
                                    lon_range = maxx - minx
                                    max_range = max(lat_range, lon_range)
                                    
                                    if max_range > 10:
                                        auto_zoom = 5
                                    elif max_range > 5:
                                        auto_zoom = 6
                                    elif max_range > 2:
                                        auto_zoom = 7
                                    elif max_range > 1:
                                        auto_zoom = 8
                                    elif max_range > 0.5:
                                        auto_zoom = 9
                                    elif max_range > 0.2:
                                        auto_zoom = 10
                                    elif max_range > 0.1:
                                        auto_zoom = 11
                                    elif max_range > 0.05:
                                        auto_zoom = 12
                                    else:
                                        auto_zoom = 13
                                    
                                    # 使用四舍五入到6位小数来避免浮点数精度问题
                                    center_lat_rounded = round(center_lat, 6)
                                    center_lon_rounded = round(center_lon, 6)
                                    
                                    st.session_state['map_center_lat'] = center_lat_rounded
                                    st.session_state['map_center_lon'] = center_lon_rounded
                                    st.session_state['map_auto_zoom'] = auto_zoom
                            except Exception as e:
                                logger.warning(f"重新计算地图中心点失败: {str(e)}")
                        else:
                            # 如果没有图层了，清除地图中心点
                            if 'map_center_lat' in st.session_state:
                                del st.session_state['map_center_lat']
                            if 'map_center_lon' in st.session_state:
                                del st.session_state['map_center_lon']
                            if 'map_auto_zoom' in st.session_state:
                                del st.session_state['map_auto_zoom']
                        st.rerun()
            
            # 如果有图层，使用已保存的地图中心点（避免重复计算导致无限刷新）
            # 地图中心点应该在加载图层时计算并保存，而不是每次渲染时都计算
            if 'map_center_lat' in st.session_state and 'map_center_lon' in st.session_state:
                init_lat = st.session_state['map_center_lat']
                init_lon = st.session_state['map_center_lon']
                if 'map_auto_zoom' in st.session_state:
                    zoom_level = st.session_state['map_auto_zoom']
                logger.debug(f"使用已保存的地图中心: ({init_lat}, {init_lon}), 缩放级别: {zoom_level}")
        
        # 创建地图
        if basemap_type.startswith("百度"):
            # 百度地图
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles=None
            )
            # 注意：百度地图需要 API Key，这里使用 OpenStreetMap 作为替代
            folium.TileLayer('OpenStreetMap', name='底图').add_to(m)
        elif basemap_type.startswith("高德"):
            # 高德地图
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles=None
            )
            # 注意：高德地图需要 API Key，这里使用 OpenStreetMap 作为替代
            folium.TileLayer('OpenStreetMap', name='底图').add_to(m)
        elif basemap_type == "Google地图":
            # Google 普通地图
            # Google 地图使用 WGS84 坐标系，不需要坐标转换
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles='https://mt0.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',  # Google普通地图瓦片URL (m=普通图)
                attr='Google Maps',
                max_zoom=20,
                min_zoom=3
            )
        elif basemap_type == "GEO卫星地图":
            # GEO 卫星地图（Google 瓦片镜像，使用 WGS84 坐标系）
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles="https://gac-geo.googlecnapps.club/maps/vt?lyrs=s&x={x}&y={y}&z={z}&src=app&scale=2&from=app",
                attr="GEO Satellite",
                max_zoom=20,
                min_zoom=3,
            )
        elif basemap_type == "Google卫星地图":
            # Google 卫星地图（官方服务，可能需要特殊网络环境）
            # Google 卫星地图使用 WGS84 坐标系，不需要坐标转换
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles='https://mt0.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',  # Google卫星地图瓦片URL (s=卫星图)
                attr='Google Maps',
                max_zoom=20,
                min_zoom=3
            )
        elif basemap_type == "GMCC地图":
            # GMCC 地图瓦片服务
            # 使用 WGS84 坐标系
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles=None
            )
            folium.TileLayer(
                tiles='https://nqi.gmcc.net:20443/tiles/{z}/{x}/{y}.png',
                attr='GMCC Map',
                name='GMCC地图',
                max_zoom=20,
                min_zoom=3,
                overlay=False
            ).add_to(m)
        elif basemap_type == "Bing地图":
            # Bing Maps 瓦片服务（Virtual Earth）
            # 使用 QuadKey 格式，需要特殊处理
            # Bing Maps 使用 WGS84 坐标系
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level,
                tiles=None
            )
            # 使用 JavaScript 注入方式添加 Bing Maps 图层
            add_bing_tile_layer(
                m,
                tiles_url='http://ecn.t3.tiles.virtualearth.net/tiles/a{q}.jpeg?g=1',
                attr='Bing Maps',
                max_zoom=19,
                min_zoom=1
            )
        else:
            # OpenStreetMap
            m = folium.Map(
                location=[init_lat, init_lon],
                zoom_start=zoom_level
            )
        
        # 添加图层（按照图层顺序添加，后面的图层会覆盖前面的图层）
        if 'layers' in st.session_state and st.session_state['layers']:
            # 按照图层顺序添加图层
            if 'layer_order' in st.session_state:
                # 按照顺序添加图层
                for layer_key in st.session_state['layer_order']:
                    if layer_key in st.session_state['layers']:
                        layer_data = st.session_state['layers'][layer_key]
                        self._add_layer_to_map(m, layer_data, basemap_type)
            else:
                # 如果没有顺序列表，使用默认顺序（字典顺序）
                for layer_key, layer_data in st.session_state['layers'].items():
                    self._add_layer_to_map(m, layer_data, basemap_type)
        
        # 添加定位标记（如果用户进行了定位）
        if 'locate_lat' in st.session_state and 'locate_lon' in st.session_state:
            locate_lat = st.session_state['locate_lat']
            locate_lon = st.session_state['locate_lon']
            
            # 根据底图类型决定是否需要坐标转换
            if basemap_type.startswith("百度"):
                # 百度地图需要 BD09 坐标系
                # 假设用户输入的是 WGS84 坐标，需要转换
                locate_lon, locate_lat = CoordinateConverter.wgs84_to_bd09(locate_lon, locate_lat)
            elif basemap_type.startswith("高德"):
                # 高德地图需要 GCJ02 坐标系
                # 假设用户输入的是 WGS84 坐标，需要转换
                locate_lon, locate_lat = CoordinateConverter.wgs84_to_gcj02(locate_lon, locate_lat)
            # Google 地图和 OpenStreetMap 使用 WGS84，不需要转换
            
            # 添加定位标记
            folium.Marker(
                location=[locate_lat, locate_lon],
                popup=folium.Popup(
                    f"📍 定位位置<br>纬度: {st.session_state['locate_lat']:.6f}<br>经度: {st.session_state['locate_lon']:.6f}",
                    max_width=200
                ),
                icon=folium.Icon(color='red', icon='info-sign', prefix='glyphicon')
            ).add_to(m)
            
            # 添加一个圆形标记以更清晰地显示位置
            folium.CircleMarker(
                location=[locate_lat, locate_lon],
                radius=10,
                popup=folium.Popup(
                    f"📍 定位位置<br>纬度: {st.session_state['locate_lat']:.6f}<br>经度: {st.session_state['locate_lon']:.6f}",
                    max_width=200
                ),
                color='red',
                fill=True,
                fillColor='red',
                fillOpacity=0.6,
                weight=2
            ).add_to(m)
        
        # 添加控件
        folium.plugins.Fullscreen().add_to(m)
        folium.plugins.MeasureControl().add_to(m)
        folium.plugins.Draw(export=True).add_to(m)
        
        # 添加图层控制
        folium.LayerControl().add_to(m)
        
        # 显示地图
        # 关键修复：完全避免地图状态变化导致闪退
        # 问题根源：st_folium 返回的字典如果内容发生变化（如 zoom、center），Streamlit 会检测到并触发重新渲染
        # 解决方案：使用 st_folium 的参数来最小化状态返回，并完全忽略状态变化
        
        # 使用稳定的参数配置
        try:
            # 使用 returned_objects 只返回点击事件，return_on_hover=False 避免悬停事件
            map_data = st_folium(
                m, 
                width=1200, 
                height=600, 
                key="main_map",
                returned_objects=["last_object_clicked"],  # 只返回点击事件
                return_on_hover=False,  # 禁用悬停事件，避免触发重新渲染
                use_container_width=False  # 使用固定宽度，避免容器变化
            )
        except (TypeError, AttributeError, ValueError) as e:
            # 如果某些参数不支持，使用最小配置
            logger.warning(f"st_folium 参数错误: {str(e)}，使用最小配置")
            try:
                map_data = st_folium(
                    m, 
                    width=1200, 
                    height=600, 
                    key="main_map",
                    returned_objects=["last_object_clicked"]
                )
            except:
                map_data = st_folium(m, width=1200, height=600, key="main_map")
        
        # 关键修复：完全忽略地图状态变化
        # 即使 map_data 包含 zoom、center、bounds 等状态，我们也不读取、不保存、不使用
        # 只处理点击事件，其他状态完全忽略
        if map_data:
            clicked = map_data.get('last_object_clicked')
            
            # 只处理点击事件
            if clicked:
                # 检查是否是新的点击（避免重复处理）
                last_click_key = st.session_state.get('last_map_click_key')
                current_click_key = f"{clicked.get('lat', 0):.6f}_{clicked.get('lng', 0):.6f}"
                
                if last_click_key != current_click_key:
                    st.session_state['last_map_click_key'] = current_click_key
                    # 显示点击信息（使用 st.empty() 避免重复创建）
                    if 'map_click_info' not in st.session_state:
                        st.session_state['map_click_info'] = st.empty()
                    st.session_state['map_click_info'].info(
                        f"📍 点击位置: 纬度 {clicked.get('lat', 0):.6f}, 经度 {clicked.get('lng', 0):.6f}"
                    )
            
            # 重要：完全不读取 map_data 中的其他任何状态
            # 包括但不限于：
            # - 'zoom': 缩放级别（用户缩放地图时会变化，导致重新渲染和闪退）
            # - 'center': 地图中心点（用户拖拽地图时会变化，导致重新渲染和闪退）
            # - 'bounds': 地图边界（用户缩放/拖拽时会变化，导致重新渲染和闪退）
            # - 'last_clicked': 最后点击的位置（可能包含更多信息）
            # - 'all_drawings': 所有绘制的图形
            # 这些状态的变化会导致 Streamlit 检测到状态变化并触发重新渲染，导致地图闪退
            # 我们只处理 'last_object_clicked'，其他状态完全忽略
    
    def _add_layer_to_map(self, m, layer_data, basemap_type="OpenStreetMap"):
        """添加图层到地图"""
        # 获取原始数据（深拷贝，避免修改原始数据）
        gdf = layer_data['gdf'].copy(deep=True)
        layer_name = layer_data['name']
        fill_color = layer_data['fill_color']
        fill_opacity = layer_data['fill_opacity']
        line_color = layer_data['line_color']
        line_width = layer_data['line_width']
        point_radius = layer_data['point_radius']
        point_color = layer_data['point_color']
        convert_coords = layer_data.get('convert_coords', False)
        attr_columns = layer_data.get('attr_columns', [])
        
        # 创建要素组
        feature_group = folium.FeatureGroup(name=layer_name)
        
        # 根据用户选择决定是否限制要素数量
        render_all = layer_data.get('render_all', False)
        max_features = 1000  # 默认最多渲染1000个要素
        
        # 使用 session_state 缓存警告信息，避免每次渲染都显示
        warning_key = f"render_warning_{layer_name}"
        if not render_all and len(gdf) > max_features:
            if warning_key not in st.session_state:
                st.session_state[warning_key] = True
                st.warning(f"⚠️ 图层包含 {len(gdf):,} 个要素，为提升性能，仅渲染前 {max_features:,} 个要素。如需全量渲染，请在加载图层时勾选'全量渲染所有要素'选项。")
            gdf = gdf.head(max_features)
        elif render_all and len(gdf) > max_features:
            if f"{warning_key}_all" not in st.session_state:
                st.session_state[f"{warning_key}_all"] = True
                st.info(f"ℹ️ 图层包含 {len(gdf):,} 个要素，将全量渲染。这可能需要较长时间，请耐心等待...")
        
        # 批量处理坐标系转换（如果启用）
        # 使用 WGS84 坐标系的底图（Google/GEO），直接使用原始坐标，不进行任何转换
        # 使用缓存避免重复转换
        convert_cache_key = f"convert_cache_{layer_name}_{basemap_type}"
        
        # Google/GEO 地图使用 WGS84，直接使用原始坐标
        if basemap_type.startswith("Google") or basemap_type.startswith("GEO"):
            # 确保使用原始数据，不使用任何转换缓存
            if basemap_type.startswith("GEO"):
                map_type_name = "GEO卫星地图"
            else:
                map_type_name = "Google卫星地图" if basemap_type == "Google卫星地图" else "Google地图"
            logger.info(f"🗺️ {map_type_name}使用 WGS84 坐标系，跳过坐标转换: {layer_name} (要素数量: {len(gdf)})")
            # 清除可能存在的转换缓存，确保使用原始数据
            if convert_cache_key in st.session_state:
                logger.debug(f"清除转换缓存: {convert_cache_key}")
                del st.session_state[convert_cache_key]
            # 确保 convert_coords 标志在 Google 地图时被忽略
            convert_coords = False
        elif convert_coords:
            # 非 Google 地图且启用了坐标转换
            if convert_cache_key in st.session_state:
                gdf = st.session_state[convert_cache_key]
                logger.debug(f"使用缓存的转换结果: {layer_name}")
            else:
                with st.spinner("正在转换坐标系..."):
                    gdf = self._batch_convert_coordinates(gdf, basemap_type)
                    st.session_state[convert_cache_key] = gdf
        
        # 遍历要素（只在第一次渲染时显示进度条）
        progress_bar = None
        status_text = None
        progress_key = f"progress_{layer_name}"
        if len(gdf) > 100 and progress_key not in st.session_state:
            st.session_state[progress_key] = True
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        for idx, row in gdf.iterrows():
            if progress_bar and idx % 50 == 0:
                progress = (idx + 1) / len(gdf)
                safe_progress = min(1.0, max(0.0, progress))
                progress_bar.progress(safe_progress)
                if status_text:
                    status_text.text(f"正在渲染要素 {idx + 1}/{len(gdf)}...")
            
            geom = row.geometry
            
            # 对于非点要素，如果启用了坐标系转换，需要逐个转换
            # 点要素已在批量转换中处理
            # Google 地图使用 WGS84 坐标系，不需要转换
            if convert_coords and geom.geom_type != 'Point' and not basemap_type.startswith("Google"):
                if basemap_type.startswith("百度"):
                    # 转换为百度坐标系（仅对非点要素）
                    # 注意：geom.coords 返回的是 (x, y) 即 (lon, lat)
                    # wgs84_to_bd09 返回的是 (lon, lat) 元组
                    if geom.geom_type in ['LineString', 'MultiLineString']:
                        if geom.geom_type == 'LineString':
                            # p[0] 是 lon, p[1] 是 lat; wgs84_to_bd09 返回 (lon, lat)
                            coords = [CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in geom.coords]
                            geom = LineString(coords)
                        else:
                            lines = [LineString([CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in line.coords]) 
                                    for line in geom.geoms]
                            geom = MultiLineString(lines)
                    elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                        if geom.geom_type == 'Polygon':
                            # 转换外环
                            exterior = [CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in geom.exterior.coords]
                            # 转换内环
                            interiors = [[CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in interior.coords] 
                                        for interior in geom.interiors]
                            geom = Polygon(exterior, interiors)
                        else:
                            polygons = []
                            for poly in geom.geoms:
                                exterior = [CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in poly.exterior.coords]
                                interiors = [[CoordinateConverter.wgs84_to_bd09(p[0], p[1]) for p in interior.coords] 
                                            for interior in poly.interiors]
                                polygons.append(Polygon(exterior, interiors))
                            geom = MultiPolygon(polygons)
                elif basemap_type.startswith("高德"):
                    # 转换为高德坐标系（仅对非点要素）
                    # p[0] 是 lon, p[1] 是 lat; wgs84_to_gcj02 返回 (lon, lat)
                    if geom.geom_type in ['LineString', 'MultiLineString']:
                        if geom.geom_type == 'LineString':
                            coords = [CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in geom.coords]
                            geom = LineString(coords)
                        else:
                            lines = [LineString([CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in line.coords]) 
                                    for line in geom.geoms]
                            geom = MultiLineString(lines)
                    elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                        if geom.geom_type == 'Polygon':
                            # 转换外环
                            exterior = [CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in geom.exterior.coords]
                            # 转换内环
                            interiors = [[CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in interior.coords] 
                                        for interior in geom.interiors]
                            geom = Polygon(exterior, interiors)
                        else:
                            polygons = []
                            for poly in geom.geoms:
                                exterior = [CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in poly.exterior.coords]
                                interiors = [[CoordinateConverter.wgs84_to_gcj02(p[0], p[1]) for p in interior.coords] 
                                            for interior in poly.interiors]
                                polygons.append(Polygon(exterior, interiors))
                            geom = MultiPolygon(polygons)
            
            # 根据几何类型添加要素
            if geom.geom_type == 'Point':
                # 点要素
                popup_html = self._create_popup_html(row, attr_columns)
                folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=point_radius,
                    popup=folium.Popup(popup_html, max_width=300),
                    color=point_color,
                    fill=True,
                    fillColor=point_color,
                    fillOpacity=0.8
                ).add_to(feature_group)
            
            elif geom.geom_type in ['LineString', 'MultiLineString']:
                # 线要素
                popup_html = self._create_popup_html(row, attr_columns)
                if geom.geom_type == 'LineString':
                    folium.Polyline(
                        locations=[[point[1], point[0]] for point in geom.coords],
                        popup=folium.Popup(popup_html, max_width=300),
                        color=line_color,
                        weight=line_width
                    ).add_to(feature_group)
                else:
                    for line in geom.geoms:
                        folium.Polyline(
                            locations=[[point[1], point[0]] for point in line.coords],
                            popup=folium.Popup(popup_html, max_width=300),
                            color=line_color,
                            weight=line_width
                        ).add_to(feature_group)
            
            elif geom.geom_type in ['Polygon', 'MultiPolygon']:
                # 面要素
                popup_html = self._create_popup_html(row, attr_columns)
                if geom.geom_type == 'Polygon':
                    folium.Polygon(
                        locations=[[point[1], point[0]] for point in geom.exterior.coords],
                        popup=folium.Popup(popup_html, max_width=300),
                        color=line_color,
                        weight=line_width,
                        fill=True,
                        fillColor=fill_color,
                        fillOpacity=fill_opacity
                    ).add_to(feature_group)
                else:
                    for poly in geom.geoms:
                        folium.Polygon(
                            locations=[[point[1], point[0]] for point in poly.exterior.coords],
                            popup=folium.Popup(popup_html, max_width=300),
                            color=line_color,
                            weight=line_width,
                            fill=True,
                            fillColor=fill_color,
                            fillOpacity=fill_opacity
                        ).add_to(feature_group)
        
        # 添加到地图
        feature_group.add_to(m)
        
        if progress_bar:
            progress_bar.progress(1.0)
            if status_text:
                status_text.text("✅ 图层渲染完成")
    
    def _batch_convert_coordinates(self, gdf, basemap_type):
        """批量转换坐标系（优化性能）"""
        try:
            # Google 地图使用 WGS84 坐标系，不需要转换
            if basemap_type.startswith("Google"):
                logger.debug("Google 地图使用 WGS84 坐标系，跳过坐标转换")
                return gdf
            elif basemap_type.startswith("百度"):
                # 批量转换为百度坐标系
                def convert_geom(geom):
                    if geom is None or geom.is_empty:
                        return geom
                    if geom.geom_type == 'Point':
                        lon, lat = geom.x, geom.y
                        lon, lat = CoordinateConverter.wgs84_to_bd09(lon, lat)
                        return Point(lon, lat)
                    # 对于复杂几何，暂时跳过批量转换，在渲染时逐个处理
                    # 这样可以避免处理大量复杂几何时的性能问题
                    return geom
                # 只对点要素进行批量转换，复杂几何在渲染时处理
                point_mask = gdf.geometry.type == 'Point'
                if point_mask.any():
                    gdf.loc[point_mask, 'geometry'] = gdf.loc[point_mask, 'geometry'].apply(convert_geom)
            elif basemap_type.startswith("高德"):
                # 批量转换为高德坐标系
                def convert_geom(geom):
                    if geom is None or geom.is_empty:
                        return geom
                    if geom.geom_type == 'Point':
                        lon, lat = geom.x, geom.y
                        lon, lat = CoordinateConverter.wgs84_to_gcj02(lon, lat)
                        return Point(lon, lat)
                    return geom
                # 只对点要素进行批量转换
                point_mask = gdf.geometry.type == 'Point'
                if point_mask.any():
                    gdf.loc[point_mask, 'geometry'] = gdf.loc[point_mask, 'geometry'].apply(convert_geom)
            return gdf
        except Exception as e:
            logger.warning(f"批量坐标系转换失败，将使用原始坐标: {str(e)}")
            return gdf
    
    def _create_popup_html(self, row, attr_columns):
        """创建弹窗 HTML"""
        html = "<div style='font-family: Arial; font-size: 12px;'>"
        if attr_columns:
            for col in attr_columns:
                if col in row:
                    value = row[col]
                    if pd.notna(value):
                        html += f"<b>{col}:</b> {value}<br>"
        else:
            # 显示所有非几何字段
            for col in row.index:
                if col != 'geometry' and pd.notna(row[col]):
                    html += f"<b>{col}:</b> {row[col]}<br>"
        html += "</div>"
        return html



