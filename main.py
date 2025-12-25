import flet as ft
import base64
import csv
import io
from analysis_engine import AnalysisEngine


def main(page: ft.Page):
    # --- 1. 全局配置 ---
    page.title = "BioScanner Pro"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10
    # 禁止页面级滚动，因为我们有内部滚动区域
    page.scroll = None

    engine = AnalysisEngine()

    # --- 2. 状态管理 ---
    state = {
        # 图像显示参数
        "scale_factor": 1.0,  # 真实尺寸 / 显示尺寸
        "disp_w": 0,  # 显示宽度
        "disp_h": 0,  # 显示高度

        # 业务数据
        "points": [],  # 存储的是【虚拟显示坐标】，传给引擎前需要乘 scale_factor
        "mode": "calib",  # 'calib' | 'scan'
        "grid_real": [],  # 存储【真实坐标】的网格
        "results": [],
        "fit_results": []
    }

    # --- 3. UI 组件 ---
    status_txt = ft.Text("Step 1: Load Image", color="grey", size=12)

    # 标曲输入框
    input_name = ft.TextField(label="Curve Name", value="Batch_01", expand=True, text_size=12, dense=True)
    input_reps = ft.TextField(label="Reps", value="2", width=60, text_size=12, dense=True)
    input_concs = ft.TextField(label="Concentrations", value="0, 0.2, 0.4, 0.8, 1.0", text_size=12, dense=True)

    # 历史记录下拉框
    dd_history = ft.Dropdown(label="Select Curve", expand=True, text_size=12, dense=True)

    # 结果表格 (DataTable)
    data_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("Row"))] + [ft.DataColumn(ft.Text(str(i))) for i in range(1, 17)],
        rows=[],
        column_spacing=5,
        data_text_style=ft.TextStyle(size=10)
    )

    # 标曲计算结果显示区 (初始隐藏)
    calib_radio_group = ft.RadioGroup(content=ft.Column([]))

    def on_confirm_save(e):
        """保存用户选择的最佳通道"""
        sel_ch = calib_radio_group.value
        if not sel_ch: return

        # 从暂存结果中提取模型
        model_data = next(r for r in state["fit_results"] if r['channel'] == sel_ch)

        name = input_name.value or "Curve"
        # 保存到本地存储
        page.client_storage.set(f"curve_{name}", model_data)
        engine.active_model = model_data

        refresh_history()

        calib_result_area.visible = False
        status_txt.value = f"Saved '{name}' ({sel_ch}). Switch to Scan Tab."
        status_txt.color = "green"
        page.update()

    btn_save_curve = ft.ElevatedButton("Save & Apply", icon=ft.Icons.CHECK, on_click=on_confirm_save,
                                       bgcolor="green100")

    calib_result_area = ft.Column([
        ft.Divider(),
        ft.Text("Success! Select best channel:", weight="bold", size=12, color="blue"),
        ft.Container(
            content=calib_radio_group,
            height=120,  # 限制高度防止占满屏幕
            padding=5,
            border=ft.border.all(1, "grey"),
            border_radius=5,
            bgcolor="white"
        ),
        btn_save_curve
    ], visible=False, scroll=ft.ScrollMode.AUTO)

    # --- 4. 核心逻辑 ---

    def refresh_history():
        """刷新下拉菜单"""
        try:
            keys = page.client_storage.get_keys("curve_")
            opts = [ft.dropdown.Option("demo", text="Demo: colorN (H)")]
            if keys:
                for k in keys:
                    opts.append(ft.dropdown.Option(k, text=k.replace("curve_", "")))
            dd_history.options = opts
            dd_history.update()
        except:
            pass

    def on_load_curve(e):
        val = dd_history.value
        if not val: return

        if val == "demo":
            engine.active_model = {'k': -0.1266, 'b': 3.9606, 'channel': 'H', 'r2': 0.99}
            status_txt.value = "Active: Demo Curve (H)"
        else:
            data = page.client_storage.get(val)
            if data:
                # 兼容旧数据的容错处理
                ch = data.get('channel', 'H')
                r2 = data.get('r2', 0.0)
                engine.active_model = {'k': data['k'], 'b': data['b'], 'channel': ch, 'r2': r2}
                status_txt.value = f"Active: {val} ({ch}) R2={r2:.3f}"

        status_txt.color = "blue"
        status_txt.update()

    def on_tap_img(e: ft.TapEvent):
        """核心交互：坐标转换逻辑"""
        if not engine.current_img_data: return

        # 1. 获取点击的【虚拟坐标】 (相对于800宽度的图)
        vx, vy = e.local_x, e.local_y
        state["points"].append([vx, vy])

        # 2. 界面显示标记点 (显示在虚拟位置)
        marker = ft.Container(
            left=vx - 6, top=vy - 6, width=12, height=12,
            border=ft.border.all(2, "red"),
            border_radius=6,
            bgcolor="#80FFFF00"  # 半透明黄
        )
        stack_content.controls.append(marker)

        # 3. 如果是扫描模式，实时预览网格
        if state["mode"] == "scan" and len(state["points"]) == 3:
            # 取出最后三个点的【虚拟坐标】
            p1, p2, p3 = state["points"][-3:]

            # --- 关键：转换坐标系进行计算 ---
            scale = state["scale_factor"]

            # 转为【真实坐标】传给引擎
            real_p1 = [p1[0] * scale, p1[1] * scale]
            real_p2 = [p2[0] * scale, p2[1] * scale]
            real_p3 = [p3[0] * scale, p3[1] * scale]

            # 引擎计算出【真实网格】
            real_grid = engine.calculate_grid_128(real_p1, real_p2, real_p3)
            state["grid_real"] = real_grid  # 保存真实坐标用于取色

            # 将真实网格转回【虚拟坐标】用于绘图
            for row in real_grid:
                for rx, ry in row:
                    dvx, dvy = rx / scale, ry / scale
                    stack_content.controls.append(
                        ft.Container(left=dvx - 2, top=dvy - 2, width=4, height=4, bgcolor="#00FF00")
                    )
            status_txt.value = "Grid mapped (Green). Ready to Calc."

        elif state["mode"] == "calib":
            status_txt.value = f"Calib Point {len(state['points'])} added."

        stack_content.update()
        status_txt.update()

    def run_calibration(e):
        """执行标曲计算"""
        pts = state["points"]
        if not pts: return

        try:
            # 准备浓度数据
            base_concs = [float(x) for x in input_concs.value.split(",")]
            reps = int(input_reps.value)
            targets = []
            for c in base_concs: targets.extend([c] * reps)

            if len(targets) != len(pts):
                status_txt.value = f"Error: Points {len(pts)} != Targets {len(targets)}"
                status_txt.update();
                return

            # --- 关键：将所有选点转换为真实坐标 ---
            scale = state["scale_factor"]
            real_pts = [[p[0] * scale, p[1] * scale] for p in pts]

            # 引擎计算
            results = engine.auto_fit_channels(real_pts, targets)
            state["fit_results"] = results

            # 显示结果供选择
            radio_options = []
            for res in results[:5]:  # 只显示前5个
                label = f"{res['channel']}: R²={res['r2']:.4f}"
                radio_options.append(ft.Radio(value=res['channel'], label=label))

            calib_radio_group.content.controls = radio_options
            calib_radio_group.value = results[0]['channel']

            calib_result_area.visible = True
            status_txt.value = "Analysis Done. Check results below."
            page.update()

        except Exception as ex:
            status_txt.value = f"Error: {ex}";
            status_txt.update()

    def run_scan(e):
        """执行扫描计算"""
        if not engine.active_model:
            status_txt.value = "No Curve Loaded!";
            status_txt.update();
            return
        if not state["grid_real"]:
            status_txt.value = "No Grid Defined!";
            status_txt.update();
            return

        mod = engine.active_model
        k, b, ch = mod['k'], mod['b'], mod['channel']

        rows_ui = []
        state["results"] = [["Row"] + [str(i) for i in range(1, 17)]]  # CSV Header

        # 使用存储的【真实坐标网格】进行取色
        for r_idx, row_coords in enumerate(state["grid_real"]):
            r_name = chr(65 + r_idx)
            csv_row = [r_name]
            cells_ui = [ft.DataCell(ft.Text(r_name, weight="bold"))]

            for rx, ry in row_coords:
                # 引擎取色 (使用真实坐标)
                vals = engine.get_pixel_values(engine.current_img_data, rx, ry)
                if vals:
                    conc = k * vals[ch] + b
                    conc = max(0.0, conc)
                    txt_color = "black" if conc < 1.0 else "red"
                    conc_str = f"{conc:.2f}"
                    cells_ui.append(ft.DataCell(ft.Text(conc_str, color=txt_color)))
                    csv_row.append(conc_str)
                else:
                    cells_ui.append(ft.DataCell(ft.Text("-")))
                    csv_row.append("-")

            rows_ui.append(ft.DataRow(cells=cells_ui))
            state["results"].append(csv_row)

        data_table.rows = rows_ui
        status_txt.value = "Scan Complete."
        page.update()

    def export_csv(e):
        if not state["results"]: return
        s_io = io.StringIO()
        csv.writer(s_io).writerows(state["results"])
        page.dialog = ft.AlertDialog(
            title=ft.Text("CSV Data"),
            content=ft.TextField(value=s_io.getvalue(), multiline=True, read_only=True, text_size=10)
        )
        page.dialog.open = True
        page.update()

    # --- 5. 图像加载与虚拟化 ---

    # 核心容器：Stack的大小将不再是原图大小，而是缩放后的大小
    stack_content = ft.Stack()

    img_viewer = ft.InteractiveViewer(
        min_scale=1.0,  # 初始状态填满容器
        max_scale=10.0,  # 允许放大10倍细节
        content=ft.GestureDetector(
            on_tap_up=on_tap_img,
            content=stack_content
        ),
        expand=True
    )

    def on_file_result(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            # 1. 引擎处理 (读取原图)
            data = engine.process_img(path)
            engine.current_img_data = data
            real_w, real_h = data["size"]

            # 2. 计算显示尺寸 (关键步骤)
            # 我们强制将显示宽度设为 800像素 (兼顾清晰度和手机屏幕适应性)
            # 无论原图是 4000 还是 2000，都压缩到 800 显示
            # 这样 InteractiveViewer 初始就不会巨大
            VIRTUAL_WIDTH = 800
            scale = real_w / VIRTUAL_WIDTH
            virtual_height = int(real_h / scale)

            # 更新状态
            state["scale_factor"] = scale
            state["disp_w"] = VIRTUAL_WIDTH
            state["disp_h"] = virtual_height

            # 3. 设置 UI
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            # 重置 Stack 和 Image 的尺寸为【虚拟尺寸】
            stack_content.width = VIRTUAL_WIDTH
            stack_content.height = virtual_height
            stack_content.controls = [
                ft.Image(
                    src_base64=b64,
                    width=VIRTUAL_WIDTH,
                    height=virtual_height,
                    fit=ft.ImageFit.FILL  # 强制填满这个虚拟框
                )
            ]

            # 清理旧数据
            state["points"] = []
            state["grid_real"] = []
            calib_result_area.visible = False

            status_txt.value = f"Loaded. Real: {real_w}x{real_h} -> Display: {VIRTUAL_WIDTH}x{virtual_height}"
            page.update()

    picker = ft.FilePicker(on_result=on_file_result)
    page.overlay.append(picker)

    # --- 6. 布局组装 ---

    def switch_mode(e):
        state["mode"] = "calib" if tabs.selected_index == 0 else "scan"
        # 清除标记点
        if len(stack_content.controls) > 1:
            stack_content.controls = stack_content.controls[:1]
            state["points"] = []
            stack_content.update()

        col_calib.visible = (state["mode"] == "calib")
        col_scan.visible = (state["mode"] == "scan")
        page.update()

    tabs = ft.Tabs(
        selected_index=0,
        on_change=switch_mode,
        tabs=[ft.Tab(text="Calibration"), ft.Tab(text="128-Well Scan")]
    )

    col_calib = ft.Column([
        ft.Row([input_name, input_reps]),
        input_concs,
        ft.ElevatedButton("Analyze Curve", icon=ft.Icons.ANALYTICS, on_click=run_calibration, bgcolor="blue100",
                          width=200),
        calib_result_area
    ], spacing=5)

    col_scan = ft.Column([
        ft.Row([dd_history, ft.IconButton(ft.Icons.REFRESH, on_click=lambda _: refresh_history())]),
        ft.Row([
            ft.ElevatedButton("Calc Grid", icon=ft.Icons.CALCULATE, on_click=run_scan, bgcolor="green100", expand=True),
            ft.ElevatedButton("CSV", icon=ft.Icons.COPY, on_click=export_csv)
        ]),
        ft.Container(
            content=ft.Column([data_table], scroll=ft.ScrollMode.ALWAYS),
            height=150, border=ft.border.all(1, "grey")
        )
    ], visible=False, spacing=5)

    # 主布局
    page.add(
        ft.Column([
            ft.Row([
                ft.Text("BioScanner Pro", size=20, weight="bold"),
                ft.IconButton(ft.Icons.IMAGE_SEARCH, on_click=lambda _: picker.pick_files())
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            tabs,

            # 顶部控制面板
            ft.Container(
                content=ft.Column([col_calib, col_scan]),
                padding=10, bgcolor="#F0F4F8", border_radius=8
            ),

            status_txt,

            # 底部图片浏览区 (InteractiveViewer)
            ft.Container(
                content=img_viewer,
                expand=True,  # 占满剩余空间
                bgcolor="#333333",
                border=ft.border.all(1, "grey"),
                clip_behavior=ft.ClipBehavior.HARD_EDGE  # 裁剪溢出内容
            )
        ], expand=True)
    )

    refresh_history()
    dd_history.on_change = on_load_curve


ft.app(target=main)
