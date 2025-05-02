# gpxhandle

Minimal GPX editing app running in Python and Flet

## ディレクトリ構成

gpxhandle/
├── requirements.txt        # 依存パッケージ
├── main.py                 # エントリポイント
├── gpx_handler.py          # GPX の読込・書込ユーティリティ
├── map_view.py             # 地図＋ポリライン＋選択マーカー
└── list_view.py            # TrackPoint の一覧 UI

## 使用方法

必要なパッケージの入手
pip install -r requirements.txt

実行
flet run main.py
