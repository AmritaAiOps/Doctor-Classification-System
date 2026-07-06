"""Wires Stages 1-7 together and assembles the flat `values` dict for Stage 8."""
from backend.stages.simple_counters import (
    process_op_new_registration,
    process_op_encounters,
    process_admission_analysis,
    process_bed_occupancy,
)
from backend.stages.cat_dependent_counts import process_ip_admission, process_ip_discharges
from backend.stages.billing import process_billing_op, process_billing_ip
from backend.stages.billing_aggregation import aggregate_billing
from backend.stages.aepl_billing import process_aepl_billing

CAT_KEY_TO_ROW_SUFFIX = {
    "General": "General",
    "TPA": "TPA",
    "ECHS": "ECHS",
    "P.Card.Fund": "P.Card.Fund",
    "Corporates": "Corporates",
    "Total": "Total",
}


class StageProcessingError(Exception):
    """Raised when a specific report fails to process, so the API can tell
    the user which report was the problem instead of a generic 500."""

    def __init__(self, label: str, reason: str):
        self.label = label
        self.reason = reason
        super().__init__(f"{label}: {reason}")


def _run_stage(label, fn):
    try:
        return fn()
    except StageProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised with label context
        raise StageProcessingError(label, str(exc)) from exc


def run_pipeline(dataframes: dict) -> dict:
    """dataframes: dict of the 9 report types -> already-loaded pandas DataFrame
    (see backend.stages.loading for how these get built from uploaded files).

    Returns (values, unmapped) where values is a flat dict keyed to match
    final_output.ROW_MAP. Raises StageProcessingError naming the specific
    report that failed and why, instead of a raw exception.
    """
    bed_occupancy = _run_stage(
        "Bed Occupancy",
        lambda: process_bed_occupancy(dataframes["Bed Occupancy"]),
    )
    op_new_registration = _run_stage(
        "OP New Registration",
        lambda: process_op_new_registration(dataframes["OP New Registration"]),
    )
    op_encounters = _run_stage(
        "OP Encounters",
        lambda: process_op_encounters(dataframes["OP Encounters"]),
    )
    ip_admission = _run_stage(
        "IP Admission",
        lambda: process_ip_admission(dataframes["IP Admission"]),
    )
    admission_analysis = _run_stage(
        "Admission Analysis",
        lambda: process_admission_analysis(dataframes["Admission Analysis"]),
    )
    ip_discharges = _run_stage(
        "IP Discharges",
        lambda: process_ip_discharges(dataframes["IP Discharges"]),
    )
    billing_op_enriched, op_total = _run_stage(
        "Billing INR OP",
        lambda: process_billing_op(dataframes["Billing INR OP"]),
    )
    billing_ip_enriched, ip_total = _run_stage(
        "Billing INR IP",
        lambda: process_billing_ip(dataframes["Billing INR IP"]),
    )
    billing_aggregate = _run_stage(
        "Billing INR OP",  # combined step; a failure here traces back to one of the two billing files
        lambda: aggregate_billing(billing_op_enriched, billing_ip_enriched, op_total, ip_total),
    )
    aepl_billing = _run_stage(
        "AEPL Billing",
        lambda: process_aepl_billing(dataframes["AEPL Billing"]),
    )

    values = {
        "Bed Strength": bed_occupancy["bed_strength"],
        "Beds Occupied": bed_occupancy["beds_occupied"],
        "Occupancy %": bed_occupancy["occupancy_pct"],
        "OP New Registration": op_new_registration,
        "OP Encounters": op_encounters,
        "Emergency Admission": admission_analysis["Emergency Admission"],
        "Planned Admission": admission_analysis["Planned Admission"],
        "Admission from OP (walk-in)": admission_analysis["Admission from OP (walk-in)"],
        "OP Billing": op_total,
        "IP Billing": ip_total,
        "Total Billing": op_total + ip_total,
        "AEPL Billing": aepl_billing,
    }

    for cat_key, suffix in CAT_KEY_TO_ROW_SUFFIX.items():
        values[f"IP Admission {suffix}"] = ip_admission[cat_key]
        values[f"IP Discharges {suffix}"] = ip_discharges[cat_key]

    for key in (
        "Billing Domestic", "Billing International", "Billing Total",
        "Cash Domestic", "Cash International",
        "Credit Domestic Total", "Credit Domestic ECHS", "Credit Domestic P.Card.Fund",
        "Credit Domestic TPA", "Credit Domestic Corporates",
        "Credit International Total", "Credit International TPA Aasantha",
        "Credit International Corporates (International)", "Credit Total Billing",
    ):
        values[key] = billing_aggregate[key]

    unmapped = {
        "IP Admission": ip_admission["unmapped"],
        "IP Discharges": ip_discharges["unmapped"],
    }

    return values, unmapped
