"""
gpxhandle/graph_view.py

標高グラフの作成
"""

import flet as ft
from typing import List, Dict, Optional
import gpxpy.gpx
import math
from datetime import timedelta, datetime
import numpy as np
import traceback

class ElevationGraph(ft.Container):
    """標高グラフと統計情報表示コンポーネント"""

    SMOOTHING_WINDOW_SIZE: int = 5 # 移動平均ウィンドウサイズ (奇数推奨)
    ASCENT_THRESHOLD_METERS: float = 0.3 # 累積登り閾値 (m)

    def __init__(self):
        # --- 軸ラベル・タイトルのサイズ設定 ---
        AXIS_LABEL_SIZE = 20  # ★ 軸の数値ラベルサイズ (小さめに)
        AXIS_TITLE_SIZE = 9 # ★ 軸タイトルサイズ

        # --- 統計情報表示用 Text ---
        self.stats_text = ft.Text(
            # value="時間: -\n距離: -\n累積登り: -", # 初期値はload_pointsで設定
            value="", # 最初は空
            size=10, color=ft.Colors.BLACK87, selectable=True
        )
        stats_container = ft.Container(
            content=self.stats_text,
            bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
            padding=ft.padding.all(4),
            border_radius=ft.border_radius.all(3),
            top=5, right=5, # Stack内での位置
        )

        # --- グラフ本体 ---
        self.chart = ft.LineChart(
            expand=True,
            tooltip_bgcolor="rgba(0,0,0,0.8)",
            min_y=0, max_y=1000, # データロード時に再設定
            min_x=0, # X軸最小値
            border=ft.border.all(2, ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)),
            horizontal_grid_lines=ft.ChartGridLines(
                interval=100, color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE), width=1
            ),
            vertical_grid_lines=ft.ChartGridLines(
                interval=100, color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE), width=1
            ),
            # --- ★ 軸ラベル・タイトルのサイズ調整箇所 ---
            left_axis=ft.ChartAxis(
                labels_size=AXIS_LABEL_SIZE,
                title=ft.Text("標高(m)", size=AXIS_TITLE_SIZE, weight=ft.FontWeight.BOLD),
            ),
            bottom_axis=ft.ChartAxis(
                labels_interval=1, # X軸ラベル間隔 (データロード時に再設定)
                labels_size=AXIS_LABEL_SIZE, # X軸数値ラベルサイズ
                title=ft.Text("距離(km)", size=AXIS_TITLE_SIZE, weight=ft.FontWeight.BOLD),
            ),
            data_series=[],
        )

        # --- グラフと統計情報を重ねる ---
        graph_stack = ft.Stack(
            [
                self.chart,
                stats_container, # 統計情報を上に重ねる
            ],
            expand=True
        )

        # --- グラフ下の情報表示用 ---
        self.info_text = ft.Text("", size=11, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, height=15) # 高さを指定

        # --- 全体を Column で構成 ---
        super().__init__(
            content=ft.Column(
                [
                    graph_stack,    # グラフ本体 + 統計情報
                    self.info_text  # グラフ下の情報テキスト
                ],
                spacing=0, # グラフとテキストの間隔
                alignment=ft.MainAxisAlignment.START, # 上詰め
            ),
            expand=True,
        )
        # --- 内部データ ---
        self.points: List[Dict] = []
        self.distances: List[float] = [] # 累積距離 (km)
        self.total_time_str = "-"
        self.total_distance_km = 0.0
        self.total_ascent_m = 0.0

    def _smooth_elevations(self, elevations: List[float], window_size: int) -> List[float]:
        """標高データリストに NumPy の convolve を使って移動平均フィルタを適用する"""
        if window_size < 3 or not elevations or len(elevations) < window_size:
            print("[DEBUG Graph] Smoothing skipped (too few points or small window)")
            return elevations # 平滑化しない場合は元のリストを返す

        # NumPy 配列に変換
        elevation_array = np.array(elevations, dtype=float) # float型を指定

        # ウィンドウ（カーネル）を作成 (要素がすべて 1/window_size)
        window = np.ones(window_size) / window_size

        try:
            # 畳み込み演算で移動平均を計算
            # mode='same' は出力配列が入力と同じ長さになるように調整する
            # 境界の処理はデフォルト (zero padding) になるため、端の値は不正確になる可能性がある
            smoothed_array = np.convolve(elevation_array, window, mode='same')

            # ★ オプション: 端点の値を元の値に戻す (より自然な結果になる場合がある) ★
            half_window = window_size // 2
            smoothed_array[:half_window] = elevation_array[:half_window]
            smoothed_array[-half_window:] = elevation_array[-half_window:]
            # または smoothed_array = np.convolve(elevation_array, window, mode='valid')
            # を使い、結果の配列長が変わることに対応する（より複雑になる）

            print(f"[DEBUG Graph] Applied NumPy smoothing with window size {window_size}")
            return smoothed_array.tolist() # 結果をリストとして返す

        except Exception as e:
            print(f"[ERROR] Error during NumPy smoothing: {e}")
            traceback.print_exc()
            return elevations # エラー時は元のデータを返す
 
    def load_points(self, points: List[Dict]):
        """
        ポイントデータを読み込み、統計計算、グラフ描画を行う。
        距離計算に gpxpy.distance_2d を使用。
        累積登り計算に 移動平均(NumPy) + 閾値処理 を使用。
        """
        print(f"[DEBUG Graph] load_points: 受信ポイント数 = {len(points)}")
        self.points = points # 元の辞書リストを保持
        self.distances = [0.0] # 累積距離リスト(km)を初期化
        current_dist_m = 0.0   # 累積距離(m)
        total_ascent = 0.0     # 累積登り(m)
        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None
        data_points = []       # グラフのデータポイント用
        gpx_points = []        # gpxpyオブジェクト用リスト

        try:
            # --- 1. GPXデータからgpxpy.GPXTrackPointオブジェクトを生成 ---
            # 同時に start_time と end_time も取得
            for i, p in enumerate(points):
                lat = p.get('lat')
                lon = p.get('lon')
                ele = p.get('ele')
                time = p.get('time') # JSTのdatetimeオブジェクトのはず
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    # 標高がNoneや不正値の場合は0.0として扱う (または補間処理)
                    elevation = ele if isinstance(ele, (int, float)) else 0.0
                    gpx_p = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon, elevation=elevation, time=time)
                    gpx_points.append(gpx_p)
                    # 有効な時刻情報を記録
                    if time and isinstance(time, datetime):
                        if start_time is None: start_time = time
                        end_time = time # 最後の有効な時刻で上書き
                else:
                    print(f"[WARN] 無効な座標データ: index {i}")
                    gpx_points.append(None) # 無効な座標はNoneとしておく

            # --- 2. 標高データを抽出し、移動平均で平滑化 ---
            raw_elevations = [(p.elevation or 0.0) if p else 0.0 for p in gpx_points]
            smoothed_elevations = self._smooth_elevations(raw_elevations, self.SMOOTHING_WINDOW_SIZE)
            if len(smoothed_elevations) != len(raw_elevations):
                print("[ERROR] 平滑化後の標高データ数が一致しません！元のデータを使用します。")
                smoothed_elevations = raw_elevations

            # --- 3. 距離(2D)と累積登り(平滑化+閾値)を計算 ---
            self.distances = [0.0] # 距離リスト再初期化
            current_dist_m = 0.0
            total_ascent = 0.0
            for i in range(len(gpx_points) - 1):  # gpx_points の数でループ
                p1 = gpx_points[i]
                p2 = gpx_points[i+1]
                dist_m = 0.0
                # 平滑化後の標高差を計算
                ele_diff_smoothed = smoothed_elevations[i+1] - smoothed_elevations[i]

                # 隣接する両方のポイントが有効な場合のみ計算
                if p1 and p2:
                    # 2D距離を計算
                    dist_m = p1.distance_2d(p2) or 0.0
                    current_dist_m += dist_m
                    # 平滑化後の標高差と閾値で累積登りを計算
                    if ele_diff_smoothed > self.ASCENT_THRESHOLD_METERS:
                        total_ascent += ele_diff_smoothed
                # 距離リストには常に現在の累積距離を追加 (ポイント数と合わせるため)
                self.distances.append(current_dist_m / 1000.0) # kmで追加

            print(f"[DEBUG Graph] 距離(2D)計算完了: 全長 = {current_dist_m / 1000.0:.2f} km")
            print(f"[DEBUG Graph] 累積登り計算完了 (平滑化{self.SMOOTHING_WINDOW_SIZE}点 + 閾値>{self.ASCENT_THRESHOLD_METERS}m): {total_ascent:.1f} m")

            # --- 4. 歩行時間計算 ---
            total_seconds = 0
            if start_time and end_time and end_time > start_time:
                delta: timedelta = end_time - start_time
                total_seconds = delta.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            self.total_time_str = f"{hours:02d}:{minutes:02d}" if total_seconds > 0 else "-"
            self.total_distance_km = current_dist_m / 1000.0
            self.total_ascent_m = total_ascent

            # --- 5. 統計情報テキスト更新 ---
            self.stats_text.value = f"時間: {self.total_time_str}\n" \
                                    f"距離: {self.total_distance_km:.2f} km\n" \
                                    f"累積登り: {self.total_ascent_m:.0f} m"
            self.stats_text.update() # 統計テキストを更新

            # --- 6. グラフ用データポイント生成 (元の標高を使用) ---
            data_points = []
            for i, p_dict in enumerate(points): # 間引かれた points でループ
                ele = p_dict.get('ele')
                # ★★★ distances リストとのインデックスずれがないか確認 ★★★
                if isinstance(ele, (int, float)) and i < len(self.distances):
                    x_val = self.distances[i]
                    y_val = ele
                    if not math.isnan(x_val) and not math.isinf(x_val) and \
                       not math.isnan(y_val) and not math.isinf(y_val):
                        data_points.append(ft.LineChartDataPoint(x=x_val, y=y_val, tooltip=...))
                    else: print(f"[WARN] Invalid DP skipped: x={x_val}, y={y_val} at index {i}")
                else: print(f"[WARN] DP generation skipped: index {i}, ele={ele}, dist_len={len(self.distances)}")

            print(f"[DEBUG Graph] 生成されたグラフデータポイント数 = {len(data_points)}")
            # ★★★ 最初の数件のデータポイントを出力 ★★★
            print(f"[DEBUG Graph] First 5 data points (x, y): {[(dp.x, dp.y) for dp in data_points[:5]] if data_points else 'None'}")

            # --- 7. グラフデータ系列設定 ---
            self.chart.data_series = [
                ft.LineChartData(
                    data_points=data_points,
                    color=ft.Colors.BLUE_ACCENT_700, # 少し濃い色に
                    stroke_width=1.5, # 少し細く
                    curved=False,
                )
            ]
            print(f"[DEBUG Graph] data_series 設定完了: {len(self.chart.data_series)} 系列, ポイント数 {len(data_points)}")

            # --- 8. 軸範囲設定 ---
            # Y軸(標高)
            min_ele_valid, max_ele_valid = None, None
            if points:
                elevations = [p.get('ele') for p in points if isinstance(p.get('ele'), (int, float))]
                if elevations:
                    min_ele_valid = min(elevations)
                    max_ele_valid = max(elevations)
                    ele_range = max_ele_valid - min_ele_valid
                    padding = ele_range * 0.1 if ele_range > 10 else 5 # 最小パディング
                    self.chart.min_y = math.floor((min_ele_valid - padding) / 10) * 10
                    self.chart.max_y = math.ceil((max_ele_valid + padding) / 10) * 10
                else: self.chart.min_y = 0; self.chart.max_y = 100 # 標高データなし
            else: self.chart.min_y = 0; self.chart.max_y = 100 # ポイントなし

            # X軸(距離) と グリッド線間隔
            max_dist = self.distances[-1] if self.distances else 0
            x_interval = 1; max_x = 1 # デフォルト
            if max_dist > 0:
                intervals = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]
                ideal_ticks = 6 # 目指す目盛り数 (6本程度)
                ideal_interval = max_dist / ideal_ticks
                # ideal_interval に最も近い intervals の値を選ぶ
                x_interval = min(intervals, key=lambda x: abs(x - ideal_interval))
                # 最小間隔を保証 (例: 0.1km)
                x_interval = max(0.1, x_interval)
                max_x = math.ceil(max_dist / x_interval) * x_interval # 切りの良い最大値
            self.chart.bottom_axis.labels_interval = x_interval
            if self.chart.vertical_grid_lines: self.chart.vertical_grid_lines.interval = x_interval
            self.chart.min_x = 0
            self.chart.max_x = max_x if max_x > 0 else 1 # 最小でも1km

            # Y軸グリッド線間隔
            if self.chart.horizontal_grid_lines and min_ele_valid is not None and max_ele_valid is not None:
                y_range = self.chart.max_y - self.chart.min_y # 設定後の範囲を使う
                if y_range > 0:
                    y_intervals = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
                    ideal_y_ticks = 5
                    ideal_y_interval = y_range / ideal_y_ticks
                    y_interval = min(y_intervals, key=lambda y: abs(y - ideal_y_interval))
                    self.chart.horizontal_grid_lines.interval = max(1, y_interval) # 最小1m
                else: self.chart.horizontal_grid_lines.interval = 10
            print(f"[DEBUG Graph] Axes set: Y({self.chart.min_y:.0f}-{self.chart.max_y:.0f}, grid={self.chart.horizontal_grid_lines.interval if self.chart.horizontal_grid_lines else 'N/A'}), X({self.chart.min_x}-{self.chart.max_x:.1f}, label_int={x_interval}, grid_int={self.chart.vertical_grid_lines.interval if self.chart.vertical_grid_lines else 'N/A'})")


            # --- 9. グラフ下の情報テキストをクリア ---
            self.hide_point_info() # updateも内部で呼ぶ

            # --- 10. グラフ全体のUI更新 ---
            self.update()
            print("[DEBUG Graph] load_points: 完了")

        except Exception as load_ex:
            print(f"[ERROR] graph_view load_points でエラーが発生しました: {load_ex}")
            traceback.print_exc()
            # エラー発生時もグラフをクリアする
            self.points = []
            self.distances = []
            self.chart.data_series = []
            self.stats_text.value = "エラーが発生しました"
            self.hide_point_info()
            self.update()

    def highlight(self, index: int):
        """指定されたインデックスの情報を表示"""
        if 0 <= index < len(self.points) and index < len(self.distances):
            p = self.points[index]
            dist_km = self.distances[index]
            ele_m = p.get('ele', 0.0)
            time_obj = p.get('time') # datetime オブジェクトを取得
            time_str = time_obj.strftime('%H:%M:%S') if isinstance(time_obj, datetime) else "--:--:--"

            self.info_text.value = f"{time_str} - 距離:{dist_km:.2f}km / 標高:{ele_m:.1f}m"
            self.info_text.update() # テキストのみ更新
            # print(f"[GraphView] Showing info for index {index}")
        else:
            self.hide_point_info()

    def hide_point_info(self):
        """グラフ下の情報テキストをクリア"""
        if self.info_text.value != "":
             self.info_text.value = ""
             self.info_text.update()
