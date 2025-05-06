# gpxhandle/list_view.py

import flet as ft
from typing import List, Dict, Callable, Optional, Tuple, Set
from datetime import datetime

class TrackList(ft.ListView):
    """トラックポイント一覧 (複数回アンドゥ対応)"""
    ITEM_HEIGHT = 55

    def __init__(self, on_select: Callable[[int], None], 
                 on_data_change: Callable[[], None],
                 on_multi_selection_change: Callable[[bool], None]):
        super().__init__(expand=True, spacing=2, padding=5)
        self.on_select_cb = on_select
        self.on_data_change_cb = on_data_change
        self.on_multi_selection_change_cb = on_multi_selection_change
        self.points: List[Dict] = []
        self.idx: int = -1  # 単一選択ハイライト用インデックス
        self.selected_indices: Set[int] = set()  # 複数選択されたインデックス

        # アンドゥ履歴用スタック
        # (削除されたインデックス, 削除されたポイントデータ) のタプルのリスト
        self._undo_stack: List[Tuple[int, Dict]] = []

        # 処理中フラグ
        self._is_processing: bool = False

    def load_points(self, points: List[Dict]):
        """リストを更新し、アンドゥ履歴をクリア、最初の項目を選択"""
        self.points = points
        self.idx = -1

        # ロード時にクリア
        self._undo_stack.clear()
        self.selected_indices.clear()
        self._last_click_index = -1
        self._refresh_list()

        # 初期選択とコールバック
        # if len(self.points) > 0:
        #     self._update_selection(0, scroll_to=False, trigger_callback=True)
        # else:
        #     self.on_select_cb(-1)

        self.on_select_cb(-1) # 初期は未選択を通知
        self.on_multi_selection_change_cb(False)

        self.update()

    def _refresh_list(self):
        """現在の self.points に基づいてリスト表示を完全に再構築する。"""
        current_highlight_idx = self.idx  # ハイライト位置
        self.controls.clear()
        if not self.points:
            self.controls.append(ft.Text("データがありません", italic=True))
            self.idx = -1
        else:
            for i, p in enumerate(self.points):
                self.controls.append(self._create_list_tile(i, p))
            # ハイライト位置を復元
            self.idx = -1 # 一旦リセット
            if 0 <= current_highlight_idx < len(self.points):
                self._update_highlight(current_highlight_idx) # ハイライト再設定
            else: # 有効なハイライトがなければ未選択(-1)のまま
                 pass
        # updateは呼び出し元で行う

    def _create_list_tile(self, i: int, p: Dict) -> ft.ListTile:
        # """ListTileコントロールを作成する (直接削除ボタン付き)。"""
        # ts = p.get("time")
        # time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else "時刻なし"
        # subtitle_str = f"Lat: {p['lat']:.5f}, Lon: {p['lon']:.5f}, Ele: {p.get('ele', 0.0):.1f}m"
        # return ft.ListTile(
        #     title=ft.Text(time_str), subtitle=ft.Text(subtitle_str, size=11),
        #     data=i, on_click=self._handle_click, dense=True,
        #     trailing=ft.IconButton(
        #         icon=ft.Icons.DELETE_OUTLINE, tooltip="削除 (確認なし)",
        #         icon_color=ft.Colors.RED_400, icon_size=18,
        #         data=i, on_click=self._delete_point # 直接削除
        #     )
        # )
        """ListTileコントロールを作成する (チェックボックス付き)。"""
        ts = p.get("time")
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else "時刻なし"
        subtitle_str = f"Lat: {p['lat']:.5f}, Lon: {p['lon']:.5f}, Ele: {p.get('ele', 0.0):.1f}m"
        return ft.ListTile(
            leading=ft.Checkbox(
                value=(i in self.selected_indices), # 選択状態を反映
                data=i,
                on_change=self._handle_checkbox_change
            ),
            title=ft.Text(time_str), subtitle=ft.Text(subtitle_str, size=11),
            data=i,
            on_click=self._handle_click, # ★ Shift 対応のクリック処理
            dense=True,
        )
    
    def _handle_click(self, e: ft.ControlEvent):
        """ListTileクリック時の処理 (単一選択ハイライトのみ)。"""
        clicked_idx = e.control.data
        self._update_highlight(clicked_idx) # ハイライトを移動
        self.update() # ハイライト変更を反映
        self.on_select_cb(self.idx) # 単一選択コールバック

    def _handle_checkbox_change(self, e: ft.ControlEvent):
        """チェックボックスの状態が変わったときの処理。"""
        idx = e.control.data
        is_selected = e.control.value
        prev_selection_empty = not self.selected_indices

        if is_selected:
            self.selected_indices.add(idx)
            # チェックを付けた行をハイライト（単一選択）の起点にもする
            self._last_click_index = idx
        else:
            self.selected_indices.discard(idx)
            # チェックを外した場合、last_click_index は変更しない

        # 選択状態の有無が変わった場合にのみコールバックを呼ぶ
        current_selection_empty = not self.selected_indices
        if prev_selection_empty != current_selection_empty:
             self.on_multi_selection_change_cb(not current_selection_empty)

    def move_cursor(self, step: int): # 残しておく
        if not self.points: return
        if self.idx == -1: start_idx = 0 if step > 0 else len(self.points) - 1
        else: start_idx = self.idx
        new_idx = start_idx + step
        new_idx = max(0, min(len(self.points) - 1, new_idx))
        self._update_selection(new_idx, scroll_to=True, trigger_callback=True)
        self.update()

    def _update_selection(self, new_idx: int, scroll_to: bool, trigger_callback: bool):
         # 単一選択ハイライト用メソッド (move_cursorから呼ばれる)
         if not (0 <= new_idx < len(self.controls)) or new_idx == self.idx: return
         self._update_highlight(new_idx)
         if scroll_to:
             offset = new_idx * self.ITEM_HEIGHT
             self.scroll_to(offset=offset, duration=150)
         self.update() # ハイライト変更を反映
         # キーでのハイライト移動時もlast_click_indexを更新しておく
         self._last_click_index = new_idx
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

    def delete_before_selected(self):
        """現在ハイライトされているポイントより前のすべてを削除する。"""
        if self._is_processing or self.idx <= 0: # 未選択または先頭選択時は不可
            print("[WARN] Cannot delete before: No valid selection or already processing.")
            return
        self._is_processing = True
        print(f"Deleting points before index: {self.idx}")
        try:
            indices_to_delete = list(range(0, self.idx))
            deleted_data = [self.points[i].copy() for i in indices_to_delete]

            if deleted_data:
                self._undo_stack.append((indices_to_delete, deleted_data))
                print(f"Undo stack size: {len(self._undo_stack)}")
                del self.points[0:self.idx] # スライスで削除
                # 削除後の新しい選択インデックスは 0
                self.idx = 0
                self._refresh_list() # updateなし
                self.update()       # 更新
                # 外部に通知
                self.on_select_cb(self.idx)
                self.on_multi_selection_change_cb(bool(self.selected_indices))
                self.on_data_change_cb()
            else: print("No points to delete before.")
        finally:
            self._is_processing = False
            print("Finished deleting points before.")

    def delete_after_selected(self):
        """現在ハイライトされているポイントより後のすべてを削除する。"""
        if self._is_processing or self.idx < 0 or self.idx >= len(self.points) - 1: # 未選択または最後尾選択時は不可
            print("[WARN] Cannot delete after: No valid selection or already processing.")
            return
        self._is_processing = True
        print(f"Deleting points after index: {self.idx}")
        try:
            start_delete_idx = self.idx + 1
            indices_to_delete = list(range(start_delete_idx, len(self.points)))
            deleted_data = [self.points[i].copy() for i in indices_to_delete]

            if deleted_data:
                self._undo_stack.append((indices_to_delete, deleted_data))
                print(f"Undo stack size: {len(self._undo_stack)}")
                del self.points[start_delete_idx:] # スライスで削除
                # 選択インデックス self.idx は維持される
                self._refresh_list() # updateなし
                self.update()       # 更新
                # 外部に通知
                self.on_select_cb(self.idx) # 選択は変わらない
                self.on_multi_selection_change_cb(bool(self.selected_indices))
                self.on_data_change_cb()
            else: print("No points to delete after.")
        finally:
            self._is_processing = False
            print("Finished deleting points after.")

    def _delete_point(self, e: ft.ControlEvent):
        """指定インデックスのポイントを削除し、アンドゥスタックに保存、外部に通知する。"""
        # --- ★★★ 処理中なら何もしない ★★★ ---
        if self._is_processing:
            print("[WARN] Delete operation already in progress. Ignoring.")
            return
        
        # --- ★★★ 処理開始、フラグを立てる ★★★ ---
        self._is_processing = True
        print(f"Deleting point start...")
        try:
            idx_to_delete = e.control.data
            if not (0 <= idx_to_delete < len(self.points)):
                self._is_processing = False # 無効なインデックスならフラグを戻す
                return

            print(f"Deleting point at index: {idx_to_delete}")
            # time.sleep(0.5) # ★ デバッグ: 意図的に遅延させてテストする場合 ★
            deleted_data = self.points[idx_to_delete].copy()
            self._undo_stack.append((idx_to_delete, deleted_data))
            del self.points[idx_to_delete]

            self._refresh_list() # 再描画指示 (updateなし)
            self.update()       # ListView 更新

            # 削除後の選択決定と通知
            if self.idx >= 0:
                self.on_select_cb(self.idx)
                offset = self.idx * self.ITEM_HEIGHT
                self.scroll_to(offset=offset, duration=150)
            else:
                self.on_select_cb(-1)
            self.on_data_change_cb()
        finally:
            # --- ★★★ 処理完了、フラグを下ろす ★★★ ---
            print(f"Deleting point finished.")
            self._is_processing = False

    def delete_selected(self):
        """チェックボックスで選択された項目を一括削除する。"""
        if self._is_processing or not self.selected_indices:
            print("[WARN] Deletion in progress or no selection.")
            return
        self._is_processing = True
        print(f"Deleting selected points: indices={sorted(list(self.selected_indices))}")
        try:
            deleted_items_for_undo: List[Tuple[int, Dict]] = []
            indices_to_delete = sorted(list(self.selected_indices), reverse=True)

            for index in indices_to_delete:
                if 0 <= index < len(self.points):
                    deleted_data = self.points.pop(index)
                    deleted_items_for_undo.append((index, deleted_data))
                else: print(f"[WARN] Invalid index during multi-delete: {index}")

            if deleted_items_for_undo:
                 deleted_items_for_undo.sort(key=lambda item: item[0])
                 original_indices = [item[0] for item in deleted_items_for_undo]
                 original_data = [item[1] for item in deleted_items_for_undo]
                 self._undo_stack.append((original_indices, original_data))
                 print(f"Undo stack size: {len(self._undo_stack)}")

            # 選択状態をクリアし、リスト再描画、UI更新
            self.selected_indices.clear()
            self._refresh_list() # updateなし
            self.update() # 最後にupdate

            # 外部に通知
            self.on_select_cb(self.idx) # 新しいハイライト位置
            self.on_multi_selection_change_cb(False) # 選択解除
            self.on_data_change_cb() # データ変更
        except Exception as del_ex:
             print(f"[ERROR] Error during delete_selected: {del_ex}")
             traceback.print_exc()
        finally:
            self._is_processing = False
            print("Finished deleting selected points.")

    # --- ★★★ アンドゥ処理メソッド (アンドゥスタック使用) ★★★ ---
    def undo_delete(self):
        """直前の削除操作を元に戻す。アンドゥスタックから復元する。"""
        # --- ★★★ 処理中なら何もしない ★★★ ---
        if self._is_processing:
            print("[WARN] Undo operation already in progress. Ignoring.")
            return False

        # --- ★★★ 処理開始、フラグを立てる ★★★ ---
        self._is_processing = True
        print(f"Undo delete start...")
        result = False # アンドゥ成功フラグ
        try:
            if not self._undo_stack:
                print("アンドゥする削除操作がありません。")
                return False # result は False のまま

            # スタックから (インデックスリスト, データリスト) を取得
            # ※ delete_selected で元のインデックス順 (昇順) にソートして保存されている前提
            indices, data_list = self._undo_stack.pop()
            print(f"アンドゥ実行: インデックス {indices} に {len(data_list)} ポイントを復元します。")
            print(f"Undo stack size after pop: {len(self._undo_stack)}")

            # ★★★ インデックスが小さい順に挿入する ★★★
            restored_count = 0
            # zip で元のインデックスとデータをペアにする
            for insert_idx, point_to_restore in zip(indices, data_list):
                # 挿入位置を現在のリスト長でクリップ (安全のため)
                actual_insert_idx = min(insert_idx, len(self.points))
                self.points.insert(actual_insert_idx, point_to_restore)
                restored_count += 1
                # print(f"  - Inserted at {actual_insert_idx}") # デバッグ用

            # リスト再描画、最後に復元した最初の項目を選択
            self.idx = indices[0] if indices else -1 # 復元セットの最初のインデックス
            self._refresh_list() # updateなし
            self.update()       # 更新

            # スクロールして表示 & 外部に通知
            if self.idx >= 0:
                offset = self.idx * self.ITEM_HEIGHT
                self.scroll_to(offset=offset, duration=150)
                self.on_select_cb(self.idx)
            else:
                 self.on_select_cb(-1)
            # アンドゥ後はチェックボックス選択は解除されている状態なのでFalseを通知
            self.on_multi_selection_change_cb(False)
            self.on_data_change_cb()
            result = True
        finally:
            # --- ★★★ 処理完了、フラグを下ろす ★★★ ---
            print(f"Undo delete finished.")
            self._is_processing = False
        return result

    # --- アンドゥ可能か確認するためのプロパティ ---
    @property
    def can_undo(self) -> bool:
        """アンドゥ可能な削除操作（履歴）が存在するかどうかを返す。"""
        return bool(self._undo_stack) # スタックが空でないかチェック
