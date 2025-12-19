# -*- coding: utf-8 -*-
"""
POLYGON图层合并工具 - 优化百宝箱工具集
提供多个POLYGON图层数据的合并功能
"""

import logging
import re
import streamlit as st
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.wkt import loads as loads_wkt
try:
    from shapely.validation import make_valid
except ImportError:
    # 对于旧版本的shapely，使用buffer(0)方法修复无效几何体
    def make_valid(geom):
        if geom.is_valid:
            return geom
        return geom.buffer(0)


class PolygonMerger:
    """POLYGON合并工具类"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)

    def render(self):
        """渲染polygon功能操作界面"""
        st.title("🗺️ polygon功能操作")
        st.caption("合并多个POLYGON图层数据，检测相交并输出合并后的边框")

        # 创建选项卡
        tab1, tab2, tab3, tab4 = st.tabs(["📝 手动输入", "📄 批量导入", "✂️ POLYGON裁剪", "📦 批量链式裁剪"])

        with tab1:
            self._render_manual_input()

        with tab2:
            self._render_batch_import()
        
        with tab3:
            self._render_polygon_split()
        
        with tab4:
            self._render_batch_chain_split()

    def _render_manual_input(self):
        """渲染手动输入界面"""
        st.markdown("### 📝 手动输入POLYGON数据")

        st.info("""
        **使用说明**：
        1. 在下方文本框中输入POLYGON或MULTIPOLYGON数据（WKT格式）
        2. 每行一个POLYGON或MULTIPOLYGON，格式：
           - `POLYGON ((x1 y1, x2 y2, ...))`
           - `MULTIPOLYGON (((x1 y1, x2 y2, ...)), ((x3 y3, x4 y4, ...)))`
        3. 支持混合输入POLYGON和MULTIPOLYGON
        4. MULTIPOLYGON会自动展开为多个POLYGON进行合并
        5. **特殊功能**：如果输入只有一个POLYGON，将直接转换为单部件POLYGON
        6. 点击"合并POLYGON"按钮执行合并操作
        """)

        # 示例数据
        example_data = """POLYGON ((111.64234313364233 22.09642875544313, 111.6474929749504 22.092571662500227, 111.64817962045574 22.08382322606187, 111.64865168924293 22.08084068065836, 111.64852294320842 22.07467655390808, 111.64109858865716 22.074716323329245, 111.63955363626116 22.079249964022214, 111.63921031350847 22.086527346115208, 111.63680705423079 22.09149801993883, 111.64234313364233 22.09642875544313))

POLYGON ((111.6375370620976 22.09216435331299, 111.6395540832718 22.086875575368065, 111.63994032137529 22.08435041226416, 111.6400476097299 22.07981693527934, 111.64219337694757 22.074965158372557, 111.64828735582998 22.07504469704289, 111.64828735582998 22.081407645530078, 111.64742904893932 22.08435041226249, 111.64725738756299 22.09031529181958, 111.64665657274134 22.090573764236684, 111.6466887592522 22.092979523266624, 111.64200025789134 22.096120865890594, 111.63983303300274 22.093963685597018, 111.6375370620976 22.09216435331299))

MULTIPOLYGON (((111.830716374967 21.7073434748306, 111.831000000000 21.7080000000000, 111.832000000000 21.7090000000000, 111.830716374967 21.7073434748306)))"""

        # 输入框
        polygon_input = st.text_area(
            "输入POLYGON数据（WKT格式）",
            value=example_data,
            height=300,
            help="每行一个POLYGON，支持WKT格式",
            key="polygon_input"
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            merge_button = st.button("🔀 合并POLYGON", type="primary", use_container_width=True, key="merge_polygon_manual")
        with col2:
            if st.button("📋 清空输入", use_container_width=True, key="clear_input_manual"):
                st.rerun()

        if merge_button:
            if not polygon_input.strip():
                st.warning("⚠️ 请输入POLYGON数据")
                return

            # 处理合并
            self._process_polygons(polygon_input)

    def _render_batch_import(self):
        """渲染批量导入界面"""
        st.markdown("### 📄 批量导入POLYGON数据")

        st.info("""
        **使用说明**：
        1. 上传包含POLYGON或MULTIPOLYGON数据的文本文件或CSV文件
        2. 文件格式：每行一个POLYGON或MULTIPOLYGON（WKT格式）
        3. 支持混合格式，MULTIPOLYGON会自动展开
        4. **特殊功能**：如果文件只有一个POLYGON，将直接转换为单部件POLYGON
        5. 系统将自动解析并合并所有POLYGON
        """)

        uploaded_file = st.file_uploader(
            "选择文件",
            type=['txt', 'csv'],
            help="支持.txt和.csv文件，每行一个POLYGON（WKT格式）"
        )

        if uploaded_file:
            try:
                # 读取文件内容
                content = uploaded_file.read().decode('utf-8')
                st.success(f"✅ 文件读取成功：{uploaded_file.name}")

                # 显示文件内容预览
                with st.expander("📄 文件内容预览（前10行）"):
                    lines = content.split('\n')[:10]
                    st.code('\n'.join(lines), language='text')

                if st.button("🔀 合并POLYGON", type="primary", key="merge_polygon_batch"):
                    self._process_polygons(content)

            except Exception as e:
                st.error(f"❌ 文件读取失败：{str(e)}")

    def _render_polygon_split(self):
        """渲染POLYGON裁剪界面"""
        st.markdown("### ✂️ POLYGON裁剪")
        
        st.info("""
        **功能说明**：
        1. 输入两个POLYGON（可以是单部件或多部件）
        2. 系统将使用第一个POLYGON的边界来裁剪第二个POLYGON
        3. 输出：第二个POLYGON中与第一个POLYGON不相交的部分
        4. 输出格式：单部件POLYGON（如果是多部件，将转换为单部件）
        5. 支持POLYGON和MULTIPOLYGON的任意组合
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📐 第一个POLYGON（裁剪边界）")
            polygon1_input = st.text_area(
                "输入第一个POLYGON（WKT格式）",
                height=200,
                help="这个POLYGON将作为裁剪边界",
                key="split_polygon1"
            )
        
        with col2:
            st.markdown("#### 📐 第二个POLYGON（被裁剪对象）")
            polygon2_input = st.text_area(
                "输入第二个POLYGON（WKT格式）",
                height=200,
                help="这个POLYGON将被第一个POLYGON裁剪，输出相交部分",
                key="split_polygon2"
            )
        
        if st.button("✂️ 执行裁剪", type="primary", use_container_width=True, key="execute_clip"):
            if not polygon1_input.strip() or not polygon2_input.strip():
                st.warning("⚠️ 请输入两个POLYGON数据")
                return
            
            self._process_polygon_split(polygon1_input, polygon2_input)
    
    def _process_polygon_split(self, polygon1_text, polygon2_text):
        """处理POLYGON分割（优化版本）"""
        try:
            # 首先进行精度优化预处理
            st.markdown("### 🔧 精度优化预处理")
            with st.spinner("正在优化POLYGON精度..."):
                optimized_wkt1, optimized_wkt2 = self._optimize_polygons_for_clipping(
                    polygon1_text, polygon2_text
                )
            
            # 解析优化后的POLYGON
            geom1 = self._parse_single_geometry(optimized_wkt1)
            geom2 = self._parse_single_geometry(optimized_wkt2)
            
            if geom1 is None:
                st.error("❌ 第一个POLYGON解析失败")
                return
            
            if geom2 is None:
                st.error("❌ 第二个POLYGON解析失败")
                return
            
            # 统一几何体（如果是MULTIPOLYGON，合并为单个几何体）
            unified_geom1 = self._unify_geometry(geom1)
            unified_geom2 = self._unify_geometry(geom2)
            
            # 显示优化信息
            if optimized_wkt1 != polygon1_text or optimized_wkt2 != polygon2_text:
                st.success("✅ POLYGON精度已优化，减少了浮点数精度问题")
                with st.expander("📊 优化详情"):
                    st.write(f"原始多边形1长度: {len(polygon1_text)} 字符")
                    st.write(f"优化后多边形1长度: {len(optimized_wkt1)} 字符")
                    st.write(f"原始多边形2长度: {len(polygon2_text)} 字符")
                    st.write(f"优化后多边形2长度: {len(optimized_wkt2)} 字符")
            else:
                st.info("ℹ️ POLYGON精度已是最优状态，无需额外优化")
            
            # 显示输入信息
            st.markdown("### 📊 输入信息")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**第一个POLYGON（裁剪边界）**")
                st.write(f"  - 类型: {type(unified_geom1).__name__}")
                st.write(f"  - 面积: {unified_geom1.area:.6f} 平方度")
                st.write(f"  - 周长: {unified_geom1.length:.6f} 度")
                st.write(f"  - 是否有效: {'是' if unified_geom1.is_valid else '否'}")
            
            with col2:
                st.write("**第二个POLYGON（被裁剪对象）**")
                st.write(f"  - 类型: {type(unified_geom2).__name__}")
                st.write(f"  - 面积: {unified_geom2.area:.6f} 平方度")
                st.write(f"  - 周长: {unified_geom2.length:.6f} 度")
                st.write(f"  - 是否有效: {'是' if unified_geom2.is_valid else '否'}")
            
            # 检测相交
            st.markdown("### 🔍 相交检测")
            if not unified_geom1.intersects(unified_geom2):
                st.error("❌ 两个POLYGON不相交，无法进行裁剪")
                st.info("💡 提示：只有相交的POLYGON才能进行裁剪操作")
                return
            
            intersection_area = unified_geom1.intersection(unified_geom2).area
            st.success(f"✅ 两个POLYGON相交，相交面积：{intersection_area:.6f} 平方度")
            
            # 执行裁剪（使用difference操作）
            st.markdown("### ✂️ 裁剪处理")
            with st.spinner("正在执行裁剪操作..."):
                # difference操作：返回geom2中不在geom1内的部分（不相交部分）
                split_result = unified_geom2.difference(unified_geom1)
                
                # 确保结果有效
                if not split_result.is_valid:
                    split_result = make_valid(split_result)
                
                # 如果结果是空的，说明geom2完全在geom1内
                if split_result.is_empty:
                    st.warning("⚠️ 裁剪结果为空：第二个POLYGON完全在第一个POLYGON内")
                    return
                
                # 确保输出是单部件POLYGON
                if isinstance(split_result, MultiPolygon):
                    # 如果是MULTIPOLYGON，使用convex_hull转换为单部件POLYGON
                    split_result = split_result.convex_hull
                    st.info("ℹ️ 裁剪结果包含多个组件，已转换为单部件POLYGON（使用凸包）")
                elif not isinstance(split_result, Polygon):
                    # 如果结果不是POLYGON类型，尝试转换
                    if hasattr(split_result, 'convex_hull'):
                        split_result = split_result.convex_hull
                    else:
                        st.error("❌ 无法将结果转换为POLYGON格式")
                        return
            
            # 显示裁剪结果
            st.markdown("### 📊 裁剪结果")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("第二个POLYGON原始面积", f"{unified_geom2.area:.6f} 平方度")
            with col2:
                st.metric("裁剪后类型", "单部件POLYGON")
            with col3:
                st.metric("裁剪后面积（不相交部分）", f"{split_result.area:.6f} 平方度")
            
            # 显示裁剪比例
            if unified_geom2.area > 0:
                remaining_ratio = (split_result.area / unified_geom2.area) * 100
                removed_ratio = 100 - remaining_ratio
                st.info(f"📊 裁剪统计：保留 {remaining_ratio:.2f}%（不相交部分），移除 {removed_ratio:.2f}%（相交部分）")
            
            # 输出裁剪后的WKT（确保是POLYGON格式，不是MULTIPOLYGON）
            st.markdown("#### 📤 裁剪后的单部件POLYGON（WKT格式）")
            
            # 确保输出是POLYGON格式
            if isinstance(split_result, Polygon):
                result_wkt = split_result.wkt
            elif isinstance(split_result, MultiPolygon):
                # 如果还是MULTIPOLYGON，使用convex_hull
                result_wkt = split_result.convex_hull.wkt
            else:
                result_wkt = split_result.wkt
            
            # 双重检查：确保WKT是POLYGON格式
            if result_wkt.startswith('MULTIPOLYGON'):
                # 如果还是MULTIPOLYGON，提取第一个组件
                if isinstance(split_result, MultiPolygon) and len(split_result.geoms) > 0:
                    result_wkt = split_result.geoms[0].wkt
                else:
                    result_wkt = split_result.convex_hull.wkt
            
            st.code(result_wkt, language='text')
            
            # 复制按钮提示
            st.info("💡 提示：点击代码框右上角的复制按钮可以复制WKT数据")
            
            # 下载按钮
            st.download_button(
                label="📥 下载裁剪结果（.txt）",
                data=result_wkt,
                file_name=f"clipped_polygon_{st.session_state.get('timestamp', 'result')}.txt",
                mime="text/plain"
            )
            
            # 显示详细信息
            with st.expander("📊 裁剪详细信息"):
                st.write("**裁剪操作说明：**")
                st.write("  - 操作类型：difference（差集）")
                st.write("  - 结果 = 第二个POLYGON - 第一个POLYGON")
                st.write("  - 即：返回第二个POLYGON中与第一个POLYGON不相交的部分")
                st.write("  - 输出格式：单部件POLYGON（如果原结果多部件，已转换为单部件）")
                
                st.write("**裁剪结果信息：**")
                st.write(f"  - 类型: POLYGON（单部件）")
                st.write(f"  - 面积: {split_result.area:.6f} 平方度")
                st.write(f"  - 周长: {split_result.length:.6f} 度")
                st.write(f"  - 是否有效: {'是' if split_result.is_valid else '否（已修复）'}")
                st.write(f"  - WKT长度: {len(result_wkt)} 字符")
        
        except Exception as e:
            st.error(f"❌ 裁剪失败：{str(e)}")
            self.logger.error(f"POLYGON裁剪失败：{str(e)}", exc_info=True)
    
    def _parse_single_geometry(self, input_text):
        """解析单个几何体（可以是POLYGON或MULTIPOLYGON）"""
        try:
            # 清理输入文本
            cleaned_text = ' '.join(input_text.strip().split())
            if not cleaned_text:
                return None
            
            # 尝试解析
            geom = loads_wkt(cleaned_text)
            
            # 确保几何体有效
            if not geom.is_valid:
                geom = make_valid(geom)
            
            return geom
        
        except Exception as e:
            self.logger.warning(f"解析几何体失败：{str(e)}")
            return None
    
    def _unify_geometry(self, geom):
        """统一几何体：如果是MULTIPOLYGON，合并为单个几何体"""
        if isinstance(geom, MultiPolygon):
            # 如果是MULTIPOLYGON，使用unary_union合并
            if len(geom.geoms) > 1:
                return unary_union(geom.geoms)
            else:
                # 只有一个组件，直接返回
                return geom.geoms[0]
        elif isinstance(geom, Polygon):
            return geom
        else:
            # 其他类型，尝试使用convex_hull
            return geom.convex_hull if hasattr(geom, 'convex_hull') else geom
    
    def _optimize_polygons_for_clipping(self, wkt1, wkt2):
        """
        为裁剪操作优化两个POLYGON，解决顶点重叠和边重叠问题
        
        Args:
            wkt1: 第一个POLYGON的WKT字符串
            wkt2: 第二个POLYGON的WKT字符串
            
        Returns:
            tuple: (优化后的wkt1, 优化后的wkt2)
        """
        try:
            import re
            
            # 提取坐标并优化精度
            def optimize_wkt_precision(wkt_string, precision_digits=12):
                # 使用正则表达式提取坐标
                pattern = r'(-?\d+\.?\d*)\s+(-?\d+\.?\d*)'
                matches = re.findall(pattern, wkt_string)
                coords = [(float(x), float(y)) for x, y in matches]
                
                # 优化坐标精度
                optimized_coords = []
                tolerance = 1e-12
                
                for x, y in coords:
                    opt_x = round(x, precision_digits)
                    opt_y = round(y, precision_digits)
                    optimized_coords.append((opt_x, opt_y))
                
                # 移除重复的连续点
                if len(optimized_coords) > 1:
                    cleaned_coords = [optimized_coords[0]]
                    for i in range(1, len(optimized_coords)):
                        current = optimized_coords[i]
                        previous = cleaned_coords[-1]
                        
                        # 计算距离
                        distance = ((current[0] - previous[0])**2 + (current[1] - previous[1])**2)**0.5
                        
                        # 如果距离大于容差，保留点
                        if distance > tolerance:
                            cleaned_coords.append(current)
                    
                    # 确保多边形闭合
                    if len(cleaned_coords) >= 3 and cleaned_coords[0] != cleaned_coords[-1]:
                        cleaned_coords.append(cleaned_coords[0])
                    
                    optimized_coords = cleaned_coords
                
                # 重构WKT字符串
                if len(optimized_coords) >= 4:  # 至少需要4个点（包括闭合点）
                    coord_strings = []
                    for x, y in optimized_coords:
                        coord_strings.append(f"{x:.{precision_digits}f} {y:.{precision_digits}f}")
                    
                    return f"POLYGON (({', '.join(coord_strings)}))"
                else:
                    return wkt_string  # 如果优化后点数不足，返回原始WKT
            
            # 优化两个POLYGON
            optimized_wkt1 = optimize_wkt_precision(wkt1)
            optimized_wkt2 = optimize_wkt_precision(wkt2)
            
            return optimized_wkt1, optimized_wkt2
            
        except Exception as e:
            self.logger.warning(f"POLYGON精度优化失败，使用原始数据: {e}")
            return wkt1, wkt2
    
    def _remove_overlaps_from_results(self, result_polygons):
        """
        从批量链式裁剪结果中去除重叠，确保所有图形互不重叠
        
        Args:
            result_polygons: 链式裁剪后的结果列表
            
        Returns:
            list: 去重叠后的结果列表
        """
        if len(result_polygons) <= 1:
            return result_polygons
        
        try:
            deoverlapped_results = []
            
            # 第一个图形保持不变
            deoverlapped_results.append(result_polygons[0])
            
            # 从第二个开始，依次去除与前面所有图形的重叠
            for i in range(1, len(result_polygons)):
                current_polygon = result_polygons[i]['polygon']
                current_wkt = result_polygons[i]['wkt']
                
                # 收集前面所有已处理的图形
                previous_polygons = [item['polygon'] for item in deoverlapped_results]
                
                # 依次去除与前面图形的重叠
                processed_polygon = current_polygon
                overlaps_removed = 0
                
                for j, prev_polygon in enumerate(previous_polygons):
                    if processed_polygon.intersects(prev_polygon):
                        # 应用精度优化
                        current_opt_wkt, prev_opt_wkt = self._optimize_polygons_for_clipping(
                            processed_polygon.wkt, prev_polygon.wkt
                        )
                        
                        # 重新解析优化后的几何体
                        if current_opt_wkt != processed_polygon.wkt or prev_opt_wkt != prev_polygon.wkt:
                            opt_current_geom = self._parse_single_geometry(current_opt_wkt)
                            opt_prev_geom = self._parse_single_geometry(prev_opt_wkt)
                            
                            if opt_current_geom and opt_prev_geom:
                                processed_polygon = self._unify_geometry(opt_current_geom)
                                prev_polygon = self._unify_geometry(opt_prev_geom)
                        
                        # 执行difference操作去除重叠
                        difference_result = processed_polygon.difference(prev_polygon)
                        
                        # 确保结果有效
                        if not difference_result.is_valid:
                            difference_result = make_valid(difference_result)
                        
                        # 如果结果为空，跳过这个图形
                        if difference_result.is_empty:
                            processed_polygon = None
                            break
                        
                        # 确保结果是单部件POLYGON
                        if isinstance(difference_result, MultiPolygon):
                            if len(difference_result.geoms) > 0:
                                # 选择面积最大的部分
                                processed_polygon = max(difference_result.geoms, key=lambda x: x.area)
                            else:
                                processed_polygon = None
                                break
                        else:
                            processed_polygon = difference_result
                        
                        overlaps_removed += 1
                
                # 如果处理后的图形仍然有效，添加到结果中
                if processed_polygon is not None and not processed_polygon.is_empty:
                    # 确保WKT格式正确
                    result_wkt = processed_polygon.wkt
                    if result_wkt.startswith('MULTIPOLYGON'):
                        result_wkt = processed_polygon.convex_hull.wkt
                    
                    # 更新note信息
                    original_note = result_polygons[i]['note']
                    if overlaps_removed > 0:
                        new_note = f"{original_note}（已去除与前{overlaps_removed}个图形的重叠）"
                    else:
                        new_note = f"{original_note}（无重叠）"
                    
                    deoverlapped_results.append({
                        'index': result_polygons[i]['index'],
                        'polygon': processed_polygon,
                        'wkt': result_wkt,
                        'area': processed_polygon.area,
                        'note': new_note
                    })
            
            return deoverlapped_results
            
        except Exception as e:
            self.logger.warning(f"去重叠处理失败: {e}")
            return result_polygons
    
    def _render_batch_chain_split(self):
        """渲染批量链式裁剪界面"""
        st.markdown("### 📦 批量链式裁剪")
        
        st.info("""
        **功能说明**：
        1. 支持两种输入方式：
           - 手动输入：在文本框中输入多个POLYGON（每行一个，WKT格式）
           - 文件上传：上传包含多个POLYGON的文本文件（每行一个POLYGON，WKT格式）
        2. 链式裁剪逻辑：
           - 第一个POLYGON：保持不变
           - 第二个POLYGON：裁剪掉与第一个POLYGON相交的部分
           - 第三个POLYGON：裁剪掉与裁剪后的第二个POLYGON相交的部分
           - 以此类推...
        3. 输出：每个POLYGON裁剪后的结果列表（单部件POLYGON格式）
        4. 支持POLYGON和MULTIPOLYGON
        """)
        
        # 创建两个选项卡：手动输入和文件上传
        input_tab1, input_tab2 = st.tabs(["📝 手动输入", "📄 文件上传"])
        
        content = None
        input_source = None
        
        with input_tab1:
            st.markdown("#### 📝 手动输入POLYGON列表")
            
            # 示例数据
            example_data = """POLYGON ((111.64234313364233 22.09642875544313, 111.6474929749504 22.092571662500227, 111.64817962045574 22.08382322606187, 111.64865168924293 22.08084068065836, 111.64852294320842 22.07467655390808, 111.64109858865716 22.074716323329245, 111.63955363626116 22.079249964022214, 111.63921031350847 22.086527346115208, 111.63680705423079 22.09149801993883, 111.64234313364233 22.09642875544313))
POLYGON ((111.6375370620976 22.09216435331299, 111.6395540832718 22.086875575368065, 111.63994032137529 22.08435041226416, 111.6400476097299 22.07981693527934, 111.64219337694757 22.074965158372557, 111.64828735582998 22.07504469704289, 111.64828735582998 22.081407645530078, 111.64742904893932 22.08435041226249, 111.64725738756299 22.09031529181958, 111.64665657274134 22.090573764236684, 111.6466887592522 22.092979523266624, 111.64200025789134 22.096120865890594, 111.63983303300274 22.093963685597018, 111.6375370620976 22.09216435331299))
POLYGON ((111.630000000000 22.080000000000, 111.635000000000 22.080000000000, 111.635000000000 22.085000000000, 111.630000000000 22.085000000000, 111.630000000000 22.080000000000))"""
            
            # 手动输入框
            manual_input = st.text_area(
                "输入POLYGON列表（每行一个POLYGON，WKT格式）",
                value=example_data,
                height=300,
                help="每行一个POLYGON或MULTIPOLYGON（WKT格式）",
                key="chain_split_manual_input"
            )
            
            if manual_input.strip():
                content = manual_input
                input_source = "手动输入"
                
                # 显示输入内容预览
                lines = content.strip().split('\n')
                non_empty_lines = [line for line in lines if line.strip()]
                with st.expander(f"📄 输入内容预览（共{len(non_empty_lines)}行，显示前10行）"):
                    st.code('\n'.join(non_empty_lines[:10]), language='text')
                    if len(non_empty_lines) > 10:
                        st.write(f"... 还有 {len(non_empty_lines) - 10} 行")
        
        with input_tab2:
            st.markdown("#### 📄 文件上传")
            
            uploaded_file = st.file_uploader(
                "选择包含POLYGON列表的文件",
                type=['txt', 'csv'],
                help="文件格式：每行一个POLYGON或MULTIPOLYGON（WKT格式）",
                key="chain_split_file"
            )
            
            if uploaded_file:
                try:
                    # 读取文件内容
                    file_content = uploaded_file.read().decode('utf-8')
                    content = file_content
                    input_source = f"文件上传：{uploaded_file.name}"
                    st.success(f"✅ 文件读取成功：{uploaded_file.name}")
                    
                    # 显示文件内容预览
                    lines = content.strip().split('\n')
                    non_empty_lines = [line for line in lines if line.strip()]
                    with st.expander(f"📄 文件内容预览（共{len(non_empty_lines)}行，显示前10行）"):
                        st.code('\n'.join(non_empty_lines[:10]), language='text')
                        if len(non_empty_lines) > 10:
                            st.write(f"... 还有 {len(non_empty_lines) - 10} 行")
                
                except Exception as e:
                    st.error(f"❌ 文件读取失败：{str(e)}")
                    content = None
        
        # 执行按钮（如果有输入内容）
        if content and content.strip():
            st.markdown("---")
            col1, col2 = st.columns([1, 4])
            with col1:
                execute_clicked = st.button("📦 执行批量链式裁剪", type="primary", use_container_width=True, key="execute_chain_clip")
            with col2:
                if st.button("📋 清空输入", use_container_width=True, key="clear_input_chain"):
                    st.rerun()
            
            # 在按钮外部显示输入来源和处理结果，确保全宽显示
            if execute_clicked:
                if input_source:
                    st.info(f"📌 输入来源：{input_source}")
                self._process_batch_chain_split(content)
        elif content is None:
            st.info("💡 请在上方选择输入方式：手动输入或文件上传")
    
    def _process_batch_chain_split(self, input_text):
        """处理批量链式裁剪"""
        try:
            # 在处理开始时立即应用全宽CSS样式，确保从输入来源开始的所有内容都全宽显示
            st.markdown("""
            <style>
            /* 提示框全宽 */
            .stInfo, .stSuccess, .stWarning, .stError {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stAlert"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 代码块全宽 */
            .stCodeBlock {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stCodeBlock"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stCodeBlock"] > div {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 表格全宽 */
            div[data-testid="stDataFrame"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            .stDataFrame {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stDataFrameContainer"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 所有容器全宽 */
            .element-container {
                max-width: 100% !important;
                width: 100% !important;
            }
            div[data-baseweb="block"] {
                max-width: 100% !important;
                width: 100% !important;
            }
            [data-baseweb="block"] {
                max-width: 100% !important;
                width: 100% !important;
            }
            
            /* 主内容区域全宽 */
            section[data-testid="stMain"] > div {
                max-width: 100% !important;
            }
            section[data-testid="stMain"] > div > div {
                max-width: 100% !important;
            }
            
            /* Markdown和文本内容全宽 */
            div[data-testid="stMarkdownContainer"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # 解析所有POLYGON
            lines = input_text.strip().split('\n')
            polygons = []
            
            st.markdown("### 📊 解析输入")
            with st.spinner("正在解析POLYGON数据..."):
                for i, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    geom = self._parse_single_geometry(line)
                    if geom is None:
                        st.warning(f"⚠️ 第 {i} 行解析失败，跳过")
                        continue
                    
                    # 统一几何体
                    unified_geom = self._unify_geometry(geom)
                    polygons.append({
                        'index': i,
                        'original': unified_geom,
                        'original_wkt': unified_geom.wkt
                    })
            
            if len(polygons) == 0:
                st.error("❌ 未找到有效的POLYGON数据")
                return
            
            if len(polygons) == 1:
                st.warning("⚠️ 只有一个POLYGON，无需裁剪")
                st.info("💡 提示：链式裁剪至少需要2个POLYGON")
                return
            
            st.success(f"✅ 成功解析 {len(polygons)} 个POLYGON")
            
            # 执行链式裁剪
            st.markdown("### ✂️ 链式裁剪处理")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            result_polygons = []
            
            # 第一个POLYGON保持不变，但确保是单部件POLYGON格式
            first_polygon = polygons[0]['original']
            first_wkt = first_polygon.wkt
            
            # 确保第一个POLYGON也是单部件格式
            if isinstance(first_polygon, MultiPolygon):
                first_polygon = first_polygon.convex_hull
                first_wkt = first_polygon.wkt
                note = '第一个POLYGON（保持不变，已转换为单部件）'
            elif first_wkt.startswith('MULTIPOLYGON'):
                first_polygon = first_polygon.convex_hull
                first_wkt = first_polygon.wkt
                note = '第一个POLYGON（保持不变，已转换为单部件）'
            else:
                note = '第一个POLYGON（保持不变）'
            
            result_polygons.append({
                'index': 1,
                'polygon': first_polygon,
                'wkt': first_wkt,
                'area': first_polygon.area,
                'note': note
            })
            
            # 从第二个开始，依次裁剪
            previous_clipped = first_polygon  # 前一个裁剪后的POLYGON
            
            for i in range(1, len(polygons)):
                current_polygon = polygons[i]['original']
                status_text.text(f"正在处理第 {i+1}/{len(polygons)} 个POLYGON...")
                
                try:
                    # 检查是否相交
                    if not previous_clipped.intersects(current_polygon):
                        # 不相交，直接使用原始POLYGON（保持原样）
                        clipped_result = current_polygon
                        note = f'第{i+1}个POLYGON（与第{i}个裁剪结果不相交，保持原样）'
                    else:
                        # 相交，执行裁剪：current - previous_clipped
                        # 首先对两个POLYGON进行精度优化
                        current_wkt = current_polygon.wkt
                        previous_wkt = previous_clipped.wkt
                        
                        # 应用精度优化
                        opt_current_wkt, opt_previous_wkt = self._optimize_polygons_for_clipping(
                            current_wkt, previous_wkt
                        )
                        
                        # 重新解析优化后的几何体
                        if opt_current_wkt != current_wkt or opt_previous_wkt != previous_wkt:
                            opt_current_geom = self._parse_single_geometry(opt_current_wkt)
                            opt_previous_geom = self._parse_single_geometry(opt_previous_wkt)
                            
                            if opt_current_geom and opt_previous_geom:
                                current_polygon = self._unify_geometry(opt_current_geom)
                                previous_clipped = self._unify_geometry(opt_previous_geom)
                        
                        clipped_result = current_polygon.difference(previous_clipped)
                        
                        # 确保结果有效
                        if not clipped_result.is_valid:
                            clipped_result = make_valid(clipped_result)
                        
                        # 如果结果为空，说明完全被裁剪，但也要输出原始POLYGON（保持数量一致）
                        if clipped_result.is_empty:
                            # 使用原始POLYGON作为输出（保持原样，因为被完全裁剪后没有剩余部分）
                            clipped_result = current_polygon
                            note = f'第{i+1}个POLYGON（完全被第{i}个裁剪结果覆盖，输出原POLYGON）'
                        else:
                            # 确保输出是单部件POLYGON
                            if isinstance(clipped_result, MultiPolygon):
                                clipped_result = clipped_result.convex_hull
                                note = f'第{i+1}个POLYGON（已裁剪，转换为单部件）'
                            else:
                                note = f'第{i+1}个POLYGON（已裁剪）'
                    
                    # 确保是POLYGON类型
                    if not isinstance(clipped_result, Polygon):
                        clipped_result = clipped_result.convex_hull if hasattr(clipped_result, 'convex_hull') else clipped_result
                    
                    # 获取WKT，确保是POLYGON格式
                    result_wkt = clipped_result.wkt
                    if result_wkt.startswith('MULTIPOLYGON'):
                        result_wkt = clipped_result.convex_hull.wkt
                    
                    # 确保WKT是POLYGON格式
                    if not result_wkt.startswith('POLYGON'):
                        if isinstance(clipped_result, MultiPolygon) and len(clipped_result.geoms) > 0:
                            result_wkt = clipped_result.geoms[0].wkt
                        else:
                            result_wkt = clipped_result.convex_hull.wkt
                    
                    result_polygons.append({
                        'index': i+1,
                        'polygon': clipped_result,
                        'wkt': result_wkt,
                        'area': clipped_result.area,
                        'note': note
                    })
                    
                    # 更新previous_clipped为当前裁剪结果（如果被完全裁剪，使用原始POLYGON）
                    previous_clipped = clipped_result
                
                except Exception as e:
                    st.error(f"❌ 处理第 {i+1} 个POLYGON失败：{str(e)}")
                    # 即使处理失败，也输出原始POLYGON（保持数量一致）
                    original_wkt = polygons[i]['original_wkt']
                    # 确保是POLYGON格式
                    if original_wkt.startswith('MULTIPOLYGON'):
                        original_geom = polygons[i]['original']
                        if isinstance(original_geom, MultiPolygon) and len(original_geom.geoms) > 0:
                            original_wkt = original_geom.geoms[0].wkt
                        else:
                            original_wkt = original_geom.convex_hull.wkt
                    
                    result_polygons.append({
                        'index': i+1,
                        'polygon': polygons[i]['original'],
                        'wkt': original_wkt,
                        'area': polygons[i]['original'].area,
                        'note': f'第{i+1}个POLYGON（处理失败，输出原POLYGON：{str(e)}）'
                    })
                    # 继续处理下一个，使用原始POLYGON作为参考
                    previous_clipped = polygons[i]['original']
                    continue
                
                # 更新进度
                progress = (i + 1) / len(polygons)
                progress_bar.progress(progress)
            
            status_text.text("✅ 链式裁剪完成")
            
            # 执行去重叠处理
            st.markdown("### 🔄 去重叠处理")
            st.info("正在处理图形间的重叠问题，确保所有图形互不重叠...")
            
            deoverlapped_polygons = self._remove_overlaps_from_results(result_polygons)
            
            if len(deoverlapped_polygons) != len(result_polygons):
                st.warning(f"⚠️ 去重叠处理后，图形数量从 {len(result_polygons)} 个变为 {len(deoverlapped_polygons)} 个")
            else:
                st.success("✅ 去重叠处理完成，所有图形现在互不重叠")
            
            # 使用去重叠后的结果
            result_polygons = deoverlapped_polygons
            
            # 添加CSS确保全宽显示
            st.markdown("""
            <style>
            /* 代码块全宽 */
            .stCodeBlock {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stCodeBlock"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            div[data-testid="stCodeBlock"] > div {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 表格全宽 */
            div[data-testid="stDataFrame"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            .stDataFrame {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 所有容器全宽 */
            .element-container {
                max-width: 100% !important;
                width: 100% !important;
            }
            div[data-baseweb="block"] {
                max-width: 100% !important;
                width: 100% !important;
            }
            
            /* 主内容区域 */
            section[data-testid="stMain"] > div {
                max-width: 100% !important;
            }
            section[data-testid="stMain"] > div > div {
                max-width: 100% !important;
            }
            
            /* 表格容器 */
            div[data-testid="stDataFrameContainer"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* 确保所有block元素全宽 */
            [data-baseweb="block"] {
                max-width: 100% !important;
                width: 100% !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # 显示结果
            st.markdown("### 📊 裁剪结果")
            
            # 统计信息
            valid_results = [r for r in result_polygons if r['polygon'] is not None]
            clipped_results = [r for r in result_polygons if '已裁剪' in r['note']]
            unchanged_results = [r for r in result_polygons if '保持原样' in r['note'] or '保持不变' in r['note']]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("输入POLYGON数量", len(polygons))
            with col2:
                st.metric("输出POLYGON数量", len(result_polygons))
            with col3:
                st.metric("已裁剪数量", len(clipped_results))
            
            # 显示统计详情
            st.info(f"📊 详细统计：{len(clipped_results)} 个已裁剪，{len(unchanged_results)} 个保持原样，共 {len(result_polygons)} 个输出")
            
            st.markdown("---")
            
            # 显示结果列表
            st.markdown("#### 📋 裁剪结果列表")
            
            # 创建结果表格
            result_data = []
            for r in result_polygons:
                result_data.append({
                    '序号': r['index'],
                    '面积（平方度）': f"{r['area']:.6f}" if r['polygon'] else "0.000000",
                    '状态': "✅ 有效" if r['polygon'] else "❌ 空/失败",
                    '说明': r['note']
                })
            
            result_df = pd.DataFrame(result_data)
            # 确保表格全宽显示
            st.markdown("""<style>div[data-testid="stDataFrame"] {width: 100% !important; max-width: 100% !important;}</style>""", unsafe_allow_html=True)
            st.dataframe(result_df, use_container_width=True)
            
            st.markdown("---")
            
            # 输出所有结果的WKT
            st.markdown("#### 📤 裁剪结果POLYGON列表（WKT格式）")
            
            # 生成输出文本（每行一个POLYGON，确保数量与输入一致）
            output_lines = []
            for r in result_polygons:
                if r['polygon'] is not None and r['wkt']:
                    # 确保WKT是POLYGON格式
                    wkt = r['wkt']
                    if not wkt.startswith('POLYGON'):
                        # 如果不是POLYGON格式，尝试转换
                        if isinstance(r['polygon'], Polygon):
                            wkt = r['polygon'].wkt
                        elif isinstance(r['polygon'], MultiPolygon) and len(r['polygon'].geoms) > 0:
                            wkt = r['polygon'].geoms[0].wkt
                        else:
                            wkt = r['polygon'].convex_hull.wkt
                    output_lines.append(wkt)
                else:
                    # 如果结果为空，输出原始POLYGON（保持数量一致）
                    original_idx = r['index'] - 1
                    if original_idx < len(polygons):
                        original_wkt = polygons[original_idx]['original_wkt']
                        # 确保是POLYGON格式
                        if original_wkt.startswith('MULTIPOLYGON'):
                            original_geom = polygons[original_idx]['original']
                            if isinstance(original_geom, MultiPolygon) and len(original_geom.geoms) > 0:
                                original_wkt = original_geom.geoms[0].wkt
                            else:
                                original_wkt = original_geom.convex_hull.wkt
                        output_lines.append(original_wkt)
                    else:
                        output_lines.append("# 错误：无法获取原始POLYGON")
            
            output_text = '\n'.join(output_lines)
            
            # 显示结果预览
            with st.expander("📄 查看完整结果（前10行）"):
                preview_lines = output_lines[:10]
                st.code('\n'.join(preview_lines), language='text')
                if len(output_lines) > 10:
                    st.write(f"... 还有 {len(output_lines) - 10} 行")
            
            # 完整结果显示
            st.markdown("**完整结果（WKT格式）：**")
            # 确保代码块全宽显示
            st.markdown("""<style>div[data-testid="stCodeBlock"] {width: 100% !important; max-width: 100% !important;}</style>""", unsafe_allow_html=True)
            st.code(output_text, language='text')
            
            # 下载按钮
            st.download_button(
                label="📥 下载裁剪结果列表（.txt）",
                data=output_text,
                file_name=f"chain_clipped_polygons_{st.session_state.get('timestamp', 'result')}.txt",
                mime="text/plain",
                use_container_width=True
            )
            
            st.markdown("---")
            
            # 显示详细信息
            with st.expander("📊 链式裁剪详细信息"):
                st.write("**链式裁剪逻辑：**")
                st.write("  - 第1个POLYGON：保持不变（作为基准）")
                for i in range(1, len(polygons)):
                    st.write(f"  - 第{i+1}个POLYGON：裁剪掉与第{i}个裁剪结果相交的部分")
                
                st.write("**裁剪结果详情：**")
                for r in result_polygons:
                    if r['polygon'] is not None:
                        st.write(f"  - POLYGON {r['index']}: 面积={r['area']:.6f}, {r['note']}")
                    else:
                        st.write(f"  - POLYGON {r['index']}: {r['note']}")
        
        except Exception as e:
            st.error(f"❌ 批量链式裁剪失败：{str(e)}")
            self.logger.error(f"批量链式裁剪失败：{str(e)}", exc_info=True)

    def _process_polygons(self, input_text):
        """处理POLYGON合并"""
        try:
            # 先尝试整体解析，检查是否是单个几何体（用于单POLYGON转换功能）
            original_geom = None
            try:
                # 移除所有换行符和多余空格，但保留WKT结构
                cleaned_text = ' '.join(input_text.strip().split())
                if cleaned_text:
                    original_geom = loads_wkt(cleaned_text)
            except Exception:
                pass
            
            # 检查是否是单个几何体（POLYGON或只有一个组件的MULTIPOLYGON）
            if original_geom:
                if isinstance(original_geom, Polygon):
                    # 单个POLYGON，直接转换
                    st.info("ℹ️ 检测到单个POLYGON，将直接转换为单部件POLYGON")
                    
                    single_polygon = original_geom
                    
                    # 确保几何体有效，但保持为单个POLYGON
                    if not single_polygon.is_valid:
                        fixed_geom = make_valid(single_polygon)
                        # 如果修复后变成了MultiPolygon，提取第一个组件
                        if isinstance(fixed_geom, MultiPolygon):
                            if len(fixed_geom.geoms) > 0:
                                # 使用最大的组件（通常是最重要的）
                                single_polygon = max(fixed_geom.geoms, key=lambda p: p.area)
                                st.warning("⚠️ 几何体修复后包含多个组件，已选择最大组件作为单部件POLYGON")
                            else:
                                single_polygon = fixed_geom.geoms[0]
                        elif isinstance(fixed_geom, Polygon):
                            single_polygon = fixed_geom
                        else:
                            # 如果修复后是其他类型，尝试使用convex_hull
                            single_polygon = fixed_geom.convex_hull if hasattr(fixed_geom, 'convex_hull') else single_polygon
                    
                    # 最终确保是单个POLYGON
                    if not isinstance(single_polygon, Polygon):
                        # 如果还是MultiPolygon，提取第一个组件
                        if isinstance(single_polygon, MultiPolygon) and len(single_polygon.geoms) > 0:
                            single_polygon = single_polygon.geoms[0]
                        else:
                            # 最后的手段：使用convex_hull
                            single_polygon = original_geom.convex_hull
                    
                    # 显示结果
                    st.markdown("### 📊 转换结果")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("输入类型", "POLYGON")
                    with col2:
                        st.metric("面积", f"{single_polygon.area:.6f} 平方度")
                    with col3:
                        st.metric("周长", f"{single_polygon.length:.6f} 度")
                    
                    # 输出转换后的WKT（确保是POLYGON格式）
                    st.markdown("#### 📤 转换后的单部件POLYGON（WKT格式）")
                    
                    # 确保single_polygon是Polygon类型
                    if isinstance(single_polygon, MultiPolygon):
                        if len(single_polygon.geoms) > 0:
                            single_polygon = single_polygon.geoms[0]
                        else:
                            # 如果MultiPolygon为空，使用convex_hull
                            single_polygon = original_geom.convex_hull
                    
                    # 获取WKT，确保是POLYGON格式
                    result_wkt = single_polygon.wkt
                    
                    # 双重检查：如果WKT还是MULTIPOLYGON，强制转换为POLYGON
                    if result_wkt.startswith('MULTIPOLYGON'):
                        # 重新获取第一个组件
                        if isinstance(single_polygon, MultiPolygon) and len(single_polygon.geoms) > 0:
                            result_wkt = single_polygon.geoms[0].wkt
                        else:
                            # 如果还是MultiPolygon，使用convex_hull
                            result_wkt = single_polygon.convex_hull.wkt
                    
                    st.code(result_wkt, language='text')
                    
                    # 复制按钮提示
                    st.info("💡 提示：点击代码框右上角的复制按钮可以复制WKT数据")
                    
                    # 下载按钮
                    st.download_button(
                        label="📥 下载转换结果（.txt）",
                        data=result_wkt,
                        file_name=f"single_polygon_{st.session_state.get('timestamp', 'result')}.txt",
                        mime="text/plain"
                    )
                    
                    # 显示详细信息
                    with st.expander("📊 详细信息"):
                        st.write("**输入POLYGON信息：**")
                        st.write(f"  - 面积: {single_polygon.area:.6f} 平方度")
                        st.write(f"  - 周长: {single_polygon.length:.6f} 度")
                        st.write(f"  - 是否有效: {'是' if single_polygon.is_valid else '否（已修复）'}")
                        st.write(f"  - WKT长度: {len(result_wkt)} 字符")
                    
                    return
                elif isinstance(original_geom, MultiPolygon):
                    if len(original_geom.geoms) == 1:
                        # 单个MULTIPOLYGON，但只有一个POLYGON组件，直接转换为单部件POLYGON
                        st.info("ℹ️ 检测到单个MULTIPOLYGON（只有一个组件），将直接转换为单部件POLYGON")
                        
                        single_polygon = original_geom.geoms[0]
                        
                        # 确保几何体有效，但保持为单个POLYGON
                        if not single_polygon.is_valid:
                            fixed_geom = make_valid(single_polygon)
                            # 如果修复后变成了MultiPolygon，提取第一个组件
                            if isinstance(fixed_geom, MultiPolygon):
                                if len(fixed_geom.geoms) > 0:
                                    # 使用最大的组件（通常是最重要的）
                                    single_polygon = max(fixed_geom.geoms, key=lambda p: p.area)
                                    st.warning("⚠️ 几何体修复后包含多个组件，已选择最大组件作为单部件POLYGON")
                                else:
                                    single_polygon = fixed_geom.geoms[0]
                            elif isinstance(fixed_geom, Polygon):
                                single_polygon = fixed_geom
                            else:
                                # 如果修复后是其他类型，尝试使用convex_hull
                                single_polygon = fixed_geom.convex_hull if hasattr(fixed_geom, 'convex_hull') else single_polygon
                        
                        # 最终确保是单个POLYGON
                        if not isinstance(single_polygon, Polygon):
                            # 如果还是MultiPolygon，提取第一个组件
                            if isinstance(single_polygon, MultiPolygon) and len(single_polygon.geoms) > 0:
                                single_polygon = single_polygon.geoms[0]
                            else:
                                # 最后的手段：使用convex_hull
                                single_polygon = original_geom.convex_hull
                        
                        # 显示结果
                        st.markdown("### 📊 转换结果")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("输入类型", "MULTIPOLYGON（单组件）")
                        with col2:
                            st.metric("面积", f"{single_polygon.area:.6f} 平方度")
                        with col3:
                            st.metric("周长", f"{single_polygon.length:.6f} 度")
                        
                        # 输出转换后的WKT（确保是POLYGON格式，不是MULTIPOLYGON）
                        st.markdown("#### 📤 转换后的单部件POLYGON（WKT格式）")
                        
                        # 确保single_polygon是Polygon类型
                        if isinstance(single_polygon, MultiPolygon):
                            if len(single_polygon.geoms) > 0:
                                single_polygon = single_polygon.geoms[0]
                            else:
                                # 如果MultiPolygon为空，使用convex_hull
                                single_polygon = original_geom.convex_hull
                        
                        # 获取WKT，确保是POLYGON格式
                        result_wkt = single_polygon.wkt
                        
                        # 双重检查：如果WKT还是MULTIPOLYGON，强制转换为POLYGON
                        if result_wkt.startswith('MULTIPOLYGON'):
                            # 重新获取第一个组件
                            if isinstance(single_polygon, MultiPolygon) and len(single_polygon.geoms) > 0:
                                result_wkt = single_polygon.geoms[0].wkt
                            else:
                                # 如果还是MultiPolygon，使用convex_hull
                                result_wkt = single_polygon.convex_hull.wkt
                        
                        st.code(result_wkt, language='text')
                        
                        # 复制按钮提示
                        st.info("💡 提示：点击代码框右上角的复制按钮可以复制WKT数据")
                        
                        # 下载按钮
                        st.download_button(
                            label="📥 下载转换结果（.txt）",
                            data=result_wkt,
                            file_name=f"single_polygon_{st.session_state.get('timestamp', 'result')}.txt",
                            mime="text/plain"
                        )
                        
                        # 显示详细信息
                        with st.expander("📊 详细信息"):
                            st.write("**输入MULTIPOLYGON信息：**")
                            st.write(f"  - 组件数量: 1")
                            st.write(f"  - 面积: {single_polygon.area:.6f} 平方度")
                            st.write(f"  - 周长: {single_polygon.length:.6f} 度")
                            st.write(f"  - 是否有效: {'是' if single_polygon.is_valid else '否（已修复）'}")
                            st.write(f"  - WKT长度: {len(result_wkt)} 字符")
                            st.write(f"  - 输出类型: {type(single_polygon).__name__}")
                        
                        return
            
            # 解析POLYGON数据
            polygons = self._parse_polygons(input_text)

            if not polygons:
                st.error("❌ 未找到有效的POLYGON数据")
                return

            # 统计原始输入和展开后的数量
            original_count = len(input_text.strip().split('\n'))
            expanded_count = len(polygons)
            if expanded_count > original_count:
                st.success(f"✅ 成功解析：原始输入 {original_count} 行，展开后 {expanded_count} 个POLYGON（包含MULTIPOLYGON展开）")
            else:
                st.success(f"✅ 成功解析 {len(polygons)} 个POLYGON")

            # 显示解析结果
            with st.expander(f"📊 解析结果详情（共{len(polygons)}个POLYGON）"):
                for i, poly in enumerate(polygons, 1):
                    st.write(f"**POLYGON {i}**:")
                    # 只显示WKT的前200个字符，避免显示过长
                    wkt_preview = poly.wkt[:200] + "..." if len(poly.wkt) > 200 else poly.wkt
                    st.code(wkt_preview, language='text')
                    st.write(f"  面积: {poly.area:.6f} 平方度")
                    st.write(f"  周长: {poly.length:.6f} 度")
                    st.write(f"  完整WKT长度: {len(poly.wkt)} 字符")
                    st.markdown("---")

            # 特殊处理：如果只有一个POLYGON，直接转换为单部件POLYGON
            if len(polygons) == 1:
                st.info("ℹ️ 检测到只有一个POLYGON，将直接转换为单部件POLYGON")
                
                single_polygon = polygons[0]
                
                # 确保是单部件的POLYGON（不是MultiPolygon的一部分）
                if isinstance(single_polygon, Polygon):
                    # 已经是单部件POLYGON
                    result_polygon = single_polygon
                else:
                    # 如果是其他类型，尝试提取第一个组件
                    result_polygon = single_polygon
                
                # 确保几何体有效
                if not result_polygon.is_valid:
                    result_polygon = make_valid(result_polygon)
                
                # 显示结果
                st.markdown("### 📊 转换结果")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("输入类型", "单POLYGON")
                with col2:
                    st.metric("面积", f"{result_polygon.area:.6f} 平方度")
                with col3:
                    st.metric("周长", f"{result_polygon.length:.6f} 度")
                
                # 输出转换后的WKT
                st.markdown("#### 📤 转换后的单部件POLYGON（WKT格式）")
                result_wkt = result_polygon.wkt
                st.code(result_wkt, language='text')
                
                # 复制按钮提示
                st.info("💡 提示：点击代码框右上角的复制按钮可以复制WKT数据")
                
                # 下载按钮
                st.download_button(
                    label="📥 下载转换结果（.txt）",
                    data=result_wkt,
                    file_name=f"single_polygon_{st.session_state.get('timestamp', 'result')}.txt",
                    mime="text/plain"
                )
                
                # 显示详细信息
                with st.expander("📊 详细信息"):
                    st.write("**输入POLYGON信息：**")
                    st.write(f"  - 面积: {result_polygon.area:.6f} 平方度")
                    st.write(f"  - 周长: {result_polygon.length:.6f} 度")
                    st.write(f"  - 是否有效: {'是' if result_polygon.is_valid else '否（已修复）'}")
                    st.write(f"  - WKT长度: {len(result_wkt)} 字符")
                
                return

            # 检测相交
            st.markdown("### 🔍 相交检测")
            intersection_info = self._check_intersections(polygons)

            if not intersection_info['has_intersection']:
                st.error("❌ **POLYGON不相交，无法合并**")
                st.info("💡 提示：只有相交的POLYGON才能合并")
                
                # 显示不相交的详细信息
                with st.expander("📊 不相交详情"):
                    st.write(f"检测到 {len(polygons)} 个POLYGON，但它们之间没有相交关系")
                    for i, info in enumerate(intersection_info['details'], 1):
                        st.write(f"POLYGON {i}: {info}")
                return

            # 执行合并
            st.markdown("### 🔀 合并处理")
            with st.spinner("正在合并POLYGON..."):
                merged_polygon = self._merge_polygons(polygons)

            if merged_polygon:
                st.success("✅ POLYGON合并成功！")

                # 显示合并结果
                st.markdown("### 📊 合并结果")
                
                # 基本信息
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("合并前POLYGON数量", len(polygons))
                with col2:
                    st.metric("合并后面积", f"{merged_polygon.area:.6f} 平方度")
                with col3:
                    st.metric("合并后周长", f"{merged_polygon.length:.6f} 度")

                # 输出合并后的WKT
                st.markdown("#### 📤 合并后的POLYGON边框（WKT格式）")
                merged_wkt = merged_polygon.wkt
                st.code(merged_wkt, language='text')

                # 复制按钮提示
                st.info("💡 提示：点击代码框右上角的复制按钮可以复制WKT数据")

                # 下载按钮
                st.download_button(
                    label="📥 下载合并结果（.txt）",
                    data=merged_wkt,
                    file_name=f"merged_polygon_{st.session_state.get('timestamp', 'result')}.txt",
                    mime="text/plain"
                )

                # 显示详细信息
                with st.expander("📊 合并详细信息"):
                    st.write("**合并前POLYGON列表：**")
                    for i, poly in enumerate(polygons, 1):
                        st.write(f"  - POLYGON {i}: 面积={poly.area:.6f}, 周长={poly.length:.6f}")
                    
                    st.write("**相交关系：**")
                    for detail in intersection_info['details']:
                        st.write(f"  - {detail}")

            else:
                st.error("❌ POLYGON合并失败")

        except Exception as e:
            st.error(f"❌ 处理失败：{str(e)}")
            self.logger.error(f"POLYGON合并失败：{str(e)}", exc_info=True)

    def _parse_polygons(self, input_text):
        """解析POLYGON和MULTIPOLYGON数据"""
        polygons = []
        # 先尝试将整个文本作为一个WKT解析（处理跨行的MULTIPOLYGON）
        try:
            # 移除所有换行符和多余空格，但保留WKT结构
            cleaned_text = ' '.join(input_text.split())
            geom = loads_wkt(cleaned_text)
            if isinstance(geom, MultiPolygon):
                for poly in geom.geoms:
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    polygons.append(poly)
                st.success(f"✅ 成功解析为单个MULTIPOLYGON，包含 {len(geom.geoms)} 个POLYGON")
                return polygons
            elif isinstance(geom, Polygon):
                if not geom.is_valid:
                    geom = make_valid(geom)
                polygons.append(geom)
                st.success("✅ 成功解析为单个POLYGON")
                return polygons
        except Exception:
            # 如果整体解析失败，继续按行解析
            pass
        
        # 按行解析
        lines = input_text.strip().split('\n')
        processed_lines = set()  # 记录已处理的行，避免重复处理跨行的MULTIPOLYGON

        for line_num, line in enumerate(lines, 1):
            # 跳过已处理的行（跨行MULTIPOLYGON的后续行）
            if line_num in processed_lines:
                continue
                
            line = line.strip()
            if not line:
                continue

            try:
                # 尝试直接解析WKT
                geom = loads_wkt(line)
                
                # 处理POLYGON类型
                if isinstance(geom, Polygon):
                    # 修复无效的几何体
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    polygons.append(geom)
                
                # 处理MULTIPOLYGON类型
                elif isinstance(geom, MultiPolygon):
                    # 将MULTIPOLYGON展开为多个POLYGON
                    for poly in geom.geoms:
                        if not poly.is_valid:
                            poly = make_valid(poly)
                        polygons.append(poly)
                    st.info(f"ℹ️ 第 {line_num} 行：MULTIPOLYGON包含 {len(geom.geoms)} 个POLYGON，已展开")
                
                else:
                    st.warning(f"⚠️ 第 {line_num} 行：不支持的地理类型 {type(geom).__name__}：{line[:50]}...")
                    
            except Exception as e:
                # 如果直接解析失败，尝试提取POLYGON或MULTIPOLYGON字符串
                # 先尝试MULTIPOLYGON（因为它可能包含POLYGON字符串）
                # MULTIPOLYGON的正则表达式需要匹配嵌套的括号
                multipolygon_pattern = r'MULTIPOLYGON\s*\((?:\([^()]*(?:\([^()]*\)[^()]*)*\)\s*,?\s*)+\)'
                multipolygon_match = re.search(multipolygon_pattern, line, re.IGNORECASE | re.DOTALL)
                
                if not multipolygon_match:
                    # 尝试更宽松的MULTIPOLYGON匹配（匹配到行尾或后续行）
                    if 'MULTIPOLYGON' in line.upper():
                        # 找到MULTIPOLYGON开始位置
                        start_idx = line.upper().find('MULTIPOLYGON')
                        # 尝试收集后续行直到找到完整的WKT
                        collected_lines = [line[start_idx:]]
                        current_line_idx = line_num
                        
                        # 检查括号是否匹配
                        bracket_count = collected_lines[0].count('(') - collected_lines[0].count(')')
                        
                        # 如果括号不匹配，继续收集后续行
                        while bracket_count > 0 and current_line_idx < len(lines):
                            current_line_idx += 1
                            if current_line_idx <= len(lines):
                                # 注意：line_num是从1开始的，所以需要减1才是索引
                                next_line = lines[current_line_idx - 1].strip() if current_line_idx - 1 < len(lines) else ""
                                if next_line:
                                    collected_lines.append(next_line)
                                    bracket_count += next_line.count('(') - next_line.count(')')
                                    # 标记该行已处理
                                    processed_lines.add(current_line_idx)
                                else:
                                    break
                            else:
                                break
                        
                        # 合并所有行
                        multipolygon_str = ' '.join(collected_lines).strip()
                        multipolygon_match = type('Match', (), {'group': lambda x: multipolygon_str})()

                if multipolygon_match:
                    try:
                        multipolygon_str = multipolygon_match.group(0) if hasattr(multipolygon_match, 'group') else multipolygon_match
                        geom = loads_wkt(multipolygon_str)
                        if isinstance(geom, MultiPolygon):
                            for poly in geom.geoms:
                                if not poly.is_valid:
                                    poly = make_valid(poly)
                                polygons.append(poly)
                            st.info(f"ℹ️ 第 {line_num} 行：MULTIPOLYGON包含 {len(geom.geoms)} 个POLYGON，已展开")
                        elif isinstance(geom, Polygon):
                            if not geom.is_valid:
                                geom = make_valid(geom)
                            polygons.append(geom)
                        else:
                            st.warning(f"⚠️ 第 {line_num} 行：解析结果不是POLYGON或MULTIPOLYGON")
                    except Exception as e2:
                        st.warning(f"⚠️ 第 {line_num} 行MULTIPOLYGON解析失败：{str(e2)}")
                        # 如果解析失败，尝试直接使用整行作为WKT
                        try:
                            geom = loads_wkt(line)
                            if isinstance(geom, MultiPolygon):
                                for poly in geom.geoms:
                                    if not poly.is_valid:
                                        poly = make_valid(poly)
                                    polygons.append(poly)
                                st.info(f"ℹ️ 第 {line_num} 行：MULTIPOLYGON包含 {len(geom.geoms)} 个POLYGON，已展开")
                            elif isinstance(geom, Polygon):
                                if not geom.is_valid:
                                    geom = make_valid(geom)
                                polygons.append(geom)
                        except Exception as e3:
                            st.warning(f"⚠️ 第 {line_num} 行：最终解析失败：{str(e3)}")
                else:
                    # 尝试POLYGON
                    polygon_match = re.search(r'POLYGON\s*\([^)]+\)', line, re.IGNORECASE)
                    if polygon_match:
                        try:
                            polygon_str = polygon_match.group(0)
                            geom = loads_wkt(polygon_str)
                            if isinstance(geom, Polygon):
                                if not geom.is_valid:
                                    geom = make_valid(geom)
                                polygons.append(geom)
                            elif isinstance(geom, MultiPolygon):
                                for poly in geom.geoms:
                                    if not poly.is_valid:
                                        poly = make_valid(poly)
                                    polygons.append(poly)
                                st.info(f"ℹ️ 第 {line_num} 行：MULTIPOLYGON包含 {len(geom.geoms)} 个POLYGON，已展开")
                            else:
                                st.warning(f"⚠️ 第 {line_num} 行：解析结果不是POLYGON或MULTIPOLYGON")
                        except Exception as e2:
                            st.warning(f"⚠️ 第 {line_num} 行POLYGON解析失败：{str(e2)}")
                    else:
                        st.warning(f"⚠️ 第 {line_num} 行未找到POLYGON或MULTIPOLYGON格式：{line[:50]}...")

        return polygons

    def _check_intersections(self, polygons):
        """检测POLYGON之间的相交关系"""
        has_intersection = False
        details = []

        if len(polygons) < 2:
            return {
                'has_intersection': False,
                'details': ["至少需要2个POLYGON才能检测相交"]
            }

        # 检查所有POLYGON对
        intersection_pairs = []
        for i in range(len(polygons)):
            for j in range(i + 1, len(polygons)):
                poly1 = polygons[i]
                poly2 = polygons[j]
                
                if poly1.intersects(poly2):
                    has_intersection = True
                    intersection_pairs.append((i + 1, j + 1))
                    intersection_area = poly1.intersection(poly2).area
                    details.append(f"POLYGON {i+1} 与 POLYGON {j+1} 相交（相交面积：{intersection_area:.6f}）")

        if not has_intersection:
            details.append(f"共检测 {len(polygons)} 个POLYGON，但它们之间没有相交关系")

        return {
            'has_intersection': has_intersection,
            'details': details,
            'intersection_pairs': intersection_pairs
        }

    def _merge_polygons(self, polygons):
        """合并POLYGON"""
        try:
            if len(polygons) == 0:
                return None

            if len(polygons) == 1:
                return polygons[0]

            # 使用unary_union合并所有POLYGON
            merged = unary_union(polygons)

            # 如果结果是MultiPolygon，尝试转换为单个Polygon
            if hasattr(merged, 'geoms'):
                # 如果合并后是多个不相交的POLYGON，返回第一个
                if len(merged.geoms) > 1:
                    st.warning(f"⚠️ 合并后产生了 {len(merged.geoms)} 个独立的POLYGON，返回外包络线")
                    # 返回所有POLYGON的外包络线
                    return merged.convex_hull
                else:
                    merged = merged.geoms[0]

            # 修复无效的几何体
            if not merged.is_valid:
                merged = make_valid(merged)

            return merged

        except Exception as e:
            self.logger.error(f"合并POLYGON失败：{str(e)}", exc_info=True)
            raise Exception(f"合并失败：{str(e)}")

