"""The 10 required daily reports, in canonical name form used throughout the app."""

REPORT_TYPES = [
    "OP New Registration",
    "OP Encounters",
    "IP Admission",
    "Admission Analysis",
    "IP Discharges",
    "Billing INR OP",
    "Billing INR IP",
    "AEPL Billing",
    "Bed Occupancy",
]

# Report types whose Stage 1-7 processing depends on fixed row/column
# positions (or raw positional row-scanning) rather than named columns --
# these must be loaded with header=None so Excel row N maps directly to
# DataFrame row N-1, with no header-row offset applied.
RAW_POSITIONAL_REPORTS = {"OP Encounters"}
