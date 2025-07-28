import streamlit as st
import pandas as pd
from pymodbus.client import ModbusTcpClient
import pdfplumber
import re
from math import sqrt
from datetime import datetime
import webbrowser
import ast
import io
from io import StringIO
# =============================
# Global state
# =============================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "log" not in st.session_state:
    st.session_state.log = []

def log_message(msg: str):
    """Append a timestamped message to our in-app log."""
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    st.session_state.log.append(f"{ts} {msg}")

log_message("App started")
# ──────────────────────────────────────────
# Navigation options (edit here to add/remove)
# ──────────────────────────────────────────
NAV_OPTIONS = [
    "PDF Extraction",
    "Inputs & Modbus",
    "Calculations & Export",
    "Debug Log",
]
# =============================
# Authentication
# =============================
if not st.session_state.get("authenticated", False):
    st.title("EnerFlow Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Sign in"):
        # TODO: replace with real corporate SSO
        if username == "admin" and password == "secret":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()


# ───────────────────────────────────────────────────────
# Dark/Light Mode Toggle
# ───────────────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

def toggle_theme():
    st.session_state.dark_mode = not st.session_state.dark_mode

theme_button = "🌙 Dark" if not st.session_state.dark_mode else "☀️ Light"
st.sidebar.button(theme_button, on_click=toggle_theme)

if st.session_state.dark_mode:
    st.markdown(
        """
        <style>
        body { background-color: #222 !important; color: #ddd !important; }
        .stButton>button { background-color: #444 !important; color: #ddd !important; }
        </style>
        """,
        unsafe_allow_html=True
    )
# ───────────────────────────────────────────────────────

# =============================
# Modbus register definitions
# =============================
registers = {
    "Set_Point_Value_Underload":        (26, 1),
    "Start_Delay_Underload":           (105, 1),
    "Trigger_Delay_Underload":         (106, 1),
    "Restart_Attempts_Underload":      (108, 1),
    "Down_Time_Underload":             (107, 1),
    "Set_Point_Value_Overload":        (27, 1),
    "Start_Delay_Overload":            (113, 1),
    "Trigger_Delay_Overload":          (114, 1),
    "Restart_Attempts_Overload":       (116, 1),
    "Down_Time_Overload":              (115, 1),
    "Set_Point_Value_Low_Frequency":   (33, 1),
    "Start_Delay_Low_Frequency":       (117, 1),
    "Trigger_Delay_Low_Frequency":     (118, 1),
    "Restart_Attempts_Low_Frequency":  (120, 1),
    "Down_Time_Low_Frequency":         (119, 1),
    "Set_Point_Value_High_Winding_Temp": (225, 1),
    "Start_Delay_High_Winding_Temp":   (131, 1),
    "Trigger_Delay_High_Winding_Temp": (132, 1),
    "Restart_Attempts_High_Winding_Temp": (134,1),
    "Down_Time_High_Winding_Temp":     (133, 1),
}

additional_registers = {
    "Output_Freq_Hz":                     (2103, 1),
    "Motor_Current_A":                    (2149, 1),
    "VFD_Current_A":                      (2105, 1),
    "Fluid_Temp_F":                       (0,    1),
    "Motor_Temp_F":                       (2,    1),
    "DC_Bus_Voltage_V":                   (2109, 1),
    "Motor_Voltage_V":                    (2150, 1),
    "Output_Voltage_V":                   (2108, 1),
    "General_Down_Time":                  (28,   1),
    "Max_Volt_at_max_Frequency_Spoc_(V)": (29,   1),
    "Normal_Running_Amp_(A)":             (30,   1),
    "DH_MOTOR_TEMP_UL_ACTION":            (226,  1),
}
# ————————————————————————————————————————————————————————————————
# Triol-specific Modbus maps & scaling
# ————————————————————————————————————————————————————————————————
TRIOL_REGISTERS = {
    "Protection_Underload":             (2304, 1),
    "Protection_Overload":              (2181, 1),
    "Protection_Low_Frequency":         (3460, 1),
    "Protection_High_Intake_Temp":      (4999, 1),
    "Protection_High_Winding_Temp":     (8839, 1),
    "Set_Point_Value_Underload":        (2308, 1),
    "Set_Point_Value_Overload":         (2178, 1),
    "Set_Point_Value_Low_Frequency":    (3457, 1),
    "Set_Point_Value_High_Intake_Temp": (4997, 2),
    "Set_Point_Value_High_Winding_Temp":(8837, 2),
    "Start_Delay_Underload":            (2309, 1),
    "Start_Delay_Overload":             (2179, 1),
    "Start_Delay_Low_Frequency":        (3458, 1),
    "Start_Delay_High_Intake_Temp":     (5002, 1),
    "Start_Delay_High_Winding_Temp":    (8842, 1),
    "Trigger_Delay_Underload":          (2310, 1),
    "Trigger_Delay_Overload":           (2180, 1),
    "Trigger_Delay_Low_Frequency":      (3459, 1),
    "Trigger_Delay_High_Intake_Temp":   (5003, 1),
    "Trigger_Delay_High_Winding_Temp":  (8843, 1),
    "Restart_Attempts_Underload":       (2312, 1),
    "Restart_Attempts_Overload":        (2182, 1),
    "Restart_Attempts_Low_Frequency":   (3461, 1),
    "Restart_Attempts_High_Intake_Temp":(5001, 1),
    "Restart_Attempts_High_Winding_Temp":(8841,1),
    "Down_Time_Underload":              (2313, 1),
    "Down_Time_Overload":               (2183, 1),
    "Down_Time_Low_Frequency":          (3456, 1),
    "Down_Time_High_Intake_Temp":       (5000, 1),
    "Down_Time_High_Winding_Temp":      (8840, 1),
}

TRIOL_ADDITIONAL = {
    "Output_Freq_Hz":        (1,    1),
    "Motor_Current_A":       (2,    1),
    "VFD_Current_A":         (8,    1),
    "Fluid_Temp_F":          (4993, 2),
    "Motor_Temp_F":          (8833, 2),
    "DC_Bus_Voltage_V":      (128,  1),
    "Motor_Voltage_V":       (132,  1),
    "Output_Voltage_V":      (135,  1),
    "Power_factor":          (7,    1),
}

# scale‐maps lifted from your template logic
TRIOL_DIVIDE = {
    **{k: 10 for k in ("Output_Freq_Hz","Motor_Current_A","Power_factor")},
    **{k: 100 for k in ("Fluid_Temp_F","Motor_Temp_F")},
    **{k: 10 for k in (
        "Set_Point_Value_Underload","Set_Point_Value_Overload",
        "Set_Point_Value_Low_Frequency"
    )},
    "Set_Point_Value_High_Intake_Temp":  100,
    "Set_Point_Value_High_Winding_Temp": 100,
    **{k: 10 for k in (
        "Start_Delay_Underload","Start_Delay_Overload",
        "Start_Delay_Low_Frequency","Start_Delay_High_Intake_Temp",
        "Start_Delay_High_Winding_Temp",

    )},
}

TRIOL_MULTIPLY = {
    # if you had any multiply rules—e.g. none by default:
}
def make_template_bytes(core_map: dict,
                        add_map: dict,
                        drive_name: str,
                        divide_map: dict | None = None,
                        multiply_map: dict | None = None) -> bytes:
    """
    Build an Excel “Mappings” sheet from core & additional register dicts.
    """
    import pandas as pd

    divide_map   = divide_map   or {}
    multiply_map = multiply_map or {}

    rows = []
    # merge core + additional, mark category
    for name, (addr, cnt) in {**core_map, **add_map}.items():
        rows.append({
            "Drive Type":       drive_name,
            "Parameter Name":   name,
            "Register Address": addr,
            "Register Count":   cnt,
            "Category":         "core" if name in core_map else "additional",
            "Data Type":        "int32" if cnt == 2 else "int16",
            "Scale Divide":     divide_map.get(name, ""),
            "Scale Multiply":   multiply_map.get(name, ""),
        })

    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(
        buf,
        sheet_name="Mappings",
        index=False,
        engine="xlsxwriter"
    )
    buf.seek(0)
    return buf.read()
def read_registers(reg_dict, client):
    """Read a dict of registers from Modbus client."""
    vals = {}
    for name, (addr, count) in reg_dict.items():
        resp = client.read_holding_registers(addr, count=count, device_id=1)
        if not resp.isError():
            if count == 2:
                low, high = resp.registers
                vals[name] = (high << 16) | low
            else:
                vals[name] = resp.registers[0]
        else:
            vals[name] = None
    return vals

def read_modbus_data(ip: str, port: int):
    """Connect to SPOC drive via Modbus, scale values, and build
    a 12-column live-data table with Protection logic."""
    # 1) Connect
    log_message("Attempting Modbus connection...")
    client = ModbusTcpClient(ip, port=port)
    if not client.connect():
        log_message("Modbus connection failed")
        raise ConnectionError("Could not connect to Modbus device")
    log_message("Modbus connected successfully")

    # 2) Read raw registers
    before     = read_registers(registers, client)
    additional = read_registers(additional_registers, client)
    client.close()

    # 3) Apply your existing SPOC scaling rules
    log_message("Scaling Modbus values")
    if isinstance(additional.get("VFD_Current_A"), (int, float)):
        additional["VFD_Current_A"] /= 10
    if isinstance(additional.get("Fluid_Temp_F"), (int, float)):
        additional["Fluid_Temp_F"] /= 10
    if isinstance(additional.get("Motor_Temp_F"), (int, float)):
        additional["Motor_Temp_F"] /= 10
    if isinstance(additional.get("Output_Voltage_V"), (int, float)):
        additional["Output_Voltage_V"] /= 10
    if isinstance(additional.get("Output_Freq_Hz"), (int, float)):
        additional["Output_Freq_Hz"] /= 100

    for key in ("Set_Point_Value_Underload","Set_Point_Value_Overload"):
        if isinstance(before.get(key),(int,float)):
            before[key] /= 10
    for key in ("Start_Delay_Underload","Start_Delay_Overload"):
        if isinstance(before.get(key),(int,float)):
            before[key] *= 60
    if isinstance(before.get("Set_Point_Value_Low_Frequency"),(int,float)):
        before["Set_Point_Value_Low_Frequency"] /= 100
    if isinstance(before.get("Start_Delay_Low_Frequency"),(int,float)):
        before["Start_Delay_Low_Frequency"] *= 60
    if isinstance(before.get("Set_Point_Value_High_Winding_Temp"),(int,float)):
        before["Set_Point_Value_High_Winding_Temp"] /= 10

    # 4) Build unified 12-column live-data table
    #    - Protection=“On” for all except High_Winding_Temp_(F)
    #    - High_Winding_Temp protection driven by DH_MOTOR_TEMP_UL_ACTION
    spoc_prot_map = {0: "Off", 1: "Warning", 2: "On"}
    mapping = [
        ("Underload_(A)",        "Set_Point_Value_Underload",     "Start_Delay_Underload",      "Trigger_Delay_Underload",      "Restart_Attempts_Underload",      "Down_Time_Underload"),
        ("Overload_(A)",         "Set_Point_Value_Overload",      "Start_Delay_Overload",       "Trigger_Delay_Overload",       "Restart_Attempts_Overload",       "Down_Time_Overload"),
        ("Low_Frequency_(Hz)",    "Set_Point_Value_Low_Frequency", "Start_Delay_Low_Frequency",  "Trigger_Delay_Low_Frequency",  "Restart_Attempts_Low_Frequency",  "Down_Time_Low_Frequency"),
        ("High_Intake_Temp_(F)",  "Set_Point_Value_High_Intake_Temp","Start_Delay_High_Intake_Temp","Trigger_Delay_High_Intake_Temp","Restart_Attempts_High_Intake_Temp","Down_Time_High_Intake_Temp"),
        ("High_Winding_Temp_(F)", "Set_Point_Value_High_Winding_Temp","Start_Delay_High_Winding_Temp","Trigger_Delay_High_Winding_Temp","Restart_Attempts_High_Winding_Temp","Down_Time_High_Winding_Temp"),
    ]

    rows = []
    for label, sp, sd, tr, ra, dt in mapping:
        if label != "High_Winding_Temp_(F)":
            prot_before = "On"
        else:
            raw = additional.get("DH_MOTOR_TEMP_UL_ACTION", 0)
            prot_before = spoc_prot_map.get(raw, str(raw))
        rows.append({
            "Parameter":                    label,
            "Protection (Before)":         prot_before,
            "Protection (After)":          "Same",
            "Set_Point_Value (Before)":    before.get(sp),
            "Set_Point_Value (After)":     "Same",
            "Start_Delay_(s) (Before)":    before.get(sd),
            "Start_Delay_(s) (After)":     "Same",
            "Trigger_Delay_(s) (Before)":  before.get(tr),
            "Trigger_Delay_(s) (After)":   "Same",
            "Restart_Attempts (Before)":   before.get(ra),
            "Restart_Attempts (After)":    "Same",
            "Down_Time_(min) (Before)":    before.get(dt),
            "Down_Time_(min) (After)":     "Same",
        })
    df_live = pd.DataFrame(rows)

    # 5) Additional register table stays the same
    df_additional = pd.DataFrame({
        "Parameter": list(additional_registers.keys()),
        "Value":     [additional[k] for k in additional_registers.keys()],
    })

    log_message("Modbus data ready")
    return additional, before, df_live, df_additional

def read_triold_modbus_data(ip: str, port: int):
    """Like read_modbus_data but for Triol’s registers & scaling,
    and with Triol-specific Protection decoding."""
    # 1) Connect & read raw
    client = ModbusTcpClient(ip, port=port)
    if not client.connect():
        raise ConnectionError("Could not connect to Triol device")
    before     = read_registers(TRIOL_REGISTERS, client)
    additional = read_registers(TRIOL_ADDITIONAL, client)
    client.close()

    # 2) Apply Triol scaling
    for nm, raw in list(before.items()):
        if raw is None: continue
        if nm in TRIOL_DIVIDE:
            before[nm] = raw / TRIOL_DIVIDE[nm]
        if nm in TRIOL_MULTIPLY:
            before[nm] = before[nm] * TRIOL_MULTIPLY[nm]
    for nm, raw in list(additional.items()):
        if raw is None: continue
        if nm in TRIOL_DIVIDE:
            additional[nm] = raw / TRIOL_DIVIDE[nm]
        if nm in TRIOL_MULTIPLY:
            additional[nm] = additional[nm] * TRIOL_MULTIPLY[nm]

    # 3) Build unified 12-column live-data table
    triol_prot_map = {0: "Off", 1: "Lockout", 2: "Autorestart", 3: "Warning"}
    prot_reg_map = {
        "Underload_(A)":        "Protection_Underload",
        "Overload_(A)":         "Protection_Overload",
        "Low_Frequency_(Hz)":    "Protection_Low_Frequency",
        "High_Intake_Temp_(F)":  "Protection_High_Intake_Temp",
        "High_Winding_Temp_(F)": "Protection_High_Winding_Temp",
    }
    mapping = [
        ("Underload_(A)",        "Set_Point_Value_Underload",     "Start_Delay_Underload",      "Trigger_Delay_Underload",      "Restart_Attempts_Underload",      "Down_Time_Underload"),
        ("Overload_(A)",         "Set_Point_Value_Overload",      "Start_Delay_Overload",       "Trigger_Delay_Overload",       "Restart_Attempts_Overload",       "Down_Time_Overload"),
        ("Low_Frequency_(Hz)",    "Set_Point_Value_Low_Frequency", "Start_Delay_Low_Frequency",  "Trigger_Delay_Low_Frequency",  "Restart_Attempts_Low_Frequency",  "Down_Time_Low_Frequency"),
        ("High_Intake_Temp_(F)",  "Set_Point_Value_High_Intake_Temp","Start_Delay_High_Intake_Temp","Trigger_Delay_High_Intake_Temp","Restart_Attempts_High_Intake_Temp","Down_Time_High_Intake_Temp"),
        ("High_Winding_Temp_(F)", "Set_Point_Value_High_Winding_Temp","Start_Delay_High_Winding_Temp","Trigger_Delay_High_Winding_Temp","Restart_Attempts_High_Winding_Temp","Down_Time_High_Winding_Temp"),
    ]

    rows = []
    for label, sp, sd, tr, ra, dt in mapping:
        raw_prot = before.get(prot_reg_map[label], 0)
        prot_before = triol_prot_map.get(raw_prot, str(raw_prot))
        rows.append({
            "Parameter":                    label,
            "Protection (Before)":         prot_before,
            "Protection (After)":          "Same",
            "Set_Point_Value (Before)":    before.get(sp),
            "Set_Point_Value (After)":     "Same",
            "Start_Delay_(s) (Before)":    before.get(sd),
            "Start_Delay_(s) (After)":     "Same",
            "Trigger_Delay_(s) (Before)":  before.get(tr),
            "Trigger_Delay_(s) (After)":   "Same",
            "Restart_Attempts (Before)":   before.get(ra),
            "Restart_Attempts (After)":    "Same",
            "Down_Time_(min) (Before)":    before.get(dt),
            "Down_Time_(min) (After)":     "Same",
        })
    df_live = pd.DataFrame(rows)

    # 4) Additional registers (same as SPOC)
    df_additional = pd.DataFrame({
        "Parameter": list(additional.keys()),
        "Value":     [additional[k] for k in additional.keys()],
    })

    return additional, before, df_live, df_additional

# =============================
# PDF Extraction (from enerflowv5) – FINAL
# =============================
def extract_pdf_data(pdf_file) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """
    1-for-1 port of enerflowv5.extract_pdf_data.
    Works with either a filepath or Streamlit’s UploadedFile.
    """
    log_message("Extracting data from PDF...")

    # ── working vars ─────────────────────────────────────
    install_type = customer = well_number = start_date = None
    vsd_amp_rating = disconnect_size = casing_size_wt = None
    pump_details, motor_details = [], []
    first_motor_set_depth = None
    power_cable_number = None
    no_load_vpp = []
    total_pump_stages = 0
    total_motor_voltages = 0
    nameplate_amp = None
    transformer_secondary = None
    pump_size = None
    incomplete_motor_desc = ""
    # ── helpers ──────────────────────────────────────────────
    pump_serials  = set()   # make sure each pump counted once
    motor_serials = set()   # make sure each motor counted once
    # ── open the PDF ─────────────────────────────────────
    with pdfplumber.open(pdf_file) as pdf:

        for page_num, page in enumerate(pdf.pages, start=1):
            text   = page.extract_text() or ""
            tables = page.extract_tables() or []

            # -------- headline fields (simple regex, all UPPERCASE) ------
            if "INSTALL TYPE:" in text:
                m = re.search(r"INSTALL TYPE:\s*(\w+)", text)
                if m: install_type = m.group(1)

            if "CUSTOMER:" in text:
                m = re.search(r"CUSTOMER:\s*([^\n]+)", text)
                if m:
                    raw = m.group(1).strip()
                    customer = raw.split("APPLICATION")[0].strip() if "APPLICATION" in raw.upper() else raw

            if "WELL #:" in text:
                m = re.search(r"WELL #:\s*([^\n]+)", text)
                if m:
                    raw = m.group(1).strip()
                    well_number = raw.split("START DATE")[0].strip() if "START DATE" in raw.upper() else raw

            if "START DATE:" in text:
                m = re.search(r"START DATE:\s*([^\n]+)", text)
                if m: start_date = m.group(1).strip()

            if vsd_amp_rating is None and "VSD AMPERAGE RATING" in text:
                m = re.search(r"VSD AMPERAGE RATING\s+(\d+)", text)
                if m: vsd_amp_rating = int(m.group(1))

            if disconnect_size is None and "DISCONNECT SIZE" in text:
                m = re.search(r"DISCONNECT SIZE\s+(\d+)", text)
                if m: disconnect_size = int(m.group(1))

            if transformer_secondary is None and "TRANSFORMER SECONDARY" in text:
                m = re.search(r"TRANSFORMER SECONDARY\s+(\d+)", text)
                if m: transformer_secondary = int(m.group(1))

            if casing_size_wt is None:
                for tbl in tables:                                   # every table on page
                    for r_idx, row in enumerate(tbl):                # every row in table
                        for c_idx, cell in enumerate(row):           # every cell in row
                            if (
                                isinstance(cell, str)
                                and re.search(r"CASING\s*SIZE\s*/\s*WT", cell, re.I)
                            ):
                                # neighbour cell is *usually* same column, next row ↓
                                if r_idx + 1 < len(tbl):
                                    neighbour = tbl[r_idx + 1][c_idx]
                                    if isinstance(neighbour, str) and neighbour.strip():
                                        casing_size_wt = neighbour.strip()
                                break          # stop after first hit in this row
                        if casing_size_wt:
                            break              # stop scanning rows in this table
                    if casing_size_wt:
                        break                  # stop scanning tables
            # -------- POWER CABLE NUMBER (greedy, multi-line) ------------
            if power_cable_number is None:
                m = re.search(
                    r"POWER\s+CABLE\s+SERIAL.*?CABLE\s*#\s*(\d+)",
                    text, re.I | re.S
                )
                if m: power_cable_number = int(m.group(1))
            # -------- iterate tables -------------------------------------
            for tbl in tables:

                # a) dedicated MOTORS table
                if tbl and tbl[0] and tbl[0][0].strip().upper() == "MOTORS":
                    for row in tbl[1:]:
                        if len(row) < 6:
                            continue

                        serial      = (row[0] or "").strip()
                        if not serial or serial in motor_serials:
                            continue
                        motor_serials.add(serial)

                        # description lives in col-3 or col-2
                        description = (row[3] or row[2] or "").strip()
                        # right-most float is always the set-depth
                        depth       = next(
                            (c for c in reversed(row)
                            if isinstance(c, str) and re.fullmatch(r"\d+\.\d+", c.strip())),
                            None,
                        )

                        # incomplete description guard
                        if "ELS" in description.upper() and not description.isupper():
                            incomplete_motor_desc = description
                            continue

                        # PUMPS in the MOTORS table
                        if "ELS" in description.upper() and "PUMP" in description.upper():
                            m_sz  = re.search(r"PUMP\s+(\d{3,4})", description)
                            m_st  = re.search(r"(\d+)S\b", description)
                            p_sz  = int(m_sz.group(1)) if m_sz else None
                            p_stg = int(m_st.group(1)) if m_st else None
                            if p_stg:
                                total_pump_stages += p_stg
                            if pump_size is None and p_sz:
                                pump_size = p_sz

                            pump_details.append({
                                "serial":      serial,
                                "description": description.title(),
                                "pump_size":   p_sz,
                                "stage":       p_stg,
                                "set_depth":   float(depth) if depth else None,
                            })
                            log_message(f"[pump] added {serial} size={p_sz}")

                        # MOTORS in the MOTORS table
                        elif "ELS" in description.upper() and "MOTOR" in description.upper():
                            v_match = re.search(r"(\d{3,4})V\b",    description)
                            a_match = re.search(r"(\d+(?:\.\d+)?)A\b", description)
                            m_volt  = int(v_match.group(1)) if v_match else None

                            if a_match and nameplate_amp is None:
                                nameplate_amp = float(a_match.group(1))
                            if m_volt:
                                total_motor_voltages += m_volt
                            if depth and first_motor_set_depth is None:
                                try:
                                    first_motor_set_depth = float(depth)
                                except ValueError:
                                    pass

                            motor_details.append({
                                "serial":        serial,
                                "description":   description.title(),
                                "motor_voltage": m_volt,
                                "nameplate_amp": nameplate_amp,
                                "set_depth":     float(depth) if depth else None,
                            })
                            log_message(f"[motor] added {serial}")

                    # skip the generic fallback for this table
                    continue

                # b) generic equipment rows – catch PUMPs or MOTORS
                for row in tbl:
                    if len(row) < 4:
                        continue

                    serial   = (row[0] or "").strip()
                    desc_raw = (row[3] or row[2] or "").strip()
                    desc      = desc_raw.upper()

                    # ── PUMPS fallback ───────────────────────────────────
                    if " PUMP " in desc and "ELS" in desc and "PUMP HEAD" not in desc:
                        if not serial or serial in pump_serials:
                            continue
                        pump_serials.add(serial)

                        m_sz  = re.search(r"PUMP\s+(\d{3,4})", desc)
                        m_st  = re.search(r"(\d+)S\b", desc)
                        p_sz  = int(m_sz.group(1)) if m_sz else None
                        p_stg = int(m_st.group(1)) if m_st else None
                        if p_stg:
                            total_pump_stages += p_stg
                        if pump_size is None and p_sz:
                            pump_size = p_sz

                        depth_s = next(
                            (c for c in reversed(row)
                            if isinstance(c, str) and re.fullmatch(r"\d+\.\d+", c.strip())),
                            None,
                        )
                        pump_details.append({
                            "serial":      serial,
                            "description": desc_raw.title(),
                            "pump_size":   p_sz,
                            "stage":       p_stg,
                            "set_depth":   float(depth_s) if depth_s else None,
                        })
                        log_message(f"[pump] added {serial} size={p_sz}")

                    # ── MOTORS fallback ─────────────────────────────────
                    elif " MOTOR " in desc and "ELS" in desc:
                        if not serial or serial in motor_serials:
                            continue
                        motor_serials.add(serial)

                        v_m = re.search(r"(\d{3,4})V\b", desc)
                        a_m = re.search(r"(\d+(?:\.\d+)?)A\b", desc)

                        if v_m:
                            total_motor_voltages += int(v_m.group(1))
                        if a_m and nameplate_amp is None:
                            nameplate_amp = float(a_m.group(1))

                        depth_s = next(
                            (c for c in reversed(row)
                            if isinstance(c, str) and re.fullmatch(r"\d+\.\d+", c.strip())),
                            None,
                        )
                        if depth_s and first_motor_set_depth is None:
                            first_motor_set_depth = float(depth_s)

                        motor_details.append({
                            "serial":        serial,
                            "description":   desc_raw.title(),
                            "motor_voltage": int(v_m.group(1)) if v_m else None,
                            "nameplate_amp": float(a_m.group(1)) if a_m else None,
                            "set_depth":     float(depth_s) if depth_s else None,
                        })
                        log_message(f"[motor] added {serial}")

                    # ── NO-LOAD VOLTAGE rows ─────────────────────────────
                    if any("NO LOAD VOLTAGE" in (c or "").upper() for c in row):
                        nums = re.findall(r"\d+\.\d+|\d+", " ".join(str(c or "") for c in row[1:4]))
                        no_load_vpp.extend(float(n) for n in nums)
           


    # ───────────────  P U M P   S U M M A R Y  ──────────────────────────
    if pump_details:
        # 1) one row per physical pump (serial)  ➜ eliminates dupes across pages
        pump_df = pd.DataFrame(pump_details).drop_duplicates(subset="serial")

        # 2) aggregate by size
        pump_summary = (
            pump_df
            .groupby("pump_size", as_index=False, dropna=False)         # 1750 | 3000 …
            .agg(
                description=("description", "first"),                   # example text
                stage=("stage", "sum"),                                 # 98+98+98…
                set_depth=("set_depth", "min"),                         # shallowest
                Count=("serial", "nunique"),                            # ✅ real count
            )
        )
    else:
        pump_summary = pd.DataFrame(
            columns=["pump_size", "description", "stage", "set_depth", "Count"]
        )

    motor_df = pd.DataFrame(motor_details)
    if not motor_df.empty:
        motor_summary = (
            motor_df
            .groupby("description", as_index=False, dropna=False)
            .agg(nameplate_amp=("nameplate_amp", "first"),
                 motor_voltage=("motor_voltage", "first"),
                 set_depth=("set_depth", "first"))
        )
        motor_summary["Count"] = motor_df.groupby("description")["description"].transform("count")
    else:
        motor_summary = pd.DataFrame(columns=["description","nameplate_amp","motor_voltage","set_depth","Count"])

    extracted = {
        "Nameplate Amp (A)":           nameplate_amp,
        "Total Motor Voltages (V)":    total_motor_voltages,
        "VSD AMPERAGE RATING (A)":     vsd_amp_rating,
        "POWER CABLE NUMBER":          power_cable_number,
        "First Motor Set Depth (ft)":  first_motor_set_depth,
        "Main Pump Size":              pump_size,
        "Total Pump Stages":           total_pump_stages,
        "Customer":                    customer,
        "WELL #":                      well_number,
        "START DATE":                  start_date,
        "Install Type":                install_type,
        "CASING SIZE/WT":              casing_size_wt,
        "DISCONNECT SIZE (A)":         disconnect_size,
        "TRANSFORMER SECONDARY (V)":   transformer_secondary,
        "NO LOAD VOLTAGE":             no_load_vpp,
    }

    log_message("PDF extraction complete")
    return extracted, pump_summary, motor_summary

# =============================
# Calculations
# =============================
def perform_calculations(manual_vals: dict, extracted: dict, modbus_vals: dict):
    log_message("Performing calculations...")

    # === 1. Unpack all numeric inputs safely using the helper function ===

    # Unpack manual inputs
    output_freq    = safe_float(manual_vals.get("Output Freq (Hz)*"))
    motor_current  = safe_float(manual_vals.get("Motor Current (A)*"),   default=1.0)
    vfd_current    = safe_float(manual_vals.get("VFD Current (A)*"),     default=1.0)
    fluid_temp     = safe_float(manual_vals.get("Fluid Temp (F)*"))
    dc_bus_voltage = safe_float(manual_vals.get("DC Bus Voltage (V)*"))
    motor_voltage  = safe_float(manual_vals.get("Motor Voltage (V)*"))
    motor_eff      = safe_float(manual_vals.get("Motor Efficiency (%)"))
    max_freq       = safe_float(manual_vals.get("Max Frequency (Hz)"))
    Base_freq   = safe_float(manual_vals.get("Base Frequency (Hz)"))
    ov             = safe_float(manual_vals.get("Output Voltage (V)*"),  default=1.0)

    # Unpack extracted PDF data (now also safe)
    nameplate_amp   = safe_float(extracted.get("Nameplate Amp (A)"))
    total_motor_v   = safe_float(extracted.get("Total Motor Voltages (V)"))
    vsd_amp_rating  = safe_float(extracted.get("VSD AMPERAGE RATING (A)"))
    cable_num       = safe_float(extracted.get("POWER CABLE NUMBER"))
    depth           = safe_float(extracted.get("First Motor Set Depth (ft)"))
    pump_size       = safe_float(extracted.get("Main Pump Size"))
    disconnect_size = safe_float(extracted.get("DISCONNECT SIZE (A)"))

    # Safely parse the list of no-load voltages
    raw_no_load = extracted.get("NO LOAD VOLTAGE", [])
    no_load_volts = []
    if isinstance(raw_no_load, str):
        found_nums = re.findall(r"[\d\.]+", raw_no_load)
        no_load_volts = [safe_float(n) for n in found_nums]
    elif isinstance(raw_no_load, list):
        no_load_volts = [safe_float(n) for n in raw_no_load]

    # core calculations
    ratio = vfd_current / motor_current if motor_current else 0
    underload = vfd_current * 0.65
    vsd_amp = vsd_amp_rating if disconnect_size == 0 else min(vsd_amp_rating, disconnect_size)
    overload = min(vsd_amp, 1.2 * nameplate_amp * ratio) if nameplate_amp else None

    # cable drop
    cable_drop = 0
    if depth:
        if cable_num == 2:
            cable_drop = 0.29 * motor_current * (0.0022 * fluid_temp + 0.85) * (depth / 1000)
        elif cable_num == 4:
            cable_drop = 0.45 * motor_current * (0.002 * fluid_temp + 0.85) * (depth / 1000)

    # ideal voltages
    if Base_freq is not None and total_motor_v is not None:
        base_v = total_motor_v * max_freq / Base_freq + cable_drop
        ideal_v = base_v
        min_v = base_v * 0.9
        max_v = base_v * 1.1
    else:
        ideal_v = min_v = max_v = None

    current_hp = motor_voltage * motor_current * sqrt(3) * (motor_eff/100) / 1000 / 1.34
    motor_hz    = sqrt(nameplate_amp/motor_current)*output_freq if motor_current else None
    vfd_hz      = sqrt(vsd_amp/vfd_current)*output_freq if vfd_current else None
    if motor_current and total_motor_v and Base_freq:
        transf_hz = (
        (vfd_current/motor_current) * (dc_bus_voltage/sqrt(2))
        - cable_drop
        ) / total_motor_v * Base_freq
    else:
        transf_hz = None

    transf_hz_err = transf_hz * 1.05 if transf_hz else None

    dc_bus_volts = "Over Capacity" if abs(dc_bus_voltage / sqrt(2) - ov) < 3 else (dc_bus_voltage / sqrt(2) / ov) * output_freq


    if pump_size and current_hp and Base_freq:
        factor = 200 if pump_size<=1750 else 410
        shaft_load = output_freq * sqrt(factor*output_freq/Base_freq/current_hp)
    else:
        shaft_load = None
    # transformer secondary range
    # only compute if we actually have no-load data, a valid ideal_v AND a non-zero dc_bus_voltage
    if not no_load_volts or ideal_v is None or dc_bus_voltage == 0:
        transformer_secondary_range = None

    elif all(min_v <= v <= max_v for v in no_load_volts):
        transformer_secondary_range = None

    else:
        ts_min = ideal_v * (480/(dc_bus_voltage/sqrt(2))) * 0.9
        ts_max = ideal_v * (480/(dc_bus_voltage/sqrt(2))) * 1.1
        transformer_secondary_range = f"{ts_min:.2f} - {ts_max:.2f}"


    frequency_results = {
        "Motor Hz": motor_hz,
        "VFD Hz": vfd_hz,
        "Transformer Hz": transf_hz,
        "Transformer Hz incl Error": transf_hz_err,
        "DC Bus Volts": dc_bus_volts,
        "Shaft Load": shaft_load,
        "Max Recommended Hz": min(filter(None, [motor_hz, vfd_hz, transf_hz, transf_hz_err])) if all((motor_hz, vfd_hz, transf_hz, transf_hz_err)) else None
    }
    results_df = pd.DataFrame(list(frequency_results.items()), columns=["Type of Frequency","Value"])

    summary_data = {
        "INSTALL TYPE":             extracted.get("Install Type"),
        "CUSTOMER":                 extracted.get("Customer"),
        "WELL #":                   extracted.get("WELL #"),
        "START DATE":               extracted.get("START DATE"),
        "VSD AMPERAGE RATING (A)":  vsd_amp_rating,
        "DISCONNECT SIZE (A)":      disconnect_size,
        "CASING SIZE/WT":           extracted.get("CASING SIZE/WT"),
        "POWER CABLE NUMBER":       cable_num,
        "Total Pump Stages":        extracted.get("Total Pump Stages"),
        "Cable Drop (V)":           f"{cable_drop:.2f}",
        "Transformation Ratio":     f"{ratio:.2f}",
        "Ideal Real-life Voltage (V)": (f"{ideal_v:.2f}" if ideal_v is not None else None),
        "Current HP":               f"{current_hp:.2f}" if current_hp else None,
        "Recomend Underload (A)":   f"{underload:.2f}",
        "Recomend Overload (A)":    f"{overload:.2f}" if overload else None,
        "No Load Voltage Average":  f"{sum(no_load_volts)/len(no_load_volts):.2f}" if no_load_volts else "N/A",
        "No Load RL Voltage Within Range": transformer_secondary_range is None,
        "TRANSFORMER SECONDARY RANGE": transformer_secondary_range or "N/A"
    }
    summary_df = pd.DataFrame(list(summary_data.items()), columns=["Parameter","Value"])

    log_message("Calculations complete")

    return results_df, summary_df



def safe_float(value, default=0.0):
    """
    Safely converts a value to a float. Handles None, strings, and numbers.
    Returns a default value if conversion is not possible.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        # Handle string cases
        s_value = str(value).strip()
        if s_value.lower() == 'none' or not s_value:
            return default
        return float(s_value)
    except (ValueError, TypeError):
        return default
# =============================
# Excel export
# =============================
def export_to_excel(
    output_file: str,
    results_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    pump_summary: pd.DataFrame,
    motor_summary: pd.DataFrame,
    df_live: pd.DataFrame,
    df_additional: pd.DataFrame
):
    log_message("Exporting to Excel")
    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        # Modbus Data sheet
        df_live.to_excel(writer, sheet_name="Modbus Data", index=False, startrow=0)
        df_additional.to_excel(writer, sheet_name="Modbus Data", index=False, startrow=len(df_live)+2)

        # Commission Check sheet
        sheet = "Commission Check"
        results_df.to_excel(writer, sheet_name=sheet, index=False, startrow=0)
        summary_df.to_excel(writer, sheet_name=sheet, index=False, startrow=len(results_df)+2)
        df_live.to_excel(writer, sheet_name=sheet, index=False, startrow=len(results_df)+len(summary_df)+4)
        pump_summary.to_excel(writer, sheet_name=sheet, index=False, startrow=len(results_df)+len(summary_df)+len(df_live)+6)
        motor_summary.to_excel(writer, sheet_name=sheet, index=False, startrow=len(results_df)+len(summary_df)+len(df_live)+len(pump_summary)+8)

    log_message(f"Excel file saved: {output_file}")

# =============================
# Streamlit UI
# =============================
# ────────────────────────────────────────────────────────────────
#  New helper utilities (put these near the top of the file)
# ────────────────────────────────────────────────────────────────
def clear_inputs():
    """Wipe ALL Modbus + manual fields and reset UI widgets."""
    for k in st.session_state.manual_vals:
        st.session_state.manual_vals[k] = ""
    st.session_state.add_vals       = {}
    st.session_state.before_vals    = {}
    st.session_state.df_live        = pd.DataFrame()
    st.session_state.df_additional  = pd.DataFrame()
    st.session_state.modbus_ip      = "input IP address from Inspatial"
    st.session_state.modbus_port    = 502
    st.session_state.last_poll_ts   = None
    log_message("Inputs cleared")

def decode_dh_status(raw: int | None) -> str:
    """Map DH_MOTOR_TEMP_UL_ACTION numeric code → human text."""
    return {0: "NONE", 1: "WARN", 2: "FAULT"}.get(raw, "—")


def render_inputs_modbus_tab():
    import pandas as pd
    from pymodbus.client import ModbusTcpClient
    from datetime import datetime

    if st.session_state.pop("clear_connection", False):
        st.session_state.modbus_ip   = "input IP address from Inspatial"
        st.session_state.modbus_port = 502

    st.header("Inputs & Modbus")

    # ── 0) Init imported‐drives storage
    if "imported_drives" not in st.session_state:
        st.session_state.imported_drives = []
        st.session_state.mapping_dfs = {}

    # ── 1) Drive selector + download/import templates
    drives = ["Triol", "SPOC"] + st.session_state.imported_drives
    option = st.selectbox("Select Drive Template", drives, key="drive_option")

    with st.expander("Drive Templates & Import", expanded=True):
        c1, c2, c3 = st.columns(3)

        # Download Triol
        with c1:
            triol_xlsx = make_template_bytes(
                TRIOL_REGISTERS, TRIOL_ADDITIONAL, "Triol",
                divide_map=TRIOL_DIVIDE, multiply_map=TRIOL_MULTIPLY
            )
            st.download_button(
                "Download Triol template",
                triol_xlsx,
                file_name="triol_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Download SPOC
        with c2:
            spoc_xlsx = make_template_bytes(
                registers, additional_registers, "SPOC"
            )
            st.download_button(
                "Download SPOC template",
                spoc_xlsx,
                file_name="spoc_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Download Blank
        with c3:
            blank_xlsx = make_template_bytes(
                registers, additional_registers, "YourDriveType"
            )
            st.download_button(
                "Download blank template",
                blank_xlsx,
                file_name="mapping_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.markdown(
            """
            **To import a new drive template:**  
            1. Download the blank template above.  
            2. Change **Drive Type** to your drive’s name.  
            3. Fill in **core** registers and **additional** registers as needed.  
            4. (Optionally) set **Scale Divide** / **Scale Multiply**.  
            5. Upload your completed `.xlsx` below.
            """
        )
        uploaded = st.file_uploader(
            "Upload mapping template (.xlsx)", type=["xlsx","xls"], key="mapping_file"
        )
        if uploaded:
            df_map = pd.read_excel(uploaded, sheet_name="Mappings")
            if "Drive Type" not in df_map.columns:
                st.error("Template missing a 'Drive Type' column.")
            else:
                for drv in df_map["Drive Type"].unique():
                    if drv not in st.session_state.imported_drives:
                        st.session_state.imported_drives.append(drv)
                        st.session_state.mapping_dfs[drv] = df_map[df_map["Drive Type"] == drv]

    # ── 2) Clear everything
    if st.button("🗑️ Clear All"):
        clear_inputs()
        # also clear drive‐specific state
        st.session_state.modbus_ip = "input IP address from Inspatial"
        st.session_state.modbus_port = 502
        st.session_state.last_poll_ts = None

    # ── 3) Modbus connection pane
    with st.expander("Modbus Connection", expanded=True):
        ip = st.text_input("IP Address", st.session_state.get("modbus_ip", ""), key="modbus_ip")
        port = st.number_input(
            "Port", min_value=1, max_value=65535,
            value=st.session_state.get("modbus_port", 502),
            key="modbus_port"
        )
        connect = st.button("🔌 Connect / Refresh")

        if connect and ip:
            try:
                # pick the right reader
                if option == "Triol":
                    add_vals, before_vals, df_live, df_add = read_triold_modbus_data(ip, port)
                elif option == "SPOC":
                    add_vals, before_vals, df_live, df_add = read_modbus_data(ip, port)
                else:
                    # generic: use the imported mapping
                    df_map = st.session_state.mapping_dfs[option]
                    # build core_regs & add_regs
                    core_regs = {
                        row["Parameter Name"]: (int(row["Register Address"]), int(row["Register Count"]))
                        for _, row in df_map[df_map.Category == "core"].iterrows()
                    }
                    add_regs = {
                        row["Parameter Name"]: (int(row["Register Address"]), int(row["Register Count"]))
                        for _, row in df_map[df_map.Category == "additional"].iterrows()
                    }
                    # read raw
                    client = ModbusTcpClient(ip, port=port)
                    if not client.connect():
                        raise ConnectionError("Could not connect")
                    raw_before = read_registers(core_regs, client)
                    raw_add    = read_registers(add_regs, client)
                    client.close()
                    # apply scale from df_map
                    for nm, raw in list(raw_before.items()):
                        cfg = df_map[df_map["Parameter Name"] == nm].iloc[0]
                        dv, mv = cfg["Scale Divide"], cfg["Scale Multiply"]
                        if pd.notna(dv): raw /= dv
                        if pd.notna(mv): raw *= mv
                        raw_before[nm] = raw
                    for nm, raw in list(raw_add.items()):
                        cfg = df_map[df_map["Parameter Name"] == nm].iloc[0]
                        dv, mv = cfg["Scale Divide"], cfg["Scale Multiply"]
                        if pd.notna(dv): raw /= dv
                        if pd.notna(mv): raw *= mv
                        raw_add[nm] = raw
                    # build dfs
                    df_live = pd.DataFrame([
                        {
                            "Parameter": suffix,
                            "Before": raw_before.get(field),
                            "After": "Same"
                        }
                        for suffix, field in [
                            ("Underload_(A)", "Set_Point_Value_Underload"),
                            ("Overload_(A)", "Set_Point_Value_Overload"),
                            ("Low_Frequency_(Hz)", "Set_Point_Value_Low_Frequency"),
                            ("High_Intake_Temp_(F)", "Set_Point_Value_High_Intake_Temp"),
                            ("High_Winding_Temp_(F)", "Set_Point_Value_High_Winding_Temp"),
                        ]
                    ])
                    df_add = pd.DataFrame({
                        "Parameter": list(raw_add.keys()),
                        "Value":     [raw_add[k] for k in raw_add]
                    })
                    add_vals, before_vals = raw_add, raw_before

                # stash everything
                st.session_state.add_vals      = add_vals
                st.session_state.before_vals   = before_vals
                st.session_state.df_live       = df_live
                st.session_state.df_additional = df_add
                st.session_state.last_poll_ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_message("Modbus data polled")
                st.session_state.clear_connection = True
                st.rerun()

            except Exception as e:
                st.error(f"Modbus error: {e}")
                log_message(f"Modbus error: {e}")

    # ── 4) Manual Inputs (auto‐populate from any drive)
    st.subheader("Manual Inputs")
    mapping = {
        "Output Freq (Hz)*":    "Output_Freq_Hz",
        "Motor Current (A)*":   "Motor_Current_A",
        "VFD Current (A)*":     "VFD_Current_A",
        "Fluid Temp (F)*":      "Fluid_Temp_F",
        "Motor Temp (F)*":      "Motor_Temp_F",
        "DC Bus Voltage (V)*":  "DC_Bus_Voltage_V",
        "Motor Voltage (V)*":   "Motor_Voltage_V",
        "Output Voltage (V)*":  "Output_Voltage_V",
        "Motor Efficiency (%)":"",  # no Modbus source
        "Max Frequency (Hz)":   "",
        "Base Frequency (Hz)": ""
    }

    for label in st.session_state.manual_vals:
        # auto-fill from Modbus if available
        if mapping.get(label) and mapping[label] in st.session_state.add_vals:
            default = str(st.session_state.add_vals[mapping[label]])
        else:
            default = st.session_state.manual_vals[label]

        # render input and immediately save it
        new_val = st.text_input(label, default, key=f"mv_{label}")
        st.session_state.manual_vals[label] = new_val


    

    # ── 5) Modbus Live Data + Additional Registers
    st.subheader("Modbus Live Data")
    st.dataframe(st.session_state.df_live, use_container_width=True)

    with st.expander("Additional Registers / TSV", expanded=False):
        st.dataframe(st.session_state.df_additional, use_container_width=True)
        tsv = io.StringIO()
        if not st.session_state.df_live.empty:
            st.session_state.df_live.to_csv(tsv, sep="\t", index=False)
        if not st.session_state.df_additional.empty:
            tsv.write("\n")
            st.session_state.df_additional.to_csv(tsv, sep="\t", index=False)
        st.text_area("Copyable TSV", value=tsv.getvalue(), height=300)

    # 6) Run Calculations (moved from Calculations & Export)
    if st.button("▶️ Run Calculations"):
        try:
            # perform calculations
            results_df, summary_df = perform_calculations(
                st.session_state.manual_vals,
                st.session_state.extracted,
                st.session_state.add_vals
            )
            # stash results
            st.session_state.results_df   = results_df
            st.session_state.summary_df   = summary_df
            
            # SET THE SUCCESS FLAG instead of changing the tab directly
            st.session_state.calculation_success = True
            
            write_log("Calculations completed")
            goto_calculations_tab()

        except Exception as e:
            write_log(f"Calculation error: {e}")
            st.error(f"Calculation error: {e}")
    


# 1) session-state defaults
if "extracted" not in st.session_state:
    st.session_state.extracted = {
        "Nameplate Amp (A)": "",
        "Total Motor Voltages (V)": "",
        "VSD AMPERAGE RATING (A)": "",
        "POWER CABLE NUMBER": "",
        "First Motor Set Depth (ft)": "",
        "Main Pump Size": "",
        "Total Pump Stages": "",
        "Customer": "",
        "WELL #": "",
        "START DATE": "",
        "Install Type": "",
        "CASING SIZE/WT": "",
        "DISCONNECT SIZE (A)": "",
        "TRANSFORMER SECONDARY (V)": "",
        "NO LOAD VOLTAGE": ""
        }

if "pump_summary" not in st.session_state:
    st.session_state.pump_summary = pd.DataFrame()
if "motor_summary" not in st.session_state:
    st.session_state.motor_summary = pd.DataFrame()
if "manual_vals" not in st.session_state:
    st.session_state.manual_vals = {
        "Output Freq (Hz)*": "",
        "Motor Current (A)*": "",
        "VFD Current (A)*": "",
        "Fluid Temp (F)*": "",
        "Motor Temp (F)*": "",
        "DC Bus Voltage (V)*": "",
        "Motor Voltage (V)*": "",
        "Output Voltage (V)*": "",
        "Motor Efficiency (%)": "",
        "Max Frequency (Hz)": "",
        "Base Frequency (Hz)": ""
    }
if "add_vals" not in st.session_state:
    st.session_state.add_vals = {}
if "before_vals" not in st.session_state:
    st.session_state.before_vals = {}
if "df_live" not in st.session_state:
    st.session_state.df_live = pd.DataFrame()
if "df_additional" not in st.session_state:
    st.session_state.df_additional = pd.DataFrame()
if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()
if "summary_df" not in st.session_state:
    st.session_state.summary_df = pd.DataFrame()
if "log" not in st.session_state:
    st.session_state.log = []

def write_log(msg: str):
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    st.session_state.log.append(f"{ts} {msg}")

write_log("UI initialized")

# 2) sidebar navigation with programmatic override support
if "next_tab" in st.session_state:
    default = st.session_state.next_tab
    del st.session_state.next_tab
else:
    default = st.session_state.get("nav_radio", NAV_OPTIONS[0])

idx = NAV_OPTIONS.index(default) if default in NAV_OPTIONS else 0
section = st.sidebar.radio(
    "Navigate",
    NAV_OPTIONS,
    index=idx,
    key="nav_radio"
)
st.sidebar.markdown(f"🔎 **Current:** {section}")

def goto_inputs_tab() -> None:
    """Schedule a jump to the Inputs & Modbus tab on next rerun."""
    st.session_state.next_tab = "Inputs & Modbus"
    st.rerun()

def goto_calculations_tab() -> None:
    """Switch to the Calculations & Export tab."""
    st.session_state.next_tab = "Calculations & Export"
    st.rerun()

# 3) PDF Extraction tab
if section == "PDF Extraction":
    st.header("PDF Extraction")

    # ── 1) File selector ─────────────────────────────────────
    pdf_file = st.file_uploader("Select Commissioning PDF", type="pdf", key="pdf_file")

    # ── 2) Extract & Clear buttons ──────────────────────────
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("🔍 Extract PDF"):
            if not pdf_file:
                st.warning("Please upload a PDF file first.")
            else:
                try:
                    # calls your exact enerflowv5 logic:
                    extracted, pump_df, motor_df = extract_pdf_data(pdf_file)
                    st.session_state.extracted     = extracted
                    st.session_state.pump_summary  = pump_df
                    st.session_state.motor_summary = motor_df
                    write_log("PDF extraction succeeded.")
                    st.success("Extraction succeeded.")
                except Exception as e:
                    write_log(f"PDF extraction error: {e}")
                    st.error(f"Extraction error: {e}")
    with col2:
        if st.button("🗑️ Clear PDF"):
            st.session_state.extracted      = {}
            st.session_state.pump_summary   = pd.DataFrame()
            st.session_state.motor_summary  = pd.DataFrame()
            write_log("Cleared PDF fields.")

    # ── 3) Show & edit fields ───────────────────────────────
    if st.session_state.extracted:
        EXTRACTED_KEYS = [
            "Nameplate Amp (A)",
            "Total Motor Voltages (V)",
            "VSD AMPERAGE RATING (A)",
            "POWER CABLE NUMBER",
            "First Motor Set Depth (ft)",
            "Main Pump Size",
            "Total Pump Stages",
            "Customer",
            "WELL #",
            "START DATE",
            "Install Type",
            "CASING SIZE/WT",
            "DISCONNECT SIZE (A)",
            "TRANSFORMER SECONDARY (V)",
            "NO LOAD VOLTAGE",
        ]
    # ── 3) Extracted / Manual Entry Fields ─────────────────────
        st.subheader("Extracted / Manual Entry Fields")

        for key in EXTRACTED_KEYS:
            current = st.session_state.extracted.get(key, "")
            if key == "NO LOAD VOLTAGE":
                new = st.text_area(key, value=str(current), height=80, key=f"ex_{key}")
            else:
                new = st.text_input(key, value=str(current), key=f"ex_{key}")
            # overwrite session_state so these values feed into your calculations
            st.session_state.extracted[key] = new
        # ── 4) Update button to persist manual edits & clear summaries ─────────
        if st.button("🔄 Update Fields"):
            # 1) Persist whatever’s in the inputs
            for key in EXTRACTED_KEYS:
                st.session_state.extracted[key] = st.session_state.get(f"ex_{key}", "")

            # 2) Wipe out the existing summaries so you can rebuild / overwrite them
            st.session_state.pump_summary = pd.DataFrame()
            st.session_state.motor_summary = pd.DataFrame()

            st.success("Manual fields saved; pump & motor summaries cleared.")

        # ── 4) Pump & Motor Summaries (only if data exists) ────────
        if not st.session_state.pump_summary.empty:
            st.subheader("Pump Summary")
            st.dataframe(st.session_state.pump_summary, use_container_width=True)
        if not st.session_state.motor_summary.empty:
            st.subheader("Motor Summary")
            st.dataframe(st.session_state.motor_summary, use_container_width=True)

        # ── 5) Next button ─────────────────────────────────────────
        if st.button("➡️ Next: Inputs & Modbus"):
            goto_inputs_tab()


# 4) Inputs & Modbus tab  ← add this block
elif section == "Inputs & Modbus":
    render_inputs_modbus_tab()


# 5) Calculations & Export tab
elif section == "Calculations & Export":
    st.header("Calculations & Export")

    if st.session_state.results_df.empty:
        st.info("No calculation results yet. Please run ▶️ Run Calculations in the Inputs & Modbus tab first.")
    else:
        # — cast Value → str to avoid ArrowTypeError
        df_freq = st.session_state.results_df.copy()
        df_freq["Value"] = df_freq["Value"].astype(str)
        st.subheader("Frequency Results")
        st.dataframe(df_freq)

        df_sum = st.session_state.summary_df.copy()
        df_sum["Value"] = df_sum["Value"].astype(str)
        st.subheader("Summary")
        st.dataframe(df_sum)

        # ────────────────────────────────────────────────────────
        # Configuration Summary TSV
        # ────────────────────────────────────────────────────────
        st.subheader("Configuration Summary (TSV)")

        # pull out the three fields from your summary_df
        def pick(param):
            row = df_sum[df_sum["Parameter"] == param]
            return row["Value"].iloc[0] if not row.empty else ""

        vsd    = pick("VSD AMPERAGE RATING (A)")
        casing = pick("CASING SIZE/WT")
        disc   = pick("DISCONNECT SIZE (A)")

        lines = []
        # header
        lines.append("VSD AMPERAGE RATING (A)\tCASING SIZE/WT\tDISCONNECT SIZE (A)")
        # values
        lines.append(f"{vsd}\t{casing}\t{disc}")

        # pump summary
        if not st.session_state.pump_summary.empty:
            lines.append("")  # blank line
            lines.append("=== Pump Summary ===")
            lines.extend(st.session_state.pump_summary.to_csv(sep="\t", index=False).splitlines())

        # motor summary
        if not st.session_state.motor_summary.empty:
            lines.append("")  # blank line
            lines.append("=== Motor Summary ===")
            lines.extend(st.session_state.motor_summary.to_csv(sep="\t", index=False).splitlines())

        st.text_area(
            "Copyable configuration TSV",
            value="\n".join(lines),
            height=300,
        )

        st.markdown("---")
        st.subheader("Export to Excel")

        # default filename based on WELL #
        well = st.session_state.extracted.get("WELL #", "well").replace(" ", "_")
        default_fname = f"{well}_commissioning_check.xlsx"

        output_path = st.text_input(
            "Output filename",
            default_fname,
            key="export_filename"      # unique key
        )
        if st.button("💾 Export"):
            try:
                export_to_excel(
                    output_path,
                    st.session_state.results_df,
                    st.session_state.summary_df,
                    st.session_state.pump_summary,
                    st.session_state.motor_summary,
                    st.session_state.df_live,
                    st.session_state.df_additional
                )
                write_log(f"Exported to {output_path}")
                st.success(f"Saved as {output_path}")
            except Exception as e:
                write_log(f"Export error: {e}")
                st.error(f"Export error: {e}")

# 6) Debug Log tab
elif section == "Debug Log":
    st.header("Debug Log")
    for line in st.session_state.log:
        st.text(line)




# cd "C:\\Users\\Thai.phi\\OneDrive - Endurance Lift Solutions\\Desktop\\modbus dashboard"
# streamlit run "commisioning check all drive.py"
