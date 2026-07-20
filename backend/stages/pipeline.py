"""Wires Stages 1-7 together and assembles the flat `values` dict for Stage 8."""
from backend.stages.simple_counters import (
    process_op_new_registration,
    process_op_encounters,
    process_admission_analysis,
    process_bed_occupancy,
)
from backend.stages.cat_dependent_counts import process_ip_admission, process_ip_discharges
from backend.stages.long_stay_patients import process_long_stay_patients
from backend.stages.billing import process_billing_op, process_billing_ip
from backend.stages.billing_aggregation import aggregate_billing
from backend.stages.aepl_billing import process_aepl_billing
from backend.stages.category_review import merge_reviews

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


def run_pipeline(dataframes: dict, overrides: dict = None) -> dict:
    """dataframes: dict of the 9 report types -> already-loaded pandas DataFrame
    (see backend.stages.loading for how these get built from uploaded files).
    overrides: run-scoped raw-category -> bucket corrections from the Category
    Review panel (see category_mapping.resolve_category). Never persisted.

    Returns (values, category_review) where values is a flat dict keyed to
    match final_output.ROW_MAP, and category_review is the merged
    {"possible_matches": [...], "unmatched": [...]} breakdown across every
    report that uses Category (IP Admission, IP Discharges, Long Stay
    Patients, Billing OP, Billing IP). Raises StageProcessingError naming the
    specific report that failed and why, instead of a raw exception.
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
        lambda: process_ip_admission(dataframes["IP Admission"], "IP Admission", overrides),
    )
    admission_analysis = _run_stage(
        "Admission Analysis",
        lambda: process_admission_analysis(dataframes["Admission Analysis"]),
    )
    ip_discharges = _run_stage(
        "IP Discharges",
        lambda: process_ip_discharges(dataframes["IP Discharges"], "IP Discharges", overrides),
    )
    long_stay_patients = _run_stage(
        "IP Discharges",  # reuses the same uploaded file/DataFrame as IP Discharges above
        lambda: process_long_stay_patients(dataframes["IP Discharges"], "IP Discharges", overrides),
    )
    billing_op_enriched, op_total, billing_op_review = _run_stage(
        "Billing INR OP",
        lambda: process_billing_op(dataframes["Billing INR OP"], "Billing INR OP", overrides),
    )
    billing_ip_enriched, ip_total, billing_ip_review = _run_stage(
        "Billing INR IP",
        lambda: process_billing_ip(dataframes["Billing INR IP"], "Billing INR IP", overrides),
    )
    aepl_billing = _run_stage(
        "AEPL Billing",
        lambda: process_aepl_billing(dataframes["AEPL Billing"]),
    )

    total_billing = op_total + ip_total
    billing_aggregate = _run_stage(
        "Billing Aggregation",
        lambda: aggregate_billing(billing_op_enriched, billing_ip_enriched, op_total, ip_total),
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
        "Long Stay Patients": long_stay_patients["Total"],
        "OP Billing": op_total,
        "IP Billing": ip_total,
        "Total Billing": total_billing,
        "AEPL Billing": aepl_billing,
        "Hospital Revenue (Net of AEPL)": total_billing - aepl_billing,
    }

    for cat_key, suffix in CAT_KEY_TO_ROW_SUFFIX.items():
        values[f"IP Admission {suffix}"] = ip_admission[cat_key]
        values[f"IP Discharges {suffix}"] = ip_discharges[cat_key]
        # Long Stay Patients only has one flat row in Final output (row 29),
        # but the bucket breakdown is still useful for the results dashboard.
        values[f"Long Stay Patients {suffix}"] = long_stay_patients[cat_key]

    for key in (
        "Billing Domestic", "Billing International", "Billing Total",
        "Cash Domestic", "Cash International",
        "Credit Domestic Total", "Credit Domestic ECHS", "Credit Domestic P.Card.Fund",
        "Credit Domestic TPA", "Credit Domestic Corporates",
        "Credit International Total", "Credit International TPA Aasantha",
        "Credit International Corporates (International)", "Credit Total Billing",
    ):
        values[key] = billing_aggregate[key]

    category_review = merge_reviews([
        ip_admission["category_review"],
        ip_discharges["category_review"],
        long_stay_patients["category_review"],
        billing_op_review,
        billing_ip_review,
    ])

    return values, category_review
