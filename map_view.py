# gpxhandle/map_view.py

import flet as ft
import flet_map as fmap # flet-map == 0.1.0
from typing import List, Dict, Optional
import traceback # エラー表示用

# --- タイル情報 (クレジットはここでは表示できない) ---
TILE_SOURCES = {
    "osm": {
        "name": "OpenStreetMap",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution_text": "© OpenStreetMap contributors", # 表示できないが情報は保持
    },
    "gsi_std": {
        "name": "地理院地図 標準",
        "url": "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
        "attribution_text": "国土地理院",
    },
    "gsi_pale": {
        "name": "地理院地図 淡色",
        "url": "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
        "attribution_text": "国土地理院",
    },
    "gsi_photo": {
        "name": "地理院地図 航空写真",
        "url": "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg",
        "attribution_text": "国土地理院",
    },
}

class MapView(ft.Container):
    """地図表示コンポーネント (flet-map==0.1.0 対応)"""
    def __init__(self):
        super().__init__(expand=True, border_radius=ft.border_radius.all(5))

        self.poly_layer = fmap.PolylineLayer(polylines=[])
        self.marker_layer = fmap.MarkerLayer(markers=[])
        self._current_zoom: float = 5.0

        # --- 初期タイルレイヤー ---
        # self.current_tile_key = "osm" # Open Street Map
        self.current_tile_key = "gsi_std"  # 地理院地図 標準
        self.tile_layer = fmap.TileLayer(
            url_template=TILE_SOURCES[self.current_tile_key]["url"],
            # attribution 引数はない
        )

        self.map = fmap.Map(
            expand=True,
            initial_center=fmap.MapLatitudeLongitude(35.681236, 139.767125),
            initial_zoom=10,
            layers=[
                self.tile_layer,
                self.poly_layer,
                self.marker_layer,
            ],
            # options 引数はない
        )
        self.content = self.map
        self.points: List[Dict] = []
        self.current_highlight_idx: int = -1

    def load_points(self, points: List[Dict]):
        self.points = points
        self.current_highlight_idx = -1
        self._update_map_display()
        self._auto_zoom() # 簡易版ズームを実行
        if points:
            self.highlight(0)

    def _update_map_display(self):
        if not self.points:
            self.poly_layer.polylines = []
            self.marker_layer.markers = []
            if self.map.page: self.map.update()
            return

        coords = [fmap.MapLatitudeLongitude(p["lat"], p["lon"]) for p in self.points]
        self.poly_layer.polylines = [
            fmap.PolylineMarker(
                coordinates=coords,
                border_stroke_width=4,
                border_color=ft.Colors.BLUE_700,
            )
        ]
        self.marker_layer.markers = [] # マーカーはhighlightで
        if self.map.page: self.map.update()

    def _get_zoom_level(self, span: float) -> float:
        """地理的な広がり(度)から簡易的にズームレベルを推定するヘルパー関数"""
        # この対応表は調整の余地あり
        if span == 0: return 18.0
        if span < 0.004: return 17.0 # より細かく
        if span < 0.008: return 16.0
        if span < 0.015: return 15.0
        if span < 0.03: return 14.0
        if span < 0.06: return 13.0
        if span < 0.12: return 12.0
        if span < 0.25: return 11.0
        if span < 0.5: return 10.0
        if span < 1.0: return 9.0
        if span < 2.0: return 8.0
        if span < 4.0: return 7.0
        if span < 8.0: return 6.0
        if span < 15.0: return 5.0
        if span < 30.0: return 4.0
        return 3.0 # それ以上はZoom 3
    
    def _auto_zoom(self):
        """
        軌跡全体が画面に収まるように中心とズームを計算し、
        少し余裕を持たせたズームレベルを設定する。
        """
        if not self.points: return  # ポイントなければ終了

        # --- center と new_zoom の初期化 ---
        center: Optional[fmap.MapLatitudeLongitude] = None # デフォルトの中心
        new_zoom = self._current_zoom # デフォルトのズーム

        if len(self.points) == 1:
            p = self.points[0]
            center = fmap.MapLatitudeLongitude(p["lat"], p["lon"])
            new_zoom = 15.0 # 1点の場合は固定
        elif len(self.points) > 1:  # ポイントが2つ以上の場合のみ計算
            lats = [p["lat"] for p in self.points]; lons = [p["lon"] for p in self.points]
            min_lat, max_lat = min(lats), max(lats); min_lon, max_lon = min(lons), max(lons)

            # 中心座標を計算
            center_lat = (max_lat + min_lat) / 2
            center_lon = (max_lon + min_lon) / 2
            center = fmap.MapLatitudeLongitude(center_lat, center_lon)

            # --- 緯度と経度の広がりをそれぞれ計算 ---
            lat_span = max_lat - min_lat
            lon_span = max_lon - min_lon

            # --- ★★★ 緯度/経度の広がりそれぞれに必要なズームレベルを計算 ★★★ ---
            # ヘルパー関数を使って、各spanを収めるのに必要なズームレベルを推定
            zoom_for_lat = self._get_zoom_level(lat_span)
            zoom_for_lon = self._get_zoom_level(lon_span)

            # --- ★★★ より小さいズームレベルを採用（広い範囲を表示） ★★★ ---
            # 緯度も経度も両方画面に収めるには、より広域を表示するズームレベルを選ぶ必要がある
            base_zoom = min(zoom_for_lat, zoom_for_lon)

            # --- ★★★ さらにマージンとしてズームレベルを1段階下げる ★★★ ---
            # これが「1.2倍大きく枠をとる」に近い効果を狙う調整
            adjusted_zoom = max(base_zoom - 1.0, 1.0) # 最小ズームは1
            new_zoom = adjusted_zoom

            print(f"[DEBUG] _auto_zoom: lat_span={lat_span:.4f}(zoom={zoom_for_lat}), lon_span={lon_span:.4f}(zoom={zoom_for_lon}) -> base_zoom={base_zoom}, adjusted_zoom={new_zoom}")
        else:
            # ポイントが0個の場合
            print("[WARN] _auto_zoom: No points to calculate zoom.")
            # この場合、中心やズームは変更しない（初期表示のまま）
            return            

        # 最終的な中心とズームで地図を設定
        self._current_center = center
        self._current_zoom = new_zoom
        self.map.center_on(self._current_center, zoom=self._current_zoom) # 地図に設定
        if self.map.page: self.map.update()

    def highlight(self, idx: int):
        self.current_highlight_idx = idx
        if not (0 <= idx < len(self.points)):
            self.marker_layer.markers = []
            if self.map.page: self.map.update()
            return

        p = self.points[idx]
        loc = fmap.MapLatitudeLongitude(p["lat"], p["lon"])

        if not self.marker_layer.markers:
            self.marker_layer.markers = [
                fmap.Marker(
                    content=ft.Icon(ft.Icons.LOCATION_ON, color=ft.Colors.RED_600, size=30),
                    coordinates=loc, width=30.0, height=30.0, alignment=ft.alignment.top_center,
                )
            ]
        else:
            self.marker_layer.markers[0].coordinates = loc

        # self.map.center_on(loc, zoom=None)
        if self.map.page: self.map.update()

    def change_tile_layer(self, tile_key: str):
        """タイルレイヤーを新しいオブジェクトに差し替える。"""
        if tile_key not in TILE_SOURCES or tile_key == self.current_tile_key:
            # キーが無効か、現在と同じなら何もしない
            return

        new_tile_info = TILE_SOURCES[tile_key]
        print(f"タイルレイヤー変更試行: {new_tile_info['name']}")

        try:
            # 1. 現在のタイルレイヤー (self.tile_layer) を layers リストから削除
            #    存在確認をしてから削除する
            if self.tile_layer in self.map.layers:
                print(f"  - Removing old tile layer: {self.tile_layer.url_template}")
                self.map.layers.remove(self.tile_layer)
            else:
                # self.tile_layer が見つからない場合 (念のため他のTileLayerも探す)
                print("  - WARN: self.tile_layer not found directly in map.layers. Searching...")
                found_and_removed = False
                for i, layer in enumerate(list(self.map.layers)): # リストのコピーでループ
                    if isinstance(layer, fmap.TileLayer):
                        print(f"  - Found TileLayer at index {i}, removing it.")
                        self.map.layers.pop(i) # インデックスで削除
                        found_and_removed = True
                        break
                if not found_and_removed:
                    print("  - ERROR: No TileLayer found to remove.")
                    # return # 続行不能かもしれないが、新しいレイヤー追加は試みる

            # 2. 新しい TileLayer オブジェクトを作成
            new_tile_layer = fmap.TileLayer(
                url_template=new_tile_info["url"],
                # attribution は設定できない
            )
            print(f"  - Creating new tile layer: {new_tile_layer.url_template}")

            # 3. 新しいレイヤーを layers リストの先頭 (インデックス 0) に挿入
            #    ※ layers[0] が一番下に表示されるレイヤー
            self.map.layers.insert(0, new_tile_layer)
            print(f"  - Inserted new layer at index 0. Total layers: {len(self.map.layers)}")

            # 4. self.tile_layer と self.current_tile_key を更新
            self.tile_layer = new_tile_layer # 新しいインスタンスを保持
            self.current_tile_key = tile_key

            # 5. 地図の更新を要求
            if self.map.page:
                print("  - Calling map.update()")
                self.map.update()
            else:
                print("  - Map not attached to page, skipping update.")

        except Exception as e:
            print(f"[ERROR] タイルレイヤー変更中にエラーが発生しました: {e}")
            traceback.print_exc()

    def get_current_tile_attribution(self) -> str:
        """現在のタイルソースのクレジット文字列を返す"""
        return TILE_SOURCES.get(self.current_tile_key, {}).get("attribution_text", "")

    def zoom_in(self):
        """地図を1段階ズームインする（中心は維持）"""
        max_zoom = 18
        new_zoom = min(self._current_zoom + 1, max_zoom)
        if new_zoom != self._current_zoom:
            print(f"Zooming in to: {new_zoom}")
            self._current_zoom = new_zoom # 内部状態更新
            # ★ 現在の中心座標(_current_center)と新しいズームレベルでcenter_onを呼ぶ ★
            self.map.center_on(self._current_center, zoom=self._current_zoom)
            if self.map.page: self.map.update()
        else: print(f"Already at max zoom ({max_zoom})")

    def zoom_out(self):
        """地図を1段階ズームアウトする（中心は維持）"""
        min_zoom = 1
        new_zoom = max(self._current_zoom - 1, min_zoom)
        if new_zoom != self._current_zoom:
            print(f"Zooming out to: {new_zoom}")
            self._current_zoom = new_zoom # 内部状態更新
            # ★ 現在の中心座標(_current_center)と新しいズームレベルでcenter_onを呼ぶ ★
            self.map.center_on(self._current_center, zoom=self._current_zoom)
            if self.map.page: self.map.update()
        else: print(f"Already at min zoom ({min_zoom})")

    def refresh(self):
        """データ変更時にポリラインとハイライトを更新"""
        self._update_map_display()
        if self.points and self.current_highlight_idx >= 0:
            self.highlight(self.current_highlight_idx)
