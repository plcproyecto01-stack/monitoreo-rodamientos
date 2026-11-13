# -*- coding: utf-8 -*-
"""Núcleo de cálculo del sistema de monitoreo Goulds 3642 (ESPE Latacunga).

Contiene: almacenamiento (local o Supabase), carga de la data sintética del ingeniero, variables
derivadas, NPSH a nivel del mar y en Latacunga, reglas de estado de falla, modelos MLP (estado y RUL),
diagnóstico con soluciones, análisis de rodamientos y de cavitación (réplica de las tablas Excel del
docente, con las fórmulas corregidas), selección del transmisor IR, mantenimiento y alertas Telegram.
"""
import html
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

BASE = Path(__file__).resolve().parent
DIR_PRUEBA = BASE / "datos_prueba"
DIR_CATALOGOS = BASE / "catalogos"
ARCH_DATOS = BASE / "datos_rodamientos.csv"
ARCH_EQUIPO = BASE / "datos_equipo.json"
ARCH_MODELO = BASE / "modelo_estimacion.json"
ARCH_CATALOGO = BASE / "catalogo_ir.json"
ARCH_ALERTAS = BASE / "alertas.json"
ARCH_MANT = BASE / "mantenimiento.json"
ARCH_HIST_ROD = BASE / "historial_rodamientos.json"

DOCENTE = "Ing. Wilson Sánchez Ocaña"
G = 9.80665
ORIGEN_BASE = "Goulds (ingeniero)"
ORIGEN_NUEVO = "Registro nuevo"

# -----------------------------------------------------------------------------
# Estados de falla (columna estado_falla de la data del ingeniero)
# -----------------------------------------------------------------------------
ESTADOS = ["NORMAL", "CAVITACION_INCIPIENTE", "CAVITACION_SEVERA", "DEGRADACION_RODAMIENTO",
           "RODAMIENTO_CRITICO", "FALLA_COMBINADA", "DETENIDA", "MANTENIMIENTO"]
NOMBRE_ESTADO = {"NORMAL": "Normal", "CAVITACION_INCIPIENTE": "Cavitación incipiente",
                 "CAVITACION_SEVERA": "Cavitación severa", "DEGRADACION_RODAMIENTO": "Degradación de rodamiento",
                 "RODAMIENTO_CRITICO": "Rodamiento crítico", "FALLA_COMBINADA": "Falla combinada",
                 "DETENIDA": "Detenida", "MANTENIMIENTO": "Mantenimiento"}
COLOR_ESTADO = {"NORMAL": "#2E9E5B", "CAVITACION_INCIPIENTE": "#F2B705", "CAVITACION_SEVERA": "#D64545",
                "DEGRADACION_RODAMIENTO": "#F28C28", "RODAMIENTO_CRITICO": "#B3261E", "FALLA_COMBINADA": "#6A1B9A",
                "DETENIDA": "#8A9BB8", "MANTENIMIENTO": "#1F6FEB"}
NIVEL_ESTADO = {"NORMAL": 0, "DETENIDA": 0, "MANTENIMIENTO": 0, "CAVITACION_INCIPIENTE": 1,
                "DEGRADACION_RODAMIENTO": 1, "CAVITACION_SEVERA": 2, "RODAMIENTO_CRITICO": 2, "FALLA_COMBINADA": 2}
COLOR_ZONA = {0: "#2E9E5B", 1: "#F2B705", 2: "#D64545"}
TEXTO_ZONA = {0: "Normal", 1: "Alerta", 2: "Crítico"}

# Reglas reconstruidas por el docente (árbol de decisión, concordancia 100 %)
REGLAS = {"margen_severa": 0.107, "margen_incipiente": 0.82, "hi_degradacion": 0.672, "hi_critico": 0.385}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------
MEDIDAS = ["estado_bomba", "horas_trabajo_acum_h", "nivel_tanque_mm", "caudal_L_h", "presion_succion_PSI",
           "presion_descarga_PSI", "vibracion_succion_mm_s", "vibracion_descarga_mm_s", "temperatura_motor_C",
           "V_L1L2_V", "V_L2L3_V", "V_L3L1_V", "I_L1_A", "I_L2_A", "I_L3_A", "potencia_activa_kW",
           "potencia_reactiva_kVAr"]
COLS = ["ID", "timestamp", "Origen", "Operador", "Observaciones"] + MEDIDAS
TEXTO = ["timestamp", "Origen", "Operador", "Observaciones"]

ETIQUETAS = {
    "estado_bomba": "Estado de la bomba (1 operando, 0 detenida)", "horas_trabajo_acum_h": "Horas de trabajo acumuladas (h)",
    "nivel_tanque_mm": "Nivel del tanque (mm)", "caudal_L_h": "Caudal (L/h)", "caudal_GPM": "Caudal (GPM)",
    "presion_succion_PSI": "Presión de succión (psi)", "presion_descarga_PSI": "Presión de descarga (psi)",
    "head_total_m": "Altura total (m)", "NPSHa_m": "NPSH disponible (m)", "NPSHr_m": "NPSH requerido (m)",
    "margen_NPSH_m": "Margen NPSH (m)", "margen_mar_m": "Margen NPSH a nivel del mar (m)",
    "margen_lat_m": "Margen NPSH en Latacunga (m)", "vibracion_succion_mm_s": "Vibración en succión (mm/s RMS)",
    "vibracion_descarga_mm_s": "Vibración en descarga (mm/s RMS)", "temperatura_motor_C": "Temperatura IR del escudo (°C)",
    "T_F": "Temperatura IR del escudo (°F)", "V_L1L2_V": "Voltaje L1-L2 (V)", "V_L2L3_V": "Voltaje L2-L3 (V)",
    "V_L3L1_V": "Voltaje L3-L1 (V)", "I_L1_A": "Corriente L1 (A)", "I_L2_A": "Corriente L2 (A)", "I_L3_A": "Corriente L3 (A)",
    "potencia_activa_kW": "Potencia activa (kW)", "potencia_reactiva_kVAr": "Potencia reactiva (kVAr)",
    "potencia_aparente_kVA": "Potencia aparente (kVA)", "factor_potencia": "Factor de potencia",
    "I_prom_A": "Corriente promedio (A)", "carga_pct": "Carga del motor (% de I nominal)",
    "desb_corriente_pct": "Desbalance de corriente (%)", "desb_tension_pct": "Desbalance de tensión (%)",
    "Vib_max": "Vibración máxima (mm/s)", "health_index_rodamiento": "Índice de salud del rodamiento (0–1)",
    "RUL_h": "Vida remanente del rodamiento (h)", "eta_global_pct": "Eficiencia global (%)", "E_H_pct": "Error de altura vs curva (%)",
}
# Entradas del MLP (mismas 19 variables medibles del cuaderno Colab del docente)
FEATURES = ["caudal_GPM", "presion_succion_PSI", "presion_descarga_PSI", "head_total_m", "nivel_tanque_mm",
            "vibracion_succion_mm_s", "vibracion_descarga_mm_s", "temperatura_motor_C",
            "I_L1_A", "I_L2_A", "I_L3_A", "potencia_activa_kW", "potencia_reactiva_kVAr", "factor_potencia",
            "V_L1L2_V", "V_L2L3_V", "V_L3L1_V", "desb_corriente_pct", "desb_tension_pct"]
CANDIDATAS = ["caudal_GPM", "presion_succion_PSI", "presion_descarga_PSI", "head_total_m", "nivel_tanque_mm",
              "vibracion_succion_mm_s", "vibracion_descarga_mm_s", "Vib_max", "I_prom_A", "carga_pct",
              "potencia_activa_kW", "potencia_reactiva_kVAr", "factor_potencia", "desb_corriente_pct",
              "desb_tension_pct", "horas_trabajo_acum_h", "margen_NPSH_m", "eta_global_pct"]
DEPENDE = {
    "caudal_GPM": ["caudal_L_h"], "head_total_m": ["presion_succion_PSI", "presion_descarga_PSI"],
    "Vib_max": ["vibracion_succion_mm_s", "vibracion_descarga_mm_s"], "I_prom_A": ["I_L1_A", "I_L2_A", "I_L3_A"],
    "carga_pct": ["I_L1_A", "I_L2_A", "I_L3_A"], "factor_potencia": ["potencia_activa_kW", "potencia_reactiva_kVAr"],
    "desb_corriente_pct": ["I_L1_A", "I_L2_A", "I_L3_A"], "desb_tension_pct": ["V_L1L2_V", "V_L2L3_V", "V_L3L1_V"],
    "margen_NPSH_m": ["presion_succion_PSI", "caudal_L_h"],
    "eta_global_pct": ["caudal_L_h", "presion_succion_PSI", "presion_descarga_PSI", "potencia_activa_kW"],
}

# Curva Goulds 3642, 1¼ × 1½ – 5, impulsor 3 5/8", 3500 rpm (hoja Curva_Fabricante_Aprox)
CURVA = pd.DataFrame({
    "Q_gpm": [0, 10, 20, 30, 40, 50, 60, 70, 80],
    "H_m": [15.6972, 15.60576, 15.3924, 14.9352, 14.1732, 13.2588, 12.192, 10.9728, 9.6012],
    "Eficiencia_pct": [0, 28, 45, 55, 60, 63, 62, 58, 50],
    "NPSHr_m": [1.9812, 2.07264, 2.19456, 2.4384, 2.7432, 3.2004, 3.9624, 5.1816, 6.858],
})
COEF_HQ = (-0.000963, -0.000294, 15.7312)

# Base de rodamientos de la tabla del docente (solo estos cinco)
BD_RODAMIENTOS = {
    "6202": {"n": 8, "d": 5.95, "D": 23.5, "alfa": 0.0},
    "6203": {"n": 8, "d": 6.75, "D": 28.5, "alfa": 0.0},
    "6206": {"n": 9, "d": 9.525, "D": 46.0, "alfa": 0.0},
    "6207": {"n": 9, "d": 11.112, "D": 53.5, "alfa": 0.0},
    "6208": {"n": 9, "d": 11.906, "D": 60.0, "alfa": 0.0},
}

DEF_EQUIPO = {
    "version": 5, "operadores": [], "asignatura": "", "nrc": "", "periodo": "",
    "proyecto": "Selección de un transmisor de temperatura infrarrojo y modelo de estimación para el monitoreo "
                "predictivo de rodamientos",
    "motor_marca": "Emerson Motor Company", "motor_modelo": "P55CST-1247", "motor_hp": 0.75, "motor_v": 230.0,
    "motor_i": 3.0, "motor_i_sf": 3.4, "motor_rpm": 3450.0, "motor_polos": 2, "motor_f": 60.0,
    "motor_aislamiento": "B (130 °C)", "motor_ip": "IP22 (ODP)", "motor_prot_term": "Ninguna",
    "bomba_marca": "Goulds Pumps (ITT)", "bomba_modelo": "3642", "bomba_index": "2BF10734",
    "bomba_tamano": "1 1/4 x 1 1/2 - 5", "bomba_impulsor": "3 5/8 in", "bomba_serie": "K0457068", "bomba_alabes": 8,
    "rod_DE": "6203", "rod_NDE": "6202", "d_succion_mm": 40.9, "t_agua_C": 20.0,
    "ubicacion": "Latacunga", "altitud_m": 2750.0, "p_baro_kpa": None,
    # Límites (el docente indica que las alarmas de rodamiento suelen estar entre 75 y 90 °C)
    "alarma_C": 75.0, "disparo_C": 90.0, "iso_A": 0.71, "iso_B": 1.8, "iso_C": 4.5, "rul_aviso_h": 200.0,
    # Requisitos del transmisor IR (criterios del informe técnico del docente)
    "ir_rango_min_C": 0.0, "ir_rango_max_C": 150.0, "ir_ds_min": 15.0, "ir_cabezal_min_C": 85.0,
    "ir_resp_max_ms": 150.0, "ir_salida": "4–20 mA", "ir_alimentacion_V": 24.0, "ir_ip_min": 65,
    "ir_d_objetivo_mm": 30.0, "ir_distancia_mm": 120.0, "ir_exactitud_C": 2.0,
}


# =============================================================================
# Almacenamiento: archivos locales o Supabase
# =============================================================================
def secreto(clave: str, defecto=None):
    try:
        return st.secrets[clave]
    except Exception:
        return defecto


SUPA_URL = str(secreto("supabase_url", "") or "").rstrip("/")
SUPA_KEY = str(secreto("supabase_key", "") or "")
NUBE = bool(SUPA_URL and SUPA_KEY)


def _cabeceras(extra=None) -> dict:
    h = {"apikey": SUPA_KEY, "Content-Type": "application/json"}
    if not SUPA_KEY.startswith("sb_"):
        h["Authorization"] = f"Bearer {SUPA_KEY}"
    return {**h, **(extra or {})}


def _supa(metodo: str, ruta: str, **kw):
    r = requests.request(metodo, f"{SUPA_URL}/rest/v1/{ruta}", headers=_cabeceras(kw.pop("headers", None)),
                         timeout=30, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
    return r


def limpio(v):
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v


@st.cache_data(ttl=45, show_spinner=False)
def _leer_config_nube(clave: str):
    filas = _supa("GET", f"config?clave=eq.{clave}&select=valor").json()
    return filas[0]["valor"] if filas else None


def cargar_json(ruta: Path, defecto):
    datos = None
    if NUBE:
        datos = _leer_config_nube(ruta.stem)
    elif ruta.exists():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            datos = None
    if datos is None:
        return json.loads(json.dumps(defecto)) if defecto is not None else None
    if isinstance(defecto, dict) and isinstance(datos, dict):
        return {**defecto, **datos}
    return datos


def guardar_json(ruta: Path, datos) -> None:
    datos = json.loads(json.dumps(datos, ensure_ascii=False, default=lambda o: limpio(o) if limpio(o) is not o else str(o)))
    if NUBE:
        _supa("POST", "config", json=[{"clave": ruta.stem, "valor": datos}],
              headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        st.cache_data.clear()
    else:
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[COLS].copy()
    for c in MEDIDAS + ["ID"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in TEXTO:
        df[c] = df[c].fillna("").astype(str).replace({"nan": "", "None": "", "NaT": ""})
    df["Origen"] = ORIGEN_NUEVO
    return df


def _fila_json(fila: dict) -> dict:
    return {c: limpio(fila.get(c)) for c in COLS if c != "ID"}


@st.cache_data(ttl=45, show_spinner="Cargando registros...")
def _leer_registros_nube() -> list:
    filas, inicio = [], 0
    while True:
        lote = _supa("GET", "registros?select=id,datos&order=id.asc",
                     headers={"Range-Unit": "items", "Range": f"{inicio}-{inicio + 999}"}).json()
        filas.extend(lote)
        if len(lote) < 1000:
            return filas
        inicio += 1000


def cargar_registros() -> pd.DataFrame:
    """Registros nuevos (medidos o ingresados después de la data del ingeniero)."""
    if NUBE:
        filas = _leer_registros_nube()
        df = pd.DataFrame([{**f["datos"], "ID": f["id"]} for f in filas]) if filas else pd.DataFrame(columns=COLS)
    elif ARCH_DATOS.exists():
        df = pd.read_csv(ARCH_DATOS, low_memory=False)
    else:
        df = pd.DataFrame(columns=COLS)
    # descarta registros de versiones anteriores que no tienen las variables de la data del ingeniero
    if len(df) and not set(MEDIDAS) & set(df.columns):
        df = pd.DataFrame(columns=COLS)
    df = normalizar(df)
    df = df[df[MEDIDAS].notna().any(axis=1)].reset_index(drop=True)
    st.session_state["_huella"] = {int(r["ID"]): json.dumps(_fila_json(r), sort_keys=True, default=str)
                                   for r in df.to_dict("records") if not pd.isna(r["ID"])}
    return df


def guardar_registros(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar(df.reset_index(drop=True))
    faltan = df["ID"].isna()
    if faltan.any():
        maximo = int(df["ID"].max()) if df["ID"].notna().any() else 0
        if NUBE:
            r = _supa("GET", "registros?select=id&order=id.desc&limit=1").json()
            maximo = max(maximo, r[0]["id"] if r else 0)
        df.loc[faltan, "ID"] = np.arange(maximo + 1, maximo + 1 + int(faltan.sum()))
    vacias = df["timestamp"].str.strip() == ""
    df.loc[vacias, "timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if NUBE:
        huella = st.session_state.get("_huella", {})
        cambiadas, actuales = [], set()
        for r in df.to_dict("records"):
            i = int(r["ID"])
            actuales.add(i)
            datos = _fila_json(r)
            if huella.get(i) != json.dumps(datos, sort_keys=True, default=str):
                cambiadas.append({"id": i, "datos": datos})
        for k in range(0, len(cambiadas), 500):
            _supa("POST", "registros", json=cambiadas[k:k + 500], headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        borradas = sorted(set(huella) - actuales)
        for k in range(0, len(borradas), 150):
            _supa("DELETE", f"registros?id=in.({','.join(map(str, borradas[k:k + 150]))})")
        st.cache_data.clear()
    else:
        df.to_csv(ARCH_DATOS, index=False)
    return df


# =============================================================================
# Data del ingeniero
# =============================================================================
def archivo_base() -> Path | None:
    arch = sorted(DIR_PRUEBA.glob("Data_Sintetica*.xlsx")) if DIR_PRUEBA.exists() else []
    return arch[0] if arch else None


@st.cache_data(show_spinner="Cargando la data Goulds 3642 del ingeniero...")
def cargar_base() -> pd.DataFrame:
    ruta = archivo_base()
    if ruta is None:
        return pd.DataFrame()
    d = pd.read_excel(ruta, sheet_name="Data_Sintetica")
    d = d.drop(columns=[c for c in ("Deteccion de Anomalia", "Diagnostico de Falla", "Severidad", "RUL") if c in d.columns])
    d["timestamp"] = pd.to_datetime(d["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    d["ID"] = np.arange(1, len(d) + 1)
    d["Origen"] = ORIGEN_BASE
    d["Operador"] = ""
    d["Observaciones"] = d["evento_mantenimiento"].fillna("").astype(str)
    return d


# =============================================================================
# Cálculos físicos y variables derivadas
# =============================================================================
def f_a_c(f):
    return (f - 32) / 1.8


def c_a_f(c):
    return c * 1.8 + 32


def p_atm_kpa(eq: dict) -> float:
    if eq.get("p_baro_kpa"):
        return float(eq["p_baro_kpa"])
    return 101.325 * (1 - 2.25577e-5 * float(eq.get("altitud_m") or 0)) ** 5.25588


def p_vapor_kpa(t_c):
    return 0.61094 * np.exp(17.625 * t_c / (t_c + 243.04))


def densidad_agua(t_c):
    return 1000 * (1 - (t_c + 288.9414) / (508929.2 * (t_c + 68.12963)) * (t_c - 3.9863) ** 2)


def h_ref(q_gpm):
    a, b, c = COEF_HQ
    return a * q_gpm ** 2 + b * q_gpm + c


def npsha(p_succ_psi, caudal_L_h, patm_kpa, eq):
    t = float(eq.get("t_agua_C") or 20.0)
    rho = densidad_agua(t)
    q = caudal_L_h / 1000 / 3600
    area = math.pi * (float(eq["d_succion_mm"]) / 1000) ** 2 / 4
    v = q / area
    return (patm_kpa + p_succ_psi * 6.89476 - p_vapor_kpa(t)) * 1000 / (rho * G) + v ** 2 / (2 * G)


def zona_iso(v, eq):
    return np.where(pd.isna(v), np.nan, np.select([v <= eq["iso_B"], v <= eq["iso_C"]], [0, 1], 2))


def derivar(df: pd.DataFrame, eq: dict) -> pd.DataFrame:
    """Completa variables calculadas. Respeta las columnas que ya trae la data del ingeniero."""
    d = df.copy()
    for c in ("caudal_GPM", "head_total_m", "NPSHa_m", "NPSHr_m", "margen_NPSH_m", "potencia_aparente_kVA",
              "factor_potencia", "health_index_rodamiento", "RUL_rodamiento_h", "estado_falla", "evento_mantenimiento"):
        if c not in d.columns:
            d[c] = np.nan
    d["caudal_GPM"] = pd.to_numeric(d["caudal_GPM"], errors="coerce").fillna(d["caudal_L_h"] / 227.1247)
    d["head_total_m"] = pd.to_numeric(d["head_total_m"], errors="coerce").fillna(
        (d["presion_descarga_PSI"] - d["presion_succion_PSI"]) * 0.70307)
    opera = d["estado_bomba"] == 1
    # NPSH: nivel del mar (como la data del ingeniero) y Latacunga (presión local)
    d["NPSHr_calc"] = np.interp(d["caudal_GPM"].fillna(0), CURVA["Q_gpm"], CURVA["NPSHr_m"])
    mar = npsha(d["presion_succion_PSI"], d["caudal_L_h"], 101.325, eq)
    lat = npsha(d["presion_succion_PSI"], d["caudal_L_h"], p_atm_kpa(eq), eq)
    d["margen_mar_m"] = (mar - d["NPSHr_calc"]).where(opera)
    d["margen_lat_m"] = (lat - d["NPSHr_calc"]).where(opera)
    d["NPSHa_lat_m"] = lat.where(opera)
    nuevo = d["Origen"] == ORIGEN_NUEVO
    # Registros nuevos: medidos en el banco real (Latacunga) → NPSH con presión local
    d.loc[nuevo, "NPSHa_m"] = lat[nuevo].where(opera[nuevo])
    d.loc[nuevo, "NPSHr_m"] = d.loc[nuevo, "NPSHr_calc"].where(opera[nuevo])
    d.loc[nuevo, "margen_NPSH_m"] = d.loc[nuevo, "margen_lat_m"]
    # Eléctricas
    s = np.sqrt(d["potencia_activa_kW"] ** 2 + d["potencia_reactiva_kVAr"] ** 2)
    d["potencia_aparente_kVA"] = pd.to_numeric(d["potencia_aparente_kVA"], errors="coerce").fillna(s)
    d["factor_potencia"] = pd.to_numeric(d["factor_potencia"], errors="coerce").fillna(d["potencia_activa_kW"] / s.replace(0, np.nan))
    I = d[["I_L1_A", "I_L2_A", "I_L3_A"]]
    V = d[["V_L1L2_V", "V_L2L3_V", "V_L3L1_V"]]
    d["I_prom_A"] = I.mean(axis=1)
    d["desb_corriente_pct"] = ((I.max(axis=1) - I.mean(axis=1)) / I.mean(axis=1).replace(0, np.nan) * 100).fillna(0)
    d["desb_tension_pct"] = ((V.max(axis=1) - V.mean(axis=1)) / V.mean(axis=1).replace(0, np.nan) * 100)
    d["carga_pct"] = d["I_prom_A"] / float(eq["motor_i"]) * 100
    d["Vib_max"] = d[["vibracion_succion_mm_s", "vibracion_descarga_mm_s"]].max(axis=1)
    d["T_F"] = c_a_f(d["temperatura_motor_C"])
    q_m3s = d["caudal_L_h"] / 1000 / 3600
    d["eta_global_pct"] = (densidad_agua(20.0) * G * q_m3s * d["head_total_m"] / (d["potencia_activa_kW"] * 1000) * 100).where(opera)
    d["E_H_pct"] = ((d["head_total_m"] - h_ref(d["caudal_GPM"])) / h_ref(d["caudal_GPM"]) * 100).where(opera)
    # Zonas
    t = d["temperatura_motor_C"]
    d["zona_T"] = np.where(t.isna() | ~opera, np.nan, np.select([t < eq["alarma_C"], t < eq["disparo_C"]], [0, 1], 2))
    d["zona_vib"] = np.where(opera, zona_iso(d["Vib_max"], eq), np.nan)
    i = d["I_prom_A"]
    d["zona_carga"] = np.where(i.isna() | ~opera, np.nan, np.select([i <= eq["motor_i"], i <= eq["motor_i_sf"]], [0, 1], 2))
    return d


def estado_por_reglas(margen, hi, operando) -> str:
    """Reglas del docente: margen NPSH + índice de salud."""
    if not operando:
        return "DETENIDA"
    if margen is not None and not pd.isna(margen) and margen <= REGLAS["margen_severa"]:
        return "FALLA_COMBINADA" if (hi is not None and not pd.isna(hi) and hi <= REGLAS["hi_degradacion"]) else "CAVITACION_SEVERA"
    if hi is not None and not pd.isna(hi) and hi <= REGLAS["hi_critico"]:
        return "RODAMIENTO_CRITICO"
    if margen is not None and not pd.isna(margen) and margen <= REGLAS["margen_incipiente"]:
        return "CAVITACION_INCIPIENTE"
    if hi is not None and not pd.isna(hi) and hi <= REGLAS["hi_degradacion"]:
        return "DEGRADACION_RODAMIENTO"
    return "NORMAL"


# =============================================================================
# Modelos MLP (estado de falla y RUL) — misma metodología del cuaderno Colab del docente
# =============================================================================
RUL_TOPE_H = 800
BLOQUE_H = 24


@st.cache_resource(show_spinner="Entrenando la red neuronal MLP con la data del ingeniero...")
def entrenar_modelos(_base: pd.DataFrame, eq_hash: str):
    from sklearn.metrics import classification_report, confusion_matrix, f1_score, mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    from sklearn.preprocessing import StandardScaler

    op = _base[_base["estado_bomba"] == 1].copy().reset_index(drop=True)
    op["ciclo"] = _base["evento_mantenimiento"].notna().cumsum()[_base["estado_bomba"] == 1].values
    racha = (op["estado_falla"] != op["estado_falla"].shift()).cumsum()
    grupo = racha.astype(str) + "_" + (op.groupby(racha).cumcount() // BLOQUE_H).astype(str)
    n_cls = op["estado_falla"].nunique()
    tr = va = te = None
    for s in range(42, 642):
        partes = [t for _, t in StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=s).split(op, op["estado_falla"], groups=grupo)]
        te_, va_ = partes[0], partes[1]
        tr_ = np.setdiff1d(np.arange(len(op)), np.r_[te_, va_])
        tr, va, te = tr_, va_, te_
        if all(op["estado_falla"].iloc[i].nunique() == n_cls for i in (tr_, va_, te_)):
            break
    entren = np.r_[tr, va]
    X = op[FEATURES].astype(float).values
    sc = StandardScaler().fit(X[entren])
    Xs = sc.transform(X)
    y = op["estado_falla"].values
    # sobremuestreo de clases pequeñas (equivale al class_weight del cuaderno)
    rng = np.random.default_rng(42)
    idx = list(entren)
    for c in np.unique(y[entren]):
        cls_idx = entren[y[entren] == c]
        if len(cls_idx) < 200:
            idx += list(rng.choice(cls_idx, 200 - len(cls_idx), replace=True))
    idx = np.array(idx)
    clf = MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=600, early_stopping=True,
                        validation_fraction=0.15, n_iter_no_change=25, random_state=42).fit(Xs[idx], y[idx])
    pred = clf.predict(Xs[te])
    clases = list(clf.classes_)
    rep = classification_report(y[te], pred, labels=clases, output_dict=True, zero_division=0)
    cm = confusion_matrix(y[te], pred, labels=clases)
    presentes = [c for c in clases if (y[te] == c).any()]
    f1 = f1_score(y[te], pred, average="macro", labels=presentes, zero_division=0)
    y_rul = np.minimum(op["RUL_rodamiento_h"].values, RUL_TOPE_H).astype(float)
    reg = MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=800, early_stopping=True,
                       n_iter_no_change=25, random_state=42).fit(Xs[entren], y_rul[entren] / RUL_TOPE_H)
    p_rul = np.clip(reg.predict(Xs[te]), 0, 1) * RUL_TOPE_H
    ciclo0 = np.where(op["ciclo"].values == 0)[0]
    curva_rul = pd.DataFrame({"horas": op["horas_trabajo_acum_h"].values[ciclo0], "RUL real": y_rul[ciclo0],
                              "RUL MLP": np.clip(reg.predict(Xs[ciclo0]), 0, 1) * RUL_TOPE_H})
    return {"scaler": sc, "clf": clf, "reg": reg, "clases": clases, "reporte": rep, "matriz": cm, "f1": f1,
            "mae": mean_absolute_error(y_rul[te], p_rul), "rmse": mean_squared_error(y_rul[te], p_rul) ** 0.5,
            "r2": r2_score(y_rul[te], p_rul), "n_train": len(entren), "n_test": len(te), "curva_rul": curva_rul}


def predecir(modelos: dict, d: pd.DataFrame) -> pd.DataFrame:
    """Estado (MLP + regla de margen NPSH) y RUL para registros nuevos en operación."""
    out = pd.DataFrame(index=d.index, data={"estado_ia": "", "prob_ia": np.nan, "RUL_ia_h": np.nan})
    ok = (d["estado_bomba"] == 1) & d[FEATURES].notna().all(axis=1)
    if ok.any():
        Xs = modelos["scaler"].transform(d.loc[ok, FEATURES].astype(float).values)
        prob = modelos["clf"].predict_proba(Xs)
        out.loc[ok, "estado_ia"] = np.array(modelos["clases"])[prob.argmax(1)]
        out.loc[ok, "prob_ia"] = prob.max(1)
        out.loc[ok, "RUL_ia_h"] = np.clip(modelos["reg"].predict(Xs), 0, 1) * RUL_TOPE_H
    return out


def completar_estado(d: pd.DataFrame, modelos: dict | None) -> pd.DataFrame:
    """estado: etiqueta del docente (data base) o IA + regla NPSH (registros nuevos)."""
    d = d.copy()
    d["estado"] = d["estado_falla"].astype(object)
    d["fuente_estado"] = np.where(d["estado"].notna(), "Etiqueta de la data del ingeniero", "")
    d["RUL_h"] = pd.to_numeric(d["RUL_rodamiento_h"], errors="coerce")
    nuevo = d["Origen"] == ORIGEN_NUEVO
    if nuevo.any():
        p = predecir(modelos, d[nuevo]) if modelos else pd.DataFrame(index=d[nuevo].index, data={"estado_ia": "", "prob_ia": np.nan, "RUL_ia_h": np.nan})
        for i in d.index[nuevo]:
            fila = d.loc[i]
            if fila["estado_bomba"] != 1:
                est, fuente = "DETENIDA", "Bomba detenida"
            else:
                est = p.at[i, "estado_ia"] or "NORMAL"
                fuente = f"Red MLP ({p.at[i, 'prob_ia'] * 100:.0f} % de confianza)" if p.at[i, "estado_ia"] else "Datos incompletos para la IA"
                m = fila["margen_NPSH_m"]
                if not pd.isna(m) and m <= REGLAS["margen_incipiente"]:
                    rod = est in ("DEGRADACION_RODAMIENTO", "RODAMIENTO_CRITICO", "FALLA_COMBINADA")
                    if m <= REGLAS["margen_severa"]:
                        est = "FALLA_COMBINADA" if rod else "CAVITACION_SEVERA"
                    elif not rod:
                        est = "CAVITACION_INCIPIENTE"
                    fuente += " + regla de margen NPSH en Latacunga"
            d.at[i, "estado"], d.at[i, "fuente_estado"] = est, fuente
            d.at[i, "RUL_h"] = p.at[i, "RUL_ia_h"]
    d["estado"] = d["estado"].fillna("NORMAL")
    d["nivel"] = d["estado"].map(NIVEL_ESTADO).fillna(0)
    d["estado_txt"] = d["estado"].map(NOMBRE_ESTADO).fillna(d["estado"])
    return d


# =============================================================================
# Diagnóstico con soluciones
# =============================================================================
SOLUCIONES = {
    "CAVITACION_INCIPIENTE": {
        "causas": ["Margen NPSH reducido: nivel bajo en el tanque de succión", "Colador o filtro de succión parcialmente obstruido",
                   "Válvula de succión parcialmente cerrada", "Caudal alto (el NPSHr crece con el caudal)"],
        "acciones": ["Verificar y recuperar el nivel del tanque de succión", "Limpiar el colador de succión",
                     "Abrir completamente la válvula de succión (no regular con ella)",
                     "Reducir el caudal cerrando parcialmente la descarga", "Confirmar con la sección «Cavitación» (BPF)"]},
    "CAVITACION_SEVERA": {
        "causas": ["NPSH disponible menor o igual al requerido", "Restricción fuerte en la succión o tanque casi vacío",
                   "Entrada de aire o vórtice en la succión"],
        "acciones": ["Detener la bomba si se escucha ruido de grava (implosión de burbujas)", "Restablecer el nivel del tanque",
                     "Desobstruir la succión y revisar fugas de aire", "Inspeccionar el impulsor por erosión antes de volver a operar"]},
    "DEGRADACION_RODAMIENTO": {
        "causas": ["Desgaste progresivo del rodamiento", "Lubricación deficiente o grasa degradada (rodamiento sellado al final de su vida)",
                   "Contaminación, desalineación o carga axial elevada del impulsor"],
        "acciones": ["Aumentar la frecuencia de monitoreo de temperatura y vibración",
                     "Medir el espectro y comparar con BPFO/BPFI en la sección «Rodamientos»",
                     "Programar el cambio de rodamiento dentro del RUL estimado y preparar el repuesto",
                     "Verificar alineación y pernos de anclaje"]},
    "RODAMIENTO_CRITICO": {
        "causas": ["Rodamiento en etapa final de falla (índice de salud muy bajo)", "Daño avanzado en pistas o elementos rodantes"],
        "acciones": ["Programar el cambio de rodamiento de inmediato (6203 lado bomba / 6202 lado ventilador)",
                     "Reducir carga o tiempo de operación hasta la intervención",
                     "Detener si la temperatura supera el disparo o aparece ruido metálico"]},
    "FALLA_COMBINADA": {
        "causas": ["Cavitación y rodamiento degradado al mismo tiempo", "La cavitación aumenta la vibración y acelera el daño del rodamiento"],
        "acciones": ["Detener la bomba", "Corregir primero la condición de succión (nivel, colador, válvula)",
                     "Cambiar el rodamiento antes de volver a operar", "Inspeccionar impulsor y sello mecánico"]},
    "DETENIDA": {"causas": ["Parada programada u operativa"], "acciones": ["Sin acción; verificar que la parada sea esperada"]},
    "MANTENIMIENTO": {"causas": ["Intervención programada (cambio de rodamiento)"], "acciones": ["Registrar el mantenimiento y reiniciar el horómetro del rodamiento"]},
}


def diagnosticar(f: dict, eq: dict) -> list[dict]:
    def num(c):
        try:
            v = float(f.get(c))
            return None if math.isnan(v) else v
        except (TypeError, ValueError):
            return None
    out = []
    est = f.get("estado", "NORMAL")
    if est in SOLUCIONES and NIVEL_ESTADO.get(est, 0) > 0:
        ev = [f"Fuente: {f.get('fuente_estado', '')}"]
        if num("margen_NPSH_m") is not None:
            ev.append(f"margen NPSH {num('margen_NPSH_m'):.2f} m")
        if num("health_index_rodamiento") is not None:
            ev.append(f"índice de salud {num('health_index_rodamiento'):.2f}")
        out.append({"Falla": NOMBRE_ESTADO[est], "Gravedad": NIVEL_ESTADO[est], "Evidencia": "; ".join(ev), **{k.capitalize(): v for k, v in SOLUCIONES[est].items()}})
    if f.get("estado_bomba") != 1:
        return out
    t = num("temperatura_motor_C")
    if t is not None and t >= eq["alarma_C"]:
        crit = t >= eq["disparo_C"]
        out.append({"Falla": "Temperatura del escudo sobre el límite", "Gravedad": 2 if crit else 1,
                    "Evidencia": f"{t:.1f} °C ({c_a_f(t):.1f} °F); alarma {eq['alarma_C']:.0f} °C, disparo {eq['disparo_C']:.0f} °C",
                    "Causas": ["Fricción anormal en el rodamiento", "Sobrecarga del motor", "Ventilación obstruida o ambiente caliente"],
                    "Acciones": (["Detener la bomba y dejar enfriar"] if crit else ["Vigilar la tendencia cada pocos minutos"])
                    + ["Comparar con la corriente y la vibración", "Limpiar rejillas de ventilación del motor"]})
    rul = num("RUL_h")
    if rul is not None and rul <= eq["rul_aviso_h"] and est not in ("DETENIDA", "MANTENIMIENTO"):
        out.append({"Falla": "Vida remanente del rodamiento baja", "Gravedad": 2 if rul <= eq["rul_aviso_h"] / 4 else 1,
                    "Evidencia": f"RUL ≈ {rul:.0f} h (aviso a {eq['rul_aviso_h']:.0f} h)",
                    "Causas": ["El rodamiento se acerca al final de su vida útil"],
                    "Acciones": ["Programar el cambio de rodamiento en «Mantenimiento»", "Confirmar repuesto y fecha de parada"]})
    zv, vmax = num("zona_vib"), num("Vib_max")
    if zv is not None and zv >= 1:
        out.append({"Falla": "Vibración global en zona " + ("D (inaceptable)" if zv >= 2 else "C (insatisfactoria)"),
                    "Gravedad": int(zv), "Evidencia": f"{vmax:.2f} mm/s RMS (ISO 10816 clase I)",
                    "Causas": ["Rodamiento dañado", "Cavitación", "Desalineación, desbalance o pernos flojos"],
                    "Acciones": ["Analizar el espectro en «Rodamientos» y «Cavitación»", "Reapretar anclajes y verificar alineación"]})
    i = num("I_prom_A")
    if i is not None and i > eq["motor_i"]:
        crit = i > eq["motor_i_sf"]
        out.append({"Falla": "Sobrecarga del motor" if crit else "Corriente sobre la nominal", "Gravedad": 2 if crit else 1,
                    "Evidencia": f"{i:.2f} A (nominal {eq['motor_i']} A, SF {eq['motor_i_sf']} A)",
                    "Causas": ["Caudal excesivo", "Roce interno o rodamiento frenado", "Voltaje bajo o desbalanceado"],
                    "Acciones": ["Medir voltajes", "Cerrar parcialmente la descarga", "Verificar el relé térmico (el motor no tiene protección propia)"]})
    db = num("desb_corriente_pct")
    if db is not None and db > 10:
        out.append({"Falla": "Desbalance de corriente", "Gravedad": 2 if db > 20 else 1, "Evidencia": f"{db:.1f} %",
                    "Causas": ["Tensión desbalanceada", "Borne flojo", "Falla en un devanado"],
                    "Acciones": ["Medir las tres tensiones", "Reapretar bornes y contactor"]})
    dv = num("desb_tension_pct")
    if dv is not None and dv > 2:
        out.append({"Falla": "Desbalance de tensión", "Gravedad": 1, "Evidencia": f"{dv:.2f} % (NEMA recomienda < 1 %)",
                    "Causas": ["Cargas monofásicas desbalanceadas en la red", "Conexión deficiente"],
                    "Acciones": ["Revisar la alimentación del tablero"]})
    return sorted(out, key=lambda x: -x["Gravedad"])


# =============================================================================
# Rodamientos (réplica de la hoja PRINCIPAL del docente, fórmulas corregidas)
# =============================================================================
UMBRALES_ROD = {"mm_s": (1.4, 2.8, 4.5), "g": (0.05, 0.10, 0.20), "coinc": (0.02, 0.05)}


def analisis_rodamiento(rod: str, polos: int, hz_vfd: float, rpm_placa: float, hz_placa: float,
                        vib: float | None, acel: float | None, pico: float | None, u=UMBRALES_ROD) -> dict:
    g = BD_RODAMIENTOS[rod]
    rpm = rpm_placa * (hz_vfd / hz_placa) if hz_placa else None
    fr = rpm / 60 if rpm else None
    k = g["d"] / g["D"] * math.cos(math.radians(g["alfa"]))
    factores = {"FTF (jaula)": 0.5 * (1 - k), "BPFO (pista exterior)": g["n"] / 2 * (1 - k),
                "BPFI (pista interior)": g["n"] / 2 * (1 + k), "BSF (elemento rodante)": g["D"] / (2 * g["d"]) * (1 - k ** 2)}
    revisar = {"FTF (jaula)": "Posible daño de jaula", "BPFO (pista exterior)": "Posible daño de pista exterior",
               "BPFI (pista interior)": "Posible daño de pista interior", "BSF (elemento rodante)": "Posible daño del elemento rodante"}
    filas = []
    for nom, fac in factores.items():
        hz = fac * fr if fr else None
        dev = abs(pico - hz) / hz if (pico and hz) else None
        res = "" if dev is None else "FUERTE" if dev <= u["coinc"][0] else "POSIBLE" if dev <= u["coinc"][1] else "NO COINCIDE"
        filas.append({"Falla": nom, "Factor × fr": fac, "Frecuencia (Hz)": hz, "Qué revisar": revisar[nom], "Desviación": dev, "Resultado": res})
    mm, gg = u["mm_s"], u["g"]
    est_v = "SIN DATO" if vib is None else "NORMAL" if vib <= mm[0] else "ATENCIÓN" if vib <= mm[1] else "ALARMA" if vib <= mm[2] else "CRÍTICO"
    est_g = "SIN DATO" if acel is None else "BAJO" if acel <= gg[0] else "VIGILAR" if acel <= gg[1] else "ALERTA" if acel <= gg[2] else "MUY ALTO"
    devs = [f["Desviación"] for f in filas if f["Desviación"] is not None]
    dmin = min(devs) if devs else None
    mejor = next((f["Falla"] for f in filas if f["Desviación"] == dmin), "SIN PICO") if dmin is not None else "SIN PICO"
    if vib is None and acel is None and pico is None:
        diag, reco = "INGRESE UNA MEDICIÓN", "Coloque el valor que entrega el IRD en mm/s RMS, g o Hz según el modo seleccionado."
    elif est_v == "CRÍTICO" or est_g == "MUY ALTO":
        diag = "🔴 INTERVENCIÓN PRIORITARIA"
        reco = "Inspección prioritaria. Revisar desbalance, desalineación, holgura, lubricación, montaje y condición del rodamiento."
    elif pico and dmin is not None and dmin <= u["coinc"][0]:
        diag = "🟠 REVISAR FRECUENCIA DE FALLA"
        reco = ("Existe una coincidencia fuerte con una frecuencia característica. Confirmar con armónicos, bandas laterales y "
                "tendencia antes de cambiar el rodamiento.")
    elif est_v == "ALARMA" or est_g == "ALERTA" or (pico and dmin is not None and dmin <= u["coinc"][1]):
        diag, reco = "🟡 VIGILAR / INVESTIGAR", "Registrar tendencia y revisar espectro. Investigar causa antes de intervenir."
    else:
        diag, reco = "🟢 CONDICIÓN NORMAL", "Continuar monitoreo y registrar la medición como línea base."
    return {"geom": g, "rpm_sinc": 120 * hz_vfd / polos, "rpm": rpm, "fr": fr,
            "armonicos": {f"{n}× RPM": n * fr for n in (1, 2, 3, 4)} if fr else {}, "tabla": pd.DataFrame(filas),
            "estado_v": est_v, "estado_g": est_g, "mejor": mejor, "dev_min": dmin, "diagnostico": diag, "recomendacion": reco}


# =============================================================================
# Cavitación (réplica de la hoja CAVITACION del docente)
# =============================================================================
def analisis_cavitacion(hp, hz_placa, rpm_placa, hz_vfd, z, fundacion, rpm_real, vib_global, amp_normal, amp_actual,
                        pico, umbral_pct) -> dict:
    rpm = rpm_real if rpm_real else rpm_placa * hz_vfd / hz_placa
    fr = rpm / 60
    bpf = z * rpm / 60
    clase = "CLASE I" if hp < 20 else "CLASE II" if hp <= 100 else ("CLASE IV" if fundacion == "BLANDA" else "CLASE III")
    lim = {"CLASE I": (0.71, 1.8, 4.5), "CLASE II": (1.12, 2.8, 7.1), "CLASE III": (1.8, 4.5, 11.2), "CLASE IV": (2.8, 7.1, 18.0)}[clase]
    if vib_global is None:
        estado = "INGRESE RMS"
    else:
        estado = "BUENO" if vib_global <= lim[0] else "SATISFACTORIO" if vib_global <= lim[1] else "INSATISFACTORIO" if vib_global <= lim[2] else "INACEPTABLE"
    if amp_normal is None or amp_actual is None:
        aumento = None
        aum_txt = "FALTAN DATOS"
    elif amp_normal == 0:
        aumento, aum_txt = None, "SIN REFERENCIA"
    else:
        aumento = (amp_actual - amp_normal) / amp_normal * 100
        aum_txt = f"{aumento:.1f} %"
    coinc = "NO EVALUADO" if not pico else ("SÍ, CERCA DE BPF" if abs(pico - bpf) <= 0.05 * bpf else "NO")
    if vib_global is None:
        diag = "FALTA MEDICIÓN RMS"
    elif aumento is None:
        diag = "SOLO SEVERIDAD GLOBAL – FALTA COMPARACIÓN BPF"
    elif aumento < umbral_pct and vib_global <= lim[1]:
        diag = "SIN INDICIOS CLAROS DE CAVITACIÓN"
    elif aumento >= umbral_pct and vib_global <= lim[0]:
        diag = "POSIBLE CAVITACIÓN – VIGILAR"
    elif aumento >= umbral_pct and vib_global <= lim[2]:
        diag = "CAVITACIÓN PROBABLE"
    elif aumento >= umbral_pct and vib_global > lim[2]:
        diag = "CAVITACIÓN SEVERA / INSPECCIONAR"
    else:
        diag = "VIBRACIÓN ELEVADA – REVISAR OTRA FALLA"
    return {"rpm": rpm, "fr": fr, "f2": 2 * fr, "bpf": bpf, "clase": clase, "lim": lim, "estado": estado,
            "aumento": aumento, "aumento_txt": aum_txt, "coincidencia": coinc, "diagnostico": diag}


# =============================================================================
# Transmisor IR: catálogo y evaluación con los criterios del docente
# =============================================================================
CATALOGO_DEF = [
    {"Marca": "Optris", "Modelo": "CT LT22", "Tipo": "Cabezal + caja electrónica con display", "T_min_C": -50, "T_max_C": 975,
     "DS": 22.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0, "Emis_min": 0.1, "Emis_max": 1.1,
     "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K", "V_min": 8.0, "V_max": 36.0, "Tcab_C": 180, "Telec_C": 85,
     "IP": 65, "Montaje": "Cabezal M12 + caja electrónica", "Proveedor": "", "Local": False, "Precio_USD": None,
     "PDF": "Optris_CT_LT_datasheet.pdf", "Notas": "Rango de salida programable (p. ej. 0–150 °C). Display y salida de alarma."},
    {"Marca": "Optris", "Modelo": "CT LT15", "Tipo": "Cabezal + caja electrónica con display", "T_min_C": -50, "T_max_C": 600,
     "DS": 15.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0, "Emis_min": 0.1, "Emis_max": 1.1,
     "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K", "V_min": 8.0, "V_max": 36.0, "Tcab_C": 180, "Telec_C": 85,
     "IP": 65, "Montaje": "Cabezal M12 + caja electrónica", "Proveedor": "", "Local": False, "Precio_USD": None,
     "PDF": "Optris_CT_LT_datasheet.pdf", "Notas": "Rango de salida programable. Display y salida de alarma."},
    {"Marca": "Optris", "Modelo": "CThot LT10H", "Tipo": "Cabezal + caja electrónica (ambiente caliente)", "T_min_C": -40, "T_max_C": 975,
     "DS": 10.0, "Resp_ms": 100, "Exact_C": 1.5, "Exact_pct": 1.0, "Emis_min": 0.1, "Emis_max": 1.1,
     "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K", "V_min": 8.0, "V_max": 36.0, "Tcab_C": 250, "Telec_C": 85,
     "IP": 65, "Montaje": "Cabezal + caja electrónica", "Proveedor": "", "Local": False, "Precio_USD": None,
     "PDF": "Optris_CThot_LT_datasheet.pdf", "Notas": "Para ambientes muy calientes; sobredimensionado."},
    {"Marca": "Optris", "Modelo": "CSmicro LT15 (versión mA)", "Tipo": "Transmisor M12, electrónica en cable", "T_min_C": -50, "T_max_C": 1030,
     "DS": 15.0, "Resp_ms": 14, "Exact_C": 1.0, "Exact_pct": 1.0, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA",
     "V_min": 5.0, "V_max": 30.0, "Tcab_C": 120, "Telec_C": 75, "IP": None, "Montaje": "Rosca M12×1", "Proveedor": "",
     "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf", "Notas": "IP no indicado en el folleto consultado."},
    {"Marca": "Optris", "Modelo": "CSmicro LT15 HS", "Tipo": "Transmisor M18 a 2 hilos", "T_min_C": -20, "T_max_C": 150,
     "DS": 15.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA",
     "V_min": 5.0, "V_max": 30.0, "Tcab_C": 75, "Telec_C": 75, "IP": None, "Montaje": "Rosca M18×1", "Proveedor": "",
     "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf", "Notas": "Alta sensibilidad; cabezal hasta 75 °C."},
    {"Marca": "Optris", "Modelo": "CS LT", "Tipo": "Transmisor M12 una pieza", "T_min_C": -40, "T_max_C": 1030,
     "DS": 15.0, "Resp_ms": 25, "Exact_C": 1.5, "Exact_pct": 1.5, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "0–5 V; 0–10 V; termopar K",
     "V_min": 5.0, "V_max": 30.0, "Tcab_C": 80, "Telec_C": 80, "IP": None, "Montaje": "Rosca M12×1", "Proveedor": "",
     "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf", "Notas": "Salida 0–10 V directa a la CPU 1214C."},
    {"Marca": "OPTEX-FA / HTM Sensors", "Modelo": "SA-80T-2A", "Tipo": "Transmisor M18", "T_min_C": 0, "T_max_C": 200,
     "DS": 6.25, "Resp_ms": 100, "Exact_C": 2.0, "Exact_pct": 0.0, "Emis_min": 0.95, "Emis_max": 0.95, "Salidas": "4–20 mA",
     "V_min": 10.8, "V_max": 26.4, "Tcab_C": 70, "Telec_C": 70, "IP": 67, "Montaje": "Rosca M18×1, cable 2 m",
     "Proveedor": "POTENTA Ecuador, código 111431001", "Local": True, "Precio_USD": None, "PDF": "OPTEX-FA_SA-80_datasheet.pdf",
     "Notas": "Campo de visión ø80 mm a 500 mm. Emisividad fija 0,95. Carga máx. del lazo 250 Ω."},
    {"Marca": "OPTEX-FA / HTM Sensors", "Modelo": "SA-80T-4A", "Tipo": "Transmisor M18", "T_min_C": 0, "T_max_C": 400,
     "DS": 6.25, "Resp_ms": 100, "Exact_C": 2.0, "Exact_pct": 1.0, "Emis_min": 0.95, "Emis_max": 0.95, "Salidas": "4–20 mA",
     "V_min": 10.8, "V_max": 26.4, "Tcab_C": 70, "Telec_C": 70, "IP": 67, "Montaje": "Rosca M18×1, cable 2 m",
     "Proveedor": "POTENTA Ecuador, código 111431002", "Local": True, "Precio_USD": None, "PDF": "OPTEX-FA_SA-80_datasheet.pdf", "Notas": ""},
]
PORTATILES = [
    {"Equipo": "PT100 de contacto + SM 1231 RTD", "Uso": "Referencia para calibrar y validar el IR (recomendado por el docente)"},
    {"Equipo": "Optris MSPlus LT (portátil)", "Uso": "Referencia sin contacto con emisividad ajustable 0,10–1,10"},
]


def requisitos_ir(d: pd.DataFrame, eq: dict) -> dict:
    t = d.loc[d["estado_bomba"] == 1, "temperatura_motor_C"].dropna()
    t_max = float(t.max()) if len(t) else None
    rango_max = max(float(eq["ir_rango_max_C"]), (t_max or 0) + 20, float(eq["disparo_C"]) + 20)
    spot_max = float(eq["ir_d_objetivo_mm"]) / 1.5
    ds_geo = float(eq["ir_distancia_mm"]) / spot_max
    return {"t_max_obs_C": t_max, "t_p95_C": float(np.percentile(t, 95)) if len(t) else None,
            "rango_min_C": float(eq["ir_rango_min_C"]), "rango_max_C": rango_max,
            "ds_req": max(float(eq["ir_ds_min"]), ds_geo), "ds_geo": ds_geo, "spot_max_mm": spot_max,
            "resp_ms": float(eq["ir_resp_max_ms"]), "cabezal_C": float(eq["ir_cabezal_min_C"]), "exactitud_C": float(eq["ir_exactitud_C"]),
            "salida": eq["ir_salida"], "alim_V": float(eq["ir_alimentacion_V"]), "ip_min": int(eq["ir_ip_min"]),
            "distancia_mm": float(eq["ir_distancia_mm"])}


def evaluar_catalogo(cat: list[dict], r: dict) -> pd.DataFrame:
    filas = []
    precios = [c["Precio_USD"] for c in cat if c.get("Precio_USD")]
    for c in cat:
        exact = max(float(c.get("Exact_C") or 0), float(c.get("Exact_pct") or 0) * 85 / 100)
        chk = {"Rango": c["T_min_C"] <= r["rango_min_C"] and c["T_max_C"] >= r["rango_max_C"],
               "D:S": float(c["DS"]) >= r["ds_req"] - 1e-9, "Respuesta": float(c["Resp_ms"]) <= r["resp_ms"],
               "Cabezal": float(c.get("Tcab_C") or 0) >= r["cabezal_C"], "Exactitud": exact <= r["exactitud_C"] + 1e-9,
               "Salida": r["salida"] in str(c["Salidas"]), "Alimentación": c["V_min"] <= r["alim_V"] <= c["V_max"],
               "IP": (c.get("IP") or 0) >= r["ip_min"]}
        p = 30 * min(1.0, r["exactitud_C"] / max(exact, 0.1)) + 25 * min(1.0, float(c["DS"]) / (1.5 * r["ds_req"]))
        p += 15 if c["Emis_max"] > c["Emis_min"] else 0
        p += 10 if (c.get("IP") or 0) >= 67 else 7 if (c.get("IP") or 0) >= 65 else 0
        p += 10 if c.get("Local") else 0
        p += 10 * (min(precios) / c["Precio_USD"]) if precios and c.get("Precio_USD") else 5
        filas.append({"Modelo": c["Modelo"], "Marca": c["Marca"], "Cumple todo": all(chk.values()),
                      **{k: "✔" if v else "✘" for k, v in chk.items()}, "Exactitud (°C)": round(exact, 2),
                      "Punto medido (mm)": round(r["distancia_mm"] / float(c["DS"]), 1), "Puntaje": round(p, 1),
                      "No cumple": ", ".join(k for k, v in chk.items() if not v)})
    t = pd.DataFrame(filas)
    return t.sort_values(["Cumple todo", "Puntaje"], ascending=[False, False]).reset_index(drop=True) if len(t) else t


# =============================================================================
# Mantenimiento
# =============================================================================
MANT_DEF = {"horometro_h": 0.0, "ultimo_aviso": "", "historial": [], "tareas": [
    {"Tarea": "Inspección visual: ruidos, fugas y temperatura", "Cada_dias": 7, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Limpieza del colador de succión y verificación del nivel del tanque", "Cada_dias": 30, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Limpieza del lente del transmisor IR y revisión de la cinta de emisividad", "Cada_dias": 90, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Reapriete de bornes, revisión de contactor y relé térmico", "Cada_dias": 180, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Verificación de anclajes y alineación", "Cada_dias": 180, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Medición de aislamiento del motor (megóhmetro)", "Cada_dias": 365, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
    {"Tarea": "Revisión del sello mecánico", "Cada_dias": None, "Cada_horas": 2000, "Ultima_fecha": "", "Ultima_horas": None},
]}


def estado_mantenimiento(mant: dict) -> pd.DataFrame:
    hoy = datetime.now().date()
    horas = float(mant.get("horometro_h") or 0)
    filas = []
    for t in mant.get("tareas", []):
        restos, textos = [], []
        if t.get("Cada_dias"):
            if t.get("Ultima_fecha"):
                dd = int(t["Cada_dias"]) - (hoy - pd.to_datetime(t["Ultima_fecha"]).date()).days
                restos.append(dd / int(t["Cada_dias"]))
                textos.append(f"vence en {dd} días" if dd >= 0 else f"vencida hace {-dd} días")
            else:
                restos.append(0.1)
                textos.append("sin registro previo")
        if t.get("Cada_horas"):
            if t.get("Ultima_horas") is not None:
                h = float(t["Cada_horas"]) - (horas - float(t["Ultima_horas"]))
                restos.append(h / float(t["Cada_horas"]))
                textos.append(f"faltan {h:.0f} h" if h >= 0 else f"vencida por {-h:.0f} h")
            else:
                restos.append(0.1)
                textos.append("sin registro previo")
        if restos:
            m = min(restos)
            filas.append({"Tarea": t["Tarea"], "Frecuencia": " / ".join(x for x in [
                f"cada {t['Cada_dias']} días" if t.get("Cada_dias") else "", f"cada {t['Cada_horas']} h" if t.get("Cada_horas") else ""] if x),
                "Última vez": t.get("Ultima_fecha") or "—", "Estado": ", ".join(textos), "nivel": 2 if m < 0 else 1 if m <= 0.15 else 0})
    return pd.DataFrame(filas, columns=["Tarea", "Frecuencia", "Última vez", "Estado", "nivel"])


# =============================================================================
# Alertas Telegram
# =============================================================================
ALERTAS_DEF = {"activo": False, "token": "", "chats": "", "nivel_min": 1, "historial": []}


def telegram_enviar(texto: str, cfg: dict) -> tuple[bool, str]:
    token = str(cfg.get("token") or "").strip()
    chats = [c.strip() for c in str(cfg.get("chats") or "").replace(";", ",").split(",") if c.strip()]
    if not token or not chats:
        return False, "Falta el token del bot o el chat ID."
    errores = []
    for chat in chats:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
            if not r.ok:
                errores.append(f"{chat}: {r.json().get('description', r.status_code)}")
        except requests.RequestException as ex:
            errores.append(f"{chat}: {ex}")
    return (not errores), ("Enviado" if not errores else "; ".join(errores))


def mensaje_alerta(f: dict, diags: list[dict], prefijo: str = "") -> str:
    peor = max(d["Gravedad"] for d in diags)
    lineas = [f"{prefijo}{'🔴 <b>CRÍTICO</b>' if peor == 2 else '🟡 <b>ALERTA</b>'} – Monitoreo Goulds 3642 ESPE",
              f"{html.escape(str(f.get('timestamp', '')))} | Estado: <b>{html.escape(NOMBRE_ESTADO.get(f.get('estado'), str(f.get('estado'))))}</b>"]
    t = f.get("temperatura_motor_C")
    if t is not None and not pd.isna(t):
        lineas.append(f"Temperatura IR: {t:.1f} °C ({c_a_f(t):.1f} °F)")
    rul = f.get("RUL_h")
    if rul is not None and not pd.isna(rul):
        lineas.append(f"RUL del rodamiento: {rul:.0f} h")
    lineas.append("")
    for d in diags[:3]:
        lineas.append(f"{'🔴' if d['Gravedad'] == 2 else '🟡'} <b>{html.escape(d['Falla'])}</b>")
        lineas.append(f"   Causa probable: {html.escape(d['Causas'][0])}")
        lineas.append(f"   Acción: {html.escape(d['Acciones'][0])}")
    return "\n".join(lineas)


def registrar_alerta(cfg: dict, tipo: str, resumen: str, ok: bool, detalle: str) -> None:
    cfg["historial"] = ([{"Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "Tipo": tipo, "Resumen": resumen,
                          "Envío": "✔" if ok else f"✘ {detalle}"}] + cfg.get("historial", []))[:150]
    guardar_json(ARCH_ALERTAS, cfg)


# =============================================================================
# Regresión para el modelo de temperatura
# =============================================================================
def regresion(X: np.ndarray, y: np.ndarray) -> dict:
    try:
        from scipy import stats as sstats
    except ImportError:
        sstats = None
    n, k = X.shape
    A = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ beta
    sse, sst = float(res @ res), float(((y - y.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    gl = n - k - 1
    if gl > 0:
        se = np.sqrt(np.clip(np.diag(sse / gl * np.linalg.pinv(A.T @ A)), 0, None))
        with np.errstate(divide="ignore", invalid="ignore"):
            t = beta / se
        p = 2 * (1 - sstats.t.cdf(np.abs(t), gl)) if sstats else np.full_like(t, np.nan)
    else:
        se = t = p = np.full_like(beta, np.nan)
    return {"beta": beta, "r2": r2, "r2a": 1 - (1 - r2) * (n - 1) / gl if gl > 0 else float("nan"),
            "rmse": math.sqrt(sse / n), "se": se, "t": t, "p": p}


def matriz_terminos(df: pd.DataFrame, terminos: list[str]) -> pd.DataFrame:
    return pd.DataFrame({t: (df[t[:-2]] ** 2 if t.endswith("^2") else df[t]) for t in terminos}, index=df.index)


def vif(Xdf: pd.DataFrame) -> list[float]:
    cols = list(Xdf.columns)
    if len(cols) < 2:
        return [1.0] * len(cols)
    out = []
    for c in cols:
        r2 = regresion(Xdf[[o for o in cols if o != c]].values, Xdf[c].values)["r2"]
        out.append(float("inf") if r2 >= 0.9999 else 1 / (1 - r2))
    return out


def ecuacion_texto(y: str, b0: float, coefs, terminos) -> str:
    s = f"{y} = {b0:.4f}"
    for b, v in zip(coefs, terminos):
        s += f" {'+' if b >= 0 else '−'} {abs(b):.6g}·{v}"
    return s


def evaluar_modelo(modelo: dict, fila: pd.DataFrame) -> float:
    X = matriz_terminos(fila, modelo["terminos"])
    return modelo["intercepto"] + float(np.dot(modelo["coeficientes"], X.iloc[0].values))
