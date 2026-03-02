"""
Data model for the scan / auto-import feature.

Usage:
    from lightml.models.scan import ScanStats
"""

from dataclasses import dataclass, field


@dataclass
class ScanStats:
    models_registered: int = 0
    metrics_logged: int = 0
    skipped_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
