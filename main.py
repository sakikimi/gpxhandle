# gpxhandle/main.py

import flet as ft
from pathlib import Path
from gpx_handler import load_gpx, save_gpx, Point
from list_view import TrackList
from map_view import MapView, TILE_SOURCES # TILE_SOURCES をインポート

def main(page: ft.Page):
    # --- ページ設定 ---
    page.title = "GPX Editor"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10
    page.window_width = 1200
    page.window_height = 800

    # --- 状態変数 ---
    current_file_path: Path | None = None
    current_points: list[Point] = []
    current_track_name: str = "-"

    # --- UIインスタンス ---
    map_view = MapView()

    # --- アンドゥボタンへの参照 ---
    undo_btn_ref = ft.Ref[ft.IconButton]()

    def update_undo_button_state():
        """アンドゥボタンの有効/無効を TrackList の状態に合わせて更新"""
        can_undo = track_list.can_undo # TrackList のプロパティを参照
        if undo_btn_ref.current: # ボタンがレンダリングされていれば
            undo_btn_ref.current.disabled = not can_undo
            undo_btn_ref.current.update()

    # --- コールバック ---
    def on_list_select(idx: int):
        if idx >= 0: map_view.highlight(idx)

    def on_track_data_change():
        """リストデータ変更時(削除/アンドゥ)のコールバック"""
        print("Track data changed. Refreshing map and updating buttons.")
        nonlocal current_points
        current_points = track_list.points # 最新データを反映
        map_view.refresh() # 地図更新
        update_button_states() # 保存ボタンの状態更新
        update_undo_button_state() # ★アンドゥボタンの状態更新

    track_list = TrackList(
        on_select=on_list_select,
        on_data_change=on_track_data_change, # データ変更コールバックを渡す
    )

    # --- トラック名表示を TextField に変更 ---
    track_name_input = ft.TextField( # TextからTextFieldに変更
        label="トラック名",
        value=current_track_name, # 初期値
        dense=True,
        expand=True,
        # on_change=lambda e: print(f"Track name changed: {e.control.value}") # 必要なら変更時処理
    )

    file_picker = ft.FilePicker(on_result=lambda e: open_gpx_result(e))
    save_picker = ft.FilePicker(on_result=lambda e: save_gpx_result(e))
    page.overlay.extend([file_picker, save_picker])
    status_text = ft.Text("GPXファイルを開いてください", color=ft.Colors.GREY_700, size=12)
    # --- 地図クレジット表示用テキスト ---
    map_attribution_text = ft.Text(
        map_view.get_current_tile_attribution(), # 初期クレジット
        size=9, color=ft.Colors.GREY_600, italic=True
    )
    open_btn = ft.ElevatedButton("ファイルを開く", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=lambda _: open_gpx())
    export_btn = ft.ElevatedButton("名前を付けて保存", icon=ft.Icons.SAVE_AS_OUTLINED, on_click=lambda _: export_gpx(), disabled=True)

    # --- 地図タイル切り替えドロップダウン ---
    def handle_tile_change(e):
        selected_key = e.control.value
        map_view.change_tile_layer(selected_key)
        # --- クレジット表示も更新 ---
        map_attribution_text.value = map_view.get_current_tile_attribution()
        map_attribution_text.update()

    tile_dropdown = ft.Dropdown(
        label="地図タイル", hint_text="地図を選択", expand=True, dense=True,
        options=[ft.dropdown.Option(key=key, text=info["name"]) for key, info in TILE_SOURCES.items()],
        # value=map_view.current_tile_key, # MapView の初期値と合わせる
        value="gsi_std",
        on_change=handle_tile_change,
    )

    # --- アンドゥボタンのクリック処理 ---
    def handle_undo(e):
        """アンドゥ処理を実行し、実行中はボタンを無効化する"""
        print("[DEBUG] handle_undo: 開始")
        # --- ★★★ 処理開始時にボタンを無効化 ★★★ ---
        if undo_btn_ref.current:
            undo_btn_ref.current.disabled = True
            undo_btn_ref.current.update() # ボタンの状態を即時反映
            # page.update() # 必要に応じてページ全体も更新 (通常は不要のはず)
            print("[DEBUG] handle_undo: アンドゥボタンを無効化")
        else:
            print("[WARN] handle_undo: undo_btn_ref is not current yet.")
            return # ボタンがなければ処理中断

        # --- アンドゥ処理を実行 ---
        # time.sleep(0.2) # ★ デバッグ: 意図的に遅延させて競合を誘発/確認する場合 ★
        undo_successful = track_list.undo_delete() # アンドゥ実行を試みる

        if undo_successful:
            print("Undo successful.")
        else:
            print("Undo failed or nothing to undo.")
            # アンドゥ失敗時もボタン状態を更新する必要がある
            update_undo_button_state() # 失敗したら can_undo は False のはず

        print("[DEBUG] handle_undo: 終了 (ボタン状態は on_data_change で最終更新)")
        # 注意: on_data_change が呼ばれることで update_undo_button_state が
        #       再度呼ばれ、can_undo に基づいて最終的な有効/無効が決まる

    # --- イベントハンドラ / コールバック関数 ---
    def update_status(message: str, color: str = ft.Colors.GREY_700):
        status_text.value = message
        status_text.color = color
        status_text.update()

    def update_button_states():
        export_btn.disabled = not bool(current_points)
        export_btn.update()

    def open_gpx_result(e: ft.FilePickerResultEvent):
        nonlocal current_file_path, current_points, current_track_name
        if not e.files or not e.files[0].path:
            update_status("ファイル選択キャンセル", ft.Colors.ORANGE_700); return
        selected_path = Path(e.files[0].path)
        try:
            pts, name = load_gpx(selected_path)
            current_file_path = selected_path
            current_points = pts
            current_track_name = name
            # --- TextField の値を更新 ---
            track_name_input.value = current_track_name
            track_name_input.update() # TextFieldの更新
            map_view.load_points(pts)
            track_list.load_points(pts)
            update_status(f"読み込み完了: {selected_path.name}", ft.Colors.GREEN_700)
        except (IOError, Exception) as ex:
            current_file_path = None; current_points = []; current_track_name = "-"
            map_view.load_points([]); track_list.load_points([])
            # --- TextField の値を更新 ---
            track_name_input.value = current_track_name
            track_name_input.update() # TextFieldの更新
            update_status(f"読込エラー: {ex}", ft.Colors.RED_700)
        finally:
            update_button_states()

    def save_gpx_result(e: ft.FilePickerResultEvent):
        if not e.path or not current_points: update_status("保存キャンセル", ft.Colors.ORANGE_700); return
        save_path = Path(e.path); save_path = save_path.with_suffix(".gpx") if save_path.suffix.lower() != ".gpx" else save_path
        try:
            # --- TextField からトラック名を取得 ---
            track_name_to_save = track_name_input.value.strip() or "GPX Track" # 未入力ならデフォルト名
            save_gpx(current_points, save_path, track_name_to_save) # 取得した名前で保存
            update_status(f"保存しました: {save_path.name}", ft.Colors.GREEN_700)
        except (IOError, Exception) as ex: update_status(f"保存エラー: {ex}", ft.Colors.RED_700)

    def open_gpx():
        if file_picker: file_picker.pick_files(dialog_title="GPXを開く",allowed_extensions=["gpx"])

    def export_gpx():
        if not current_points: update_status("保存データなし", ft.Colors.RED); return
        if save_picker:
            # --- TextField からデフォルトファイル名を取得 ---
            initial_filename = f"{track_name_input.value.strip() or 'track'}.gpx"
            initial_dir = str(current_file_path.parent) if current_file_path else str(Path.home())
            save_picker.save_file(dialog_title="名前を付けて保存",file_name=initial_filename, initial_directory=initial_dir, allowed_extensions=["gpx"])

    # --- レイアウト定義 (左パネル下にクレジット表示追加) ---
    left_panel = ft.Stack( # ★★★ Column から Stack に戻す ★★★
        [
            # --- 地図本体 (Stackの最初の子要素 = 最下層) ---
            map_view, # expand は MapView 内の Container で設定されているはず

            # --- ズームボタンコンテナ (右上に配置) ---
            ft.Container(
                content=ft.Column(
                    [
                        ft.IconButton( # Zoom In
                            icon=ft.Icons.ADD, tooltip="ズームイン",
                            on_click=lambda _: map_view.zoom_in(),
                            bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
                            icon_color=ft.Colors.BLACK, icon_size=18,
                        ),
                        ft.IconButton( # Zoom Out
                            icon=ft.Icons.REMOVE, tooltip="ズームアウト",
                            on_click=lambda _: map_view.zoom_out(),
                            bgcolor=ft.colors.with_opacity(0.7, ft.Colors.WHITE),
                            icon_color=ft.Colors.BLACK, icon_size=18,
                        ),
                    ],
                    spacing=1, tight=True,
                ),
                top=10, right=10, # Stack内での絶対位置指定
                padding=ft.padding.all(2),
                border_radius=ft.border_radius.all(5),
            ),

            # --- クレジット表示コンテナ (左下に配置) ---
            ft.Container(
                content=map_attribution_text,
                bottom=5, left=5, # Stack内での絶対位置指定
                padding=ft.padding.symmetric(horizontal=4, vertical=1),
                bgcolor=ft.colors.with_opacity(0.6, ft.Colors.WHITE),
                border_radius=ft.border_radius.all(3),
            )
        ],
        expand=5, # Stack 全体の幅の比率
    )
    right_panel = ft.Column(
        [
            ft.Container( # タイル選択
                content=ft.Row([tile_dropdown]),
                padding=ft.padding.only(left=10, right=10, bottom=5)
            ),
            ft.Container( # トラック情報
                content=ft.Row([track_name_input]), # Text("トラック名:") ラベルはTextFieldのlabelに含むspacing=5),
                padding=10, border=ft.border.all(1, ft.colors.with_opacity(0.5, ft.Colors.OUTLINE)), border_radius=ft.border_radius.all(5)
            ),
            ft.Container( # リストエリア
                content=track_list,
                padding=ft.padding.symmetric(vertical=5), border=ft.border.all(1, ft.colors.with_opacity(0.5, ft.Colors.OUTLINE)),
                border_radius=ft.border_radius.all(5), expand=True
            ),
            ft.Row(  # ボタン
                [
                    open_btn,
                    export_btn,
                    # --- アンドゥボタン ---
                    ft.IconButton(
                        ref=undo_btn_ref, # 参照を設定
                        icon=ft.Icons.UNDO,
                        tooltip="削除を元に戻す",
                        on_click=handle_undo,
                        disabled=True # 初期状態は無効
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_EVENLY
            ),
            ft.Container(content=status_text, padding=ft.padding.only(top=5)) # ステータス
        ],
        expand=2, spacing=10
    )
    main_layout = ft.Row([left_panel, right_panel], expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

    page.add(main_layout)
    update_button_states()
    update_undo_button_state() # 初期のアンドゥボタン状態設定
    page.update()

if __name__ == "__main__":
    ft.app(target=main)