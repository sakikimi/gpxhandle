# gpxhandle/list_view.py

import flet as ft
from typing import List, Dict, Callable, Optional, Tuple # Tuple を追加
from datetime import datetime

class TrackList(ft.ListView):
    """トラックポイント一覧 (複数回アンドゥ対応)"""
    ITEM_HEIGHT = 55

    def __init__(self, on_select: Callable[[int], None], on_data_change: Callable[[], None]):
        super().__init__(expand=True, spacing=2, padding=5)
        self.on_select_cb = on_select
        self.on_data_change_cb = on_data_change
        self.points: List[Dict] = []
        self.idx: int = -1

        # --- ★★★ アンドゥ履歴用スタック ★★★ ---
        # (削除されたインデックス, 削除されたポイントデータ) のタプルのリスト
        self._undo_stack: List[Tuple[int, Dict]] = []

        # --- 確認ダイアログ関連は削除済 ---

    def load_points(self, points: List[Dict]):
        """リストを更新し、アンドゥ履歴をクリア、最初の項目を選択"""
        self.points = points
        self.idx = -1

        # ロード時にアンドゥ履歴をクリア
        self._undo_stack.clear()
        self._refresh_list()

        # 初期選択とコールバック
        if len(self.points) > 0:
            self._update_selection(0, scroll_to=False, trigger_callback=True)
        else:
            self.on_select_cb(-1)
        
        self.update()

    def _refresh_list(self):
        """現在の self.points に基づいてリスト表示を完全に再構築する。"""
        current_selected_idx = self.idx # インデックス調整のため保持
        self.controls.clear()
        if not self.points:
            self.controls.append(ft.Text("データがありません", italic=True))
            self.idx = -1
        else:
            for i, p in enumerate(self.points):
                self.controls.append(self._create_list_tile(i, p))
            # 削除やアンドゥ後のインデックス調整
            if 0 <= current_selected_idx < len(self.points):
                self.idx = current_selected_idx
            elif len(self.points) > 0:
                self.idx = max(0, len(self.points) - 1)
            else:
                self.idx = -1
            # ハイライト設定 (UI更新はここではしない)
            if self.idx >= 0:
                self._update_highlight(self.idx)

    def _create_list_tile(self, i: int, p: Dict) -> ft.ListTile:
        """ListTileコントロールを作成する (直接削除ボタン付き)。"""
        ts = p.get("time")
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else "時刻なし"
        subtitle_str = f"Lat: {p['lat']:.5f}, Lon: {p['lon']:.5f}, Ele: {p.get('ele', 0.0):.1f}m"
        return ft.ListTile(
            title=ft.Text(time_str), subtitle=ft.Text(subtitle_str, size=11),
            data=i, on_click=self._handle_click, dense=True,
            trailing=ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, tooltip="削除 (確認なし)",
                icon_color=ft.Colors.RED_400, icon_size=18,
                data=i, on_click=self._delete_point # 直接削除
            )
        )

    def _handle_click(self, e: ft.ControlEvent):
        selected_idx = e.control.data
        self._update_selection(selected_idx, scroll_to=False, trigger_callback=True)
        self.update()

    def move_cursor(self, step: int): # 残しておく
        if not self.points: return
        if self.idx == -1: start_idx = 0 if step > 0 else len(self.points) - 1
        else: start_idx = self.idx
        new_idx = start_idx + step
        new_idx = max(0, min(len(self.points) - 1, new_idx))
        self._update_selection(new_idx, scroll_to=True, trigger_callback=True)
        self.update()

    def _update_selection(self, new_idx: int, scroll_to: bool, trigger_callback: bool):
        """選択状態の更新、UI反映、コールバック呼び出しを行う。"""
        if not (0 <= new_idx < len(self.controls)) or new_idx == self.idx: return

        # 1. ハイライト表示を更新 (self.idx も更新, updateは呼ばない)
        self._update_highlight(new_idx)

        # 2. 必要ならスクロール (scroll_to は内部で update を呼ぶと期待)
        if scroll_to:
            offset = new_idx * self.ITEM_HEIGHT
            self.scroll_to(offset=offset, duration=150, curve=ft.AnimationCurve.EASE_OUT)

        # --- ★★★ このメソッドの最後に update を呼ぶ (ハイライト反映のため) ★★★ ---
        # scroll_toがupdateしても、ハイライトのbgcolor変更を反映するために必要
        self.update()

        # 3. コールバック呼び出し
        if trigger_callback: self.on_select_cb(self.idx)

    def _update_highlight(self, new_idx: int):
        """リスト内のハイライト表示のみを更新し、self.idx を設定する。(UI更新は行わない)"""
        if 0 <= self.idx < len(self.controls):
            control = self.controls[self.idx]
            if isinstance(control, ft.ListTile): control.bgcolor = None
        self.idx = new_idx
        if 0 <= self.idx < len(self.controls):
            new_control = self.controls[self.idx]
            if isinstance(new_control, ft.ListTile): new_control.bgcolor = ft.Colors.BLUE_50

    # --- 削除処理メソッド (アンドゥスタック使用) ---
    def _delete_point(self, e: ft.ControlEvent):
        """指定インデックスのポイントを削除し、アンドゥスタックに保存、外部に通知する。"""
        idx_to_delete = e.control.data
        if not (0 <= idx_to_delete < len(self.points)): return

        print(f"Deleting point at index: {idx_to_delete}")
        # --- アンドゥスタックに保存 ---
        deleted_data = self.points[idx_to_delete].copy() # 必ずコピーを保存
        self._undo_stack.append((idx_to_delete, deleted_data))
        print(f"Undo stack size: {len(self._undo_stack)}")

        # データ削除
        del self.points[idx_to_delete]

        self._refresh_list() # 再描画指示 (内部でupdateしない)
        self.update()

        # 削除後の選択決定
        if self.idx >= 0:
            # ★★★ update_selection を使わず直接コールバックとスクロール ★★★
            # self.on_select_cb(self.idx)
            offset = self.idx * self.ITEM_HEIGHT
            self.scroll_to(offset=offset, duration=150)
        # else:
        #     self.on_select_cb(-1)
        
        self.update()

        # データ変更通知 (Map更新と Undoボタン更新)
        self.on_data_change_cb()

        # 通知後に選択コールバックを呼ぶ？
        if self.idx >= 0: self.on_select_cb(self.idx)
        else: self.on_select_cb(-1)

    # --- ★★★ アンドゥ処理メソッド (アンドゥスタック使用) ★★★ ---
    def undo_delete(self):
        """直前の削除操作を元に戻す。アンドゥスタックから復元する。"""
        if not self._undo_stack: # スタックが空かチェック
            print("アンドゥする削除操作がありません。")
            return False # アンドゥ失敗

        # --- スタックから最後の削除操作を取得 ---
        insert_idx, point_to_restore = self._undo_stack.pop()
        print(f"アンドゥ実行: インデックス {insert_idx} にポイントを復元します。")
        print(f"Undo stack size after pop: {len(self._undo_stack)}")

        # 挿入位置のインデックスがリスト範囲内か確認 (基本的には問題ないはず)
        if not (0 <= insert_idx <= len(self.points)):
            print(f"[WARN] アンドゥ時の挿入インデックス {insert_idx} が不正です。末尾に追加します。")
            insert_idx = len(self.points)

        # データを元の位置（または調整後位置）に挿入
        self.points.insert(insert_idx, point_to_restore)

        # 1. リスト内容を再構築 (updateは呼ばない)
        self.idx = insert_idx
        self._refresh_list()

        # 2. ListViewの再構築結果をまずUIに反映させる
        self.update()

        # 3. UI更新後、スクロールを実行 (内部で再度 update が呼ばれる可能性あり)
        offset = self.idx * self.ITEM_HEIGHT
        self.scroll_to(offset=offset, duration=150)

        # 4. 外部に通知
        self.on_select_cb(self.idx)
        self.on_data_change_cb()
        return True

    # --- アンドゥ可能か確認するためのプロパティ ---
    @property
    def can_undo(self) -> bool:
        """アンドゥ可能な削除操作（履歴）が存在するかどうかを返す。"""
        return bool(self._undo_stack) # スタックが空でないかチェック
