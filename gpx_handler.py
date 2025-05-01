"""
GPX 読み書きユーティリティ
- 読込時に UTC→JST(+9h) へ変換
- 書出時に JST→UTC へ戻して出力
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any
import gpxpy
import gpxpy.gpx

# タイムゾーン定義
UTC = timezone.utc
JST = timezone(timedelta(hours=9), 'JST')  # JSTタイムゾーンを明示的に定義

# ポイントデータの型エイリアス
Point = Dict[str, Any]  # {"lat":float, "lon":float, "ele":float, "time":datetime|None}

def to_jst(t: datetime | None) -> datetime | None:
    """
    UTC時間をJST(+9h)に変換する。
    タイムゾーン情報がない場合はUTCとして扱う。
    """
    if t is None:
        return None
    # タイムゾーン情報がない場合、UTCとみなす
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    # JSTに変換
    return t.astimezone(JST)

def load_gpx(path: str | Path) -> tuple[List[Point], str]:
    """
    GPXファイルを読み込み、ポイントリストとトラック名を返す。

    Args:
        path (str | Path): GPXファイルのパス。

    Returns:
        tuple[List[Point], str]: ポイントデータのリストとトラック名。
                                  ポイントデータは緯度(lat), 経度(lon), 高度(ele), 時刻(time in JST) を含む辞書。
    """
    try:
        with open(path, encoding="utf-8") as fp:
            gpx = gpxpy.parse(fp)
    except Exception as e:
        raise IOError(f"GPXファイルの読み込みに失敗しました: {e}") from e

    pts: List[Point] = []
    # GPXファイル内の全トラック、全セグメントを走査
    for trk in gpx.tracks:
        for seg in trk.segments:
            for p in seg.points:
                # 各ポイントの情報を抽出し、リストに追加
                pts.append({
                    "lat": p.latitude,
                    "lon": p.longitude,
                    "ele": p.elevation or 0.0,  # 高度がない場合は0.0
                    "time": to_jst(p.time),    # 時刻をJSTに変換
                })

    # トラック名を取得。なければファイル名を代用
    name = gpx.name or (gpx.tracks[0].name if gpx.tracks and gpx.tracks[0].name else Path(path).stem)
    return pts, name

def save_gpx(points: List[Point], dst: str | Path, trk_name: str) -> None:
    """
    ポイントリストをGPXファイルとして保存する。

    Args:
        points (List[Point]): 保存するポイントデータのリスト。
        dst (str | Path): 保存先のファイルパス。
        trk_name (str): GPXファイルに記録するトラック名。
    """
    # 新しいGPXオブジェクトを作成
    gpx = gpxpy.gpx.GPX()
    gpx.name = trk_name # GPX全体の名前

    # GPXトラックを作成
    trk = gpxpy.gpx.GPXTrack(name=trk_name)
    gpx.tracks.append(trk)

    # GPXセグメントを作成
    seg = gpxpy.gpx.GPXTrackSegment()
    trk.segments.append(seg)

    # ポイントデータをGPX形式に変換して追加
    for p in points:
        t = p.get("time")
        utc_time = None
        if t is not None:
            # タイムゾーン情報がない場合はJSTとみなす（load_gpxでJSTに変換しているため）
            if t.tzinfo is None:
                t = JST.localize(t)
            # UTCに変換して保存
            utc_time = t.astimezone(UTC)

        seg.points.append(
            gpxpy.gpx.GPXTrackPoint(
                latitude=p["lat"],
                longitude=p["lon"],
                elevation=p["ele"],
                time=utc_time  # 時刻はUTCで保存
            )
        )

    try:
        # GPXデータをXML形式でファイルに書き込み
        with open(dst, "w", encoding="utf-8") as fp:
            # prettyprint=True で整形されたXMLを出力（デバッグしやすい）
            fp.write(gpx.to_xml(prettyprint=True))
    except Exception as e:
        raise IOError(f"GPXファイルの保存に失敗しました: {e}") from e
    