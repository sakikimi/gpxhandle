"""
main.py

・地図上にGPSの軌跡を表示
・データ点を選択して削除（1点削除、選択データの前を全て削除、選択データの後を全て削除）
・削除のやり直し
・GPSデータから歩行時間、距離、累積登りを計算
・地図データの表示切替
"""

import flet as ft
from pathlib import Path # ファイルパス操作で使用
from gpx_handler import load_gpx, save_gpx, Point
from list_view import TrackList
from map_view import MapView, TILE_SOURCES
from graph_view import ElevationGraph
# 不要なインポートを削除: json, threading, Optional

# --- 設定ファイル関連コードは削除 ---

def main(page: ft.Page):
    # --- ウィンドウ初期サイズ (固定値) ---
    initial_width = 1500
    initial_height = 900

    # --- ページ設定 ---
    page.title = "GPX Editor"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10
    page.window_width = initial_width # 初期幅設定
    page.window_height = initial_height # 初期高さ設定

    # --- リサイズイベントハンドラは削除 ---
    # --- ウィンドウイベントハンドラは削除 ---

    # --- 状態変数 ---
    current_file_path: Path | None = None
    current_points: list[Point] = []
    current_track_name: str = "-"

    # --- UIインスタンス ---
    map_view = MapView()
    graph_view = ElevationGraph()
    # --- ボタン参照 ---
    export_btn_ref = ft.Ref[ft.ElevatedButton]() # エクスポートボタン用 Ref 追加
    delete_selected_btn_ref = ft.Ref[ft.ElevatedButton]()
    undo_btn_ref = ft.Ref[ft.ElevatedButton]()
    delete_before_btn_ref = ft.Ref[ft.ElevatedButton]()
    delete_after_btn_ref = ft.Ref[ft.ElevatedButton]()

    # --- UI更新用関数 ---
    def update_status(message: str, color: str = ft.Colors.GREY_700):
        """ステータステキストを更新"""
        status_text.value = message
        status_text.color = color
        status_text.update()

    def update_range_delete_buttons_state(selected_idx: int):
        """選択状態に基づいて前/後削除ボタンの有効/無効を更新"""
        # track_list が初期化されていない場合も考慮
        points_count = len(track_list.points) if track_list else 0
        can_delete_before = selected_idx > 0
        can_delete_after = 0 <= selected_idx < points_count - 1

        if delete_before_btn_ref.current:
             delete_before_btn_ref.current.disabled = not can_delete_before
             delete_before_btn_ref.current.update()
        if delete_after_btn_ref.current:
             delete_after_btn_ref.current.disabled = not can_delete_after
             delete_after_btn_ref.current.update()

    def update_delete_selected_button_state(has_selection: bool):
        """選択項目削除ボタンの状態更新"""
        try:
            if delete_selected_btn_ref.current:
                delete_selected_btn_ref.current.disabled = not has_selection
                delete_selected_btn_ref.current.update()
        except Exception as e:
            print(f"Error updating delete selected button: {e}")

    def update_undo_button_state():
        """アンドゥボタンの状態更新"""
        try:
            if undo_btn_ref.current:
                can_undo = track_list.can_undo if track_list else False
                # 状態が変わる場合のみ update
                if undo_btn_ref.current.disabled == can_undo:
                    undo_btn_ref.current.disabled = not can_undo
                    undo_btn_ref.current.update()
        except Exception as e:
            print(f"Error updating undo button: {e}")

    def update_export_button_state():
        """エクスポートボタンの状態更新"""
        try:
            if export_btn_ref.current:
                can_export = bool(current_points)
                # 状態が変わる場合のみ update
                if export_btn_ref.current.disabled == can_export:
                    export_btn_ref.current.disabled = not can_export
                    export_btn_ref.current.update()
        except Exception as e:
            print(f"Error updating export button: {e}")

    def update_all_button_states():
        """関連する全てのボタンの状態を更新"""
        update_export_button_state()
        update_range_delete_buttons_state(track_list.idx if track_list else -1)
        update_delete_selected_button_state(bool(track_list.selected_indices) if track_list else False)
        update_undo_button_state()

    # --- コールバック関数 ---
    def on_list_select(idx: int):
        """リスト選択時のコールバック"""
        if idx >= 0:
            map_view.highlight(idx)
            graph_view.highlight(idx)
        else:
            map_view.highlight(-1)
            graph_view.hide_point_info()
        # 範囲削除ボタンの状態を更新
        update_range_delete_buttons_state(idx)

    def on_track_data_change():
        """リストデータ変更時(削除/アンドゥ)のコールバック"""
        nonlocal current_points
        current_points = track_list.points # 最新データを反映
        map_view.refresh() # 地図更新
        graph_view.load_points(current_points)  # グラフ更新
        # ハイライト更新
        current_idx = track_list.idx
        on_list_select(current_idx) # 選択状態に基づいてハイライトと範囲削除ボタンを更新
        # 全ての関連ボタン状態を更新
        update_all_button_states()

    # --- トラックリストの初期化 ---
    track_list = TrackList(
        on_select=on_list_select,
        on_data_change=on_track_data_change,
        on_multi_selection_change=update_delete_selected_button_state, # 複数選択変更時のコールバック
    )

    # --- トラック名の編集用 ---
    track_name_input = ft.TextField(
        label="トラック名",
        value=current_track_name,
        dense=True,
        expand=True,
    )

    # --- ファイルピッカー関連 ---
    def open_gpx_result(e: ft.FilePickerResultEvent):
        nonlocal current_file_path, current_points, current_track_name
        if not e.files or not e.files[0].path:
            update_status("ファイル選択キャンセル", ft.Colors.ORANGE_700)
            return
        selected_path = Path(e.files[0].path)
        try:
            pts, name = load_gpx(selected_path)
            current_file_path = selected_path
            current_points = pts
            # GPXファイルに名前がない場合はファイル名から取得
            current_track_name = name if name else selected_path.stem
            track_name_input.value = current_track_name
            track_name_input.update()

            map_view.load_points(pts)
            track_list.load_points(pts)
            graph_view.load_points(pts)
            update_status(f"読み込み完了: {selected_path.name}", ft.Colors.GREEN_700)
        except Exception as ex:
            current_file_path = None
            current_points = []
            current_track_name = "-"
            track_name_input.value = current_track_name
            track_name_input.update()
            map_view.load_points([])
            track_list.load_points([])
            graph_view.load_points([])
            update_status(f"読込エラー: {ex}", ft.Colors.RED_700)
        finally:
            # 読み込み後、選択状態をリセットし、ボタン状態を更新
            on_list_select(-1)
            update_all_button_states()

    def save_gpx_result(e: ft.FilePickerResultEvent):
        if not e.path:
            update_status("保存キャンセル", ft.Colors.ORANGE_700)
            return
        if not current_points:
             update_status("保存するデータがありません", ft.Colors.ORANGE_700)
             return

        save_path = Path(e.path)
        # 拡張子が .gpx でなければ追加
        if save_path.suffix.lower() != ".gpx":
            save_path = save_path.with_suffix(".gpx")

        try:
            # TextField からトラック名を取得 (空ならデフォルト名)
            track_name_to_save = track_name_input.value.strip() or "GPX Track"
            save_gpx(current_points, save_path, track_name_to_save)
            update_status(f"保存しました: {save_path.name}", ft.Colors.GREEN_700)
        except Exception as ex:
            update_status(f"保存エラー: {ex}", ft.Colors.RED_700)

    file_picker = ft.FilePicker(on_result=open_gpx_result)
    save_picker = ft.FilePicker(on_result=save_gpx_result)
    page.overlay.extend([file_picker, save_picker])
    status_text = ft.Text("GPXファイルを開いてください", color=ft.Colors.GREY_700, size=12)

    # --- 地図クレジット表示用テキスト ---
    map_attribution_text = ft.Text(
        map_view.get_current_tile_attribution(),
        size=9, color=ft.Colors.GREY_600, italic=True
    )

    # --- イベントハンドラ (ボタンクリック等) ---
    def open_gpx(e):
        """「ファイルを開く」ボタンのハンドラ"""
        file_picker.pick_files(dialog_title="GPXを開く", allowed_extensions=["gpx"])

    def export_gpx(e):
        """「名前を付けて保存」ボタンのハンドラ"""
        if not current_points:
            update_status("保存するデータがありません", ft.Colors.RED)
            return
        initial_filename = f"{track_name_input.value.strip() or 'track'}.gpx"
        initial_dir = str(current_file_path.parent) if current_file_path else str(Path.home())
        save_picker.save_file(dialog_title="名前を付けて保存", file_name=initial_filename, initial_directory=initial_dir, allowed_extensions=["gpx"])

    def handle_tile_change(e):
        """地図タイル変更時のハンドラ"""
        selected_key = e.control.value
        map_view.change_tile_layer(selected_key)
        map_attribution_text.value = map_view.get_current_tile_attribution()
        map_attribution_text.update()

    def handle_delete_before(e):
        """「前削除」ボタンのハンドラ"""
        track_list.delete_before_selected()
        # on_track_data_change でUI更新

    def handle_delete_after(e):
        """「後削除」ボタンのハンドラ"""
        track_list.delete_after_selected()
        # on_track_data_change でUI更新

    def handle_delete_selected(e):
        """「選択削除」ボタンのハンドラ"""
        track_list.delete_selected()
        # on_track_data_change でUI更新

    def handle_undo(e):
        """「元に戻す」ボタンのハンドラ"""
        # 連打防止のため、処理開始前にボタンを無効化
        if undo_btn_ref.current:
            undo_btn_ref.current.disabled = True
            undo_btn_ref.current.update()
        else: return

        undo_successful = track_list.undo_delete()

        # アンドゥが成功した場合、on_track_data_change が呼ばれてボタン状態が更新される
        # 失敗した場合 (アンドゥ対象がない等) は on_track_data_change が呼ばれないため、
        # ここでボタン状態を再評価する必要がある
        if not undo_successful:
            update_undo_button_state() # ボタン状態を再評価

    # --- ボタン定義 ---
    open_btn = ft.ElevatedButton("ファイルを開く", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=open_gpx, tooltip="GPXファイルを開く", height=38)
    export_btn = ft.ElevatedButton(ref=export_btn_ref, text="名前を付けて保存", icon=ft.Icons.SAVE_AS_OUTLINED, on_click=export_gpx, disabled=True, tooltip="GPX形式で保存", height=38)
    undo_button = ft.ElevatedButton(ref=undo_btn_ref, text="元に戻す", icon=ft.Icons.UNDO, tooltip="削除を元に戻す", on_click=handle_undo, disabled=True, height=38)
    delete_selected_button = ft.ElevatedButton(ref=delete_selected_btn_ref, text="選択削除", icon=ft.Icons.DELETE_SWEEP_OUTLINED,tooltip="チェックした項目を削除", on_click=handle_delete_selected, disabled=True, style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.RED_700), height=38)
    delete_before_button = ft.ElevatedButton(ref=delete_before_btn_ref, text="前削除", icon=ft.Icons.VERTICAL_ALIGN_TOP, tooltip="選択より前を削除", on_click=handle_delete_before, disabled=True, height=38)
    delete_after_button = ft.ElevatedButton(ref=delete_after_btn_ref, text="後削除", icon=ft.Icons.VERTICAL_ALIGN_BOTTOM, tooltip="選択より後を削除", on_click=handle_delete_after, disabled=True, height=38)

    # --- 地図タイル選択ドロップダウン ---
    tile_dropdown = ft.Dropdown(
        label="地図タイル", hint_text="地図を選択", expand=True, dense=True,
        options=[ft.dropdown.Option(key=key, text=info["name"]) for key, info in TILE_SOURCES.items()],
        value=map_view.current_tile_key, # MapView の初期キーを使用
        on_change=handle_tile_change,
    )

    # --- レイアウト定義 ---
    left_panel = ft.Column(
        [
            ft.Container( # Open/Save ボタンエリア
                content=ft.Row([open_btn, export_btn], spacing=5),
                padding=ft.padding.only(bottom=5)
            ),
            ft.Stack( # 地図エリア (Stackで要素を重ねる)
                [
                    map_view, # 地図本体
                    ft.Container( # ズームボタンコンテナ
                        content=ft.Column(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.ADD, tooltip="ズームイン",
                                    on_click=lambda _: map_view.zoom_in(),
                                    bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
                                    icon_color=ft.Colors.BLACK, icon_size=18, height=30, width=30,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.REMOVE, tooltip="ズームアウト",
                                    on_click=lambda _: map_view.zoom_out(),
                                    bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
                                    icon_color=ft.Colors.BLACK, icon_size=18, height=30, width=30,
                                ),
                            ],
                            spacing=1, tight=True,
                        ),
                        top=10, right=10, # 右上に配置
                        padding=ft.padding.all(2),
                        border_radius=ft.border_radius.all(5),
                        bgcolor=ft.colors.with_opacity(0.6, ft.Colors.WHITE),
                    ),
                    ft.Container( # クレジット表示コンテナ
                        content=map_attribution_text,
                        bottom=5, left=5, # 左下に配置
                        padding=ft.padding.symmetric(horizontal=4, vertical=1),
                        bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
                        border_radius=ft.border_radius.all(3),
                    ),
                ],
                expand=3 # 地図エリアの高さ比率
            ),
            ft.Text("標高グラフ (水平距離 m)", weight=ft.FontWeight.BOLD, size=13), # グラフタイトル
            ft.Container( # グラフエリア
                content=graph_view,
                expand=1, # グラフエリアの高さ比率
                padding=ft.padding.only(top=2, bottom=2)
            ),
        ],
        expand=5, # 左パネルの幅の比率
        spacing=5 # 要素間のスペース
    )

    right_panel = ft.Column(
        [
            ft.Container( # 上部コントロールエリア (タイル選択、操作ボタン)
                content=ft.Column([
                    ft.Row([tile_dropdown]),
                    ft.Row( # 削除・アンドゥ等ボタン行
                        [ delete_before_button, delete_after_button,
                          ft.Container(expand=True), # スペーサー
                          delete_selected_button, undo_button ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN, # ボタン配置調整
                        spacing=5
                    )
                ]),
                padding=ft.padding.only(bottom=5)
            ),
            ft.Container( # トラック情報編集エリア
                content=ft.Row([track_name_input]),
                padding=ft.padding.only(top=5, bottom=10, left=5, right=5),
            ),
            ft.Text("トラックポイント", weight=ft.FontWeight.BOLD, size=13), # リストタイトル
            ft.Container( # リストエリア
                content=track_list,
                expand=True # 高さを可能な限り広げる
            ),
            ft.Container( # ステータス表示エリア
                content=status_text,
                padding=ft.padding.only(top=8, bottom=2)
            )
        ],
        expand=2, # 右パネルの幅の比率
        spacing=5 # 要素間のスペース
    )

    main_layout = ft.Row(
        [left_panel, right_panel],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH
    )

    # --- ページにメインレイアウトを追加 ---
    page.add(main_layout)

    # --- アプリケーション開始時にボタンの状態を初期化 ---
    update_all_button_states()
    # page.update() # page.add の後、通常は自動で update される

if __name__ == "__main__":
    ft.app(target=main)