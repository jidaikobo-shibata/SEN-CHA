from dataclasses import asdict, dataclass


REGION_GRIDS = {"fine": (8, 6), "broad": (4, 3), "whole": (0, 0)}
DEFAULT_SENSITIVITY = "high"
SENSITIVITY_LABELS = {"high": "標準設定", "standard": "低感度"}


@dataclass(frozen=True)
class Settings:
    width: int = 320
    columns: int = 8
    rows: int = 6
    window_seconds: float = 1.0
    standard_delta: float = 0.10
    high_delta: float = 0.06
    standard_count: int = 4
    high_count: int = 3
    merge_gap: float = 0.25
    max_candidates: int = 1000
    max_dimension: int = 8192
    max_upload_bytes: int = 4 * 1024**3
    max_duration: float = 4 * 3600
    idle_timeout: float = 60.0

    def export(self):
        return asdict(self)


DEFAULT = Settings()
LIMITATIONS = [
    "WCAG適合判定・医療上の安全性評価ではなく、目視確認の候補抽出です。",
    "縮小と領域平均により、小さい点滅や領域内で相殺される点滅を見逃すことがあります。",
    "カメラ移動、反復する場面転換などを点滅として拾う場合があります。",
    "赤色は独自の簡易指標です。WCAGの赤色閃光・視角・面積の閾値を厳密には実装していません。",
    "area_fractionは検出領域の画面比で、実際に閃光した画素の面積ではありません。",
    "SDR色変換は近似です。色情報が省略された動画は仮定を使用します。",
    "全編の正常完了と、処理失敗・中止は区別してください。候補なしは適合を意味しません。",
]
