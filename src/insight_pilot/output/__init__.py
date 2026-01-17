"""Output generation modules."""
from insight_pilot.output.index import generate_index, generate_index_with_reports
from insight_pilot.output.report import generate_report, save_report

__all__ = [
    "generate_index",
    "generate_index_with_reports",
    "generate_report",
    "save_report",
]
