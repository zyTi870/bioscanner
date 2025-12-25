import cv2
import numpy as np


class AnalysisEngine:
    def __init__(self):
        self.active_model = None  # {'k': float, 'b': float, 'channel': str, 'r2': float}
        self.current_img_data = None

    def process_img(self, img_path):
        """
        读取图像并返回多通道数据
        返回: 图像数据字典
        """
        img = cv2.imread(img_path)
        if img is None: return None

        # 预处理：轻微模糊去噪，防止单像素噪点干扰采样
        img_smooth = cv2.medianBlur(img, 3)
        hsv = cv2.cvtColor(img_smooth, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(img_smooth, cv2.COLOR_BGR2GRAY)

        return {
            "BGR": img_smooth,
            "HSV": hsv,
            "GRAY": gray,
            "size": (img.shape[1], img.shape[0])  # real_width, real_height
        }

    def get_pixel_values(self, img_data, x, y, r=4):
        """获取真实坐标 (x,y) 周围的颜色均值"""
        w, h = img_data["size"]
        ix, iy = int(round(x)), int(round(y))

        # 边界保护
        y_min, y_max = max(0, iy - r), min(h, iy + r)
        x_min, x_max = max(0, ix - r), min(w, ix + r)

        if x_min >= x_max or y_min >= y_max:
            return None

        # 提取各个通道的 ROI (Region of Interest)
        bgr = img_data["BGR"][y_min:y_max, x_min:x_max]
        hsv = img_data["HSV"][y_min:y_max, x_min:x_max]
        gray = img_data["GRAY"][y_min:y_max, x_min:x_max]

        # 计算均值
        m_bgr = np.mean(bgr, axis=(0, 1))
        m_hsv = np.mean(hsv, axis=(0, 1))
        m_gray = np.mean(gray)

        return {
            "B": m_bgr[0], "G": m_bgr[1], "R": m_bgr[2],
            "H": m_hsv[0], "S": m_hsv[1], "V": m_hsv[2],
            "Gray": m_gray
        }

    def auto_fit_channels(self, points, concs):
        """对7个通道分别进行拟合，返回排序后的结果列表"""
        if not self.current_img_data:
            raise Exception("Image not loaded")

        # 1. 采集数据
        raw_data = {k: [] for k in ["R", "G", "B", "H", "S", "V", "Gray"]}
        valid_points_count = 0

        for p in points:
            # p[0], p[1] 必须是真实原图坐标
            vals = self.get_pixel_values(self.current_img_data, p[0], p[1])
            if vals:
                valid_points_count += 1
                for k in raw_data:
                    raw_data[k].append(vals[k])

        if valid_points_count != len(concs):
            raise Exception(f"Sampling mismatch: Found {valid_points_count} valid points, expected {len(concs)}")

        Y = np.array(concs)
        results = []

        # 2. 拟合计算
        for ch, values in raw_data.items():
            X = np.array(values)
            if np.std(X) < 1e-6: continue  # 方差过小，跳过

            # 线性回归: Concentration = k * Color + b
            try:
                k, b = np.polyfit(X, Y, 1)

                # 计算 R2
                y_pred = k * X + b
                ss_res = np.sum((Y - y_pred) ** 2)
                ss_tot = np.sum((Y - np.mean(Y)) ** 2)
                r2 = 1 - (ss_res / (ss_tot + 1e-10))

                results.append({"channel": ch, "k": k, "b": b, "r2": r2})
            except:
                pass

        # 3. 按 R2 降序排序
        results.sort(key=lambda x: x["r2"], reverse=True)
        return results

    def calculate_grid_128(self, p_a1, p_a16, p_h1):
        """计算 16列 x 8行 网格坐标"""
        grid = []
        # 向量计算
        vx_c = (p_a16[0] - p_a1[0]) / 15.0
        vy_c = (p_a16[1] - p_a1[1]) / 15.0
        vx_r = (p_h1[0] - p_a1[0]) / 7.0
        vy_r = (p_h1[1] - p_a1[1]) / 7.0

        for r in range(8):
            row_pts = []
            for c in range(16):
                x = p_a1[0] + c * vx_c + r * vx_r
                y = p_a1[1] + c * vy_c + r * vy_r
                row_pts.append((x, y))
            grid.append(row_pts)
        return grid
