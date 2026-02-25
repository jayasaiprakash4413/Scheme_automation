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

force_flexi_mode = st.sidebar.checkbox("Force Flexi PF Mode")

# ============================================================
# EXTRACTIONS
# ============================================================

def extract_ltv_from_code(refname):
    match = re.search(r'\((.*?)\)', str(refname))
    if not match:
        return None

    code = match.group(1).lower()
    mapping = {
        "e0": 80,
        "s5": 75,
        "s7": 77,
        "s6": 76,
        "si5": 75
    }
    return Decimal(mapping.get(code, 0))

def extract_tenure(refname):
    match = re.search(r'(\d+)M', str(refname))
    return int(match.group(1)) if match else None

def extract_pf(refname):
    match = re.search(r'PF[- ]*([0-9.]+)%', str(refname))
    return Decimal(match.group(1)) if match else None

def extract_pf_range(refname):
    match = re.search(r'PF.*?([0-9.]+)%\s*-\s*([0-9.]+)%', str(refname))
    if match:
        return Decimal(match.group(1)), Decimal(match.group(2))
    return None, None

def extract_opp(refname):
    parts = str(refname).split("PF")[0]
    match = re.search(r'([0-9]+\.[0-9]+)%', parts)
    return Decimal(match.group(1)) if match else None

# ============================================================
# DECISION ENGINE (12M SAFE)
# ============================================================

def decision_engine(overall_ltv, monthly_opp, requested_tenure):

    secure_s1 = Decimal("9.95")

    if requested_tenure == 12:
        secure_ltv = Decimal("60")
        unsecure_s1 = Decimal("37.65")
        final_tenure = 12
    else:
        secure_ltv = Decimal("67")
        unsecure_s1 = Decimal("48.00")
        final_tenure = requested_tenure

    if overall_ltv <= secure_ltv:
        return ("Royal", final_tenure)

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
        return ("Delight", final_tenure)

    return ("Royal", final_tenure)

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
        secure_ltv = Decimal("67") if tenure != 12 else Decimal("60")
    else:
        secure_s1 = SECURE_S1_ROYAL
        secure_s2 = SECURE_S2_ROYAL
        secure_ltv = Decimal("66") if tenure != 12 else Decimal("60")

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
        "secure_ltv": secure_ltv
    }

# ============================================================
# JSON UPDATE
# ============================================================

def update_interest_json(json_str, slabs, tenure_days):
    data = json.loads(json_str)
    for i in range(3):
        value = Decimal(slabs[i]).quantize(Decimal("0.00"), ROUND_HALF_UP)
        data["interestSlabs"][i]["interestRate"] = float(value)
    data["interestSlabs"][-1]["toDay"] = tenure_days
    return json.dumps(data)

# ============================================================
# STREAMLIT FLOW
# ============================================================

uploaded_file = st.file_uploader("Upload Scheme CSV", type=["csv"])

if uploaded_file:

    if "df" not in st.session_state:
        st.session_state.df = pd.read_csv(uploaded_file)

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

            if not all([overall_ltv, requested_tenure, monthly_opp]):
                continue

            scheme, final_tenure = decision_engine(
                overall_ltv,
                monthly_opp,
                requested_tenure
            )

            # ✅ ONLY FIX YOU REQUESTED
            if "bs1-legalName" in df.columns:
                df.at[idx, "bs1-legalName"] = f"Rupeek {scheme}"

            result = interest_engine(
                scheme,
                final_tenure,
                overall_ltv,
                monthly_opp
            )

            tenure_days = final_tenure * 30

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

        st.session_state.df = df

        st.success("Computation Complete")
        st.subheader("Updated Schemes")
        st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download Updated CSV",
        st.session_state.df.to_csv(index=False),
        "updated_scheme.csv"
    )