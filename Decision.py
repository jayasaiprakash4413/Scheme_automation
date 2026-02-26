import streamlit as st
import pandas as pd
import json
import re
from decimal import Decimal, getcontext, ROUND_HALF_UP

getcontext().prec = 50

st.set_page_config(layout="wide")
st.title("Final Scheme Configuration Engine")

# ============================================================
# CONSTANTS (DO NOT TOUCH)
# ============================================================

SECURE_S1_DELIGHT = Decimal("9.95")
SECURE_S2_DELIGHT = Decimal("17.00")

SECURE_S1_ROYAL = Decimal("13.20")
SECURE_S2_ROYAL = Decimal("18.50")

UNSECURE_JSON_6_7 = (Decimal("48.00"), Decimal("48.00"), Decimal("48.00"))
UNSECURE_JSON_12 = (Decimal("37.65"), Decimal("37.65"), Decimal("37.65"))

# Internal calc values
UNSECURE_CALC_6_7 = (Decimal("48.00"), Decimal("46.00"), Decimal("48.00"))
UNSECURE_CALC_12 = (Decimal("37.65"), Decimal("32.00"), Decimal("37.65"))

LTV_CODE_MAP = {
    "e0": Decimal("80"),
    "s5": Decimal("75"),
    "s7": Decimal("77"),
    "s6": Decimal("76"),
    "si5": Decimal("65")
}

force_flexi_mode = st.sidebar.checkbox("Force Flexi PF Mode")

# ============================================================
# EXTRACTIONS
# ============================================================

def extract_ltv_from_code(refname):
    refname_str = str(refname).lower()

    bracket_matches = re.findall(r'\((.*?)\)', refname_str)
    for segment in bracket_matches:
        tokens = [token for token in re.split(r'[^a-z0-9]+', segment) if token]
        for token in tokens:
            if token in LTV_CODE_MAP:
                return LTV_CODE_MAP[token]

    tokens = [token for token in re.split(r'[^a-z0-9]+', refname_str) if token]
    for token in tokens:
        if token in LTV_CODE_MAP:
            return LTV_CODE_MAP[token]

    return None

def extract_tenure(refname):
    match = re.search(r'\b(\d{1,2})\s*M\b', str(refname), re.IGNORECASE)
    return int(match.group(1)) if match else None

def extract_pf(refname):
    match = re.search(r'PF\s*[-:]?\s*([0-9]+(?:\.[0-9]+)?)%', str(refname), re.IGNORECASE)
    return Decimal(match.group(1)) if match else None

def extract_pf_range(refname):
    match = re.search(
        r'PF\s*[-:]?\s*([0-9]+(?:\.[0-9]+)?)%\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)%',
        str(refname),
        re.IGNORECASE
    )
    if match:
        return Decimal(match.group(1)), Decimal(match.group(2))
    return None, None

def extract_opp(refname):
    parts = re.split(r'PF', str(refname), flags=re.IGNORECASE)[0]
    match = re.search(r'([0-9]+(?:\.[0-9]+)?)%', parts)
    return Decimal(match.group(1)) if match else None

def update_refname_tenure(refname, tenure):
    return re.sub(r'\b(\d{1,2})\s*M\b', f'{tenure}M', str(refname), count=1, flags=re.IGNORECASE)

def get_tenure_days(tenure):
    mapping = {6: 180, 7: 210, 12: 360}
    return mapping.get(int(tenure), int(tenure) * 30)

# ============================================================
# DECISION ENGINE (12M SAFE)
# ============================================================

def decision_engine(overall_ltv, monthly_opp, requested_tenure):

    secure_s1 = Decimal("9.95")

    if requested_tenure == 12:
        secure_ltv = Decimal("60")
        unsecure_s1 = Decimal("37.65")
    else:
        secure_ltv = Decimal("67")
        unsecure_s1 = Decimal("48.00")

    if overall_ltv <= secure_ltv:
        return ("Royal", requested_tenure)

    secure_weight = secure_ltv / overall_ltv
    unsecure_weight = (overall_ltv - secure_ltv) / overall_ltv

    min_opp = (secure_weight * secure_s1) / Decimal("12")
    max_opp = (
        secure_weight * secure_s1 +
        unsecure_weight * unsecure_s1
    ) / Decimal("12")

    min_opp = min_opp.quantize(Decimal("0.01"), ROUND_HALF_UP)
    max_opp = max_opp.quantize(Decimal("0.01"), ROUND_HALF_UP)

    if min_opp <= monthly_opp <= max_opp:
        return ("Delight", requested_tenure)

    return ("Royal", requested_tenure)

# ============================================================
# INTEREST ENGINE
# ============================================================

def secure_slab3(tenure):
    r = Decimal("0.229")
    m = Decimal("12")
    t = Decimal(str(tenure))
    compound = (Decimal("1") + r/m) ** t
    result = (compound - Decimal("1")) * m / t
    return (result * 100).quantize(Decimal("0.00"), ROUND_HALF_UP)

def interest_engine(scheme, tenure, overall_ltv, monthly_opp):

    if scheme == "Delight":
        secure_s1 = SECURE_S1_DELIGHT
        secure_s2 = SECURE_S2_DELIGHT
    else:
        secure_s1 = SECURE_S1_ROYAL
        secure_s2 = SECURE_S2_ROYAL

    # secure_ltv = Decimal("67") if tenure != 12 else Decimal("60")
    if tenure == 6:
        secure_ltv = Decimal("67")
    elif tenure == 7:
        secure_ltv = Decimal("66")
    else:
        secure_ltv=Decimal("60")

    secure_s3 = secure_slab3(tenure)

    if tenure == 12:
        calc_unsecure = UNSECURE_CALC_12
        json_unsecure = UNSECURE_JSON_12
    else:
        calc_unsecure = UNSECURE_CALC_6_7
        json_unsecure = UNSECURE_JSON_6_7

    secure_weight = secure_ltv / overall_ltv
    unsecure_weight = (overall_ltv - secure_ltv) / overall_ltv

    s1 = (monthly_opp * Decimal("12")).quantize(Decimal("0.00"), ROUND_HALF_UP)

    s2 = (
        secure_weight * secure_s2 +
        unsecure_weight * calc_unsecure[1]
    ).quantize(Decimal("0.00"), ROUND_HALF_UP)

    s3 = (
        secure_weight * secure_s3 +
        unsecure_weight * calc_unsecure[2]
    ).quantize(Decimal("0.00"), ROUND_HALF_UP)

    return {
        "secure_slabs": (secure_s1, secure_s2, secure_s3),
        "unsecure_slabs": json_unsecure,
        "overall_slabs": (s1, s2, s3),
        "secure_ltv": secure_ltv,
        "calc_unsecure_slabs": calc_unsecure
    }

def update_charge_text(json_str, unsecure_pf, overall_pf):
    data = json.loads(json_str)
    data["secureProcessingFee"] = "0%"
    data["unsecureProcessingFee"] = f"{unsecure_pf.quantize(Decimal('0.00'), ROUND_HALF_UP)}%+GST"
    data["processingFee"] = f"{overall_pf.quantize(Decimal('0.00'), ROUND_HALF_UP)}%+GST"
    return json.dumps(data)

def update_bs2_charge_2(json_str, charge_value, backcalc_min, backcalc_max):
    data = json.loads(json_str)
    data["chargeValue"] = float(charge_value.quantize(Decimal("0.00"), ROUND_HALF_UP))
    if "chargesMetaData" not in data or not isinstance(data["chargesMetaData"], dict):
        data["chargesMetaData"] = {}
    data["chargesMetaData"]["minPercentUnsecure"] = float(backcalc_min.quantize(Decimal("0.00"), ROUND_HALF_UP))
    data["chargesMetaData"]["maxPercentUnsecure"] = float(backcalc_max.quantize(Decimal("0.00"), ROUND_HALF_UP))
    return json.dumps(data)

def update_bs2_legal_name(text, tenure, encoding):
    updated = re.sub(r'\b(6M|7M|12M)\b', f'{tenure}M', str(text), count=1)

    if re.search(r'(th7\.si5|f8)', updated):
        updated = re.sub(r'(th7\.si5|f8)', encoding, updated, count=1)
    else:
        updated = re.sub(r'(48(?:\.00)?%|37\.65%)', encoding, updated, count=1)

    return updated

# ============================================================
# JSON UPDATE
# ============================================================

def _find_slab_list(node):
    if isinstance(node, dict):
        if "interestSlabs" in node and isinstance(node["interestSlabs"], list):
            return node["interestSlabs"]
        for value in node.values():
            found = _find_slab_list(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        if len(node) >= 3 and all(isinstance(item, dict) for item in node):
            if any("interestRate" in item for item in node):
                return node
        for item in node:
            found = _find_slab_list(item)
            if found is not None:
                return found
    return None


def update_interest_json(json_str, slabs, tenure_days):
    try:
        data = json.loads(json_str)
    except Exception:
        return json_str

    slab_list = _find_slab_list(data)
    if not slab_list:
        return json.dumps(data)

    max_count = min(3, len(slab_list), len(slabs))
    for i in range(max_count):
        value = Decimal(slabs[i]).quantize(Decimal("0.00"), ROUND_HALF_UP)
        slab_list[i]["interestRate"] = float(value)

    if slab_list and isinstance(slab_list[-1], dict):
        slab_list[-1]["toDay"] = tenure_days

    return json.dumps(data)

# ============================================================
# STREAMLIT FLOW
# ============================================================

uploaded_file = st.file_uploader("Upload Scheme CSV", type=["csv"])

if uploaded_file:

    current_upload_key = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("uploaded_file_key") != current_upload_key:
        st.session_state.df = pd.read_csv(uploaded_file)
        st.session_state.uploaded_file_key = current_upload_key

    edited_df = st.data_editor(
        st.session_state.df,
        use_container_width=True,
        num_rows="dynamic"
    )

    if st.button("Compute"):

        df = edited_df.copy()

        for idx in df.index:

            refname = df.at[idx, "refName"]

            overall_ltv = extract_ltv_from_code(refname)
            requested_tenure = extract_tenure(refname)
            monthly_opp = extract_opp(refname)
            pf_min, pf_max = extract_pf_range(refname)
            overall_pf = pf_max if pf_max is not None else extract_pf(refname)

            if not all([overall_ltv, requested_tenure, monthly_opp, overall_pf]):
                continue

            df.at[idx, "customerLtv"] = float(overall_ltv)

            scheme, final_tenure = decision_engine(
                overall_ltv,
                monthly_opp,
                requested_tenure
            )

            df.at[idx, "tenure"] = final_tenure
            df.at[idx, "refName"] = update_refname_tenure(refname, final_tenure)

            # ✅ ONLY FIX YOU REQUESTED
            if "bs1-legalName" in df.columns:
                df.at[idx, "bs1-legalName"] = f"Rupeek {scheme}"

            result = interest_engine(
                scheme,
                final_tenure,
                overall_ltv,
                monthly_opp
            )

            if "bs1-ltv" in df.columns:
                df.at[idx, "bs1-ltv"] = float(result["secure_ltv"])

            tenure_days = get_tenure_days(final_tenure)

            df.at[idx, "OverallInterestCalculation"] = update_interest_json(
                df.at[idx, "OverallInterestCalculation"],
                result["overall_slabs"],
                tenure_days
            )

            df.at[idx, "bs1-addon-1"] = update_interest_json(
                df.at[idx, "bs1-addon-1"],
                result["secure_slabs"],
                tenure_days
            )

            df.at[idx, "bs2-addon-1"] = update_interest_json(
                df.at[idx, "bs2-addon-1"],
                result["unsecure_slabs"],
                tenure_days
            )

            if "bs2-calculation" in df.columns:
                df.at[idx, "bs2-calculation"] = update_interest_json(
                    df.at[idx, "bs2-calculation"],
                    result["unsecure_slabs"],
                    tenure_days
                )

            secure_ltv = result["secure_ltv"]
            denominator = Decimal("1") - (secure_ltv / overall_ltv)
            if denominator == 0:
                continue

            min_pf_input = pf_min if pf_min is not None else overall_pf
            max_pf_input = pf_max if pf_max is not None else overall_pf

            min_unsecure_pf = (min_pf_input / denominator).quantize(Decimal("0.00"), ROUND_HALF_UP)
            max_unsecure_pf = (max_pf_input / denominator).quantize(Decimal("0.00"), ROUND_HALF_UP)

            refname_lower = str(df.at[idx, "refName"]).lower()
            is_flexi = force_flexi_mode or any(token in refname_lower for token in ["flexipf", "flexi pf", "flexi-pf"])
            charge_pf_value = max_unsecure_pf if is_flexi else min_unsecure_pf

            if "chargeText" in df.columns:
                charge_text_overall_pf = max_pf_input if is_flexi else min_pf_input
                df.at[idx, "chargeText"] = update_charge_text(
                    df.at[idx, "chargeText"],
                    charge_pf_value,
                    charge_text_overall_pf
                )

            if "bs2-charge-2" in df.columns:
                df.at[idx, "bs2-charge-2"] = update_bs2_charge_2(
                    df.at[idx, "bs2-charge-2"],
                    charge_pf_value,
                    min_unsecure_pf,
                    max_unsecure_pf
                )

            if "bs2-legalName" in df.columns:
                encoding = "th7.si5" if final_tenure == 12 else "f8"
                df.at[idx, "bs2-legalName"] = update_bs2_legal_name(
                    df.at[idx, "bs2-legalName"],
                    final_tenure,
                    encoding
                )

        st.session_state.df = df

        st.success("Computation Complete")
        st.subheader("Updated Schemes")
        st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download Updated CSV",
        st.session_state.df.to_csv(index=False),
        "updated_scheme.csv"
    )
