import flet as ft
import base64, time, os
from analysis_engine import AnalysisEngine


def main(page: ft.Page):
    page.title = "BioScanner Pro"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.ADAPTIVE
    engine = AnalysisEngine()

    # UI 常量与状态存储
    C_W, C_H = 500, 380
    state = {"hsv": None, "orig_size": (1, 1), "pts": [], "fitted": False}

    # --- UI 组件 ---
    status = ft.Text("Step 1: Calibration -> Step 2: Scan", color="blue700", weight="bold")
    input_name = ft.TextField(label="Curve Name (to save)", value="Batch_001", expand=True)
    input_concs = ft.TextField(label="Concentration Gradients", value="0.2,0.4,0.6,0.8,1.0", expand=True)
    input_reps = ft.TextField(label="Reps", value="3", width=80)

    # 历史记录下拉框
    history_dd = ft.Dropdown(label="Select Saved Curve", expand=True)

    img_ctrl = ft.Image(fit=ft.ImageFit.FILL, width=C_W, height=C_H)
    canvas = ft.Stack(width=C_W, height=C_H)
    res_list = ft.ListView(expand=True, spacing=2, height=180)

    # --- 核心业务逻辑 ---
    def load_selected_curve(e):
        curve_key = f"curve_{e.control.value}"
        data = page.client_storage.get(curve_key)
        if data:
            engine.k, engine.b = data['k'], data['b']
            state["fitted"] = True
            status.value = f"Active Curve: {e.control.value}"
            page.update()

    def refresh_history():
        keys = page.client_storage.get_keys("curve_")
        history_dd.options = [ft.dropdown.Option(k.replace("curve_", "")) for k in keys]
        history_dd.on_change = load_selected_curve
        page.update()

    def handle_click(e: ft.TapEvent):
        if state["hsv"] is None: return
        sx, sy = state["orig_size"][0] / C_W, state["orig_size"][1] / C_H
        rx, ry = e.local_x * sx, e.local_y * sy
        state["pts"].append([rx, ry])

        canvas.controls.append(
            ft.Container(bgcolor="red", width=6, height=6, border_radius=3, left=e.local_x - 3, top=e.local_y - 3))

        # 128孔模式：三点定位 A1, A16, H1
        if tabs.selected_index == 1 and len(state["pts"]) == 3:
            grid = engine.calculate_rigid_grid(state["pts"][0], state["pts"][1], state["pts"][2])
            state["pts"] = grid
            img_node = canvas.controls[0]
            canvas.controls.clear()
            canvas.controls.append(img_node)
            for gx, gy in grid:
                canvas.controls.append(
                    ft.Container(border=ft.border.all(1, "green"), width=4, height=4, left=gx / sx - 2,
                                 top=gy / sy - 2))
            status.value = "128-Well Grid Mapped"
        page.update()

    def do_analyze(e):
        if state["hsv"] is None or not state["pts"]: return
        if tabs.selected_index == 0:  # Calibration Mode
            h_vals = [engine.get_h_value(state["hsv"], p[0], p[1]) for p in state["pts"]]
            try:
                concs_raw = [float(x.strip()) for x in input_concs.value.split(",")]
                targets = [c for c in concs_raw for _ in range(int(input_reps.value))]
                k, b, r2 = engine.fit_curve(h_vals, targets)
                state["fitted"] = True
                # 持久化保存
                page.client_storage.set(f"curve_{input_name.value}", {"k": k, "b": b, "r2": r2})
                status.value = f"Success! R²={r2:.4f}. Saved as {input_name.value}"
                refresh_history()
            except Exception as ex:
                status.value = f"Error: {ex}"
        else:  # Analysis Mode
            if not state["fitted"]:
                status.value = "Error: Please select a curve or calibrate!"
            else:
                results = [max(0.0, engine.k * engine.get_h_value(state["hsv"], p[0], p[1]) + engine.b) for p in
                           state["pts"]]
                res_list.controls.clear()
                for i in range(0, 128, 16):
                    row_str = " | ".join([f"{v:.2f}" for v in results[i:i + 16]])
                    res_list.controls.append(
                        ft.Text(f"Row {chr(65 + i // 16)}: {row_str}", size=11, font_family="monospace"))
                status.value = "Scan Complete"
        page.update()

    # --- UI 布局 ---
    tabs = ft.Tabs(selected_index=0, tabs=[
        ft.Tab(text="Calibration", icon=ft.Icons.EDIT),
        ft.Tab(text="Scan 128-Well", icon=ft.Icons.GRID_ON)
    ], on_change=lambda _: [state["pts"].clear(), canvas.controls.clear(), page.update()])

    def on_upload(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            state["hsv"], state["orig_size"] = engine.process_img(path)
            with open(path, "rb") as f:
                img_ctrl.src_base64 = base64.b64encode(f.read()).decode()
            canvas.controls.clear()
            canvas.controls.append(ft.GestureDetector(content=img_ctrl, on_tap_down=handle_click))
            state["pts"] = []
            status.value = "Image Loaded"
            page.update()

    file_picker = ft.FilePicker(on_result=on_upload)
    page.overlay.append(file_picker)

    page.add(
        ft.AppBar(title=ft.Text("BioScanner Pro"), bgcolor="bluegrey50"),
        tabs,
        ft.Container(content=ft.Row([input_name, input_reps]), padding=5),
        ft.Container(
            content=ft.Row([history_dd, ft.IconButton(ft.Icons.REFRESH, on_click=lambda _: refresh_history())]),
            padding=5),
        ft.Container(content=input_concs, padding=5),
        status,
        ft.Container(content=canvas, width=C_W, height=C_H, border=ft.border.all(1, "grey"), border_radius=10),
        ft.Container(content=ft.Row([
            ft.ElevatedButton("Import Image", icon=ft.Icons.IMAGE, on_click=lambda _: file_picker.pick_files()),
            ft.FilledButton("Calculate", icon=ft.Icons.ANALYTICS, on_click=do_analyze)
        ], alignment=ft.MainAxisAlignment.CENTER), padding=10),
        res_list
    )
    refresh_history()


ft.app(target=main)