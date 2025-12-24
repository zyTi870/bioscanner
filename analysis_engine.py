import cv2
import numpy as np
from sklearn.linear_model import LinearRegression

class AnalysisEngine:
    def __init__(self):
        self.k = None
        self.b = None

    def process_img(self, img_path):
        """科研级图像预处理：中值滤波降噪"""
        img = cv2.imread(img_path)
        if img is None: return None, (1, 1)
        orig_h, orig_w = img.shape[:2]
        # 使用中值滤波平滑密集孔位背景，降低采样噪音
        hsv = cv2.cvtColor(cv2.medianBlur(img, 5), cv2.COLOR_BGR2HSV)
        return hsv, (orig_w, orig_h)

    def calculate_rigid_grid(self, p_a1, p_a16, p_h1):
        """基于 A1, A16, H1 三点计算 128孔(16x8) 固定步长网格"""
        grid = []
        # 计算单孔横向步长矢量 (16列对应15个间隔)
        col_vx = (p_a16[0] - p_a1[0]) / 15.0
        col_vy = (p_a16[1] - p_a1[1]) / 15.0
        # 计算单孔纵向步长矢量 (8行对应7个间隔)
        row_vx = (p_h1[0] - p_a1[0]) / 7.0
        row_vy = (p_h1[1] - p_a1[1]) / 7.0

        for r in range(8):
            for c in range(16):
                x = p_a1[0] + c * col_vx + r * row_vx
                y = p_a1[1] + c * col_vy + r * row_vy
                grid.append([x, y])
        return grid

    def get_h_value(self, hsv_img, x, y, r=3):
        """密集点位下采样半径设为3，防止跨孔采样"""
        h_dim, w_dim = hsv_img.shape[:2]
        ix, iy = int(round(x)), int(round(y))
        roi = hsv_img[max(0, iy-r):min(h_dim, iy+r), max(0, ix-r):min(w_dim, ix+r), 0]
        return np.mean(roi) if roi.size > 0 else 0

    def fit_curve(self, h_vals, concs):
        """线性拟合标准曲线"""
        X = np.array(h_vals).reshape(-1, 1)
        Y = np.array(concs)
        model = LinearRegression().fit(X, Y)
        self.k, self.b = model.coef_[0], model.intercept_
        return self.k, self.b, model.score(X, Y)