# -*- coding: utf-8 -*-
"""
Monitoreo térmico de rodamientos, modelo de estimación en °F y selección del
transmisor infrarrojo. Motor Emerson P55CST-1247 + bomba Goulds 3642.
Universidad de las Fuerzas Armadas ESPE – Sede Latacunga | Ingeniería Electromecánica

Instalar (una sola vez):
    python -m pip install streamlit pandas numpy altair scipy openpyxl python-docx matplotlib
Ejecutar (desde esta carpeta):
    python -m streamlit run app_rodamientos.py

Carpeta del proyecto:
    app_rodamientos.py, logo_espe.png, logo_em.png, .streamlit/ (colores),
    catalogos/ (PDF de los transmisores), datos_prueba/ (Excel de data sintética)
Archivos que crea la aplicación:
    datos_rodamientos.csv, datos_equipo.json, modelo_estimacion.json, catalogo_ir.json
"""
import base64
import html
import json
import math
import warnings
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import altair as alt
import requests
import numpy as np
import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parent
_ICONO = BASE / "logo_em.png"
st.set_page_config(page_title="ESPE | Monitoreo de rodamientos",
                   page_icon=str(_ICONO) if _ICONO.exists() else "⚡", layout="wide")

try:
    from scipy import stats as sstats
except ImportError:
    sstats = None

# =============================================================================
# Archivos y constantes
# =============================================================================
ARCH_DATOS = BASE / "datos_rodamientos.csv"
ARCH_EQUIPO = BASE / "datos_equipo.json"
ARCH_MODELO = BASE / "modelo_estimacion.json"
ARCH_CATALOGO = BASE / "catalogo_ir.json"
ARCH_ALERTAS = BASE / "alertas.json"
ARCH_MANT = BASE / "mantenimiento.json"
DIR_CATALOGOS = BASE / "catalogos"
DIR_PRUEBA = BASE / "datos_prueba"

DOCENTE = "Ing. Wilson Sánchez Ocaña"
PALETA = ["#1F6FEB", "#0A1F44", "#00A3FF", "#F2B705", "#5B8DEF", "#8A9BB8", "#0D3B8C"]
COLOR_ZONA = {0: "#2E9E5B", 1: "#F2B705", 2: "#D64545"}
TEXTO_ZONA = {0: "Normal", 1: "Alerta", 2: "Crítico"}
G = 9.80665

COLS = [
    "ID", "Fecha_hora", "Origen", "Ensayo", "Operador", "Instrumento_T",
    "t_min", "Apertura_valvula_pct",
    "V_V", "I_A", "I_L1_A", "I_L2_A", "I_L3_A", "f_Hz", "FP", "P_kW", "rpm",
    "Q_Lmin", "P_succ_psi", "P_desc_psi", "T_agua_F",
    "Vib_succ_mms", "Vib_desc_mms",
    "Vib_DE_H_mms", "Vib_DE_V_mms", "Vib_DE_A_mms",
    "Vib_NDE_H_mms", "Vib_NDE_V_mms", "Vib_NDE_A_mms",
    "Acel_DE_g", "Acel_NDE_g", "Pico_Hz", "Amp_BPF_mms",
    "T_amb_F", "T_rod_DE_F", "T_rod_NDE_F", "Observaciones",
]
TEXTO = ["Fecha_hora", "Origen", "Ensayo", "Operador", "Instrumento_T", "Observaciones"]
NUMERICAS = [c for c in COLS if c not in TEXTO and c != "ID"]
OBJ_TEMP = ["T_rod_DE_F", "T_rod_NDE_F"]

ETIQUETAS = {
    "t_min": "Tiempo de operación (min)", "Apertura_valvula_pct": "Apertura válvula (%)",
    "V_V": "Voltaje de línea (V)", "I_A": "Corriente promedio (A)",
    "I_L1_A": "Corriente L1 (A)", "I_L2_A": "Corriente L2 (A)", "I_L3_A": "Corriente L3 (A)",
    "f_Hz": "Frecuencia (Hz)", "FP": "Factor de potencia", "P_kW": "Potencia activa (kW)",
    "rpm": "Velocidad (rpm)", "Q_Lmin": "Caudal medido (L/min)",
    "P_succ_psi": "Presión succión manométrica (psi)", "P_desc_psi": "Presión descarga (psi)",
    "T_agua_F": "Temperatura del agua (°F)",
    "Vib_succ_mms": "Vibración bomba succión (mm/s)", "Vib_desc_mms": "Vibración bomba descarga (mm/s)",
    "Vib_DE_H_mms": "Vib. motor DE horizontal (mm/s)", "Vib_DE_V_mms": "Vib. motor DE vertical (mm/s)",
    "Vib_DE_A_mms": "Vib. motor DE axial (mm/s)", "Vib_NDE_H_mms": "Vib. motor NDE horizontal (mm/s)",
    "Vib_NDE_V_mms": "Vib. motor NDE vertical (mm/s)", "Vib_NDE_A_mms": "Vib. motor NDE axial (mm/s)",
    "Acel_DE_g": "Aceleración DE (g)", "Acel_NDE_g": "Aceleración NDE (g)",
    "Pico_Hz": "Pico espectral medido (Hz)", "Amp_BPF_mms": "Amplitud en BPF (mm/s)",
    "T_amb_F": "Temperatura ambiente (°F)",
    "T_rod_DE_F": "T rodamiento DE – lado bomba (°F)", "T_rod_NDE_F": "T rodamiento NDE – lado ventilador (°F)",
    # derivadas
    "I_prom_A": "Corriente promedio usada (A)", "desb_I_pct": "Desbalance de corriente (%)",
    "carga_pct": "Carga del motor (% de I nominal)", "P_elec_kW": "Potencia eléctrica (kW)",
    "s_pct": "Deslizamiento (%)", "dP_psi": "ΔP descarga − succión (psi)", "H_m": "Altura medida (m)",
    "Q_gpm": "Caudal usado (GPM)", "H_ref_m": "Altura de referencia del fabricante (m)",
    "E_H_pct": "Error de altura vs curva (%)", "P_hid_W": "Potencia hidráulica (W)",
    "eta_global_pct": "Eficiencia global (%)", "P_succ_abs_kPa": "Presión absoluta en succión (kPa)",
    "NPSHa_m": "NPSH disponible (m)", "NPSHr_m": "NPSH requerido (m)",
    "margen_NPSH_m": "Margen NPSHa − NPSHr (m)", "ratio_NPSH": "Relación NPSHa / NPSHr",
    "Vib_motor_max": "Vibración máxima motor (mm/s)", "Vib_bomba_max": "Vibración máxima bomba (mm/s)",
    "Vib_max": "Vibración máxima global (mm/s)", "dT_DE_F": "ΔT DE = T − Tamb (°F)",
    "dT_NDE_F": "ΔT NDE = T − Tamb (°F)", "I2": "Corriente² (A²)",
}
DERIVADAS = ["I_prom_A", "desb_I_pct", "carga_pct", "P_elec_kW", "s_pct", "dP_psi", "H_m", "Q_gpm",
             "E_H_pct", "P_hid_W", "eta_global_pct", "NPSHa_m", "margen_NPSH_m", "ratio_NPSH",
             "Vib_motor_max", "Vib_bomba_max", "Vib_max", "I2"]
CANDIDATAS = [c for c in NUMERICAS if c not in OBJ_TEMP] + DERIVADAS
VIB_MOTOR = ["Vib_DE_H_mms", "Vib_DE_V_mms", "Vib_DE_A_mms", "Vib_NDE_H_mms", "Vib_NDE_V_mms", "Vib_NDE_A_mms"]
VIB_BOMBA = ["Vib_succ_mms", "Vib_desc_mms"]

# Variables medidas de las que depende cada variable calculada (para el estimador)
DEPENDE = {
    "I_prom_A": ["I_A"], "I2": ["I_A"], "carga_pct": ["I_A"], "desb_I_pct": ["I_L1_A", "I_L2_A", "I_L3_A"],
    "P_elec_kW": ["V_V", "I_A", "FP"], "s_pct": ["f_Hz", "rpm"],
    "dP_psi": ["P_desc_psi", "P_succ_psi"], "H_m": ["P_desc_psi", "P_succ_psi"],
    "Q_gpm": ["Q_Lmin", "P_desc_psi", "P_succ_psi"], "E_H_pct": ["Q_Lmin", "P_desc_psi", "P_succ_psi"],
    "P_hid_W": ["Q_Lmin", "P_desc_psi", "P_succ_psi"],
    "eta_global_pct": ["Q_Lmin", "P_desc_psi", "P_succ_psi", "V_V", "I_A", "FP"],
    "NPSHa_m": ["P_succ_psi", "Q_Lmin", "T_agua_F"],
    "margen_NPSH_m": ["P_succ_psi", "Q_Lmin", "P_desc_psi", "T_agua_F"],
    "ratio_NPSH": ["P_succ_psi", "Q_Lmin", "P_desc_psi", "T_agua_F"],
    "Vib_motor_max": VIB_MOTOR, "Vib_bomba_max": VIB_BOMBA, "Vib_max": VIB_MOTOR + VIB_BOMBA,
}

# Curva de la bomba Goulds 3642, 1¼ × 1½ – 5, impulsor 3 5/8", 3500 rpm
# (digitalización aproximada del folleto Goulds/Xylem, documento del docente)
CURVA = pd.DataFrame({
    "Q_gpm": [0, 10, 20, 30, 40, 50, 60, 70, 80],
    "H_m": [15.6972, 15.60576, 15.3924, 14.9352, 14.1732, 13.2588, 12.192, 10.9728, 9.6012],
    "Eficiencia_pct": [0, 28, 45, 55, 60, 63, 62, 58, 50],
    "NPSHr_m": [1.9812, 2.07264, 2.19456, 2.4384, 2.7432, 3.2004, 3.9624, 5.1816, 6.858],
})
COEF_HQ = (-0.000963, -0.000294, 15.7312)  # H(m) = a·Q² + b·Q + c, Q en GPM

BD_RODAMIENTOS = {  # tabla del docente (valores de referencia; verificar con el fabricante)
    "6202": {"n": 8, "d": 5.95, "D": 23.5, "alfa": 0.0},
    "6203": {"n": 8, "d": 6.75, "D": 28.5, "alfa": 0.0},
    "6206": {"n": 9, "d": 9.525, "D": 46.0, "alfa": 0.0},
    "6207": {"n": 9, "d": 11.112, "D": 53.5, "alfa": 0.0},
    "6208": {"n": 9, "d": 11.906, "D": 60.0, "alfa": 0.0},
}

DEF_EQUIPO = {
    "operadores": [], "asignatura": "", "nrc": "", "periodo": "",
    "proyecto": "Selección de un transmisor de temperatura infrarrojo y modelo de estimación "
                "para el monitoreo de rodamientos",
    # Motor (placa)
    "motor_marca": "Emerson Motor Company", "motor_modelo": "P55CST-1247", "motor_hp": 0.75,
    "motor_v": 230.0, "motor_i": 3.0, "motor_i_sf": 3.4, "motor_sf": 1.5, "motor_rpm": 3450.0,
    "motor_polos": 2, "motor_f": 60.0, "motor_fp": 0.84, "motor_aislamiento": "B (130 °C)",
    "motor_amb": 40.0, "motor_ip": "IP22 (ODP, abierto)", "motor_prot_term": "Ninguna",
    # Bomba (placa)
    "bomba_marca": "Goulds Pumps (ITT)", "bomba_modelo": "3642", "bomba_index": "2BF10734",
    "bomba_tamano": "1 1/4 x 1 1/2 - 5", "bomba_impulsor": "3 5/8 in", "bomba_serie": "K0457068",
    "bomba_config": "Close-coupled: el impulsor va en el eje del motor", "bomba_alabes": None,
    "d_succion_mm": 40.9,
    # Rodamientos (probables, confirmar)
    "rod_DE": "6203", "rod_NDE": "6202", "rod_confirmado": False, "grasa": "",
    # Sitio
    "ubicacion": "Latacunga", "altitud_m": 2750.0, "p_baro_kpa": None, "t_agua_C": 18.0,
    # Límites
    "alarma_F": 185.0, "disparo_F": 203.0,
    "iso_A": 0.71, "iso_B": 1.8, "iso_C": 4.5,
    "npsh_normal": 1.30, "npsh_alerta": 1.10,
    # Requisitos para el transmisor IR
    "ir_superficie": "Pintada (ε ≈ 0,90–0,95)", "ir_cinta": False, "ir_d_objetivo_mm": 50.0,
    "ir_distancia_mm": 150.0, "ir_amb_max_C": 50.0, "ir_ip_min": 65, "ir_salida": "4–20 mA",
    "ir_alimentacion_V": 24.0, "ir_margen_rango_C": 20.0, "ir_exactitud_manual": None,
}

SUPERFICIES = ["Pintada (ε ≈ 0,90–0,95)", "Fundición u óxido (ε ≈ 0,60–0,85)", "Metal brillante (ε < 0,30)"]

CATALOGO_DEF = [
    {"Marca": "OPTEX-FA / HTM Sensors", "Modelo": "SA-80T-2A", "Tipo": "Transmisor fijo M18",
     "T_min_C": 0, "T_max_C": 200, "DS": 6.25, "Resp_ms": 100, "Exact_C": 2.0, "Exact_pct": 0.0,
     "Repet_C": 1.0, "Emis_min": 0.95, "Emis_max": 0.95, "Salidas": "4–20 mA",
     "V_min": 10.8, "V_max": 26.4, "Tamb_max_C": 70, "IP": 67, "Montaje": "Rosca M18×1, cable 2 m",
     "Proveedor_local": "POTENTA Ecuador, código 111431001", "Local": True, "Precio_USD": None,
     "PDF": "OPTEX-FA_SA-80_datasheet.pdf",
     "Notas": "Campo de visión ø80 mm a 500 mm. Emisividad fija 0,95. Carga máx. del lazo 250 Ω. Termopila 8–14 µm."},
    {"Marca": "OPTEX-FA / HTM Sensors", "Modelo": "SA-80T-4A", "Tipo": "Transmisor fijo M18",
     "T_min_C": 0, "T_max_C": 400, "DS": 6.25, "Resp_ms": 100, "Exact_C": 2.0, "Exact_pct": 1.0,
     "Repet_C": 1.0, "Emis_min": 0.95, "Emis_max": 0.95, "Salidas": "4–20 mA",
     "V_min": 10.8, "V_max": 26.4, "Tamb_max_C": 70, "IP": 67, "Montaje": "Rosca M18×1, cable 2 m",
     "Proveedor_local": "POTENTA Ecuador, código 111431002", "Local": True, "Precio_USD": None,
     "PDF": "OPTEX-FA_SA-80_datasheet.pdf",
     "Notas": "Igual al 2A con rango hasta 400 °C (±2 °C hasta 200 °C, ±1 % de 201 a 400 °C)."},
    {"Marca": "OPTEX-FA", "Modelo": "SA-80T-4IO", "Tipo": "Transmisor fijo M18 IO-Link",
     "T_min_C": 0, "T_max_C": 400, "DS": 6.25, "Resp_ms": 100, "Exact_C": 2.0, "Exact_pct": 1.0,
     "Repet_C": 1.0, "Emis_min": 0.1, "Emis_max": 1.2, "Salidas": "IO-Link",
     "V_min": 16.2, "V_max": 33.0, "Tamb_max_C": 70, "IP": 67, "Montaje": "Rosca M18×1, conector M12",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "OPTEX-FA_SA-80_datasheet.pdf",
     "Notas": "Requiere maestro IO-Link. Emisividad ajustable 0,1–1,2."},
    {"Marca": "Optris", "Modelo": "CSmicro LT15 HS", "Tipo": "Transmisor fijo M18 a 2 hilos",
     "T_min_C": -20, "T_max_C": 150, "DS": 15.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0,
     "Repet_C": None, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA",
     "V_min": 5.0, "V_max": 30.0, "Tamb_max_C": 75, "IP": None, "Montaje": "Rosca M18×1, electrónica en el cable",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf",
     "Notas": "Alta sensibilidad (resolución 0,025 K). Emisividad ajustable por software: confirmar en la hoja del modelo. IP no indicado en el folleto."},
    {"Marca": "Optris", "Modelo": "CSmicro LT15 (versión mA)", "Tipo": "Transmisor fijo M12",
     "T_min_C": -50, "T_max_C": 1030, "DS": 15.0, "Resp_ms": 14, "Exact_C": 1.0, "Exact_pct": 1.0,
     "Repet_C": None, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA",
     "V_min": 5.0, "V_max": 30.0, "Tamb_max_C": 75, "IP": None, "Montaje": "Rosca M12×1, electrónica en el cable",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf",
     "Notas": "Rango escalable. Cabezal hasta 120 °C, electrónica mA hasta 75 °C. IP no indicado en el folleto."},
    {"Marca": "Optris", "Modelo": "CS LT", "Tipo": "Transmisor fijo M12",
     "T_min_C": -40, "T_max_C": 1030, "DS": 15.0, "Resp_ms": 25, "Exact_C": 1.5, "Exact_pct": 1.5,
     "Repet_C": None, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "0–5 V; 0–10 V; termopar K",
     "V_min": 5.0, "V_max": 30.0, "Tamb_max_C": 80, "IP": None, "Montaje": "Rosca M12×1, una pieza",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "optris-product-brochure.pdf",
     "Notas": "No tiene salida 4–20 mA; sirve solo si el PLC lee 0–10 V."},
    {"Marca": "Optris", "Modelo": "CT LT15", "Tipo": "Cabezal + caja electrónica con display",
     "T_min_C": -50, "T_max_C": 600, "DS": 15.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0,
     "Repet_C": 0.5, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K",
     "V_min": 8.0, "V_max": 36.0, "Tamb_max_C": 85, "IP": 65, "Montaje": "Cabezal M12 + caja electrónica",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "Optris_CT_LT_datasheet.pdf",
     "Notas": "Display y teclas para programar; salida de alarma. Cabezal hasta 180 °C, electrónica hasta 85 °C."},
    {"Marca": "Optris", "Modelo": "CT LT22", "Tipo": "Cabezal + caja electrónica con display",
     "T_min_C": -50, "T_max_C": 975, "DS": 22.0, "Resp_ms": 150, "Exact_C": 1.0, "Exact_pct": 1.0,
     "Repet_C": 0.5, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K",
     "V_min": 8.0, "V_max": 36.0, "Tamb_max_C": 85, "IP": 65, "Montaje": "Cabezal M12 + caja electrónica",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "Optris_CT_LT_datasheet.pdf",
     "Notas": "Mejor óptica (22:1) para montar más lejos."},
    {"Marca": "Optris", "Modelo": "CThot LT10H", "Tipo": "Cabezal + caja electrónica (ambiente caliente)",
     "T_min_C": -40, "T_max_C": 975, "DS": 10.0, "Resp_ms": 100, "Exact_C": 1.5, "Exact_pct": 1.0,
     "Repet_C": 0.5, "Emis_min": 0.1, "Emis_max": 1.1, "Salidas": "4–20 mA; 0–20 mA; 0–5 V; 0–10 V; termopar J/K",
     "V_min": 8.0, "V_max": 36.0, "Tamb_max_C": 85, "IP": 65, "Montaje": "Cabezal + caja electrónica",
     "Proveedor_local": "", "Local": False, "Precio_USD": None, "PDF": "Optris_CThot_LT_datasheet.pdf",
     "Notas": "Pensado para ambientes de hasta 250 °C en el cabezal; sobredimensionado para rodamientos."},
]
PORTATILES = [
    {"Equipo": "Optris MS LT", "Rango": "−32 … 420 °C", "D:S": "20:1", "Exactitud": "±1 °C o ±1 %",
     "Emisividad": "0,95 fija", "Uso": "Medición de referencia sobre superficies pintadas"},
    {"Equipo": "Optris MSPlus LT", "Rango": "−32 … 530 °C", "D:S": "20:1", "Exactitud": "±1 °C o ±1 %",
     "Emisividad": "0,10 – 1,10 ajustable", "Uso": "Referencia; permite igualar la emisividad del transmisor"},
]


# =============================================================================
# Archivos
# =============================================================================
# -----------------------------------------------------------------------------
# Almacenamiento: archivos locales o base de datos en la nube (Supabase)
# -----------------------------------------------------------------------------
def secreto(clave: str, defecto=None):
    try:
        return st.secrets[clave]
    except Exception:
        return defecto


SUPA_URL = str(secreto("supabase_url", "") or "").rstrip("/")
SUPA_KEY = str(secreto("supabase_key", "") or "")
NUBE = bool(SUPA_URL and SUPA_KEY)


def _cabeceras(extra: dict | None = None) -> dict:
    h = {"apikey": SUPA_KEY, "Content-Type": "application/json"}
    if not SUPA_KEY.startswith("sb_"):  # clave antigua tipo JWT
        h["Authorization"] = f"Bearer {SUPA_KEY}"
    return {**h, **(extra or {})}


def _supa(metodo: str, ruta: str, **kw):
    r = requests.request(metodo, f"{SUPA_URL}/rest/v1/{ruta}", headers=_cabeceras(kw.pop("headers", None)),
                         timeout=30, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase {r.status_code}: {r.text[:300]}")
    return r


def _limpio(v):
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


@st.cache_data(ttl=45, show_spinner=False)
def _leer_config_nube(clave: str):
    r = _supa("GET", f"config?clave=eq.{clave}&select=valor")
    filas = r.json()
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
    datos = json.loads(json.dumps(datos, ensure_ascii=False, default=lambda o: _limpio(o) if hasattr(o, "item") else str(o)))
    if NUBE:
        _supa("POST", "config", json=[{"clave": ruta.stem, "valor": datos}],
              headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        st.cache_data.clear()
    else:
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    if "T_rod_motor_F" in df.columns and "T_rod_DE_F" not in df.columns:  # versión anterior
        df = df.rename(columns={"T_rod_motor_F": "T_rod_DE_F"})
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[COLS].copy()
    for c in NUMERICAS + ["ID"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in TEXTO:
        df[c] = df[c].fillna("").astype(str).replace({"nan": "", "None": ""})
    df.loc[df["Origen"] == "", "Origen"] = "Real"
    return df


def _fila_json(fila: dict) -> dict:
    return {c: _limpio(fila.get(c)) for c in COLS if c != "ID"}


@st.cache_data(ttl=45, show_spinner="Cargando datos...")
def _leer_registros_nube() -> list:
    filas, inicio = [], 0
    while True:
        r = _supa("GET", "registros?select=id,datos&order=id.asc",
                  headers={"Range-Unit": "items", "Range": f"{inicio}-{inicio + 999}"})
        lote = r.json()
        filas.extend(lote)
        if len(lote) < 1000:
            return filas
        inicio += 1000


def cargar_datos() -> pd.DataFrame:
    if NUBE:
        filas = _leer_registros_nube()
        df = pd.DataFrame([{**f["datos"], "ID": f["id"]} for f in filas]) if filas else pd.DataFrame(columns=COLS)
        df = normalizar(df)
    elif ARCH_DATOS.exists():
        df = pd.read_csv(ARCH_DATOS, low_memory=False)
        sobrantes = [c for c in df.columns if c not in COLS and c != "T_rod_motor_F"]
        respaldo = BASE / "datos_rodamientos_version_anterior.csv"
        if sobrantes and not respaldo.exists():
            df.to_csv(respaldo, index=False)
        df = normalizar(df)
    else:
        df = normalizar(pd.DataFrame(columns=COLS))
    # huella de lo cargado: permite subir a la nube solo lo que cambió
    st.session_state["_huella"] = {int(r["ID"]): json.dumps(_fila_json(r), sort_keys=True, default=str)
                                   for r in df.to_dict("records") if not pd.isna(r["ID"])}
    return df


def guardar_datos(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar(df.reset_index(drop=True))
    faltan = df["ID"].isna()
    if faltan.any():
        maximo = int(df["ID"].max()) if df["ID"].notna().any() else 0
        if NUBE:
            r = _supa("GET", "registros?select=id&order=id.desc&limit=1").json()
            maximo = max(maximo, r[0]["id"] if r else 0)
        df.loc[faltan, "ID"] = np.arange(maximo + 1, maximo + 1 + int(faltan.sum()))
    vacias = df["Fecha_hora"].str.strip() == ""
    df.loc[vacias, "Fecha_hora"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            _supa("POST", "registros", json=cambiadas[k:k + 500],
                  headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        borradas = sorted(set(huella) - actuales)
        for k in range(0, len(borradas), 150):
            _supa("DELETE", f"registros?id=in.({','.join(map(str, borradas[k:k + 150]))})")
        st.cache_data.clear()
    else:
        df.to_csv(ARCH_DATOS, index=False)
    return df


def ruta_pdf(nombre: str) -> Path | None:
    if not nombre:
        return None
    ruta = DIR_CATALOGOS / nombre
    return ruta if ruta.exists() else None


# =============================================================================
# Cálculos físicos
# =============================================================================
def f_a_c(f):
    return (f - 32) / 1.8


def c_a_f(c):
    return c * 1.8 + 32


def p_atm_kpa(eq: dict) -> float:
    if eq.get("p_baro_kpa"):
        return float(eq["p_baro_kpa"])
    h = float(eq.get("altitud_m") or 0)
    return 101.325 * (1 - 2.25577e-5 * h) ** 5.25588


def p_vapor_kpa(t_c):
    return 0.61094 * np.exp(17.625 * t_c / (t_c + 243.04))


def densidad_agua(t_c):
    return 1000 * (1 - (t_c + 288.9414) / (508929.2 * (t_c + 68.12963)) * (t_c - 3.9863) ** 2)


def h_ref(q_gpm):
    a, b, c = COEF_HQ
    return a * q_gpm ** 2 + b * q_gpm + c


def q_desde_h(h_m):
    a, b, c = COEF_HQ
    disc = b ** 2 - 4 * a * (c - h_m)
    q = (-b - np.sqrt(np.clip(disc, 0, None))) / (2 * a)
    q = np.where(h_m >= c, 0.0, q)
    return np.where(disc < 0, np.nan, q)


def zona_vib(v, eq):
    return np.select([v <= eq["iso_B"], v <= eq["iso_C"]], [0, 1], 2).astype(float)


def calcular_derivadas(df: pd.DataFrame, eq: dict) -> pd.DataFrame:
    d = df.copy()
    fases = d[["I_L1_A", "I_L2_A", "I_L3_A"]]
    d["I_prom_A"] = d["I_A"].fillna(fases.mean(axis=1))
    prom_f = fases.mean(axis=1)
    d["desb_I_pct"] = (fases.sub(prom_f, axis=0).abs().max(axis=1) / prom_f * 100).where(fases.notna().sum(axis=1) == 3)
    d["I2"] = d["I_prom_A"] ** 2
    d["carga_pct"] = d["I_prom_A"] / float(eq["motor_i"]) * 100
    fp = d["FP"].fillna(float(eq.get("motor_fp") or 0.84))
    d["P_elec_kW"] = d["P_kW"].fillna(math.sqrt(3) * d["V_V"] * d["I_prom_A"] * fp / 1000)
    ns = 120 * d["f_Hz"].fillna(float(eq["motor_f"])) / max(int(eq["motor_polos"]), 2)
    d["s_pct"] = (ns - d["rpm"]) / ns * 100
    # Hidráulica
    d["dP_psi"] = d["P_desc_psi"] - d["P_succ_psi"]
    d["H_m"] = d["dP_psi"] * 0.70307
    q_med = d["Q_Lmin"] / 3.78541
    q_est = pd.Series(q_desde_h(d["H_m"].to_numpy(dtype=float)), index=d.index)
    d["Q_gpm"] = q_med.fillna(q_est)
    d["Q_fuente"] = np.where(q_med.notna(), "Medido", np.where(q_est.notna(), "Estimado por curva H–Q", ""))
    d["H_ref_m"] = h_ref(d["Q_gpm"])
    d["E_H_pct"] = (d["H_m"] - d["H_ref_m"]) / d["H_ref_m"] * 100
    t_agua = f_a_c(d["T_agua_F"]).fillna(float(eq.get("t_agua_C") or 18.0))
    rho = densidad_agua(t_agua)
    q_m3s = d["Q_gpm"] * 3.78541e-3 / 60
    d["P_hid_W"] = rho * G * q_m3s * d["H_m"]
    d["eta_global_pct"] = d["P_hid_W"] / (d["P_elec_kW"] * 1000) * 100
    patm = p_atm_kpa(eq)
    d["P_succ_abs_kPa"] = patm + d["P_succ_psi"] * 6.89476
    area = math.pi * (float(eq["d_succion_mm"]) / 1000) ** 2 / 4
    v = q_m3s / area
    d["NPSHa_m"] = (d["P_succ_abs_kPa"] - p_vapor_kpa(t_agua)) * 1000 / (rho * G) + v ** 2 / (2 * G)
    d["NPSHr_m"] = np.interp(d["Q_gpm"].fillna(0), CURVA["Q_gpm"], CURVA["NPSHr_m"])
    d.loc[d["Q_gpm"].isna(), "NPSHr_m"] = np.nan
    d["margen_NPSH_m"] = d["NPSHa_m"] - d["NPSHr_m"]
    d["ratio_NPSH"] = d["NPSHa_m"] / d["NPSHr_m"]
    # Vibración
    d["Vib_motor_max"] = d[VIB_MOTOR].max(axis=1)
    d["Vib_bomba_max"] = d[VIB_BOMBA].max(axis=1)
    d["Vib_max"] = d[VIB_MOTOR + VIB_BOMBA].max(axis=1)
    # Temperatura
    d["dT_DE_F"] = d["T_rod_DE_F"] - d["T_amb_F"]
    d["dT_NDE_F"] = d["T_rod_NDE_F"] - d["T_amb_F"]
    t_max = d[OBJ_TEMP].max(axis=1)
    # Zonas: 0 normal, 1 alerta, 2 crítico
    d["zona_T"] = np.where(t_max.isna(), np.nan,
                           np.select([t_max < eq["alarma_F"], t_max < eq["disparo_F"]], [0, 1], 2))
    r = d["ratio_NPSH"]
    d["zona_NPSH"] = np.where(r.isna(), np.nan,
                              np.select([r >= eq["npsh_normal"], r >= eq["npsh_alerta"]], [0, 1], 2))
    d["zona_vib"] = np.where(d["Vib_max"].isna(), np.nan, zona_vib(d["Vib_max"], eq))
    i = d["I_prom_A"]
    d["zona_carga"] = np.where(i.isna(), np.nan,
                               np.select([i <= eq["motor_i"], i <= eq["motor_i_sf"]], [0, 1], 2))
    d["estado"] = d[["zona_T", "zona_NPSH", "zona_vib", "zona_carga"]].max(axis=1)
    d["estado_txt"] = d["estado"].map(TEXTO_ZONA).fillna("Sin datos")
    return d


def frecuencias_rodamiento(rod: str, rpm: float) -> dict:
    g = BD_RODAMIENTOS.get(str(rod))
    if not g or not rpm or np.isnan(rpm):
        return {}
    fr = rpm / 60
    k = g["d"] / g["D"] * math.cos(math.radians(g["alfa"]))
    return {
        "1× (giro)": fr, "2×": 2 * fr,
        "FTF (jaula)": fr / 2 * (1 - k),
        "BPFO (pista exterior)": g["n"] / 2 * fr * (1 - k),
        "BPFI (pista interior)": g["n"] / 2 * fr * (1 + k),
        "BSF (elemento rodante)": g["D"] / (2 * g["d"]) * fr * (1 - k ** 2),
    }


def validar(fila: dict, eq: dict) -> list[str]:
    """Avisos sobre datos incoherentes o condiciones fuera de rango."""
    av = []

    def val(c):
        x = fila.get(c)
        return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)

    i = val("I_A") or val("I_prom_A")
    if i is not None and i > eq["motor_i_sf"]:
        av.append(f"Corriente {i:.2f} A supera la corriente de factor de servicio ({eq['motor_i_sf']} A): posible sobrecarga.")
    elif i is not None and i > eq["motor_i"]:
        av.append(f"Corriente {i:.2f} A sobre la nominal ({eq['motor_i']} A), dentro del factor de servicio.")
    rpm = val("rpm")
    if rpm is not None and not (0.85 * eq["motor_rpm"] <= rpm <= 3600):
        av.append(f"Velocidad {rpm:.0f} rpm fuera de lo esperado para un motor de 2 polos a 60 Hz.")
    v = val("V_V")
    if v is not None and abs(v - eq["motor_v"]) / eq["motor_v"] > 0.10:
        av.append(f"Voltaje {v:.0f} V difiere más de 10 % del nominal ({eq['motor_v']:.0f} V).")
    fp = val("FP")
    if fp is not None and not (0 < fp <= 1):
        av.append("El factor de potencia debe estar entre 0 y 1.")
    ps = val("P_succ_psi")
    patm_psi = p_atm_kpa(eq) / 6.89476
    if ps is not None and ps < -patm_psi:
        av.append(f"Presión de succión {ps:.2f} psi imposible: el vacío no puede superar la presión atmosférica local ({patm_psi:.2f} psi).")
    pd_ = val("P_desc_psi")
    if ps is not None and pd_ is not None and pd_ < ps:
        av.append("La presión de descarga es menor que la de succión: revisar manómetros.")
    ta, tde, tnde = val("T_amb_F"), val("T_rod_DE_F"), val("T_rod_NDE_F")
    for nom, t in (("DE", tde), ("NDE", tnde)):
        if t is not None and ta is not None and t < ta - 3:
            av.append(f"La temperatura del rodamiento {nom} es menor que la ambiente: revisar medición o emisividad.")
        if t is not None and t >= eq["disparo_F"]:
            av.append(f"Rodamiento {nom} a {t:.1f} °F: sobre el límite de disparo ({eq['disparo_F']:.0f} °F).")
        elif t is not None and t >= eq["alarma_F"]:
            av.append(f"Rodamiento {nom} a {t:.1f} °F: sobre el límite de alarma ({eq['alarma_F']:.0f} °F).")
    vmax = fila.get("Vib_max")
    if vmax is not None and not np.isnan(vmax) and vmax > eq["iso_C"]:
        av.append(f"Vibración {vmax:.2f} mm/s en zona D (inaceptable) según ISO clase I.")
    r = fila.get("ratio_NPSH")
    if r is not None and not np.isnan(r) and r < eq["npsh_alerta"]:
        av.append(f"NPSHa/NPSHr = {r:.2f}: riesgo de cavitación.")
    return av


# =============================================================================
# Modelos
# =============================================================================
def regresion(X: np.ndarray, y: np.ndarray) -> dict:
    n, k = X.shape
    A = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    yhat = A @ beta
    res = y - yhat
    sse = float(res @ res)
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    gl = n - k - 1
    r2a = 1 - (1 - r2) * (n - 1) / gl if gl > 0 else float("nan")
    if gl > 0:
        cov = sse / gl * np.linalg.pinv(A.T @ A)
        se = np.sqrt(np.clip(np.diag(cov), 0, None))
        with np.errstate(divide="ignore", invalid="ignore"):
            t = beta / se
        p = 2 * (1 - sstats.t.cdf(np.abs(t), gl)) if sstats is not None else np.full_like(t, np.nan)
    else:
        se = t = p = np.full_like(beta, np.nan)
    return {"beta": beta, "yhat": yhat, "r2": r2, "r2a": r2a, "rmse": math.sqrt(sse / n),
            "se": se, "t": t, "p": p, "n": n}


def matriz_terminos(df: pd.DataFrame, terminos: list[str]) -> pd.DataFrame:
    salida = {}
    for t in terminos:
        salida[t] = df[t[:-2]] ** 2 if t.endswith("^2") else df[t]
    return pd.DataFrame(salida, index=df.index)


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


def comparar_modelos(dder: pd.DataFrame, objetivo: str, variables: list[str], validar_: bool) -> list[dict]:
    """Ajusta lineal, lineal sobre ΔT y polinómico de 2º orden. Error medido siempre en T (°F)."""
    resultados = []
    columnas = list(dict.fromkeys(["ID", objetivo, "T_amb_F"] + variables))
    base = dder[columnas].apply(pd.to_numeric, errors="coerce")
    candidatos = [("Lineal", objetivo, variables)]
    if "T_amb_F" not in variables and base["T_amb_F"].notna().sum() >= 5:
        candidatos.append(("Lineal sobre ΔT", "dT", variables))
    candidatos.append(("Polinómico 2º orden", objetivo, variables + [f"{v}^2" for v in variables]))
    for nombre, tipo_y, terminos in candidatos:
        req = [objetivo] + variables + (["T_amb_F"] if tipo_y == "dT" else [])
        dm = base.dropna(subset=list(dict.fromkeys(req))).sort_values("ID")
        n, k = len(dm), len(terminos)
        if n < k + 3:
            continue
        X = matriz_terminos(dm, terminos)
        y = dm[objetivo] - dm["T_amb_F"] if tipo_y == "dT" else dm[objetivo]
        corte = int(round(n * 0.7)) if validar_ and n >= 10 else n
        r = regresion(X.iloc[:corte].values, y.iloc[:corte].values)
        A = np.column_stack([np.ones(n), X.values])
        pred = A @ r["beta"] + (dm["T_amb_F"].values if tipo_y == "dT" else 0)
        real = dm[objetivo].values
        rmse_aj = math.sqrt(float(((real[:corte] - pred[:corte]) ** 2).mean()))
        rmse_val = math.sqrt(float(((real[corte:] - pred[corte:]) ** 2).mean())) if corte < n else None
        resultados.append({"nombre": nombre, "tipo_y": tipo_y, "terminos": terminos, "reg": r,
                           "X": X, "dm": dm, "corte": corte, "pred": pred, "real": real,
                           "rmse_aj": rmse_aj, "rmse_val": rmse_val,
                           "criterio": rmse_val if rmse_val is not None else rmse_aj})
    return resultados


def evaluar_modelo(modelo: dict, fila: pd.DataFrame) -> float:
    X = matriz_terminos(fila, modelo["terminos"])
    valor = modelo["intercepto"] + float(np.dot(modelo["coeficientes"], X.iloc[0].values))
    if modelo.get("tipo_y") == "dT":
        valor += float(fila["T_amb_F"].iloc[0])
    return valor


def ajuste_calentamiento(t: np.ndarray, T: np.ndarray) -> dict | None:
    """T(t) = T∞ − (T∞ − T0)·e^(−t/τ). Búsqueda de τ y mínimos cuadrados lineales."""
    ok = ~(np.isnan(t) | np.isnan(T))
    t, T = t[ok], T[ok]
    if len(t) < 5 or np.ptp(t) <= 0 or np.ptp(T) < 1:
        return None
    t = t - t.min()
    mejor = None
    for tau in np.geomspace(max(np.ptp(t) / 200, 0.2), np.ptp(t) * 5, 400):
        A = np.column_stack([np.ones_like(t), np.exp(-t / tau)])
        b, *_ = np.linalg.lstsq(A, T, rcond=None)
        sse = float(((A @ b - T) ** 2).sum())
        if mejor is None or sse < mejor[0]:
            mejor = (sse, tau, b)
    sse, tau, b = mejor
    sst = float(((T - T.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst else float("nan")
    # debe ser una curva de calentamiento que llegue a estabilizarse dentro del ensayo
    if b[1] > 0 or tau > np.ptp(t) or not r2 >= 0.8:
        return None
    return {"tau_min": tau, "T_inf": b[0], "T0": b[0] + b[1], "r2": r2}


def tau_de_ensayos(dder: pd.DataFrame, col: str = "T_rod_DE_F") -> list[dict]:
    out = []
    for ens, g in dder.groupby("Ensayo"):
        g = g.dropna(subset=["t_min", col]).sort_values("t_min")
        a = ajuste_calentamiento(g["t_min"].to_numpy(float), g[col].to_numpy(float))
        if a:
            out.append({"Ensayo": ens or "(sin nombre)", **a, "n": len(g)})
    return out


# =============================================================================
# Selección del transmisor IR
# =============================================================================
def requisitos_ir(dder: pd.DataFrame, eq: dict) -> dict:
    temps = pd.concat([dder[c] for c in OBJ_TEMP]).dropna()
    t_max_obs_C = f_a_c(temps.max()) if len(temps) else None
    alarma_C, disparo_C = f_a_c(eq["alarma_F"]), f_a_c(eq["disparo_F"])
    rango_max = max(t_max_obs_C or 0, disparo_C) + float(eq["ir_margen_rango_C"])
    tamb = dder["T_amb_F"].dropna()
    rango_min = min(f_a_c(tamb.min()) if len(tamb) else 10.0, 10.0) - 5
    normales = dder.loc[dder["estado"] == 0, OBJ_TEMP].stack().dropna()
    if eq.get("ir_exactitud_manual"):
        exact, origen_ex = float(eq["ir_exactitud_manual"]), "valor fijado por el usuario"
    elif len(normales) >= 10:
        banda = alarma_C - f_a_c(np.percentile(normales, 95))
        exact = float(np.clip(banda / 3, 1.0, 3.0))
        origen_ex = (f"un tercio de la distancia entre el percentil 95 de la operación normal y la alarma "
                     f"({banda:.1f} °C), limitado entre 1 y 3 °C")
    else:
        exact, origen_ex = 2.0, "valor por defecto (aún no hay suficientes datos normales)"
    taus = tau_de_ensayos(dder)
    if taus:
        tau = min(a["tau_min"] for a in taus)
        resp = float(np.clip(tau * 60_000 / 10, 100, 5000))
        origen_resp = f"un décimo de la constante térmica más rápida medida (τ = {tau:.1f} min)"
    else:
        tau, resp, origen_resp = None, 1000.0, "valor por defecto (falta un ensayo de calentamiento)"
    spot_max = float(eq["ir_d_objetivo_mm"]) / 1.5
    ds_req = float(eq["ir_distancia_mm"]) / spot_max
    sup = eq["ir_superficie"]
    if sup.startswith("Pintada") or eq["ir_cinta"]:
        emis_req, emis_txt = "fija", "basta emisividad fija 0,95 (superficie pintada o con cinta de alta emisividad)"
    elif sup.startswith("Fundición"):
        emis_req, emis_txt = "ajustable", "se necesita emisividad ajustable (o colocar cinta de alta emisividad)"
    else:
        emis_req, emis_txt = "cinta", "metal brillante: colocar cinta de alta emisividad obligatoriamente"
    return {"t_max_obs_C": t_max_obs_C, "rango_min_C": rango_min, "rango_max_C": rango_max,
            "exactitud_C": exact, "origen_exactitud": origen_ex, "resp_ms": resp, "origen_resp": origen_resp,
            "tau_min": tau, "spot_max_mm": spot_max, "ds_req": ds_req, "emis_req": emis_req,
            "emis_txt": emis_txt, "amb_C": float(eq["ir_amb_max_C"]), "ip_min": int(eq["ir_ip_min"]),
            "salida": eq["ir_salida"], "alim_V": float(eq["ir_alimentacion_V"]),
            "t_ref_C": alarma_C, "distancia_mm": float(eq["ir_distancia_mm"])}


def evaluar_catalogo(cat: list[dict], req: dict) -> pd.DataFrame:
    filas = []
    precios = [c["Precio_USD"] for c in cat if c.get("Precio_USD")]
    for c in cat:
        exact = max(float(c["Exact_C"] or 0), float(c.get("Exact_pct") or 0) * req["t_ref_C"] / 100)
        spot = float(req["distancia_mm"]) / float(c["DS"])
        chk = {
            "Rango": c["T_min_C"] <= req["rango_min_C"] and c["T_max_C"] >= req["rango_max_C"],
            "Exactitud": exact <= req["exactitud_C"] + 1e-9,
            "Respuesta": c["Resp_ms"] <= req["resp_ms"],
            "Óptica D:S": float(c["DS"]) >= req["ds_req"],
            "Emisividad": (req["emis_req"] != "ajustable") or (c["Emis_max"] > c["Emis_min"]),
            "Salida": req["salida"] in str(c["Salidas"]),
            "Alimentación": c["V_min"] <= req["alim_V"] <= c["V_max"],
            "T. ambiente": c["Tamb_max_C"] >= req["amb_C"],
            "IP": (c["IP"] or 0) >= req["ip_min"],
        }
        cumple = all(chk.values())
        punt = 30 * min(1.0, req["exactitud_C"] / max(exact, 0.1))
        punt += 20 * min(1.0, float(c["DS"]) / (2 * max(req["ds_req"], 0.1)))
        punt += 20 if c.get("Local") else 0
        punt += 10 if c["Emis_max"] > c["Emis_min"] else 0
        punt += 10 if (c["IP"] or 0) >= 67 else 7 if (c["IP"] or 0) >= 65 else 0
        punt += 5 * (min(precios) / c["Precio_USD"]) if precios and c.get("Precio_USD") else 2.5
        # resolución de la señal: un rango más angosto reparte los 16 mA en menos grados
        span = max(float(c["T_max_C"]) - float(c["T_min_C"]), 1.0)
        punt += 5 * min(1.0, (req["rango_max_C"] - req["rango_min_C"]) / span)
        filas.append({"Modelo": c["Modelo"], "Marca": c["Marca"], "Cumple todo": cumple,
                      **{k: ("✔" if v else "✘") for k, v in chk.items()},
                      "Exactitud efectiva (°C)": round(exact, 2), "Spot a la distancia (mm)": round(spot, 1),
                      "Puntaje": round(punt, 1), "Fallas": ", ".join(k for k, v in chk.items() if not v)})
    tabla = pd.DataFrame(filas)
    if len(tabla):
        tabla = tabla.sort_values(["Cumple todo", "Puntaje"], ascending=[False, False]).reset_index(drop=True)
    return tabla


# =============================================================================
# Textos de interpretación
# =============================================================================
def fmt(x, nd=1):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}".replace(".", ",")


def muestra(datos: pd.DataFrame, n: int = 500) -> pd.DataFrame:
    """Reduce los puntos que se dibujan (los cálculos siempre usan todos los datos)."""
    if len(datos) <= n:
        return datos
    return datos.iloc[np.linspace(0, len(datos) - 1, n).astype(int)]


def texto_tarjeta(que: str, como: str, datos: str) -> None:
    st.markdown(f"""
<div class="explica">
  <div><span class="etq">Qué muestra</span>{que}</div>
  <div><span class="etq">Cómo se lee</span>{como}</div>
  <div class="datos"><span class="etq">Lo que dicen tus datos</span>{datos}</div>
</div>""", unsafe_allow_html=True)


def pendiente(x: pd.Series, y: pd.Series):
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 3 or d.iloc[:, 0].std() == 0:
        return None, None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        b = np.polyfit(d.iloc[:, 0], d.iloc[:, 1], 1)[0]
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    return b, r


# =============================================================================
# Diagnóstico con soluciones
# =============================================================================
def _num(fila: dict, c: str):
    v = fila.get(c)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def diagnosticar(fila: dict, eq: dict, hist: pd.DataFrame | None = None, mant_venc: list | None = None) -> list[dict]:
    """Reglas de diagnóstico: devuelve fallas con evidencia, causas probables y acciones recomendadas."""
    out = []
    tde, tnde = _num(fila, "T_rod_DE_F"), _num(fila, "T_rod_NDE_F")
    carga, zv, vmax = _num(fila, "carga_pct"), _num(fila, "zona_vib"), _num(fila, "Vib_max")
    t_max = max([t for t in (tde, tnde) if t is not None], default=None)
    # 1. Temperatura
    if t_max is not None and t_max >= eq["alarma_F"]:
        crit = t_max >= eq["disparo_F"]
        lado = "DE (lado bomba)" if tde is not None and t_max == tde else "NDE (lado ventilador)"
        causas = []
        if carga is not None and carga > 100:
            causas.append(f"Sobrecarga del motor ({carga:.0f} % de la corriente nominal)")
        if zv is not None and zv >= 1:
            causas.append(f"Falla mecánica: la vibración también está alta ({vmax:.2f} mm/s): rodamiento dañado o desalineación")
        causas += ["Lubricación deficiente, grasa degradada o exceso de grasa",
                   "Ventilación del motor obstruida o temperatura ambiente alta",
                   "Empuje hidráulico elevado (operación lejos del punto de máxima eficiencia)"]
        acciones = (["Detener la bomba de inmediato y dejar enfriar antes de intervenir",
                     "Verificar que el eje gire libre a mano y sin ruido"] if crit else
                    ["Aumentar la frecuencia de medición a cada 5 minutos y vigilar la tendencia"])
        acciones += ["Medir la corriente de las tres fases y compararla con la placa (3,0 A)",
                     "Escuchar el rodamiento: ruido áspero o golpeteo indica daño en pistas o bolas",
                     "Limpiar las rejillas de ventilación del motor",
                     "Si los rodamientos son sellados (2Z), programar su reemplazo; si son abiertos, relubricar sin exceso"]
        out.append({"Falla": f"Sobrecalentamiento del rodamiento {lado}", "Gravedad": 2 if crit else 1,
                    "Evidencia": f"{t_max:.1f} °F (alarma {eq['alarma_F']:.0f} °F, disparo {eq['disparo_F']:.0f} °F)",
                    "Causas": causas, "Acciones": acciones})
    # 2. Calentamiento rápido (tendencia dentro del mismo ensayo)
    if hist is not None and tde is not None and _num(fila, "t_min") is not None and len(hist):
        prev = hist[(hist["Ensayo"] == fila.get("Ensayo")) & (hist["t_min"] < fila["t_min"])].dropna(subset=["T_rod_DE_F", "t_min"])
        if len(prev):
            p = prev.sort_values("t_min").iloc[-1]
            dt = fila["t_min"] - p["t_min"]
            if dt > 0:
                tasa = (tde - p["T_rod_DE_F"]) / dt
                if tasa > 1.0 and (t_max or 0) > 120:
                    out.append({"Falla": "Calentamiento rápido del rodamiento", "Gravedad": 1,
                                "Evidencia": f"Sube {tasa:.1f} °F/min (registro anterior a los {p['t_min']:.0f} min)",
                                "Causas": ["Arranque reciente (normal en los primeros minutos)",
                                           "Fricción anormal por falta de lubricación o rodamiento dañado"],
                                "Acciones": ["Verificar si el motor acaba de arrancar",
                                             "Si sigue subiendo después de 3τ, detener e inspeccionar el rodamiento"]})
    # 3. Cavitación
    r = _num(fila, "ratio_NPSH")
    if r is not None and r < eq["npsh_normal"]:
        crit = r < eq["npsh_alerta"]
        out.append({"Falla": "Riesgo de cavitación" if crit else "Margen de NPSH reducido", "Gravedad": 2 if crit else 1,
                    "Evidencia": f"NPSHa/NPSHr = {r:.2f} (NPSHa {fila.get('NPSHa_m', 0):.2f} m)",
                    "Causas": ["Filtro o colador de succión obstruido", "Nivel bajo en el tanque de succión",
                               "Válvula de succión parcialmente cerrada o tubería de succión larga",
                               "Caudal demasiado alto (el NPSHr crece con el caudal)", "Agua caliente (mayor presión de vapor)"],
                    "Acciones": ["Revisar y limpiar el colador de succión", "Verificar el nivel del tanque",
                                 "Abrir completamente la válvula de succión (nunca regular con ella)",
                                 "Cerrar parcialmente la válvula de descarga para bajar el caudal",
                                 "Si hay ruido de grava dentro de la bomba, detenerla: la cavitación erosiona el impulsor"]})
    # 4. Vibración
    if zv is not None and zv >= 1:
        crit = zv >= 2
        causas = ["Rodamiento con daño incipiente", "Desalineación o pernos de anclaje flojos",
                  "Desbalance del impulsor (suciedad o desgaste)", "Cavitación (si el NPSH también está bajo)"]
        pico = _num(fila, "Pico_Hz")
        if pico:
            rpm = _num(fila, "rpm") or eq["motor_rpm"]
            fre = frecuencias_rodamiento(eq["rod_DE"], rpm)
            if fre:
                k, v = min(fre.items(), key=lambda kv: abs(pico - kv[1]) / kv[1])
                if abs(pico - v) / v <= 0.05:
                    causas.insert(0, f"El pico de {pico:.1f} Hz coincide con {k} ({v:.1f} Hz) del rodamiento {eq['rod_DE']}")
        out.append({"Falla": "Vibración en zona D (inaceptable)" if crit else "Vibración en zona C (investigar)",
                    "Gravedad": 2 if crit else 1, "Evidencia": f"{vmax:.2f} mm/s RMS (ISO 10816 clase I)",
                    "Causas": causas,
                    "Acciones": (["Detener la bomba y programar la revisión"] if crit else ["Repetir la medición en DE y NDE en las tres direcciones"])
                    + ["Reapretar pernos de anclaje y de la base", "Verificar alineación y que no haya roce del impulsor",
                       "Comparar el espectro con las frecuencias de falla del rodamiento"]})
    # 5. Sobrecarga
    i = _num(fila, "I_prom_A")
    if i is not None and i > eq["motor_i"]:
        crit = i > eq["motor_i_sf"]
        out.append({"Falla": "Sobrecarga del motor" if crit else "Motor sobre su corriente nominal", "Gravedad": 2 if crit else 1,
                    "Evidencia": f"{i:.2f} A (nominal {eq['motor_i']} A, factor de servicio {eq['motor_i_sf']} A)",
                    "Causas": ["Caudal excesivo (válvula de descarga muy abierta)", "Roce interno o rodamiento frenado",
                               "Voltaje bajo o desbalanceado", "Fluido más denso o viscoso"],
                    "Acciones": ["Medir el voltaje entre fases", "Cerrar parcialmente la descarga y observar la corriente",
                                 "Girar el eje a mano con el motor desenergizado para detectar roce",
                                 "Verificar el ajuste del relé térmico (el motor no tiene protección térmica propia)"]})
    # 6. Desbalance de corriente y voltaje
    db = _num(fila, "desb_I_pct")
    if db is not None and db > 10:
        out.append({"Falla": "Desbalance de corriente entre fases", "Gravedad": 2 if db > 20 else 1,
                    "Evidencia": f"{db:.1f} % de desbalance",
                    "Causas": ["Voltaje desbalanceado en la red", "Borne o contacto flojo o sulfatado", "Falla en un devanado"],
                    "Acciones": ["Medir el voltaje de las tres fases", "Reapretar bornes del motor y del contactor",
                                 "Medir la resistencia de los devanados"]})
    v = _num(fila, "V_V")
    if v is not None and abs(v - eq["motor_v"]) / eq["motor_v"] > 0.10:
        out.append({"Falla": "Voltaje fuera de rango", "Gravedad": 1, "Evidencia": f"{v:.0f} V (nominal {eq['motor_v']:.0f} V ±10 %)",
                    "Causas": ["Problema en la red o en el tablero", "Caída de tensión por conductores subdimensionados"],
                    "Acciones": ["Verificar el voltaje en el tablero y en los bornes del motor"]})
    # 7. Desempeño hidráulico
    eh = _num(fila, "E_H_pct")
    if eh is not None and fila.get("Q_fuente") == "Medido" and eh < -10:
        out.append({"Falla": "Pérdida de desempeño de la bomba", "Gravedad": 1,
                    "Evidencia": f"Altura {eh:.1f} % bajo la curva del fabricante",
                    "Causas": ["Desgaste del impulsor o de los anillos de desgaste", "Impulsor obstruido", "Aire en la succión"],
                    "Acciones": ["Revisar fugas de aire en la tubería de succión", "Programar la inspección del impulsor"]})
    # 8. Medición incoherente
    ta = _num(fila, "T_amb_F")
    ps = _num(fila, "P_succ_psi")
    if (t_max is not None and ta is not None and t_max < ta - 3) or (ps is not None and ps < -p_atm_kpa(eq) / 6.89476):
        out.append({"Falla": "Medición sospechosa (instrumento)", "Gravedad": 1,
                    "Evidencia": "Temperatura menor que la ambiente o vacío mayor que la presión atmosférica",
                    "Causas": ["Emisividad mal configurada o punto de medición sin cinta", "Lente sucio o sensor desalineado",
                               "Cable roto (lazo 4–20 mA por debajo de 4 mA)", "Manómetro dañado o mal leído"],
                    "Acciones": ["Limpiar el lente y verificar el punto con la cinta de alta emisividad",
                                 "Comparar con un termómetro de referencia", "Revisar el manómetro de succión"]})
    # 9. Mantenimiento vencido (una sola tarjeta con todas las tareas)
    if mant_venc:
        out.append({"Falla": f"Mantenimiento vencido ({len(mant_venc)} tarea{'s' if len(mant_venc) > 1 else ''})", "Gravedad": 1,
                    "Evidencia": "; ".join(f"{t['Tarea']}: {t['Estado']}" for t in mant_venc[:3]) + (" …" if len(mant_venc) > 3 else ""),
                    "Causas": ["Tareas preventivas no realizadas o no registradas a tiempo"],
                    "Acciones": [f"Realizar: {t['Tarea']}" for t in mant_venc] + ["Registrar cada tarea en «🛠️ Mantenimiento»"]})
    return sorted(out, key=lambda d: -d["Gravedad"])


def tarjetas_diagnostico(diags: list[dict]) -> None:
    for d in diags:
        st.markdown(f"""
<div class="diag {'critico' if d['Gravedad'] == 2 else ''}">
  <h4>{'🔴' if d['Gravedad'] == 2 else '🟡'} {html.escape(d['Falla'])}</h4>
  <div class="ev">{html.escape(d['Evidencia'])}</div>
  <div class="cols">
    <div><b class="t">Causas probables</b><ul>{''.join(f'<li>{html.escape(c)}</li>' for c in d['Causas'])}</ul></div>
    <div><b class="t">Qué hacer</b><ul>{''.join(f'<li>{html.escape(a)}</li>' for a in d['Acciones'])}</ul></div>
  </div>
</div>""", unsafe_allow_html=True)


# =============================================================================
# Mantenimiento preventivo
# =============================================================================
MANT_DEF = {
    "horometro_h": 0.0, "ultimo_aviso": "", "historial": [],
    "tareas": [
        {"Tarea": "Inspección visual: ruidos, fugas y temperatura al tacto", "Cada_dias": 7, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Limpieza del colador o filtro de succión", "Cada_dias": 30, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Limpieza del lente del transmisor IR y revisión de la cinta de emisividad", "Cada_dias": 90, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Reapriete de bornes, revisión de contactor y relé térmico", "Cada_dias": 180, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Verificación de pernos de anclaje y alineación", "Cada_dias": 180, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Medición de aislamiento del motor (megóhmetro)", "Cada_dias": 365, "Cada_horas": None, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Revisión del sello mecánico de la bomba", "Cada_dias": None, "Cada_horas": 2000, "Ultima_fecha": "", "Ultima_horas": None},
        {"Tarea": "Revisión de rodamientos (ruido, juego); reemplazo si son sellados", "Cada_dias": None, "Cada_horas": 4000, "Ultima_fecha": "", "Ultima_horas": None},
    ],
}


def estado_mantenimiento(mant: dict) -> pd.DataFrame:
    hoy = datetime.now().date()
    horas = float(mant.get("horometro_h") or 0)
    filas = []
    for t in mant.get("tareas", []):
        restos, textos = [], []
        if t.get("Cada_dias"):
            if t.get("Ultima_fecha"):
                d = int(t["Cada_dias"]) - (hoy - pd.to_datetime(t["Ultima_fecha"]).date()).days
                restos.append(d / max(int(t["Cada_dias"]), 1))
                textos.append(f"vence en {d} días" if d >= 0 else f"vencida hace {-d} días")
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
        if not restos:
            continue
        m = min(restos)
        nivel = 2 if m < 0 else 1 if m <= 0.15 else 0
        filas.append({"Tarea": t["Tarea"], "Frecuencia": " / ".join(x for x in [
            f"cada {t['Cada_dias']} días" if t.get("Cada_dias") else "", f"cada {t['Cada_horas']} h" if t.get("Cada_horas") else ""] if x),
            "Última vez": t.get("Ultima_fecha") or "—", "Estado": ", ".join(textos), "nivel": nivel})
    return pd.DataFrame(filas, columns=["Tarea", "Frecuencia", "Última vez", "Estado", "nivel"])


# =============================================================================
# Alertas por Telegram
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
                              json={"chat_id": chat, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True},
                              timeout=10)
            if not r.ok:
                errores.append(f"{chat}: {r.json().get('description', r.status_code)}")
        except requests.RequestException as ex:
            errores.append(f"{chat}: {ex}")
    return (not errores), ("Enviado" if not errores else "; ".join(errores))


def mensaje_alerta(fila: dict, diags: list[dict]) -> str:
    peor = max(d["Gravedad"] for d in diags)
    cab = "🔴 <b>CRÍTICO</b>" if peor == 2 else "🟡 <b>ALERTA</b>"
    lineas = [f"{cab} – Monitoreo de rodamientos ESPE", f"Registro {int(fila['ID']) if _num(fila, 'ID') is not None else ''} | {fila.get('Fecha_hora', '')}",
              f"Ensayo {html.escape(str(fila.get('Ensayo', '')))} | Operador: {html.escape(str(fila.get('Operador', '') or '—'))}", ""]
    for d in diags[:4]:
        lineas.append(f"{'🔴' if d['Gravedad'] == 2 else '🟡'} <b>{html.escape(d['Falla'])}</b>")
        lineas.append(f"   {html.escape(d['Evidencia'])}")
        lineas.append(f"   Causa probable: {html.escape(d['Causas'][0])}")
        lineas.append(f"   Acción: {html.escape(d['Acciones'][0])}")
    return "\n".join(lineas)


def registrar_alerta(cfg: dict, tipo: str, resumen: str, ok: bool, detalle: str) -> None:
    cfg.setdefault("historial", [])
    cfg["historial"] = ([{"Fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "Tipo": tipo, "Resumen": resumen,
                          "Envío": "✔" if ok else f"✘ {detalle}"}] + cfg["historial"])[:150]
    guardar_json(ARCH_ALERTAS, cfg)


# =============================================================================
# Identidad visual
# =============================================================================
CSS = """
<style>
:root { --marino:#0A1F44; --marino-2:#0D3B8C; --electrico:#1F6FEB; --celeste:#00A3FF; --rayo:#F2B705; --fondo:#F4F7FC; }
.block-container { padding-top: 1.2rem; max-width: 1450px; }
.hero { border-radius: 14px; overflow: hidden; margin-bottom: 1.1rem; box-shadow: 0 6px 24px rgba(10,31,68,.18); background:#fff; }
.hero-logos { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:.9rem 1.6rem; background:#fff; flex-wrap:wrap; }
.hero-logos img.espe { height:74px; max-width:100%; object-fit:contain; }
.hero-logos img.em { height:92px; object-fit:contain; }
.hero-rayo { height:6px; background:linear-gradient(90deg, var(--rayo) 0 18%, var(--electrico) 18% 100%); }
.hero-banda { position:relative; padding:1.5rem 1.8rem 1.4rem; color:#fff; overflow:hidden;
  background: radial-gradient(circle at 92% 20%, rgba(0,163,255,.45), transparent 42%),
              linear-gradient(120deg, var(--marino) 0%, var(--marino-2) 58%, var(--electrico) 100%); }
.hero-banda::after { content:"⚡"; position:absolute; right:1.6rem; bottom:-1.6rem; font-size:7.5rem; opacity:.12; }
.hero-carrera { font-size:.95rem; color:#CFE1FF; margin:0 0 .35rem; }
.hero-banda h1 { color:#fff !important; font-size:2.05rem; line-height:1.15; margin:0 0 .45rem; padding:0; font-weight:800; }
.hero-banda p.sub { color:#E3EEFF; margin:0; font-size:1.02rem; max-width:75ch; }
.hero-fichas { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px,1fr)); gap:.8rem; padding:1rem 1.6rem 1.2rem; background:var(--fondo); }
.ficha { background:#fff; border-radius:10px; padding:.75rem 1rem; border-left:5px solid var(--electrico); }
.ficha.docente { border-left-color:var(--rayo); }
.ficha .titulo { font-size:.8rem; color:#5A6B88; margin-bottom:.2rem; }
.ficha .valor { font-size:1.02rem; font-weight:700; color:var(--marino); }
.ficha ul { margin:.1rem 0 0 1rem; padding:0; color:var(--marino); font-weight:600; }
.ficha .vacio { color:#8A9BB8; font-style:italic; }
.stTabs [data-baseweb="tab-list"] { gap:.3rem; background:#fff; padding:.35rem; border-radius:12px; box-shadow:0 2px 10px rgba(10,31,68,.08);
  flex-wrap:wrap !important; overflow:visible !important; height:auto !important; }
.stTabs [data-baseweb="tab-list"] > div, .stTabs [role="tablist"] { flex-wrap:wrap !important; }
.stTabs [data-baseweb="tab"] { border-radius:9px; padding:.5rem .85rem; font-weight:600; color:var(--marino); }
.stTabs [aria-selected="true"] { background:linear-gradient(120deg, var(--marino-2), var(--electrico)); color:#fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none; }
h2, h3 { color:var(--marino) !important; }
h3 { border-left:5px solid var(--electrico); padding-left:.6rem !important; }
[data-testid="stMetric"] { background:#fff; border-radius:10px; padding:.7rem .9rem; border-top:4px solid var(--electrico); box-shadow:0 2px 10px rgba(10,31,68,.07); }
[data-testid="stMetricValue"] { color:var(--marino); }
[data-testid="stForm"] { background:#fff; border:1px solid #D5E2F5; border-radius:12px; }
[data-testid="stSidebar"] { background:linear-gradient(180deg, var(--marino) 0%, var(--marino-2) 100%); }
[data-testid="stSidebar"] * { color:#EAF2FF; }
[data-testid="stSidebar"] [data-testid="stMetric"] { background:rgba(255,255,255,.08); border-top-color:var(--rayo); box-shadow:none; }
[data-testid="stSidebar"] [data-testid="stMetricValue"] { color:#fff; }
[data-testid="stSidebar"] code { background:rgba(255,255,255,.12); color:#fff; }
.lateral-titulo { font-size:.78rem; color:#9FC0FF !important; margin:.6rem 0 .15rem; }
.lateral-valor { font-weight:700; color:#fff !important; }
.explica { background:#fff; border:1px solid #D5E2F5; border-radius:12px; padding:.9rem 1.1rem; margin:.2rem 0 1.4rem;
  display:grid; gap:.55rem; font-size:.95rem; color:#24324d; }
.explica .etq { display:block; font-size:.74rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--electrico); margin-bottom:.1rem; }
.explica .datos { background:#EEF4FF; border-radius:8px; padding:.6rem .8rem; border-left:4px solid var(--rayo); }
.semaforo { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px,1fr)); gap:.7rem; margin:.4rem 0 1rem; }
.luz { border-radius:12px; padding:.8rem 1rem; color:#fff; box-shadow:0 2px 10px rgba(10,31,68,.12); }
.luz .t { font-size:.78rem; opacity:.9; } .luz .v { font-size:1.35rem; font-weight:800; } .luz .s { font-size:.85rem; }
.recomendado { border-radius:14px; padding:1.2rem 1.4rem; color:#fff; margin:.5rem 0 1rem;
  background:linear-gradient(120deg, var(--marino) 0%, var(--marino-2) 60%, var(--electrico) 100%); box-shadow:0 6px 20px rgba(10,31,68,.2); }
.recomendado h2 { color:#fff !important; margin:.1rem 0 .3rem; font-size:1.7rem; }
.recomendado .k { color:#CFE1FF; font-size:.85rem; letter-spacing:.04em; text-transform:uppercase; }
.recomendado .badge { display:inline-block; background:var(--rayo); color:var(--marino); font-weight:800; border-radius:20px; padding:.15rem .7rem; margin-right:.4rem; font-size:.85rem; }
.ds { width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; font-size:.93rem; }
.ds th { text-align:left; background:#E4ECF8; color:var(--marino); padding:.45rem .7rem; width:38%; }
.ds td { padding:.45rem .7rem; border-bottom:1px solid #EDF2FA; color:#24324d; }
.st-key-nav [role="radiogroup"] { gap:.35rem; flex-wrap:wrap; background:#fff; padding:.45rem; border-radius:12px; box-shadow:0 2px 10px rgba(10,31,68,.08); }
.st-key-nav [role="radiogroup"] > label { margin:0 !important; padding:.38rem .85rem !important; border-radius:20px; border:1px solid #D5E2F5; background:#F4F7FC; cursor:pointer; }
.st-key-nav [role="radiogroup"] > label > div:first-child { display:none !important; }
.st-key-nav [role="radiogroup"] > label:has(input:checked) { background:linear-gradient(120deg, var(--marino-2), var(--electrico)); border-color:transparent; }
.st-key-nav [role="radiogroup"] > label:has(input:checked) * { color:#fff !important; }
.st-key-nav [role="radiogroup"] > label p { font-weight:600; color:var(--marino); font-size:.9rem; margin:0; }
[data-testid="stSidebar"] button { background:rgba(255,255,255,.12) !important; border:1px solid rgba(255,255,255,.35) !important; }
[data-testid="stSidebar"] button:hover { background:rgba(255,255,255,.22) !important; border-color:#F2B705 !important; }
[data-testid="stSidebar"] button * { color:#fff !important; }
.diag { background:#fff; border-radius:12px; padding:.9rem 1.1rem; margin:.5rem 0 .9rem; border-left:6px solid var(--rayo); box-shadow:0 2px 10px rgba(10,31,68,.07); }
.diag.critico { border-left-color:#D64545; }
.diag h4 { margin:0 0 .2rem; color:var(--marino); font-size:1.05rem; }
.diag .ev { color:#5A6B88; font-size:.9rem; margin-bottom:.4rem; }
.diag .cols { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px,1fr)); gap:.4rem 1.2rem; }
.diag b.t { font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; color:var(--electrico); }
.diag ul { margin:.2rem 0 0 1.1rem; padding:0; font-size:.92rem; }
.login { max-width:420px; margin:3rem auto 1rem; text-align:center; }
@media (max-width: 640px) {
  .block-container { padding-left:.6rem; padding-right:.6rem; padding-top:.6rem; }
  .hero-logos { padding:.5rem .8rem; }
  .hero-logos img.espe { height:40px; } .hero-logos img.em { height:50px; }
  .hero-banda { padding:1rem 1rem .9rem; } .hero-banda h1 { font-size:1.3rem; } .hero-banda p.sub { font-size:.85rem; }
  .hero-banda::after { font-size:4rem; bottom:-1rem; }
  .hero-fichas { padding:.6rem .8rem .8rem; gap:.5rem; }
  .st-key-nav [role="radiogroup"] > label { padding:.3rem .6rem !important; } .st-key-nav [role="radiogroup"] > label p { font-size:.8rem; }
  .luz .v { font-size:1.1rem; }
}
.pie { margin-top:2rem; padding:1rem 1.4rem; border-radius:12px; text-align:center; background:var(--marino); color:#CFE1FF; font-size:.85rem; }
.pie b { color:#fff; }
</style>
"""


def imagen_b64(nombre: str) -> str | None:
    ruta = BASE / nombre
    return "data:image/png;base64," + base64.b64encode(ruta.read_bytes()).decode() if ruta.exists() else None


def mostrar_encabezado(eq: dict) -> None:
    espe, em = imagen_b64("logo_espe.png"), imagen_b64("logo_em.png")
    logo_espe = (f'<img class="espe" src="{espe}" alt="ESPE Sede Latacunga">' if espe else
                 '<b style="color:#0A7A3B;font-size:1.4rem">Universidad de las Fuerzas Armadas ESPE – Sede Latacunga</b>')
    logo_em = f'<img class="em" src="{em}" alt="Ingeniería Electromecánica">' if em else ""
    ops = [o for o in eq.get("operadores", []) if str(o.get("Nombre", "")).strip()]
    if ops:
        operadores = "<ul>" + "".join(
            f"<li>{html.escape(str(o['Nombre']))}"
            + (f" <span style='font-weight:400;color:#5A6B88'>({html.escape(str(o.get('Función', '')))})</span>"
               if str(o.get("Función", "")).strip() else "") + "</li>" for o in ops) + "</ul>"
    else:
        operadores = '<div class="vacio">Agrégalos en «⚙️ Configuración»</div>'
    curso = " | ".join(x for x in [eq.get("asignatura", ""), f"NRC {eq['nrc']}" if eq.get("nrc") else "",
                                    eq.get("periodo", "")] if x)
    ficha_curso = (f'<div class="ficha"><div class="titulo">Asignatura</div>'
                   f'<div class="valor">{html.escape(curso)}</div></div>') if curso else ""
    st.markdown(f"""
<div class="hero">
  <div class="hero-logos">{logo_espe}{logo_em}</div>
  <div class="hero-rayo"></div>
  <div class="hero-banda">
    <p class="hero-carrera">Ingeniería Electromecánica | Departamento de Eléctrica y Electrónica</p>
    <h1>Monitoreo térmico de rodamientos y selección de transmisor IR</h1>
    <p class="sub">{html.escape(eq.get("proyecto", ""))}. Motor {html.escape(eq["motor_marca"])} {html.escape(eq["motor_modelo"])}
    acoplado a bomba {html.escape(eq["bomba_marca"])} {html.escape(eq["bomba_modelo"])}; temperaturas en °F.</p>
  </div>
  <div class="hero-fichas">
    <div class="ficha docente"><div class="titulo">Docente responsable</div><div class="valor">{DOCENTE}</div></div>
    <div class="ficha"><div class="titulo">Operadores a cargo</div>{operadores}</div>
    {ficha_curso}
  </div>
</div>""", unsafe_allow_html=True)


def tarjetas_semaforo(items: list[tuple]) -> None:
    """items: (título, valor, zona 0/1/2/None, subtítulo)"""
    bloques = ""
    for titulo, valor, zona, sub in items:
        color = COLOR_ZONA.get(zona, "#8A9BB8") if zona is not None and not (isinstance(zona, float) and np.isnan(zona)) else "#8A9BB8"
        bloques += (f'<div class="luz" style="background:{color}"><div class="t">{html.escape(titulo)}</div>'
                    f'<div class="v">{html.escape(valor)}</div><div class="s">{html.escape(sub)}</div></div>')
    st.markdown(f'<div class="semaforo">{bloques}</div>', unsafe_allow_html=True)


def ficha_datasheet(c: dict) -> str:
    filas = [
        ("Fabricante / marca", c["Marca"]), ("Modelo", c["Modelo"]), ("Tipo", c["Tipo"]),
        ("Rango de medición", f"{fmt(c['T_min_C'], 0)} a {fmt(c['T_max_C'], 0)} °C "
                              f"({fmt(c_a_f(c['T_min_C']), 0)} a {fmt(c_a_f(c['T_max_C']), 0)} °F)"),
        ("Relación óptica D:S", f"{fmt(c['DS'], 2 if float(c['DS']) % 1 else 0)} : 1"), ("Tiempo de respuesta", f"{fmt(c['Resp_ms'], 0)} ms"),
        ("Exactitud", f"±{fmt(c['Exact_C'], 1)} °C" + (f" o ±{fmt(c['Exact_pct'], 1)} % (el mayor)" if c.get("Exact_pct") else "")),
        ("Repetibilidad", f"±{fmt(c['Repet_C'], 1)} °C" if c.get("Repet_C") else "Ver hoja de datos"),
        ("Emisividad", f"{fmt(c['Emis_min'], 2)} fija" if c["Emis_max"] == c["Emis_min"]
         else f"Ajustable {fmt(c['Emis_min'], 2)} – {fmt(c['Emis_max'], 2)}"),
        ("Salidas", c["Salidas"]), ("Alimentación", f"{fmt(c['V_min'], 1)} – {fmt(c['V_max'], 1)} VDC"),
        ("Temperatura ambiente máx.", f"{fmt(c['Tamb_max_C'], 0)} °C"),
        ("Grado de protección", f"IP{int(c['IP'])}" if c.get("IP") else "No indicado en el folleto"),
        ("Montaje", c["Montaje"]), ("Proveedor en Ecuador", c.get("Proveedor_local") or "Importación"),
        ("Precio referencial", f"USD {fmt(c['Precio_USD'], 2)}" if c.get("Precio_USD") else "Solicitar cotización"),
        ("Notas", c.get("Notas", "")),
    ]
    return '<table class="ds">' + "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in filas) + "</table>"


# =============================================================================
# Informe en Word
# =============================================================================
def figuras_informe(dder: pd.DataFrame, eq: dict, modelo: dict | None) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}

    def guardar(fig, nombre):
        buf = BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=160)
        plt.close(fig)
        figs[nombre] = buf.getvalue()

    azul, marino, rayo = "#1F6FEB", "#0A1F44", "#F2B705"
    q = np.linspace(0, 80, 100)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(q, h_ref(q), color=marino, lw=2, label="Curva del fabricante")
    pts = dder.dropna(subset=["Q_gpm", "H_m"])
    if len(pts):
        ax.scatter(pts["Q_gpm"], pts["H_m"], s=12, color=azul, alpha=.6, label="Puntos medidos")
    ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("Altura (m)"), ax.grid(alpha=.3), ax.legend()
    ax.set_title("Curva H–Q Goulds 3642 y puntos de operación")
    guardar(fig, "hq")

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(CURVA["Q_gpm"], CURVA["NPSHr_m"], color="#D64545", lw=2, label="NPSHr (fabricante)")
    pts = dder.dropna(subset=["Q_gpm", "NPSHa_m"])
    if len(pts):
        ax.scatter(pts["Q_gpm"], pts["NPSHa_m"], s=12, color=azul, alpha=.6, label="NPSHa calculado")
    ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("NPSH (m)"), ax.grid(alpha=.3), ax.legend()
    ax.set_title(f"NPSH disponible vs requerido ({eq['ubicacion']}, {eq['altitud_m']:.0f} m)")
    guardar(fig, "npsh")

    temps = dder["T_rod_DE_F"].dropna()
    if len(temps):
        fig, ax = plt.subplots(figsize=(7, 3.4))
        ax.hist(temps, bins=30, color=azul, alpha=.85)
        ax.axvline(eq["alarma_F"], color=rayo, lw=2, ls="--", label="Alarma")
        ax.axvline(eq["disparo_F"], color="#D64545", lw=2, ls="--", label="Disparo")
        ax.set_xlabel("Temperatura rodamiento DE (°F)"), ax.set_ylabel("Registros"), ax.legend(), ax.grid(alpha=.3)
        ax.set_title("Distribución de temperaturas del rodamiento")
        guardar(fig, "hist")

    num = dder[[c for c in CANDIDATAS + ["T_rod_DE_F"] if c in dder]].apply(pd.to_numeric, errors="coerce")
    num = num.loc[:, (num.notna().sum() >= 5) & (num.std() > 0)]
    if num.shape[1] >= 3:
        corr = num.corr()
        fig, ax = plt.subplots(figsize=(7.2, 6.2))
        im = ax.imshow(corr, cmap="RdBu", vmin=-1, vmax=1)
        ax.set_xticks(range(len(corr))), ax.set_xticklabels(corr.columns, rotation=90, fontsize=6)
        ax.set_yticks(range(len(corr))), ax.set_yticklabels(corr.columns, fontsize=6)
        fig.colorbar(im, ax=ax, fraction=.04)
        ax.set_title("Mapa de calor de correlación")
        guardar(fig, "corr")

    if modelo:
        cols = list(dict.fromkeys([modelo["objetivo"], "T_amb_F"] + modelo["variables"]))
        dm = dder.dropna(subset=[c for c in cols if c != "T_amb_F" or modelo.get("tipo_y") == "dT"])
        if len(dm):
            pred = [evaluar_modelo(modelo, dm.iloc[[i]]) for i in range(len(dm))]
            fig, ax = plt.subplots(figsize=(5.2, 4.4))
            ax.scatter(dm[modelo["objetivo"]], pred, s=12, color=azul, alpha=.6)
            lo, hi = float(np.nanmin(pred)), float(np.nanmax(pred))
            ax.plot([lo, hi], [lo, hi], color="gray", ls="--")
            ax.set_xlabel("Temperatura medida (°F)"), ax.set_ylabel("Temperatura estimada (°F)"), ax.grid(alpha=.3)
            ax.set_title("Validación del modelo")
            guardar(fig, "modelo")
    return figs


def generar_informe(dder: pd.DataFrame, eq: dict, modelo: dict | None, req: dict,
                    tabla_ir: pd.DataFrame, cat: list[dict]) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name, estilo.font.size = "Calibri", Pt(11)
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
    fila_logos = doc.add_table(rows=1, cols=2)
    fila_logos.autofit = False
    fila_logos.cell(0, 0).width, fila_logos.cell(0, 1).width = Cm(12.6), Cm(4)
    for celda, nombre, ancho in ((fila_logos.cell(0, 0), "logo_espe.png", 8), (fila_logos.cell(0, 1), "logo_em.png", 2.4)):
        if (BASE / nombre).exists():
            p = celda.paragraphs[0]
            p.add_run().add_picture(str(BASE / nombre), width=Cm(ancho))
            if nombre == "logo_em.png":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    def titulo(texto, nivel=1):
        h = doc.add_heading(texto, level=nivel)
        for r in h.runs:
            r.font.color.rgb = RGBColor(0x0A, 0x1F, 0x44)

    def tabla(filas, encabezado=None):
        t = doc.add_table(rows=0, cols=len(filas[0]))
        t.style = "Light Grid Accent 1"
        if encabezado:
            celdas = t.add_row().cells
            for i, v in enumerate(encabezado):
                celdas[i].text = str(v)
                celdas[i].paragraphs[0].runs[0].bold = True
        for f in filas:
            celdas = t.add_row().cells
            for i, v in enumerate(f):
                celdas[i].text = str(v)
        doc.add_paragraph()

    titulo(eq.get("proyecto", "Informe"), 0)
    p = doc.add_paragraph()
    p.add_run("Universidad de las Fuerzas Armadas ESPE – Sede Latacunga\n").bold = True
    p.add_run("Departamento de Eléctrica y Electrónica | Carrera de Ingeniería Electromecánica\n")
    p.add_run(f"Docente responsable: {DOCENTE}\n")
    ops = ", ".join(o["Nombre"] for o in eq.get("operadores", []) if o.get("Nombre"))
    p.add_run(f"Operadores a cargo: {ops or '—'}\n")
    curso = " | ".join(x for x in [eq.get("asignatura"), f"NRC {eq['nrc']}" if eq.get("nrc") else "", eq.get("periodo")] if x)
    if curso:
        p.add_run(f"Asignatura: {curso}\n")
    p.add_run(f"Fecha de generación: {datetime.now():%Y-%m-%d %H:%M}")

    titulo("1. Equipo ensayado")
    tabla([
        ["Motor", f"{eq['motor_marca']} {eq['motor_modelo']}, {eq['motor_hp']} HP, {eq['motor_v']:.0f} V, "
                  f"{eq['motor_i']} A, {eq['motor_rpm']:.0f} rpm, {eq['motor_polos']} polos, aislamiento {eq['motor_aislamiento']}, "
                  f"{eq['motor_ip']}, protección térmica: {eq['motor_prot_term']}"],
        ["Bomba", f"{eq['bomba_marca']} {eq['bomba_modelo']}, index {eq['bomba_index']}, tamaño {eq['bomba_tamano']}, "
                  f"impulsor {eq['bomba_impulsor']}, serie {eq['bomba_serie']}. {eq['bomba_config']}"],
        ["Rodamientos", f"DE: {eq['rod_DE']} | NDE: {eq['rod_NDE']} "
                        f"({'confirmados' if eq.get('rod_confirmado') else 'probables, por confirmar'})"],
        ["Sitio", f"{eq['ubicacion']}, {eq['altitud_m']:.0f} m s.n.m., presión atmosférica {p_atm_kpa(eq):.1f} kPa"],
    ], ["Elemento", "Datos"])

    titulo("2. Datos registrados")
    temps = dder["T_rod_DE_F"].dropna()
    origen = ", ".join(f"{k}: {v}" for k, v in dder["Origen"].value_counts().items())
    doc.add_paragraph(f"Se analizaron {len(dder)} registros ({origen}) en {dder['Ensayo'].replace('', np.nan).nunique()} ensayos. "
                      + (f"La temperatura del rodamiento DE varió entre {temps.min():.1f} °F y {temps.max():.1f} °F "
                         f"(promedio {temps.mean():.1f} °F)." if len(temps) else ""))
    try:
        figs = figuras_informe(dder, eq, modelo)
    except ImportError:
        figs = {}
        doc.add_paragraph("(Instale matplotlib para incluir las gráficas: python -m pip install matplotlib)")
    textos = {
        "hq": "Los puntos medidos se comparan con la curva del fabricante; los que quedan por debajo indican pérdida de desempeño hidráulico.",
        "npsh": "Mientras el NPSH disponible quede por encima del requerido con margen suficiente, la bomba opera sin riesgo de cavitación.",
        "hist": "La distribución de temperaturas define el rango de medición que debe cubrir el transmisor y su relación con los límites de alarma.",
        "corr": "El mapa de correlación identifica las variables que más se relacionan con la temperatura y sustenta la selección de variables del modelo.",
        "modelo": "Cuanto más cerca estén los puntos de la diagonal, mejor estima el modelo la temperatura medida.",
    }
    for i, (k, img) in enumerate(figs.items(), start=1):
        doc.add_picture(BytesIO(img), width=Cm(15 if k != "modelo" else 10))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap = doc.add_paragraph(f"Figura {i}. {textos.get(k, '')}")
        cap.runs[0].italic = True

    titulo("3. Modelo matemático de estimación")
    if modelo:
        doc.add_paragraph(f"Tipo de modelo: {modelo.get('nombre', 'Lineal')}.")
        eqp = doc.add_paragraph()
        eqp.add_run(modelo["ecuacion"]).bold = True
        if modelo.get("tipo_y") == "dT":
            doc.add_paragraph("El modelo estima el incremento sobre el ambiente: T_rod (°F) = T_amb (°F) + ΔT estimado.")
        doc.add_paragraph(f"R² = {modelo['r2']:.4f}; RMSE de ajuste = {modelo['rmse_F']:.2f} °F"
                          + (f"; RMSE de validación = {modelo['rmse_validacion_F']:.2f} °F" if modelo.get("rmse_validacion_F") else "")
                          + f"; registros usados: {modelo['n']}.")
    else:
        doc.add_paragraph("Aún no se ha guardado un modelo.")

    titulo("4. Selección del transmisor de temperatura infrarrojo")
    tabla([
        ["Rango de medición", f"{req['rango_min_C']:.0f} a {req['rango_max_C']:.0f} °C"],
        ["Exactitud requerida", f"±{req['exactitud_C']:.1f} °C ({req['origen_exactitud']})"],
        ["Tiempo de respuesta", f"≤ {req['resp_ms']:.0f} ms ({req['origen_resp']})"],
        ["Relación D:S mínima", f"{req['ds_req']:.1f}:1 (objetivo ø{eq['ir_d_objetivo_mm']:.0f} mm a {eq['ir_distancia_mm']:.0f} mm)"],
        ["Emisividad", req["emis_txt"]], ["Salida", req["salida"]],
        ["Alimentación", f"{req['alim_V']:.0f} VDC"], ["Ambiente / protección", f"≥ {req['amb_C']:.0f} °C, ≥ IP{req['ip_min']}"],
    ], ["Requisito", "Valor"])
    if len(tabla_ir):
        cols = ["Modelo", "Cumple todo", "Exactitud efectiva (°C)", "Spot a la distancia (mm)", "Puntaje", "Fallas"]
        tabla([[("Sí" if v is True else "No" if v is False else v) for v in fila]
               for fila in tabla_ir[cols].values.tolist()], cols)
        ok = tabla_ir[tabla_ir["Cumple todo"]]
        if len(ok):
            mejor = next(c for c in cat if c["Modelo"] == ok.iloc[0]["Modelo"])
            pr = doc.add_paragraph()
            pr.add_run("Transmisor recomendado: ").bold = True
            pr.add_run(f"{mejor['Marca']} {mejor['Modelo']}. ")
            pr.add_run(f"Rango {mejor['T_min_C']} a {mejor['T_max_C']} °C, D:S {mejor['DS']}:1, respuesta {mejor['Resp_ms']} ms, "
                       f"exactitud ±{mejor['Exact_C']} °C, salida {mejor['Salidas']}, "
                       f"{'IP' + str(mejor['IP']) if mejor.get('IP') else ''}. "
                       f"{('Disponible en ' + mejor['Proveedor_local'] + '.') if mejor.get('Proveedor_local') else ''}")
        else:
            doc.add_paragraph("Ningún modelo del catálogo cumple todos los requisitos; revisar los requisitos o ampliar el catálogo.")

    titulo("5. Conclusiones generadas a partir de los datos")
    for c in conclusiones(dder, eq, modelo, req, tabla_ir):
        doc.add_paragraph(c, style="List Bullet")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def conclusiones(dder, eq, modelo, req, tabla_ir) -> list[str]:
    out = []
    if eq.get("motor_prot_term", "").lower().startswith("ningun"):
        out.append("El motor no tiene protección térmica propia, lo que justifica vigilar la temperatura de sus rodamientos con un transmisor.")
    taus = tau_de_ensayos(dder)
    if taus:
        t = taus[0]
        out.append(f"En el ensayo {t['Ensayo']} el rodamiento alcanzó el 95 % de su temperatura estable en unos "
                   f"{3 * t['tau_min']:.0f} min (τ = {t['tau_min']:.1f} min), por lo que cualquier transmisor con respuesta "
                   f"menor a {req['resp_ms']:.0f} ms es suficiente.")
    r = dder["ratio_NPSH"].dropna()
    if len(r):
        out.append(f"Con la presión atmosférica de {eq['ubicacion']} ({p_atm_kpa(eq):.1f} kPa) la relación NPSHa/NPSHr mínima fue "
                   f"{r.min():.2f}; {int((r < eq['npsh_alerta']).sum())} registros quedaron en zona de riesgo de cavitación.")
    if modelo:
        out.append(f"El modelo {modelo.get('nombre', '').lower()} estima la temperatura con un error típico de "
                   f"{modelo['rmse_F']:.1f} °F (R² = {modelo['r2']:.3f}).")
    if len(tabla_ir) and tabla_ir["Cumple todo"].any():
        out.append(f"El transmisor que mejor cumple los requisitos es el {tabla_ir.iloc[0]['Modelo']}.")
    if (dder["Origen"] == "Prueba").any():
        out.append("Parte de los datos analizados son sintéticos de prueba; los resultados deben confirmarse con ensayos reales.")
    return out


# =============================================================================
# Estado de la sesión y datos
# =============================================================================
if "editor_ver" not in st.session_state:
    st.session_state.editor_ver = 0
if msg := st.session_state.pop("msg", None):
    st.toast(msg, icon="💾")

def cargar_equipo() -> dict:
    datos = cargar_json(ARCH_EQUIPO, {})
    if datos and datos.get("version") != 3:  # archivo de la versión anterior: conservar solo lo del usuario
        conservar = ("operadores", "asignatura", "nrc", "periodo", "proyecto", "alarma_F", "disparo_F")
        datos = {k: v for k, v in datos.items() if k in conservar}
        datos = {**DEF_EQUIPO, **datos, "version": 3}
        guardar_json(ARCH_EQUIPO, datos)
    return {**DEF_EQUIPO, **datos, "version": 3}


st.markdown(CSS, unsafe_allow_html=True)
CLAVE_APP = str(secreto("app_password", "") or "")
if CLAVE_APP and not st.session_state.get("autenticado"):
    logo_l = imagen_b64("logo_espe.png")
    st.markdown(f'<div class="login">{"<img src=" + chr(34) + logo_l + chr(34) + " style=max-width:100%>" if logo_l else ""}'
                '<h2>Monitoreo de rodamientos</h2><p>Ingeniería Electromecánica – ESPE Latacunga</p></div>', unsafe_allow_html=True)
    _c = st.columns([1, 2, 1])
    with _c[1].form("login"):
        clave_in = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar", type="primary", width="stretch"):
            if clave_in == CLAVE_APP:
                st.session_state["autenticado"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    st.stop()

try:
    equipo = cargar_equipo()
    catalogo = cargar_json(ARCH_CATALOGO, CATALOGO_DEF)
    alertas_cfg = cargar_json(ARCH_ALERTAS, ALERTAS_DEF)
    mant = cargar_json(ARCH_MANT, MANT_DEF)
except Exception as ex:
    st.error(f"No se pudo conectar con la base de datos: {ex}")
    st.stop()
modelo_guardado = cargar_json(ARCH_MODELO, None)
if modelo_guardado and "terminos" not in modelo_guardado:  # modelo de la versión anterior
    modelo_guardado = None
df = cargar_datos()
mant_estado = estado_mantenimiento(mant)
mant_venc = mant_estado[mant_estado["nivel"] == 2].to_dict("records")
# Evita que el traductor automático del navegador (Edge/Chrome) modifique la página: rompe las tablas editables
try:
    import streamlit.components.v1 as components
    components.html("""<script>
      const d = window.parent.document;
      d.documentElement.lang = "es";
      d.documentElement.setAttribute("translate", "no");
      d.documentElement.classList.add("notranslate");
      if (!d.querySelector('meta[name="google"]')) {
        const m = d.createElement("meta"); m.name = "google"; m.content = "notranslate"; d.head.appendChild(m);
      }
    </script>""", height=0)
except Exception:
    pass
mostrar_encabezado(equipo)

with st.sidebar:
    if (logo := imagen_b64("logo_em.png")):
        st.markdown(f'<div style="text-align:center;margin-bottom:.4rem"><img src="{logo}" '
                    f'style="width:120px;border-radius:50%;background:#fff;padding:6px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="lateral-titulo">Docente responsable</div>'
                f'<div class="lateral-valor">{DOCENTE}</div>', unsafe_allow_html=True)
    ops = [o["Nombre"] for o in equipo.get("operadores", []) if str(o.get("Nombre", "")).strip()]
    if ops:
        st.markdown('<div class="lateral-titulo">Operadores a cargo</div>' +
                    "".join(f'<div class="lateral-valor">• {html.escape(str(n))}</div>' for n in ops),
                    unsafe_allow_html=True)
    st.divider()
    st.caption("☁️ Datos en la nube (Supabase)" if NUBE else "💻 Datos en esta computadora")
    if st.button("🔄 Actualizar datos", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    origenes = ["Reales", "Prueba", "Todos"]
    hay_real = (df["Origen"] == "Real").any()
    filtro = st.radio("Datos a analizar", origenes, index=0 if hay_real else 2, horizontal=True)
    st.metric("Registros reales", int((df["Origen"] == "Real").sum()))
    st.metric("Registros de prueba", int((df["Origen"] == "Prueba").sum()))
    st.divider()
    st.caption("°F = 1,8·°C + 32  |  ΔT(°F) = 1,8·ΔT(°C)")

dder_todo = calcular_derivadas(df, equipo)
if filtro == "Reales":
    dder = dder_todo[dder_todo["Origen"] == "Real"].copy()
elif filtro == "Prueba":
    dder = dder_todo[dder_todo["Origen"] == "Prueba"].copy()
else:
    dder = dder_todo.copy()
req_ir = requisitos_ir(dder, equipo)
tabla_ir = evaluar_catalogo(catalogo, req_ir)

SECCIONES = ["🏠 Inicio", "➕ Registrar", "🩺 Diagnóstico", "🛠️ Mantenimiento", "📊 Gráficas", "🔍 Modelo",
             "🎯 Estimador", "🌡️ Transmisor IR", "📋 Datos", "🔔 Alertas", "⚙️ Configuración", "📥 Importar",
             "📄 Informe"]
with st.container(key="nav"):
    nav = st.radio("Sección", SECCIONES, horizontal=True, label_visibility="collapsed", key="seccion")

# Recordatorio diario de mantenimiento por Telegram (se envía la primera vez que alguien abre la app en el día)
hoy_txt = datetime.now().strftime("%Y-%m-%d")
if alertas_cfg.get("activo") and mant_venc and mant.get("ultimo_aviso") != hoy_txt:
    texto = "🛠️ <b>Mantenimiento pendiente</b> – Monitoreo de rodamientos ESPE\n" + "\n".join(
        f"• {html.escape(t['Tarea'])}: {html.escape(t['Estado'])}" for t in mant_venc)
    ok_, det_ = telegram_enviar(texto, alertas_cfg)
    mant["ultimo_aviso"] = hoy_txt
    guardar_json(ARCH_MANT, mant)
    registrar_alerta(alertas_cfg, "Mantenimiento", f"{len(mant_venc)} tareas vencidas", ok_, det_)

# =============================================================================
# 🏠 Inicio
# =============================================================================
if nav == "🏠 Inicio":
    st.subheader("Estado general del equipo")
    if dder.empty:
        st.info("Todavía no hay registros en el conjunto seleccionado. Agrega mediciones en «➕ Registrar» "
                "o carga los datos de prueba en «📥 Importar».")
    else:
        ult = dder.iloc[-1].to_dict()
        tde = ult.get("T_rod_DE_F")
        tarjetas_semaforo([
            ("Temperatura rodamiento DE", f"{fmt(tde)} °F", ult.get("zona_T"),
             f"Alarma {equipo['alarma_F']:.0f} °F | ΔT {fmt(ult.get('dT_DE_F'))} °F"),
            ("Cavitación (NPSHa/NPSHr)", fmt(ult.get("ratio_NPSH"), 2), ult.get("zona_NPSH"),
             f"Margen {fmt(ult.get('margen_NPSH_m'), 2)} m"),
            ("Vibración máxima", f"{fmt(ult.get('Vib_max'), 2)} mm/s", ult.get("zona_vib"), "ISO 10816 clase I"),
            ("Carga del motor", f"{fmt(ult.get('carga_pct'), 0)} %", ult.get("zona_carga"),
             f"{fmt(ult.get('I_prom_A'), 2)} A de {equipo['motor_i']} A"),
            ("Estado global", TEXTO_ZONA.get(ult.get("estado"), "Sin datos"), ult.get("estado"),
             f"Registro {int(ult['ID']) if not pd.isna(ult['ID']) else '—'} | {ult.get('Fecha_hora', '')}"),
        ])
        diags_u = diagnosticar(ult, equipo, dder_todo, mant_venc)
        if diags_u:
            st.markdown(f"**{len(diags_u)} hallazgo(s) en el último registro.** El más importante:")
            tarjetas_diagnostico(diags_u[:1])
            if len(diags_u) > 1:
                st.caption("Ver todos en «🩺 Diagnóstico».")
        else:
            st.success("El último registro no presenta fallas y el mantenimiento está al día.")
        c = st.columns(2)
        serie = dder.dropna(subset=["T_rod_DE_F"]).tail(300).reset_index(drop=True)
        if len(serie) >= 2:
            serie["n"] = serie.index + 1
            linea = alt.Chart(serie).mark_line(color="#1F6FEB").encode(
                x=alt.X("n:Q", title="Registro"), y=alt.Y("T_rod_DE_F:Q", title="°F", scale=alt.Scale(zero=False)),
                tooltip=["ID", "Fecha_hora", alt.Tooltip("T_rod_DE_F:Q", format=".1f")])
            regla = alt.Chart(pd.DataFrame({"y": [equipo["alarma_F"]]})).mark_rule(color="#F2B705", strokeDash=[6, 4]).encode(y="y:Q")
            c[0].markdown("**Temperatura del rodamiento (últimos registros)**")
            c[0].altair_chart(linea + regla, width="stretch")
        conteo = dder["estado_txt"].value_counts().reset_index()
        conteo.columns = ["Estado", "Registros"]
        c[1].markdown("**Distribución de estados**")
        c[1].altair_chart(alt.Chart(conteo).mark_bar().encode(
            x=alt.X("Registros:Q"), y=alt.Y("Estado:N", sort=["Normal", "Alerta", "Crítico", "Sin datos"]),
            color=alt.Color("Estado:N", scale=alt.Scale(domain=["Normal", "Alerta", "Crítico", "Sin datos"],
                                                        range=["#2E9E5B", "#F2B705", "#D64545", "#8A9BB8"]), legend=None),
            tooltip=["Estado", "Registros"]), width="stretch")
        ok = tabla_ir[tabla_ir["Cumple todo"]] if len(tabla_ir) else tabla_ir
        if len(ok):
            st.info(f"Transmisor IR recomendado con los datos actuales: **{ok.iloc[0]['Marca']} {ok.iloc[0]['Modelo']}** "
                    "(detalle en «🌡️ Transmisor IR»).")

# =============================================================================
# 👥 Operadores
# =============================================================================
if nav == "⚙️ Configuración":
    st.subheader("Responsables del proyecto")
    c = st.columns([1, 2])
    c[0].markdown(f"**Docente responsable:** {DOCENTE}")
    c[1].info("El docente responsable es fijo. Agrega abajo a los integrantes del grupo; aparecerán en el "
              "encabezado, en el informe y podrás elegirlos al registrar cada medición.")
    st.markdown("**Operadores a cargo**")
    clave_ops = f"ops_{st.session_state.editor_ver}"
    ops_edit = st.data_editor(
        pd.DataFrame(equipo.get("operadores", []), columns=["Nombre", "Función"]),
        num_rows="dynamic", hide_index=True, width="stretch", key=clave_ops,
        column_config={"Nombre": st.column_config.TextColumn("Nombre completo", required=True),
                       "Función": st.column_config.SelectboxColumn(
                           "Función", options=["Coordinador", "Operador de ensayo", "Registro de datos",
                                               "Instrumentación", "Análisis del modelo"])})
    cambios = st.session_state.get(clave_ops, {})
    if cambios and (cambios.get("edited_rows") or cambios.get("added_rows") or cambios.get("deleted_rows")):
        equipo["operadores"] = [o for o in ops_edit.fillna("").to_dict("records") if str(o.get("Nombre", "")).strip()]
        guardar_json(ARCH_EQUIPO, equipo)
        st.session_state.editor_ver += 1
        st.session_state["msg"] = "Operadores guardados"
        st.rerun()
    st.markdown("**Datos de la asignatura** (se muestran en el encabezado y en el informe)")
    with st.form("form_curso"):
        c = st.columns([3, 1, 1])
        asig = c[0].text_input("Asignatura", equipo.get("asignatura", ""))
        nrc = c[1].text_input("NRC", equipo.get("nrc", ""))
        per = c[2].text_input("Período", equipo.get("periodo", ""))
        proy = st.text_area("Título del proyecto", equipo.get("proyecto", ""), height=70)
        if st.form_submit_button("Guardar datos de la asignatura", type="primary"):
            equipo.update({"asignatura": asig.strip(), "nrc": nrc.strip(), "periodo": per.strip(), "proyecto": proy.strip()})
            guardar_json(ARCH_EQUIPO, equipo)
            st.session_state["msg"] = "Datos de la asignatura guardados"
            st.rerun()

# =============================================================================
# ⚙️ Datos técnicos
# =============================================================================
if nav == "⚙️ Configuración":
    st.subheader("Datos de placa, rodamientos, sitio y límites")
    st.caption("Vienen precargados con las placas del motor Emerson P55CST-1247 y de la bomba Goulds 3642.")
    with st.form("form_equipo"):
        e = dict(equipo)
        st.markdown("**Motor (placa)**")
        c = st.columns(4)
        e["motor_marca"] = c[0].text_input("Fabricante", e["motor_marca"])
        e["motor_modelo"] = c[1].text_input("Modelo", e["motor_modelo"])
        e["motor_hp"] = c[2].number_input("Potencia (HP)", value=float(e["motor_hp"]), step=0.25)
        e["motor_v"] = c[3].number_input("Voltaje de operación (V)", value=float(e["motor_v"]))
        c = st.columns(4)
        e["motor_i"] = c[0].number_input("Corriente nominal (A)", value=float(e["motor_i"]), step=0.1,
                                         help="Placa: 2,7–3,0 A en 208–230 V; 1,5 A en 460 V")
        e["motor_i_sf"] = c[1].number_input("Corriente con factor de servicio (A)", value=float(e["motor_i_sf"]), step=0.1,
                                            help="Placa: 3,6–3,4 A en 208–230 V; 1,7 A en 460 V")
        e["motor_rpm"] = c[2].number_input("Velocidad nominal (rpm)", value=float(e["motor_rpm"]))
        e["motor_polos"] = c[3].selectbox("Polos", [2, 4, 6], index=[2, 4, 6].index(int(e["motor_polos"])))
        c = st.columns(4)
        e["motor_f"] = c[0].number_input("Frecuencia (Hz)", value=float(e["motor_f"]))
        e["motor_fp"] = c[1].number_input("Factor de potencia típico", value=float(e["motor_fp"]), min_value=0.1,
                                          max_value=1.0, step=0.01, help="No figura en la placa; se usa si no se mide")
        e["motor_aislamiento"] = c[2].text_input("Clase de aislamiento", e["motor_aislamiento"])
        e["motor_prot_term"] = c[3].text_input("Protección térmica", e["motor_prot_term"])
        st.markdown("**Bomba (placa)**")
        c = st.columns(4)
        e["bomba_marca"] = c[0].text_input("Fabricante bomba", e["bomba_marca"])
        e["bomba_modelo"] = c[1].text_input("Modelo bomba", e["bomba_modelo"])
        e["bomba_index"] = c[2].text_input("Index", e["bomba_index"])
        e["bomba_serie"] = c[3].text_input("Número de serie", e["bomba_serie"])
        c = st.columns(4)
        e["bomba_tamano"] = c[0].text_input("Tamaño", e["bomba_tamano"])
        e["bomba_impulsor"] = c[1].text_input("Diámetro del impulsor", e["bomba_impulsor"])
        e["bomba_alabes"] = c[2].number_input("Número de álabes Z (para BPF)", value=e["bomba_alabes"], min_value=1,
                                              step=1, help="Contar al desarmar o consultar a Goulds")
        e["d_succion_mm"] = c[3].number_input("Diámetro interior de succión (mm)", value=float(e["d_succion_mm"]),
                                              help="1½\" cédula 40 ≈ 40,9 mm")
        st.markdown("**Rodamientos del motor** (la bomba es close-coupled: estos rodamientos soportan también al impulsor)")
        c = st.columns(4)
        opciones = list(BD_RODAMIENTOS)
        e["rod_DE"] = c[0].selectbox("Rodamiento DE (lado bomba)", opciones, index=opciones.index(e["rod_DE"]) if e["rod_DE"] in opciones else 1)
        e["rod_NDE"] = c[1].selectbox("Rodamiento NDE (lado ventilador)", opciones, index=opciones.index(e["rod_NDE"]) if e["rod_NDE"] in opciones else 0)
        e["rod_confirmado"] = c[2].checkbox("Designación confirmada", value=bool(e["rod_confirmado"]))
        e["grasa"] = c[3].text_input("Tipo de grasa", e["grasa"])
        st.markdown("**Sitio y fluido**")
        c = st.columns(4)
        e["ubicacion"] = c[0].text_input("Ubicación", e["ubicacion"])
        e["altitud_m"] = c[1].number_input("Altitud (m s.n.m.)", value=float(e["altitud_m"]), step=10.0)
        e["p_baro_kpa"] = c[2].number_input("Presión barométrica medida (kPa, opcional)", value=e["p_baro_kpa"], step=0.1)
        e["t_agua_C"] = c[3].number_input("Temperatura típica del agua (°C)", value=float(e["t_agua_C"]))
        st.markdown("**Límites de los semáforos**")
        c = st.columns(4)
        e["alarma_F"] = c[0].number_input("Alarma temperatura (°F)", value=float(e["alarma_F"]))
        e["disparo_F"] = c[1].number_input("Disparo temperatura (°F)", value=float(e["disparo_F"]))
        e["npsh_normal"] = c[2].number_input("NPSHa/NPSHr normal ≥", value=float(e["npsh_normal"]), step=0.05)
        e["npsh_alerta"] = c[3].number_input("NPSHa/NPSHr alerta ≥", value=float(e["npsh_alerta"]), step=0.05)
        c = st.columns(3)
        e["iso_A"] = c[0].number_input("ISO zona A ≤ (mm/s)", value=float(e["iso_A"]), step=0.01)
        e["iso_B"] = c[1].number_input("ISO zona B ≤ (mm/s)", value=float(e["iso_B"]), step=0.1)
        e["iso_C"] = c[2].number_input("ISO zona C ≤ (mm/s)", value=float(e["iso_C"]), step=0.1)
        if st.form_submit_button("Guardar datos técnicos", type="primary"):
            guardar_json(ARCH_EQUIPO, e)
            st.session_state["msg"] = "Datos técnicos guardados"
            st.rerun()
    c = st.columns(3)
    c[0].metric("Presión atmosférica del sitio", f"{fmt(p_atm_kpa(equipo))} kPa", f"{fmt(p_atm_kpa(equipo) / 6.89476, 2)} psi", delta_color="off")
    c[1].metric("Velocidad síncrona", f"{120 * equipo['motor_f'] / equipo['motor_polos']:.0f} rpm")
    c[2].metric("Deslizamiento nominal", f"{fmt((1 - equipo['motor_rpm'] / (120 * equipo['motor_f'] / equipo['motor_polos'])) * 100)} %")
    with st.expander("Curva de la bomba usada como referencia (Goulds 3642, impulsor 3 5/8\", 3500 rpm)"):
        st.dataframe(CURVA.rename(columns={"Q_gpm": "Caudal (GPM)", "H_m": "Altura (m)", "Eficiencia_pct": "Eficiencia (%)",
                                           "NPSHr_m": "NPSHr (m)"}), hide_index=True, width="stretch")
        st.caption("Digitalización aproximada del folleto Goulds/Xylem tomada del documento del docente; "
                   "la eficiencia y el NPSHr no son datos certificados.")

# =============================================================================
# ➕ Nuevo registro
# =============================================================================
if nav == "➕ Registrar":
    st.subheader("Agregar una medición")
    c = st.columns(3)
    u_t = c[0].radio("Unidad de temperatura", ["°F", "°C"], horizontal=True)
    u_p = c[1].radio("Unidad de los manómetros", ["psi", "bar", "kPa"], horizontal=True)
    u_q = c[2].radio("Unidad del caudal", ["L/min", "GPM"], horizontal=True)
    A_PSI = {"psi": 1.0, "bar": 14.5038, "kPa": 0.145038}
    st.caption("Se guarda siempre en °F, psi y L/min. Deja vacío lo que no midas. La presión de succión es manométrica: "
               "si el manómetro marca vacío, ingrésala con signo negativo.")
    nombres = [o["Nombre"] for o in equipo.get("operadores", []) if str(o.get("Nombre", "")).strip()]
    ult_ens = df["Ensayo"].iloc[-1] if len(df) and df["Ensayo"].iloc[-1] else "E1"
    with st.form("form_registro", clear_on_submit=True):
        st.markdown("**Ensayo**")
        c = st.columns(5)
        ensayo = c[0].text_input("Ensayo", value=ult_ens)
        operador = c[1].selectbox("Operador", nombres or ["(sin operadores)"])
        instr = c[2].selectbox("Instrumento de temperatura", ["Termómetro IR portátil", "Termocupla de contacto",
                                                               "Pt100 de contacto", "Cámara termográfica", "Otro"])
        t_min = c[3].number_input("Tiempo desde el arranque (min)", min_value=0.0, value=None, step=1.0)
        apert = c[4].number_input("Apertura válvula (%)", 0.0, 100.0, value=None, step=5.0)
        st.markdown("**Eléctricas**")
        c = st.columns(6)
        V = c[0].number_input("Voltaje línea (V)", value=None, step=1.0)
        I1 = c[1].number_input("Corriente L1 (A)", value=None, step=0.01)
        I2 = c[2].number_input("Corriente L2 (A)", value=None, step=0.01)
        I3 = c[3].number_input("Corriente L3 (A)", value=None, step=0.01)
        FP = c[4].number_input("Factor de potencia", value=None, min_value=0.0, max_value=1.0, step=0.01)
        P = c[5].number_input("Potencia activa (kW)", value=None, step=0.01)
        c = st.columns(6)
        f = c[0].number_input("Frecuencia (Hz)", value=None, step=0.1)
        rpm = c[1].number_input("Velocidad (rpm)", value=None, step=1.0)
        st.markdown("**Hidráulicas**")
        c = st.columns(4)
        ps = c[0].number_input(f"Presión succión ({u_p})", value=None, step=0.1)
        pdes = c[1].number_input(f"Presión descarga ({u_p})", value=None, step=0.1)
        q = c[2].number_input(f"Caudal ({u_q}), si hay caudalímetro", value=None, step=0.1)
        tw = c[3].number_input(f"Temperatura del agua ({u_t})", value=None, step=0.1)
        st.markdown("**Vibraciones (mm/s RMS)**")
        c = st.columns(4)
        vs = c[0].number_input("Bomba succión", value=None, step=0.01)
        vd = c[1].number_input("Bomba descarga", value=None, step=0.01)
        pico = c[2].number_input("Pico espectral (Hz, opcional)", value=None, step=0.1)
        bpf = c[3].number_input("Amplitud en BPF (mm/s, opcional)", value=None, step=0.001)
        c = st.columns(4)
        vdeh = c[0].number_input("Motor DE horizontal", value=None, step=0.01)
        vdev = c[1].number_input("Motor DE vertical", value=None, step=0.01)
        vdea = c[2].number_input("Motor DE axial", value=None, step=0.01)
        adeg = c[3].number_input("Aceleración DE (g)", value=None, step=0.001)
        c = st.columns(4)
        vndeh = c[0].number_input("Motor NDE horizontal", value=None, step=0.01)
        vndev = c[1].number_input("Motor NDE vertical", value=None, step=0.01)
        vndea = c[2].number_input("Motor NDE axial", value=None, step=0.01)
        andeg = c[3].number_input("Aceleración NDE (g)", value=None, step=0.001)
        st.markdown("**Temperaturas**")
        c = st.columns(3)
        ta = c[0].number_input(f"Ambiente ({u_t})", value=None, step=0.1)
        tde = c[1].number_input(f"Rodamiento DE – lado bomba ({u_t})", value=None, step=0.1)
        tnde = c[2].number_input(f"Rodamiento NDE – lado ventilador ({u_t})", value=None, step=0.1)
        obs = st.text_input("Observaciones (ruido, olor, fuga, emisividad usada, etc.)")
        if st.form_submit_button("Guardar medición", type="primary"):
            ct = (lambda x: c_a_f(x)) if u_t == "°C" else (lambda x: x)

            def n(x, conv=lambda y: y):
                return np.nan if x is None else float(conv(x))
            corrientes = [x for x in (I1, I2, I3) if x is not None]
            fila = {
                "ID": np.nan, "Fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Origen": "Real",
                "Ensayo": ensayo.strip(), "Operador": "" if operador == "(sin operadores)" else operador,
                "Instrumento_T": instr, "t_min": n(t_min), "Apertura_valvula_pct": n(apert),
                "V_V": n(V), "I_A": float(np.mean(corrientes)) if corrientes else np.nan,
                "I_L1_A": n(I1), "I_L2_A": n(I2), "I_L3_A": n(I3), "f_Hz": n(f), "FP": n(FP), "P_kW": n(P),
                "rpm": n(rpm), "Q_Lmin": n(q, lambda y: y * 3.78541 if u_q == "GPM" else y),
                "P_succ_psi": n(ps, lambda y: y * A_PSI[u_p]), "P_desc_psi": n(pdes, lambda y: y * A_PSI[u_p]),
                "T_agua_F": n(tw, ct), "Vib_succ_mms": n(vs), "Vib_desc_mms": n(vd),
                "Vib_DE_H_mms": n(vdeh), "Vib_DE_V_mms": n(vdev), "Vib_DE_A_mms": n(vdea),
                "Vib_NDE_H_mms": n(vndeh), "Vib_NDE_V_mms": n(vndev), "Vib_NDE_A_mms": n(vndea),
                "Acel_DE_g": n(adeg), "Acel_NDE_g": n(andeg), "Pico_Hz": n(pico), "Amp_BPF_mms": n(bpf),
                "T_amb_F": n(ta, ct), "T_rod_DE_F": n(tde, ct), "T_rod_NDE_F": n(tnde, ct), "Observaciones": obs,
            }
            if tde is None and tnde is None:
                st.error("Falta la temperatura de al menos un rodamiento: es la variable que se quiere estimar.")
            else:
                guardado = guardar_datos(pd.concat([df, pd.DataFrame([fila])], ignore_index=True))
                nuevo = calcular_derivadas(guardado.tail(1), equipo).iloc[0].to_dict()
                diags_n = diagnosticar(nuevo, equipo, dder_todo)
                st.session_state["diag_registro"] = diags_n
                if alertas_cfg.get("activo") and diags_n and max(d["Gravedad"] for d in diags_n) >= int(alertas_cfg.get("nivel_min", 1)):
                    ok_, det_ = telegram_enviar(mensaje_alerta(nuevo, diags_n), alertas_cfg)
                    registrar_alerta(alertas_cfg, "Medición", "; ".join(d["Falla"] for d in diags_n[:3]), ok_, det_)
                    st.session_state["envio_registro"] = (ok_, det_)
                st.session_state["msg"] = "Medición guardada"
                st.rerun()
    diags_n = st.session_state.pop("diag_registro", None)
    if diags_n:
        st.markdown("**Diagnóstico de la medición guardada**")
        tarjetas_diagnostico(diags_n)
        envio = st.session_state.pop("envio_registro", None)
        if envio:
            (st.success if envio[0] else st.error)("Alerta enviada por Telegram." if envio[0] else f"No se pudo enviar la alerta: {envio[1]}")
    elif diags_n is not None:
        st.success("Medición guardada sin fallas detectadas.")
    if len(df):
        st.markdown("**Últimas mediciones**")
        st.dataframe(df.tail(5), hide_index=True, width="stretch")

# =============================================================================
# 📋 Tabla de datos
# =============================================================================
if nav == "📋 Datos":
    st.subheader("Tabla de datos editable")
    st.write("Corrige cualquier celda, agrega filas con **+** o selecciona filas y presiona **Supr**. Todo se guarda solo.")
    if len(df) > 1500:
        st.caption(f"Hay {len(df)} registros; por rapidez se muestran los registros del conjunto «{filtro}».")
    clave = f"editor_{st.session_state.editor_ver}"
    vista = df if filtro == "Todos" else df[df["Origen"] == ("Real" if filtro == "Reales" else "Prueba")]
    config = {c: st.column_config.NumberColumn(ETIQUETAS.get(c, c), format="%.2f") for c in NUMERICAS}
    config["ID"] = st.column_config.NumberColumn("ID", disabled=True, format="%d")
    config["Origen"] = st.column_config.SelectboxColumn("Origen", options=["Real", "Prueba"])
    editado = st.data_editor(vista, num_rows="dynamic", width="stretch", hide_index=True, key=clave, column_config=config)
    cambios = st.session_state.get(clave, {})
    if cambios and (cambios.get("edited_rows") or cambios.get("added_rows") or cambios.get("deleted_rows")):
        resto = df.drop(index=vista.index)
        guardar_datos(pd.concat([resto, editado], ignore_index=True).sort_values("ID", na_position="last"))
        st.session_state.editor_ver += 1
        st.session_state["msg"] = "Cambios guardados"
        st.rerun()
    with st.expander("Variables calculadas (hidráulica, NPSH, carga, vibración, estados)"):
        cols_d = ["ID", "Ensayo", "Q_gpm", "Q_fuente", "H_m", "E_H_pct", "NPSHa_m", "NPSHr_m", "ratio_NPSH",
                  "carga_pct", "desb_I_pct", "s_pct", "eta_global_pct", "Vib_max", "dT_DE_F", "estado_txt"]
        st.dataframe(dder[cols_d].round(3), hide_index=True, width="stretch")
    c = st.columns(2)
    c[0].download_button("Descargar CSV (con variables calculadas)", dder.to_csv(index=False).encode("utf-8-sig"),
                         "datos_rodamientos_completo.csv", "text/csv")
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            dder.to_excel(w, sheet_name="Datos", index=False)
            pd.DataFrame([(k, str(v)) for k, v in equipo.items()], columns=["Parámetro", "Valor"]).to_excel(w, sheet_name="Equipo", index=False)
        c[1].download_button("Descargar Excel", buf.getvalue(), "datos_rodamientos.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except ImportError:
        c[1].caption("Para exportar a Excel instala openpyxl.")

# =============================================================================
# 📊 Gráficas y análisis
# =============================================================================
if nav == "📊 Gráficas":
    st.subheader("Gráficas con interpretación")
    if dder.empty:
        st.info("No hay datos en el conjunto seleccionado.")
    else:
        seccion = st.radio("Sección", ["💧 Hidráulica y NPSH", "🌡️ Térmico", "📳 Vibraciones", "⚡ Eléctrico",
                                        "🟥 Mapas de calor"], horizontal=True, label_visibility="collapsed")
        if len(dder) > 500:
            st.caption(f"Las gráficas de puntos muestran 500 de los {len(dder)} registros para que la página responda rápido; "
                       "los cálculos y textos usan todos los datos.")
        # ---------------- Hidráulica
        if seccion == "💧 Hidráulica y NPSH":
            st.markdown("### Curva H–Q del fabricante y puntos de operación")
            qq = np.linspace(0, 80, 81)
            curva = pd.DataFrame({"Q_gpm": qq, "H_m": h_ref(qq)})
            pts = muestra(dder.dropna(subset=["Q_gpm", "H_m"]))
            base = alt.Chart(curva).mark_line(color="#0A1F44", strokeWidth=3).encode(
                x=alt.X("Q_gpm:Q", title="Caudal (GPM)"), y=alt.Y("H_m:Q", title="Altura (m)", scale=alt.Scale(zero=False)))
            capa = base
            if len(pts):
                capa = base + alt.Chart(pts).mark_circle(size=45, opacity=.6).encode(
                    x="Q_gpm:Q", y="H_m:Q", color=alt.Color("Q_fuente:N", scale=alt.Scale(range=PALETA), title="Caudal"),
                    tooltip=["ID", alt.Tooltip("Q_gpm:Q", format=".1f"), alt.Tooltip("H_m:Q", format=".2f"),
                             alt.Tooltip("E_H_pct:Q", format=".1f")])
            st.altair_chart(capa, width="stretch")
            eh = dder["E_H_pct"].dropna()
            medidos = (dder["Q_fuente"] == "Medido").sum()
            texto_tarjeta(
                "La curva negra es la altura que la bomba Goulds 3642 entrega en buen estado para cada caudal; "
                "los puntos son las alturas calculadas con tus manómetros, H = (P<sub>desc</sub> − P<sub>succ</sub>)·0,703.",
                "Si los puntos caen sobre la curva, la bomba rinde como nueva. Si caen por debajo (error negativo), la bomba entrega "
                "menos energía de la esperada: desgaste del impulsor, recirculación o cavitación. Cuando no hay caudalímetro, "
                "el caudal se estima con la propia curva y los puntos quedan sobre ella, así que este análisis solo es válido con caudal medido.",
                (f"Error de altura promedio {fmt(eh.mean())} %; {int((eh < -5).sum())} de {len(eh)} registros están más de 5 % bajo la curva. "
                 if len(eh) else "Aún no hay presiones registradas. ")
                + (f"Caudal medido en {medidos} registros." if medidos else "Ningún registro tiene caudal medido."))

            st.markdown("### NPSH disponible vs NPSH requerido")
            npsh_c = CURVA[["Q_gpm", "NPSHr_m"]].copy()
            lin = alt.Chart(npsh_c).mark_line(color="#D64545", strokeWidth=3).encode(
                x=alt.X("Q_gpm:Q", title="Caudal (GPM)"), y=alt.Y("NPSHr_m:Q", title="NPSH (m)"))
            capa = lin + alt.Chart(npsh_c.assign(lim=npsh_c["NPSHr_m"] * equipo["npsh_normal"])).mark_line(
                color="#F2B705", strokeDash=[6, 4]).encode(x="Q_gpm:Q", y="lim:Q")
            pts = muestra(dder.dropna(subset=["Q_gpm", "NPSHa_m"]))
            if len(pts):
                capa = capa + alt.Chart(pts).mark_circle(size=45, opacity=.6).encode(
                    x="Q_gpm:Q", y="NPSHa_m:Q",
                    color=alt.Color("zona_NPSH:O", scale=alt.Scale(domain=[0, 1, 2], range=list(COLOR_ZONA.values())), title="Zona"),
                    tooltip=["ID", alt.Tooltip("NPSHa_m:Q", format=".2f"), alt.Tooltip("ratio_NPSH:Q", format=".2f")])
            st.altair_chart(capa, width="stretch")
            r = dder["ratio_NPSH"].dropna()
            texto_tarjeta(
                "Línea roja: energía mínima absoluta que la bomba necesita en la succión para no cavitar (NPSHr, del fabricante). "
                "Línea amarilla: NPSHr × " + fmt(equipo["npsh_normal"], 2) + ", margen recomendado. Puntos: NPSH disponible calculado con "
                "la presión absoluta de succión, NPSHa = (P<sub>atm</sub> + P<sub>succ</sub> − P<sub>v</sub>)/ρg + v²/2g.",
                "Mientras los puntos estén sobre la línea amarilla no hay riesgo. Entre amarilla y roja hay alerta; bajo la roja la bomba "
                "cavita: se forman burbujas de vapor que implotan, dañan el impulsor y aumentan la vibración. El NPSHr crece con el caudal, "
                "por eso la cavitación aparece primero a caudales altos o con succión restringida.",
                f"Presión atmosférica en {html.escape(equipo['ubicacion'])}: {fmt(p_atm_kpa(equipo))} kPa ({fmt(p_atm_kpa(equipo) / 6.89476, 2)} psi), "
                f"unos {fmt((101.325 - p_atm_kpa(equipo)) * 1000 / (998 * G))} m menos de NPSHa que a nivel del mar. "
                + (f"Relación NPSHa/NPSHr mínima {fmt(r.min(), 2)}; {int((r < equipo['npsh_alerta']).sum())} registros en riesgo y "
                   f"{int(((r >= equipo['npsh_alerta']) & (r < equipo['npsh_normal'])).sum())} en alerta." if len(r) else "Sin presiones de succión registradas."))

            st.markdown("### Eficiencia global y potencia hidráulica")
            pts = muestra(dder.dropna(subset=["Q_gpm", "eta_global_pct"]))
            if len(pts):
                st.altair_chart(alt.Chart(pts).mark_circle(size=45, opacity=.6, color="#1F6FEB").encode(
                    x=alt.X("Q_gpm:Q", title="Caudal (GPM)"), y=alt.Y("eta_global_pct:Q", title="Eficiencia global (%)"),
                    tooltip=["ID", alt.Tooltip("P_hid_W:Q", format=".0f"), alt.Tooltip("P_elec_kW:Q", format=".3f")]), width="stretch")
            ef = dder["eta_global_pct"].dropna()
            texto_tarjeta("Relación entre la potencia que recibe el agua (ρ·g·Q·H) y la potencia eléctrica que absorbe el motor.",
                          "Incluye las pérdidas del motor y de la bomba. Una caída progresiva a igual caudal indica degradación "
                          "(rodamientos, desgaste o roce). La curva del fabricante llega a unos 63 % solo de bomba.",
                          f"Eficiencia global promedio {fmt(ef.mean())} % (mín. {fmt(ef.min())} %, máx. {fmt(ef.max())} %)." if len(ef)
                          else "Se necesitan presiones y datos eléctricos para calcularla.")

        # ---------------- Térmico
        if seccion == "🌡️ Térmico":
            st.markdown("### Curva de calentamiento y constante de tiempo")
            taus = tau_de_ensayos(dder)
            ens_disp = sorted(e for e in dder["Ensayo"].unique() if e)
            sel = st.selectbox("Ensayo", ens_disp, key="ens_cal") if ens_disp else None
            if sel:
                g = dder[dder["Ensayo"] == sel].dropna(subset=["t_min", "T_rod_DE_F"]).sort_values("t_min")
                a = next((x for x in taus if x["Ensayo"] == sel), None)
                capa = alt.Chart(muestra(g)).mark_circle(size=50, color="#1F6FEB").encode(
                    x=alt.X("t_min:Q", title="Tiempo (min)"), y=alt.Y("T_rod_DE_F:Q", title="T rodamiento DE (°F)", scale=alt.Scale(zero=False)),
                    tooltip=["ID", "t_min", alt.Tooltip("T_rod_DE_F:Q", format=".1f")])
                if a and len(g):
                    tt = np.linspace(0, g["t_min"].max() - g["t_min"].min(), 200)
                    ajuste = pd.DataFrame({"t_min": tt + g["t_min"].min(),
                                           "T": a["T_inf"] - (a["T_inf"] - a["T0"]) * np.exp(-tt / a["tau_min"])})
                    capa = capa + alt.Chart(ajuste).mark_line(color="#0A1F44").encode(x="t_min:Q", y="T:Q")
                st.altair_chart(capa, width="stretch")
                texto_tarjeta(
                    "Cómo sube la temperatura del rodamiento desde el arranque y el ajuste T(t) = T<sub>∞</sub> − (T<sub>∞</sub> − T<sub>0</sub>)·e<sup>−t/τ</sup>.",
                    "τ (tau) es la constante de tiempo térmica: en τ minutos se recorre el 63 % del calentamiento y en 3τ el 95 %. "
                    "T<sub>∞</sub> es la temperatura a la que se estabiliza. Un T<sub>∞</sub> mayor en ensayos repetidos con la misma carga "
                    "indica más fricción (falta de grasa o daño). τ también define qué tan rápido debe responder el transmisor.",
                    (f"τ = {fmt(a['tau_min'])} min, temperatura estable {fmt(a['T_inf'])} °F, estabiliza (95 %) en unos {fmt(3 * a['tau_min'], 0)} min; "
                     f"ajuste R² = {fmt(a['r2'], 3)}. El transmisor debe responder en menos de {fmt(req_ir['resp_ms'], 0)} ms, "
                     "requisito que cumplen todos los modelos del catálogo." if a else
                     "No se pudo ajustar: registra al menos 5 puntos de un mismo ensayo con el tiempo desde el arranque y una subida de temperatura."))
            st.markdown("### Distribución de temperaturas y rango del transmisor")
            temps = dder[["T_rod_DE_F"]].dropna()
            if len(temps):
                cuenta, bordes = np.histogram(temps["T_rod_DE_F"], bins=30)
                hb = pd.DataFrame({"x0": bordes[:-1], "x1": bordes[1:], "n": cuenta})
                hist = alt.Chart(hb).mark_rect(color="#1F6FEB").encode(
                    x=alt.X("x0:Q", title="T rodamiento DE (°F)", scale=alt.Scale(zero=False)), x2="x1:Q",
                    y=alt.Y("n:Q", title="Registros"), y2=alt.datum(0))
                lim = alt.Chart(pd.DataFrame({"x": [equipo["alarma_F"], equipo["disparo_F"]], "L": ["Alarma", "Disparo"]})).mark_rule(
                    strokeDash=[6, 4], strokeWidth=2).encode(x="x:Q", color=alt.Color("L:N", scale=alt.Scale(range=["#F2B705", "#D64545"]), title=None))
                st.altair_chart(hist + lim, width="stretch")
                tt = temps["T_rod_DE_F"]
                texto_tarjeta("Cuántas veces se midió cada temperatura y dónde están los límites de alarma y disparo.",
                              "La forma muestra la operación habitual. Una cola larga hacia la derecha son eventos de calentamiento. "
                              "El transmisor debe cubrir con margen tanto lo medido como el límite de disparo.",
                              f"Mínimo {fmt(tt.min())} °F, máximo {fmt(tt.max())} °F, percentil 95 {fmt(np.percentile(tt, 95))} °F; "
                              f"{int((tt >= equipo['alarma_F']).sum())} registros sobre la alarma. Rango requerido para el transmisor: "
                              f"{fmt(req_ir['rango_min_C'], 0)} a {fmt(req_ir['rango_max_C'], 0)} °C "
                              f"({fmt(c_a_f(req_ir['rango_min_C']), 0)} a {fmt(c_a_f(req_ir['rango_max_C']), 0)} °F).")
            st.markdown("### Incremento de temperatura vs carga del motor")
            xcarga = "dT_DE_F" if dder["dT_DE_F"].notna().sum() >= 3 else "T_rod_DE_F"
            pts = muestra(dder.dropna(subset=["I_prom_A", xcarga]))
            if len(pts):
                sc = alt.Chart(pts).mark_circle(size=45, opacity=.6).encode(
                    x=alt.X("I_prom_A:Q", title="Corriente (A)", scale=alt.Scale(zero=False)),
                    y=alt.Y(f"{xcarga}:Q", title=ETIQUETAS[xcarga], scale=alt.Scale(zero=False)),
                    color=alt.Color("estado_txt:N", scale=alt.Scale(domain=["Normal", "Alerta", "Crítico", "Sin datos"],
                                                                    range=["#2E9E5B", "#F2B705", "#D64545", "#8A9BB8"]), title="Estado"))
                st.altair_chart(sc + sc.transform_regression("I_prom_A", xcarga).mark_line(color="#0A1F44"), width="stretch")
            b, rr = pendiente(dder["I_prom_A"], dder[xcarga])
            texto_tarjeta("Relación entre la carga eléctrica del motor y el calentamiento del rodamiento.",
                          "A más carga, más pérdidas (I²R en el rotor, que se conducen por el eje) y más carga mecánica sobre el rodamiento, "
                          "así que la temperatura sube. Si un punto queda muy por encima de la tendencia, el calor no se explica por la "
                          "carga: es una señal de falla mecánica o de lubricación.",
                          f"La temperatura sube {fmt(b, 2)} °F por cada amperio adicional (r = {fmt(rr, 2)})." if b is not None else
                          "Se necesitan corriente y temperatura en al menos 3 registros.")
            st.markdown("### Temperatura vs vibración")
            vcol = "Vib_motor_max" if dder["Vib_motor_max"].notna().sum() >= 3 else "Vib_max"
            pts = muestra(dder.dropna(subset=[vcol, "T_rod_DE_F"]))
            if len(pts):
                sc = alt.Chart(pts).mark_circle(size=45, opacity=.6, color="#1F6FEB").encode(
                    x=alt.X(f"{vcol}:Q", title=ETIQUETAS[vcol]), y=alt.Y("T_rod_DE_F:Q", title="T rodamiento DE (°F)", scale=alt.Scale(zero=False)))
                st.altair_chart(sc + sc.transform_regression(vcol, "T_rod_DE_F").mark_line(color="#0A1F44"), width="stretch")
            b, rr = pendiente(dder[vcol], dder["T_rod_DE_F"])
            texto_tarjeta("Si el calentamiento acompaña al aumento de vibración.",
                          "Un rodamiento que se degrada vibra más y se calienta más: ambas suben juntas. Si la vibración sube sin "
                          "calentamiento, la causa suele ser hidráulica (cavitación) o desalineación; si la temperatura sube sin vibración, "
                          "suele ser carga o exceso/falta de grasa.",
                          f"{fmt(b, 2)} °F por cada mm/s (r = {fmt(rr, 2)})." if b is not None else "Faltan datos de vibración.")

        # ---------------- Vibraciones
        if seccion == "📳 Vibraciones":
            st.markdown("### Tendencia de vibración sobre las zonas ISO")
            cols_v = [c for c in VIB_MOTOR + VIB_BOMBA if dder[c].notna().any()]
            if cols_v:
                lv = muestra(dder, 400).reset_index(drop=True).assign(n=lambda x: x.index + 1).melt(
                    id_vars=["n", "ID"], value_vars=cols_v, var_name="Punto", value_name="mm/s").dropna()
                lv["Punto"] = lv["Punto"].map(ETIQUETAS)
                zonas = pd.DataFrame({"y0": [0, equipo["iso_A"], equipo["iso_B"], equipo["iso_C"]],
                                      "y1": [equipo["iso_A"], equipo["iso_B"], equipo["iso_C"], max(equipo["iso_C"] * 1.6, lv["mm/s"].max() * 1.05)],
                                      "Zona": ["A", "B", "C", "D"]})
                fondo = alt.Chart(zonas).mark_rect(opacity=.15).encode(
                    y="y0:Q", y2="y1:Q", color=alt.Color("Zona:N", scale=alt.Scale(range=["#2E9E5B", "#7BC67E", "#F2B705", "#D64545"])))
                lineas = alt.Chart(lv).mark_line(point=len(lv) < 200).encode(
                    x=alt.X("n:Q", title="Registro"), y=alt.Y("mm/s:Q", title="Vibración (mm/s RMS)"),
                    strokeDash="Punto:N", detail="Punto:N", tooltip=["ID", "Punto", alt.Tooltip("mm/s:Q", format=".2f")])
                st.altair_chart(fondo + lineas, width="stretch")
            vm = dder["Vib_max"].dropna()
            zv = dder["zona_vib"].dropna()
            texto_tarjeta(
                "La vibración global de cada punto de medición sobre las zonas de severidad de ISO 10816 para máquinas pequeñas (clase I).",
                f"Zona A (≤ {fmt(equipo['iso_A'], 2)} mm/s): máquina nueva. B (≤ {fmt(equipo['iso_B'], 1)}): operación aceptable. "
                f"C (≤ {fmt(equipo['iso_C'], 1)}): no apta para operación prolongada, investigar. D: riesgo de daño. "
                "Importa más la tendencia que el valor aislado: un aumento sostenido anticipa la falla.",
                (f"Máximo {fmt(vm.max(), 2)} mm/s; {int((zv == 0).sum())} registros en zonas A/B, {int((zv == 1).sum())} en C y "
                 f"{int((zv == 2).sum())} en D." if len(vm) else "Sin vibraciones registradas.")
                + ("" if dder[VIB_MOTOR].notna().any().any() else " Aún no hay mediciones en los rodamientos del motor (DE/NDE)."))

            st.markdown("### Frecuencias de falla del rodamiento")
            rpm_med = dder["rpm"].dropna()
            rpm_uso = float(rpm_med.iloc[-1]) if len(rpm_med) else float(equipo["motor_rpm"])
            c = st.columns(2)
            rod = c[0].selectbox("Rodamiento", [f"DE – {equipo['rod_DE']}", f"NDE – {equipo['rod_NDE']}"])
            rpm_uso = c[1].number_input("Velocidad (rpm)", value=rpm_uso, step=1.0)
            frec = frecuencias_rodamiento(rod.split("– ")[1], rpm_uso)
            picos = dder["Pico_Hz"].dropna()
            pico = float(picos.iloc[-1]) if len(picos) else None
            if frec:
                tf = pd.DataFrame({"Frecuencia": list(frec), "Hz": list(frec.values())})
                barras = alt.Chart(tf).mark_bar(color="#1F6FEB").encode(
                    x=alt.X("Hz:Q"), y=alt.Y("Frecuencia:N", sort=None, title=None), tooltip=[alt.Tooltip("Hz:Q", format=".2f")])
                capa = barras
                if pico:
                    capa = barras + alt.Chart(pd.DataFrame({"x": [pico]})).mark_rule(color="#D64545", strokeWidth=3).encode(x="x:Q")
                st.altair_chart(capa, width="stretch")
                if equipo.get("bomba_alabes"):
                    st.caption(f"Frecuencia de paso de álabes BPF = Z·rpm/60 = {fmt(equipo['bomba_alabes'] * rpm_uso / 60)} Hz "
                               "(ahí se busca el aumento de amplitud por cavitación).")
                cercana = None
                if pico:
                    dif = {k: abs(pico - v) / v * 100 for k, v in frec.items()}
                    cercana = min(dif, key=dif.get)
                g_ = BD_RODAMIENTOS[rod.split("– ")[1]]
                texto_tarjeta(
                    f"Frecuencias a las que vibra un rodamiento {rod.split('– ')[1]} ({g_['n']} bolas, d = {g_['d']} mm, D = {g_['D']} mm) "
                    "cuando tiene un defecto en cada componente, a la velocidad indicada. La línea roja es el último pico medido.",
                    "Un pico que coincide (±2 %) con BPFO indica daño en la pista exterior; con BPFI, en la interior; con BSF, en las bolas; "
                    "con FTF, en la jaula. Se confirma con armónicos y bandas laterales, que requieren un espectro de alta frecuencia.",
                    (f"El pico de {fmt(pico)} Hz está a {fmt(dif[cercana])} % de {cercana}: "
                     + ("coincidencia fuerte, revisar el rodamiento." if dif[cercana] <= 2 else "coincidencia posible, vigilar." if dif[cercana] <= 5
                        else "no coincide con ninguna frecuencia de falla.")) if cercana else
                    f"BPFO = {fmt(frec['BPFO (pista exterior)'])} Hz y BPFI = {fmt(frec['BPFI (pista interior)'])} Hz a {fmt(rpm_uso, 0)} rpm. "
                    "Registra un pico espectral para compararlo.")

        # ---------------- Eléctrico
        if seccion == "⚡ Eléctrico":
            st.markdown("### Carga del motor respecto a la placa")
            pts = muestra(dder.dropna(subset=["carga_pct"]), 600).reset_index(drop=True)
            if len(pts):
                pts["n"] = pts.index + 1
                lin = alt.Chart(pts).mark_line(color="#1F6FEB").encode(x=alt.X("n:Q", title="Registro"),
                                                                        y=alt.Y("carga_pct:Q", title="Carga (% de I nominal)"))
                lim = alt.Chart(pd.DataFrame({"y": [100, equipo["motor_i_sf"] / equipo["motor_i"] * 100],
                                              "L": ["Nominal", "Factor de servicio"]})).mark_rule(strokeDash=[6, 4]).encode(
                    y="y:Q", color=alt.Color("L:N", scale=alt.Scale(range=["#F2B705", "#D64545"]), title=None))
                st.altair_chart(lin + lim, width="stretch")
            cp = dder["carga_pct"].dropna()
            texto_tarjeta(
                f"Corriente medida como porcentaje de la corriente nominal de placa ({equipo['motor_i']} A).",
                "Bajo 100 % el motor trabaja dentro de su diseño. Entre 100 % y la línea roja usa su factor de servicio "
                f"({equipo['motor_sf']}), lo que calienta más el bobinado y los rodamientos. Sobre la línea roja hay sobrecarga.",
                f"Carga promedio {fmt(cp.mean(), 0)} %, máxima {fmt(cp.max(), 0)} %; {int((cp > 100).sum())} registros sobre la nominal."
                if len(cp) else "Sin corrientes registradas.")
            st.markdown("### Desbalance de corriente entre fases")
            pts = muestra(dder.dropna(subset=["desb_I_pct"]), 300).reset_index(drop=True)
            if len(pts):
                pts["n"] = pts.index + 1
                st.altair_chart(alt.Chart(pts).mark_bar(color="#0D3B8C").encode(
                    x=alt.X("n:Q", title="Registro"), y=alt.Y("desb_I_pct:Q", title="Desbalance (%)")), width="stretch")
            db = dder["desb_I_pct"].dropna()
            texto_tarjeta("Máxima desviación de una fase respecto al promedio de las tres corrientes.",
                          "Un desbalance de corriente sobre 10 % suele venir de voltajes desbalanceados o problemas de conexión; "
                          "genera calentamiento adicional del motor que también llega a los rodamientos.",
                          f"Desbalance promedio {fmt(db.mean())} %, máximo {fmt(db.max())} %." if len(db) else
                          "Registra las tres corrientes para calcularlo.")

        # ---------------- Mapas de calor
        if seccion == "🟥 Mapas de calor":
            st.markdown("### Mapa de calor de correlación")
            num = dder[[c for c in CANDIDATAS + OBJ_TEMP]].apply(pd.to_numeric, errors="coerce")
            num = num.loc[:, (num.notna().sum() >= 3) & (num.std() > 0)]
            if num.shape[1] >= 3:
                corr = num.corr()
                mapa = corr.rename_axis("Var1").reset_index().melt(id_vars="Var1", var_name="Var2", value_name="r")
                basec = alt.Chart(mapa).encode(x=alt.X("Var1:N", sort=None, title=None), y=alt.Y("Var2:N", sort=None, title=None))
                celdas_c = basec.mark_rect().encode(color=alt.Color("r:Q", scale=alt.Scale(scheme="redblue", domain=[-1, 1])),
                                                    tooltip=["Var1", "Var2", alt.Tooltip("r:Q", format=".2f")])
                if len(corr) <= 16:
                    celdas_c = celdas_c + basec.mark_text(fontSize=9).encode(text=alt.Text("r:Q", format=".1f"))
                st.altair_chart(celdas_c.properties(height=24 * len(corr) + 40), width="stretch")
                rt = corr["T_rod_DE_F"].drop(OBJ_TEMP, errors="ignore").dropna() if "T_rod_DE_F" in corr else pd.Series(dtype=float)
                top = rt.abs().sort_values(ascending=False).head(3)
                texto_tarjeta("El coeficiente de correlación r entre cada par de variables, de −1 (azul… rojo según signo) a +1.",
                              "Cerca de +1: suben juntas. Cerca de −1: una sube cuando la otra baja. Cerca de 0: no hay relación lineal. "
                              "Las variables con |r| alto frente a la temperatura son las candidatas para el modelo; dos variables muy "
                              "correlacionadas entre sí son redundantes.",
                              "Las variables más relacionadas con la temperatura del rodamiento DE son: "
                              + ", ".join(f"{ETIQUETAS.get(k, k)} (r = {fmt(rt[k], 2)})" for k in top.index) + "." if len(top) else
                              "Falta la temperatura del rodamiento DE.")
            else:
                st.info("Se necesitan al menos 3 variables con datos que cambien.")
            st.markdown("### Mapa de calor de temperatura por condición de operación")
            opciones = [c for c in CANDIDATAS if dder[c].notna().sum() >= 5 and dder[c].std() > 0]
            if len(opciones) >= 2 and dder["T_rod_DE_F"].notna().sum() >= 5:
                c = st.columns(2)
                ix = opciones.index("Q_gpm") if "Q_gpm" in opciones else 0
                iy = opciones.index("t_min") if "t_min" in opciones else 1
                vx = c[0].selectbox("Eje X", opciones, index=ix, format_func=lambda v: ETIQUETAS.get(v, v), key="hx")
                vy = c[1].selectbox("Eje Y", opciones, index=iy, format_func=lambda v: ETIQUETAS.get(v, v), key="hy")
                dmap = dder.dropna(subset=[vx, vy, "T_rod_DE_F"])
                bx = pd.cut(dmap[vx], 18)
                by = pd.cut(dmap[vy], 18)
                celdas = dmap.groupby([bx, by], observed=True)["T_rod_DE_F"].agg(["mean", "count"]).reset_index()
                celdas["x0"] = celdas[vx].apply(lambda i: i.left)
                celdas["x1"] = celdas[vx].apply(lambda i: i.right)
                celdas["y0"] = celdas[vy].apply(lambda i: i.left)
                celdas["y1"] = celdas[vy].apply(lambda i: i.right)
                celdas = celdas[["x0", "x1", "y0", "y1", "mean", "count"]].astype(float)
                st.altair_chart(alt.Chart(celdas).mark_rect().encode(
                    x=alt.X("x0:Q", title=ETIQUETAS.get(vx, vx), scale=alt.Scale(zero=False)), x2="x1:Q",
                    y=alt.Y("y0:Q", title=ETIQUETAS.get(vy, vy), scale=alt.Scale(zero=False)), y2="y1:Q",
                    color=alt.Color("mean:Q", scale=alt.Scale(scheme="turbo"), title="T media (°F)"),
                    tooltip=[alt.Tooltip("mean:Q", format=".1f", title="T media °F"), alt.Tooltip("count:Q", title="Registros")]
                ).properties(height=380), width="stretch")
                grp = dmap.groupby(pd.cut(dmap[vx], 6), observed=True)["T_rod_DE_F"].mean()
                texto_tarjeta("La temperatura media del rodamiento (color) en cada combinación de dos condiciones de operación.",
                              "Las celdas rojas son las condiciones que más calientan el rodamiento. Sirve para decidir en qué condiciones "
                              "conviene más vigilar y para comprobar que el modelo captura esas zonas.",
                              f"La temperatura media va de {fmt(grp.min())} °F a {fmt(grp.max())} °F a lo largo de "
                              f"{ETIQUETAS.get(vx, vx).lower()}." if len(grp) else "")
            st.markdown("### Mapa de calor de estado por día y hora")
            fechas = pd.to_datetime(dder["Fecha_hora"], errors="coerce")
            de = dder.assign(Dia=fechas.dt.strftime("%Y-%m-%d"), Hora=fechas.dt.hour).dropna(subset=["Dia", "Hora", "estado"])
            if len(de):
                agg = de.groupby(["Dia", "Hora"], as_index=False)["estado"].max()
                dias = sorted(agg["Dia"].unique())
                if len(dias) > 60:
                    st.caption(f"Se muestran los últimos 60 de {len(dias)} días.")
                    agg = agg[agg["Dia"].isin(dias[-60:])]
                agg["Estado"] = agg["estado"].map(TEXTO_ZONA)
                st.altair_chart(alt.Chart(agg).mark_rect().encode(
                    x=alt.X("Hora:O", title="Hora del día"), y=alt.Y("Dia:O", title="Día", sort="descending"),
                    color=alt.Color("Estado:N", scale=alt.Scale(domain=["Normal", "Alerta", "Crítico"], range=list(COLOR_ZONA.values()))),
                    tooltip=["Dia", "Hora", "Estado"]).properties(height=min(900, 14 * agg["Dia"].nunique() + 60)), width="stretch")
                texto_tarjeta("El peor estado registrado en cada hora de cada día, combinando temperatura, cavitación, vibración y carga.",
                              "Permite ver de un vistazo cuándo empezaron los problemas y si se repiten a ciertas horas o días "
                              "(por ejemplo, con mayor demanda de caudal).",
                              f"{int((agg['estado'] == 2).sum())} horas en estado crítico y {int((agg['estado'] == 1).sum())} en alerta "
                              f"de {len(agg)} horas con datos.")

# =============================================================================
# 🔍 Correlación y modelo
# =============================================================================
if nav == "🔍 Modelo":
    st.subheader("1. Variables que mejor se relacionan con la temperatura")
    num = dder[CANDIDATAS + OBJ_TEMP].apply(pd.to_numeric, errors="coerce")
    num = num.loc[:, (num.notna().sum() >= 3) & (num.std() > 0)]
    objetivos = [o for o in OBJ_TEMP if o in num.columns]
    if len(num) < 5 or not objetivos:
        st.info("Se necesitan al menos 5 mediciones con temperatura de rodamiento y variables que cambien.")
    else:
        c = st.columns(2)
        metodo = c[0].radio("Coeficiente", ["pearson", "spearman"], horizontal=True,
                            format_func=lambda m: "Pearson (lineal)" if m == "pearson" else "Spearman (monótona)")
        objetivo = c[1].selectbox("Temperatura a estimar", objetivos, format_func=lambda v: ETIQUETAS[v])
        corr = num.corr(method=metodo)
        predictoras = [c for c in num.columns if c not in OBJ_TEMP]
        ranking = pd.DataFrame({"Variable": predictoras, "Descripción": [ETIQUETAS.get(v, v) for v in predictoras],
                                "r": [corr.loc[v, objetivo] for v in predictoras]}).dropna()
        ranking["|r|"] = ranking["r"].abs()
        ranking["Correlación"] = pd.cut(ranking["|r|"], [-0.01, 0.2, 0.4, 0.7, 1.01],
                                        labels=["Muy débil", "Débil", "Moderada", "Fuerte"]).astype(str)
        ranking = ranking.sort_values("|r|", ascending=False).reset_index(drop=True)
        cc = st.columns([3, 2])
        cc[0].altair_chart(alt.Chart(ranking).mark_bar().encode(
            x=alt.X("r:Q", scale=alt.Scale(domain=[-1, 1])), y=alt.Y("Descripción:N", sort="-x", title=None),
            color=alt.condition(alt.datum.r > 0, alt.value("#1F6FEB"), alt.value("#D64545")),
            tooltip=["Variable", alt.Tooltip("r:Q", format=".3f"), "Correlación"]), width="stretch")
        cc[1].dataframe(ranking[["Variable", "r", "Correlación"]].round(3), hide_index=True, width="stretch")

        st.subheader("2. Comparación de modelos y ecuación en °F")
        sugeridas = []  # las de mayor |r| que no sean redundantes entre sí (|r| < 0,9)
        for v in ranking["Variable"]:
            if v != "T_amb_F" and all(abs(corr.loc[v, u]) < 0.9 for u in sugeridas):
                sugeridas.append(v)
            if len(sugeridas) == 3:
                break
        vars_x = st.multiselect("Variables del modelo (empieza por las de mayor |r|)", predictoras, default=sugeridas,
                                format_func=lambda v: f"{v} — {ETIQUETAS.get(v, v)}")
        validar_ = st.checkbox("Validar: ajustar con el 70 % de los datos y probar con el 30 % restante", value=True)
        if vars_x:
            res = comparar_modelos(dder, objetivo, vars_x, validar_)
            if not res:
                st.warning("No hay suficientes registros completos para esas variables.")
            else:
                comp = pd.DataFrame([{"Modelo": r["nombre"], "Términos": len(r["terminos"]) + 1, "R² ajuste": r["reg"]["r2"],
                                      "RMSE ajuste (°F)": r["rmse_aj"], "RMSE validación (°F)": r["rmse_val"],
                                      "Registros": len(r["dm"])} for r in res])
                mejor_i = int(np.argmin([r["criterio"] for r in res]))
                st.dataframe(comp.round(4), hide_index=True, width="stretch")
                st.caption(f"Recomendado: **{res[mejor_i]['nombre']}**, por tener el menor error "
                           f"{'en validación' if res[mejor_i]['rmse_val'] is not None else 'de ajuste'}. "
                           "Un modelo más complejo solo vale la pena si baja el error en validación, no solo en ajuste.")
                elegido = st.radio("Modelo a revisar", [r["nombre"] for r in res], index=mejor_i, horizontal=True)
                r = next(x for x in res if x["nombre"] == elegido)
                reg = r["reg"]
                nombre_y = "ΔT_F" if r["tipo_y"] == "dT" else objetivo
                ecu = ecuacion_texto(nombre_y, float(reg["beta"][0]), reg["beta"][1:], r["terminos"])
                st.code(ecu, language=None)
                if r["tipo_y"] == "dT":
                    st.caption("Este modelo estima el incremento sobre el ambiente: T_rod (°F) = T_amb_F + ΔT_F.")
                m = st.columns(4)
                m[0].metric("R²", fmt(reg["r2"], 4))
                m[1].metric("R² ajustado", fmt(reg["r2a"], 4))
                m[2].metric("RMSE ajuste", f"{fmt(r['rmse_aj'], 2)} °F")
                m[3].metric("RMSE validación", f"{fmt(r['rmse_val'], 2)} °F" if r["rmse_val"] is not None else "—")
                tabla_c = pd.DataFrame({"Término": ["Intercepto"] + r["terminos"], "Coeficiente": reg["beta"],
                                        "Error estándar": reg["se"], "t": reg["t"], "p-valor": reg["p"],
                                        "VIF": [np.nan] + vif(r["X"].iloc[:r["corte"]])})
                tabla_c["¿Significativo?"] = np.where(tabla_c["p-valor"] < 0.05, "Sí", "No")
                tabla_c.loc[0, "¿Significativo?"] = "—"
                st.dataframe(tabla_c.round(5), hide_index=True, width="stretch")
                st.caption("Quita variables con p-valor > 0,05 o VIF > 5. En el modelo polinómico el VIF es alto por construcción (x y x²).")
                comp_df = pd.DataFrame({"Medida": r["real"], "Estimada": r["pred"],
                                        "Conjunto": ["Ajuste"] * r["corte"] + ["Validación"] * (len(r["real"]) - r["corte"])})
                comp_df["Residuo"] = comp_df["Medida"] - comp_df["Estimada"]
                lo, hi = float(comp_df[["Medida", "Estimada"]].min().min()), float(comp_df[["Medida", "Estimada"]].max().max())
                cg = st.columns(2)
                comp_df = muestra(comp_df.reset_index(drop=True).rename_axis("index").reset_index())
                cg[0].altair_chart(alt.Chart(comp_df).mark_circle(size=40, opacity=.6).encode(
                    x=alt.X("Medida:Q", scale=alt.Scale(domain=[lo, hi]), title="Medida (°F)"),
                    y=alt.Y("Estimada:Q", scale=alt.Scale(domain=[lo, hi]), title="Estimada (°F)"),
                    color=alt.Color("Conjunto:N", scale=alt.Scale(domain=["Ajuste", "Validación"], range=["#1F6FEB", "#F2B705"])))
                    + alt.Chart(pd.DataFrame({"x": [lo, hi], "y": [lo, hi]})).mark_line(strokeDash=[5, 5], color="gray").encode(x="x:Q", y="y:Q"),
                    width="stretch")
                cg[1].altair_chart(alt.Chart(comp_df).mark_circle(size=30, opacity=.6).encode(
                    x=alt.X("index:Q", title="Registro (orden de tiempo)"), y=alt.Y("Residuo:Q", title="Residuo (°F)"),
                    color=alt.Color("Conjunto:N", scale=alt.Scale(domain=["Ajuste", "Validación"], range=["#1F6FEB", "#F2B705"]))), width="stretch")
                texto_tarjeta("Izquierda: temperatura medida contra la estimada por la ecuación. Derecha: el error de cada registro en orden de tiempo.",
                              "Un buen modelo deja los puntos sobre la diagonal y residuos repartidos al azar alrededor de cero. Si los residuos "
                              "forman una tendencia o una curva, falta una variable o un término no lineal.",
                              f"El {elegido.lower()} explica el {fmt(reg['r2'] * 100)} % de la variación de la temperatura, con un error típico de "
                              f"{fmt(r['rmse_aj'], 2)} °F en ajuste" + (f" y {fmt(r['rmse_val'], 2)} °F en datos no vistos." if r["rmse_val"] is not None else "."))
                if st.button("Guardar este modelo para el estimador y el informe", type="primary"):
                    guardar_json(ARCH_MODELO, {
                        "nombre": elegido, "objetivo": objetivo, "tipo_y": r["tipo_y"], "variables": vars_x,
                        "terminos": r["terminos"], "intercepto": float(reg["beta"][0]),
                        "coeficientes": [float(b) for b in reg["beta"][1:]], "ecuacion": ecu, "r2": reg["r2"],
                        "rmse_F": r["rmse_aj"], "rmse_validacion_F": r["rmse_val"], "n": len(r["dm"]),
                        "datos": filtro, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")})
                    st.session_state["msg"] = "Modelo guardado"
                    st.rerun()

# =============================================================================
# 🎯 Estimador
# =============================================================================
if nav == "🎯 Estimador":
    if not modelo_guardado or "terminos" not in modelo_guardado:
        st.info("Primero ajusta y guarda un modelo en «Correlación y modelo».")
    else:
        st.subheader("Estimación de temperatura con el modelo guardado")
        st.code(modelo_guardado["ecuacion"], language=None)
        st.caption(f"{modelo_guardado['nombre']} | R² = {fmt(modelo_guardado['r2'], 4)} | RMSE = {fmt(modelo_guardado['rmse_F'], 2)} °F | "
                   f"{modelo_guardado['n']} registros ({modelo_guardado.get('datos', '')}) | {modelo_guardado['fecha']}")
        necesarias = []
        for v in modelo_guardado["variables"] + (["T_amb_F"] if modelo_guardado.get("tipo_y") == "dT" else []):
            for m in DEPENDE.get(v, [v]):
                if m not in necesarias:
                    necesarias.append(m)
        entrada = {c: np.nan for c in COLS}
        entrada.update({c: "" for c in TEXTO})
        cols = st.columns(3)
        for i, v in enumerate(necesarias):
            serie = dder[v].dropna() if v in dder else pd.Series(dtype=float)
            entrada[v] = cols[i % 3].number_input(ETIQUETAS.get(v, v), value=float(serie.iloc[-1]) if len(serie) else 0.0, key=f"est_{v}")
        fila = calcular_derivadas(normalizar(pd.DataFrame([entrada])), equipo)
        t_est = evaluar_modelo(modelo_guardado, fila)
        zona = 0 if t_est < equipo["alarma_F"] else 1 if t_est < equipo["disparo_F"] else 2
        tarjetas_semaforo([("Temperatura estimada", f"{fmt(t_est)} °F", zona, f"{fmt(f_a_c(t_est))} °C"),
                           ("Límite de alarma", f"{fmt(equipo['alarma_F'], 0)} °F", None, f"Disparo {fmt(equipo['disparo_F'], 0)} °F")])
        t_ir = st.number_input("Lectura actual del transmisor o termómetro IR (°F), opcional", value=None, step=0.1)
        if t_ir is not None:
            dif = t_ir - t_est
            lim = 2 * modelo_guardado["rmse_F"]
            if abs(dif) > lim:
                st.warning(f"Medición y estimación difieren {dif:+.1f} °F (más de 2·RMSE = {lim:.1f} °F). Revisa el sensor "
                           "(emisividad, alineación, lente sucio) o el rodamiento (lubricación, desgaste).")
            else:
                st.success(f"Medición y estimación coinciden (diferencia {dif:+.1f} °F).")

# =============================================================================
# 🌡️ Selección del transmisor IR
# =============================================================================
if nav == "🌡️ Transmisor IR":
    st.subheader("1. Condiciones de instalación")
    with st.form("form_ir"):
        c = st.columns(4)
        sup = c[0].selectbox("Superficie del punto de medición", SUPERFICIES,
                             index=SUPERFICIES.index(equipo["ir_superficie"]) if equipo["ir_superficie"] in SUPERFICIES else 0)
        cinta = c[1].checkbox("Se colocará cinta de alta emisividad (ε = 0,95)", value=bool(equipo["ir_cinta"]))
        dobj = c[2].number_input("Diámetro útil de la zona del rodamiento (mm)", value=float(equipo["ir_d_objetivo_mm"]), step=5.0)
        dist = c[3].number_input("Distancia sensor–objetivo posible (mm)", value=float(equipo["ir_distancia_mm"]), step=10.0)
        c = st.columns(4)
        amb = c[0].number_input("Temperatura ambiente máx. junto al sensor (°C)", value=float(equipo["ir_amb_max_C"]))
        ipm = c[1].selectbox("Grado IP mínimo", [54, 65, 67], index=[54, 65, 67].index(int(equipo["ir_ip_min"])))
        sal = c[2].selectbox("Salida requerida por el PLC", ["4–20 mA", "0–10 V", "IO-Link"],
                             index=["4–20 mA", "0–10 V", "IO-Link"].index(equipo["ir_salida"]))
        alim = c[3].number_input("Alimentación disponible (VDC)", value=float(equipo["ir_alimentacion_V"]))
        c = st.columns(2)
        margen = c[0].number_input("Margen del rango sobre el disparo (°C)", value=float(equipo["ir_margen_rango_C"]))
        exm = c[1].number_input("Exactitud requerida (°C), vacío = calcular con los datos", value=equipo["ir_exactitud_manual"], step=0.5)
        if st.form_submit_button("Guardar condiciones", type="primary"):
            equipo.update({"ir_superficie": sup, "ir_cinta": cinta, "ir_d_objetivo_mm": dobj, "ir_distancia_mm": dist,
                           "ir_amb_max_C": amb, "ir_ip_min": ipm, "ir_salida": sal, "ir_alimentacion_V": alim,
                           "ir_margen_rango_C": margen, "ir_exactitud_manual": exm})
            guardar_json(ARCH_EQUIPO, equipo)
            st.session_state["msg"] = "Condiciones guardadas"
            st.rerun()

    st.subheader("2. Requisitos calculados con los datos")
    r_ = req_ir
    req_tabla = pd.DataFrame([
        ("Rango de medición", f"{fmt(r_['rango_min_C'], 0)} a {fmt(r_['rango_max_C'], 0)} °C "
                              f"({fmt(c_a_f(r_['rango_min_C']), 0)} a {fmt(c_a_f(r_['rango_max_C']), 0)} °F)",
         f"Máximo medido {fmt(r_['t_max_obs_C'])} °C y disparo {fmt(f_a_c(equipo['disparo_F']))} °C, más {fmt(equipo['ir_margen_rango_C'], 0)} °C de margen"),
        ("Exactitud", f"±{fmt(r_['exactitud_C'])} °C (±{fmt(r_['exactitud_C'] * 1.8)} °F)", r_["origen_exactitud"]),
        ("Tiempo de respuesta", f"≤ {fmt(r_['resp_ms'], 0)} ms", r_["origen_resp"]),
        ("Relación óptica D:S", f"≥ {fmt(r_['ds_req'])} : 1",
         f"El punto medido debe ser ≤ {fmt(r_['spot_max_mm'])} mm (2/3 de la zona de ø{fmt(equipo['ir_d_objetivo_mm'], 0)} mm) a {fmt(equipo['ir_distancia_mm'], 0)} mm"),
        ("Emisividad", "Ajustable" if r_["emis_req"] == "ajustable" else "Fija 0,95 admitida", r_["emis_txt"]),
        ("Salida y alimentación", f"{r_['salida']}, {fmt(r_['alim_V'], 0)} VDC", "Entrada analógica del PLC"),
        ("Ambiente y protección", f"≥ {fmt(r_['amb_C'], 0)} °C, ≥ IP{r_['ip_min']}", "Motor ODP junto a una bomba de agua: polvo y salpicaduras"),
    ], columns=["Requisito", "Valor", "De dónde sale"])
    st.dataframe(req_tabla, hide_index=True, width="stretch")

    st.subheader("3. Comparación con el catálogo")
    if len(tabla_ir):
        st.dataframe(tabla_ir.drop(columns=["Marca"]), hide_index=True, width="stretch",
                     column_config={"Puntaje": st.column_config.ProgressColumn("Puntaje", min_value=0, max_value=100, format="%.0f")})
        st.caption("Puntaje (solo informativo entre los que cumplen): exactitud 30, holgura óptica 20, disponibilidad en Ecuador 20, "
                   "emisividad ajustable 10, protección IP 10, resolución de la señal 5 y precio 5 (si hay cotizaciones).")
        ok = tabla_ir[tabla_ir["Cumple todo"]]
        if len(ok):
            elegido = next(c for c in catalogo if c["Modelo"] == ok.iloc[0]["Modelo"])
            razones = ["cumple los nueve requisitos calculados"]
            if elegido.get("Local"):
                razones.append("se consigue en Ecuador")
            razones.append(f"su punto de medición a {fmt(equipo['ir_distancia_mm'], 0)} mm es de {fmt(ok.iloc[0]['Spot a la distancia (mm)'])} mm")
            st.markdown(f"""
<div class="recomendado"><div class="k">Transmisor recomendado</div>
<h2>{html.escape(elegido['Marca'])} {html.escape(elegido['Modelo'])}</h2>
<span class="badge">Puntaje {fmt(ok.iloc[0]['Puntaje'], 0)}</span><span class="badge">{html.escape(elegido['Salidas'].split(';')[0])}</span>
<span class="badge">{fmt(elegido['T_min_C'], 0)}–{fmt(elegido['T_max_C'], 0)} °C</span>
<p style="margin:.7rem 0 0;color:#E3EEFF">Se recomienda porque {html.escape(', '.join(razones))}.</p></div>""", unsafe_allow_html=True)
            st.markdown("**Hoja de datos (datasheet)**")
            ca, cb = st.columns([3, 2])
            ca.markdown(ficha_datasheet(elegido), unsafe_allow_html=True)
            with cb:
                pdf = ruta_pdf(elegido.get("PDF", ""))
                if pdf:
                    st.download_button(f"📄 Descargar datasheet oficial ({pdf.name})", pdf.read_bytes(), pdf.name, "application/pdf")
                    if hasattr(st, "pdf"):
                        try:
                            st.pdf(str(pdf), height=520)
                        except Exception:
                            st.caption("Para ver el PDF aquí instala: python -m pip install streamlit[pdf]")
                else:
                    st.caption("Coloca el PDF del fabricante en la carpeta «catalogos» para descargarlo desde aquí.")
                if "4–20" in elegido["Salidas"]:
                    st.info("**Conexión al PLC.** Las entradas analógicas integradas del S7-1200 CPU 1214C son de 0–10 V: con una "
                            "resistencia de precisión de 250 Ω en el lazo, 4–20 mA se convierten en 1–5 V. Otra opción es un módulo "
                            "SM 1231 de entradas de corriente. Revisar la carga máxima del lazo que admite el transmisor.")
            if len(ok) > 1:
                alt_txt = ", ".join(f"{m} ({fmt(p, 0)} pts)" for m, p in ok.iloc[1:4][["Modelo", "Puntaje"]].values)
                st.caption(f"Alternativas que también cumplen: {alt_txt}.")
        else:
            st.error("Ningún transmisor del catálogo cumple todos los requisitos. Revisa la columna «Fallas» para ver qué ajustar "
                     "(por ejemplo, acercar el sensor si falla la óptica, o usar cinta de alta emisividad).")
    with st.expander("Instrumento de referencia recomendado para tomar los datos (antes de comprar el transmisor)"):
        st.dataframe(pd.DataFrame(PORTATILES), hide_index=True, width="stretch")
        st.caption("Para que el modelo sea comparable con el transmisor, mide con un termómetro IR de emisividad conocida "
                   "(idealmente 0,95 sobre pintura o cinta) y siempre en el mismo punto de la carcasa del rodamiento.")
    with st.expander("Editar el catálogo de transmisores (agregar modelos, precios o cotizaciones)"):
        clave_cat = f"cat_{st.session_state.editor_ver}"
        cat_edit = st.data_editor(pd.DataFrame(catalogo), num_rows="dynamic", hide_index=True, width="stretch", key=clave_cat,
                                  column_config={"Precio_USD": st.column_config.NumberColumn("Precio (USD)", format="%.2f"),
                                                 "Local": st.column_config.CheckboxColumn("Venta en Ecuador")})
        cam = st.session_state.get(clave_cat, {})
        if cam and (cam.get("edited_rows") or cam.get("added_rows") or cam.get("deleted_rows")):
            registros = cat_edit.to_dict("records")
            for reg_ in registros:
                for k, v in list(reg_.items()):
                    if hasattr(v, "item"):
                        v = v.item()
                    reg_[k] = None if isinstance(v, float) and np.isnan(v) else v
            guardar_json(ARCH_CATALOGO, [r for r in registros if r.get("Modelo")])
            st.session_state.editor_ver += 1
            st.session_state["msg"] = "Catálogo guardado"
            st.rerun()
        if st.button("Restaurar catálogo original"):
            guardar_json(ARCH_CATALOGO, CATALOGO_DEF)
            st.session_state["msg"] = "Catálogo restaurado"
            st.rerun()
        st.caption("Datos tomados de: hoja de datos OPTEX-FA SA-80, catálogo POTENTA 2023, folleto Optris y hojas de datos Optris CT LT y CThot LT.")

# =============================================================================
# 📥 Importar / Pruebas
# =============================================================================
MAPA_SINT = {"presion_succion_PSI": "P_succ_psi", "presion_descarga_PSI": "P_desc_psi",
             "vibracion_succion_mm_s": "Vib_succ_mms", "vibracion_descarga_mm_s": "Vib_desc_mms",
             "I_L1_A": "I_L1_A", "I_L2_A": "I_L2_A", "I_L3_A": "I_L3_A",
             "potencia_activa_kW": "P_kW", "factor_potencia": "FP"}


def convertir_sintetica(s: pd.DataFrame, solo_op: bool, paso: int, tamb_F, rpm_carga: bool) -> pd.DataFrame:
    if solo_op and "estado_bomba" in s:
        s = s[s["estado_bomba"] == 1]
    s = s.iloc[::max(int(paso), 1)].reset_index(drop=True)
    out = pd.DataFrame({dst: pd.to_numeric(s[src], errors="coerce") for src, dst in MAPA_SINT.items() if src in s})
    out["Fecha_hora"] = pd.to_datetime(s["timestamp"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    out["Origen"], out["Ensayo"], out["Operador"] = "Prueba", "SINT", ""
    out["Instrumento_T"] = "Dato sintético (temperatura del motor)"
    out["t_min"] = pd.to_numeric(s["horas_trabajo_acum_h"], errors="coerce") * 60
    out["V_V"] = s[["V_L1L2_V", "V_L2L3_V", "V_L3L1_V"]].mean(axis=1)
    out["I_A"] = out[["I_L1_A", "I_L2_A", "I_L3_A"]].mean(axis=1)
    out["f_Hz"] = 60.0
    out["Q_Lmin"] = pd.to_numeric(s["caudal_L_h"], errors="coerce") / 60
    out["T_rod_DE_F"] = c_a_f(pd.to_numeric(s["temperatura_motor_C"], errors="coerce"))
    out["T_amb_F"] = float(tamb_F) if tamb_F is not None else np.nan
    if rpm_carga:
        out["rpm"] = 3600 - (3600 - equipo["motor_rpm"]) * out["I_A"] / equipo["motor_i"]
    out["Observaciones"] = s.get("estado_falla", "").astype(str)
    return normalizar(out)


if nav == "📥 Importar":
    st.subheader("Cargar datos de prueba (data sintética Goulds 3642)")
    st.write("Sirve para probar todas las funciones antes de tener datos reales. Los registros quedan marcados como "
             "**Prueba** y se pueden analizar por separado o borrar en cualquier momento.")
    st.warning("La data sintética trae la **temperatura del motor**, no la del rodamiento, y **no trae temperatura ambiente ni "
               "vibración en los rodamientos del motor**. Para las pruebas se usa como sustituta; los resultados reales saldrán de tus ensayos.")
    archivos = sorted(DIR_PRUEBA.glob("*.xlsx")) if DIR_PRUEBA.exists() else []
    subido = st.file_uploader("O sube otro archivo (Excel de data sintética, o CSV/Excel con las columnas de esta aplicación)",
                              type=["xlsx", "csv"])
    c = st.columns(4)
    solo_op = c[0].checkbox("Solo registros con la bomba operando", value=True)
    paso = c[1].number_input("Tomar 1 de cada N registros", min_value=1, value=1, step=1)
    tamb_sup = c[2].number_input("T ambiente supuesta (°F), opcional", value=None, step=1.0,
                                 help="Permite probar el modelo sobre ΔT; la data sintética no la trae")
    rpm_carga = c[3].checkbox("Estimar rpm con la carga (supuesto)", value=True,
                              help="rpm ≈ 3600 − 150·I/I_nominal, solo para pruebas")
    fuente = None
    if subido is not None:
        fuente = subido
    elif archivos:
        st.caption(f"Archivo encontrado en «datos_prueba»: {archivos[0].name}")
        fuente = archivos[0]
    if fuente is not None and st.button("Importar datos", type="primary"):
        try:
            nombre = getattr(fuente, "name", str(fuente))
            if str(nombre).lower().endswith(".csv"):
                nuevo = pd.read_csv(fuente)
            else:
                libro = pd.ExcelFile(fuente)
                hoja = "Data_Sintetica" if "Data_Sintetica" in libro.sheet_names else libro.sheet_names[0]
                nuevo = pd.read_excel(libro, sheet_name=hoja)
            if "temperatura_motor_C" in nuevo.columns:
                nuevo = convertir_sintetica(nuevo, solo_op, paso, tamb_sup, rpm_carga)
            else:
                nuevo = normalizar(nuevo)
                nuevo.loc[nuevo["Origen"] == "Real", "Origen"] = "Prueba" if subido is None else "Real"
            nuevo["ID"] = np.nan
            guardar_datos(pd.concat([df, nuevo], ignore_index=True))
            st.session_state["msg"] = f"{len(nuevo)} registros importados"
            importado = True
        except Exception as ex:
            importado = False
            st.error(f"No se pudo importar: {ex}")
        if importado:
            st.rerun()
    st.divider()
    n_prueba = int((df["Origen"] == "Prueba").sum())
    st.write(f"Registros de prueba guardados: **{n_prueba}**")
    if n_prueba and st.button("🗑️ Borrar todos los datos de prueba"):
        guardar_datos(df[df["Origen"] != "Prueba"])
        st.session_state["msg"] = "Datos de prueba borrados"
        st.rerun()
    st.markdown("**Lista de comprobación de la prueba**")
    st.markdown(
        "1. Importa los datos y elige **Prueba** en «Datos a analizar» (barra lateral).\n"
        "2. **🏠 Inicio**: aparecen los semáforos y el hallazgo principal.\n"
        "3. **🩺 Diagnóstico**: revisa las causas y soluciones de varios registros.\n"
        "4. **📊 Gráficas**: revisa las cinco secciones y los tres mapas de calor.\n"
        "5. **🔍 Modelo**: compara modelos y guarda uno; luego prueba el **🎯 Estimador**.\n"
        "6. **🌡️ Transmisor IR**: revisa los requisitos y la recomendación con su datasheet.\n"
        "7. **📄 Informe**: genera el Word y comprueba que incluye todo.")

# =============================================================================
# 📄 Informe y respaldo
# =============================================================================
if nav == "📄 Informe":
    st.subheader("Informe automático en Word")
    st.write("Incluye portada con logos, docente y operadores; datos del equipo; resumen de datos; gráficas con su explicación; "
             "ecuación del modelo; requisitos y transmisor recomendado; y conclusiones generadas con tus datos.")
    st.caption(f"Se usará el conjunto de datos «{filtro}» ({len(dder)} registros).")
    if st.button("Generar informe", type="primary"):
        try:
            with st.spinner("Generando informe..."):
                st.session_state["informe"] = generar_informe(dder, equipo, modelo_guardado, req_ir, tabla_ir, catalogo)
        except ImportError:
            st.error("Falta la librería python-docx. Instálala con: python -m pip install python-docx matplotlib")
    if st.session_state.get("informe"):
        st.download_button("📄 Descargar informe (.docx)", st.session_state["informe"],
                           f"Informe_rodamientos_{datetime.now():%Y%m%d_%H%M}.docx",
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    st.divider()
    st.subheader("Respaldo completo")
    st.write("Descarga en un ZIP los datos, la configuración, el modelo y el catálogo. Para restaurar, copia esos archivos en la carpeta del programa.")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(ARCH_DATOS.name, df.to_csv(index=False))
        for ruta, contenido in ((ARCH_EQUIPO, equipo), (ARCH_MODELO, modelo_guardado), (ARCH_CATALOGO, catalogo),
                                (ARCH_MANT, mant), (ARCH_ALERTAS, {**alertas_cfg, "token": ""})):
            if contenido:
                z.writestr(ruta.name, json.dumps(contenido, indent=2, ensure_ascii=False, default=str))
    st.download_button("💾 Descargar respaldo (.zip)", buf.getvalue(), f"respaldo_rodamientos_{datetime.now():%Y%m%d_%H%M}.zip", "application/zip")
    st.divider()
    st.subheader("Trabajo futuro")
    st.write("Una vez comprado e instalado el transmisor, la aplicación podría leer en vivo la temperatura y las demás variables "
             "desde el PLC S7-1200 por Ethernet (por ejemplo, con la librería python-snap7) y registrar los datos automáticamente.")

# =============================================================================
# 🩺 Diagnóstico
# =============================================================================
if nav == "🩺 Diagnóstico":
    st.subheader("Diagnóstico automático y soluciones")
    if dder.empty:
        st.info("No hay registros en el conjunto seleccionado.")
    else:
        ids = dder["ID"].dropna().astype(int).tolist()
        sel_id = st.selectbox("Registro a diagnosticar", ids[::-1], index=0,
                              format_func=lambda i: f"Registro {i} | " + str(dder.loc[dder['ID'] == i, 'Fecha_hora'].iloc[0]))
        fila_d = dder[dder["ID"] == sel_id].iloc[0].to_dict()
        diags = diagnosticar(fila_d, equipo, dder_todo, mant_venc if sel_id == ids[-1] else None)
        if diags:
            n2 = sum(d["Gravedad"] == 2 for d in diags)
            st.markdown(f"**{len(diags)} hallazgo(s)**, {n2} crítico(s). Ordenados de mayor a menor gravedad.")
            tarjetas_diagnostico(diags)
        else:
            st.success("Sin fallas detectadas en este registro: el equipo opera dentro de los límites.")
        st.subheader("Historial de hallazgos en el conjunto de datos")
        resumen = pd.DataFrame({
            "Hallazgo": ["Sobretemperatura (alarma o disparo)", "Margen de NPSH bajo o cavitación", "Vibración en zona C o D",
                         "Corriente sobre la nominal", "Desbalance de corriente > 10 %"],
            "Registros": [int((dder["zona_T"] >= 1).sum()), int((dder["zona_NPSH"] >= 1).sum()), int((dder["zona_vib"] >= 1).sum()),
                          int((dder["zona_carga"] >= 1).sum()), int((dder["desb_I_pct"] > 10).sum())],
            "Críticos": [int((dder["zona_T"] == 2).sum()), int((dder["zona_NPSH"] == 2).sum()), int((dder["zona_vib"] == 2).sum()),
                         int((dder["zona_carga"] == 2).sum()), int((dder["desb_I_pct"] > 20).sum())]})
        resumen["% de registros"] = (resumen["Registros"] / len(dder) * 100).round(1)
        st.dataframe(resumen, hide_index=True, width="stretch")
        st.caption("Las reglas combinan temperatura, NPSH, vibración (ISO 10816), corriente de placa, tendencia y estado del "
                   "mantenimiento para proponer la causa más probable y la acción a seguir.")

# =============================================================================
# 🛠️ Mantenimiento
# =============================================================================
if nav == "🛠️ Mantenimiento":
    st.subheader("Plan de mantenimiento preventivo")
    c = st.columns(3)
    c[0].metric("Horómetro", f"{fmt(float(mant.get('horometro_h') or 0), 1)} h")
    c[1].metric("Tareas vencidas", int((mant_estado["nivel"] == 2).sum()))
    c[2].metric("Próximas a vencer", int((mant_estado["nivel"] == 1).sum()))
    if len(mant_estado):
        vista_m = mant_estado.copy()
        vista_m["Situación"] = vista_m["nivel"].map({0: "🟢 Al día", 1: "🟡 Próxima", 2: "🔴 Vencida"})
        st.dataframe(vista_m[["Situación", "Tarea", "Frecuencia", "Última vez", "Estado"]], hide_index=True, width="stretch")
    st.markdown("**Registrar un mantenimiento realizado**")
    with st.form("form_mant", clear_on_submit=True):
        c = st.columns([3, 1, 1])
        tarea_m = c[0].selectbox("Tarea", [t["Tarea"] for t in mant["tareas"]] + ["Otra (correctiva)"])
        fecha_m = c[1].date_input("Fecha", value=datetime.now().date())
        resp_m = c[2].selectbox("Responsable", [o["Nombre"] for o in equipo.get("operadores", []) if o.get("Nombre")] or ["—"])
        obs_m = st.text_input("Observaciones (qué se encontró, repuestos usados)")
        if st.form_submit_button("Guardar mantenimiento", type="primary"):
            horas_m = float(mant.get("horometro_h") or 0)
            for t in mant["tareas"]:
                if t["Tarea"] == tarea_m:
                    t["Ultima_fecha"], t["Ultima_horas"] = str(fecha_m), horas_m
            mant["historial"] = [{"Fecha": str(fecha_m), "Tarea": tarea_m, "Responsable": resp_m, "Horas": horas_m,
                                  "Observaciones": obs_m}] + mant.get("historial", [])
            guardar_json(ARCH_MANT, mant)
            st.session_state["msg"] = "Mantenimiento registrado"
            st.rerun()
    with st.form("form_horo"):
        c = st.columns([2, 1])
        horo = c[0].number_input("Horómetro actual de la bomba (horas de operación)", value=float(mant.get("horometro_h") or 0), step=0.5)
        c[1].markdown("&nbsp;")
        if c[1].form_submit_button("Actualizar horómetro"):
            mant["horometro_h"] = horo
            guardar_json(ARCH_MANT, mant)
            st.session_state["msg"] = "Horómetro actualizado"
            st.rerun()
    if mant.get("historial"):
        st.markdown("**Historial de mantenimientos**")
        st.dataframe(pd.DataFrame(mant["historial"]), hide_index=True, width="stretch")
    with st.expander("Editar tareas y frecuencias"):
        clave_t = f"mant_{st.session_state.editor_ver}"
        t_edit = st.data_editor(pd.DataFrame(mant["tareas"]), num_rows="dynamic", hide_index=True, width="stretch", key=clave_t,
                                column_config={"Cada_dias": st.column_config.NumberColumn("Cada (días)"),
                                               "Cada_horas": st.column_config.NumberColumn("Cada (horas)"),
                                               "Ultima_fecha": st.column_config.TextColumn("Última fecha (AAAA-MM-DD)"),
                                               "Ultima_horas": st.column_config.NumberColumn("Horómetro en la última")})
        cam = st.session_state.get(clave_t, {})
        if cam and (cam.get("edited_rows") or cam.get("added_rows") or cam.get("deleted_rows")):
            mant["tareas"] = [{k: _limpio(v) for k, v in r.items()} for r in t_edit.to_dict("records") if r.get("Tarea")]
            guardar_json(ARCH_MANT, mant)
            st.session_state.editor_ver += 1
            st.session_state["msg"] = "Tareas guardadas"
            st.rerun()
        st.caption("Los motores de este tamaño suelen llevar rodamientos sellados (2Z) que no se relubrican: se revisan por "
                   "ruido y temperatura y se reemplazan. Si se confirma que son abiertos, agrega una tarea de relubricación.")

# =============================================================================
# 🔔 Alertas
# =============================================================================
if nav == "🔔 Alertas":
    st.subheader("Alertas en el celular y la computadora (Telegram)")
    st.write("Cada vez que se guarda una medición con fallas, la aplicación envía un mensaje por Telegram con la falla, la causa "
             "probable y la acción recomendada. Llega como notificación al celular y a Telegram de la computadora.")
    with st.form("form_alertas"):
        activo = st.toggle("Enviar alertas por Telegram", value=bool(alertas_cfg.get("activo")))
        token = st.text_input("Token del bot (lo entrega @BotFather)", value=alertas_cfg.get("token", ""), type="password")
        chats = st.text_input("Chat ID de los destinatarios (separados por coma)", value=alertas_cfg.get("chats", ""))
        nivel = st.radio("Enviar desde", [1, 2], index=int(alertas_cfg.get("nivel_min", 1)) - 1, horizontal=True,
                         format_func=lambda n: "🟡 Alerta y crítico" if n == 1 else "🔴 Solo crítico")
        if st.form_submit_button("Guardar configuración", type="primary"):
            alertas_cfg.update({"activo": activo, "token": token.strip(), "chats": chats.strip(), "nivel_min": nivel})
            guardar_json(ARCH_ALERTAS, alertas_cfg)
            st.session_state["msg"] = "Configuración de alertas guardada"
            st.rerun()
    c = st.columns(2)
    if c[0].button("📨 Enviar mensaje de prueba"):
        ok_, det_ = telegram_enviar("✅ Prueba de alertas – Monitoreo de rodamientos ESPE Latacunga", alertas_cfg)
        (st.success if ok_ else st.error)(det_)
    if c[1].button("🔎 Buscar mi chat ID"):
        try:
            r = requests.get(f"https://api.telegram.org/bot{alertas_cfg.get('token', '')}/getUpdates", timeout=10).json()
            encontrados = {}
            for u in r.get("result", []):
                ch = (u.get("message") or u.get("my_chat_member") or {}).get("chat", {})
                if ch.get("id"):
                    encontrados[ch["id"]] = ch.get("first_name") or ch.get("title") or ""
            if encontrados:
                st.success("Chats encontrados: " + ", ".join(f"{k} ({v})" for k, v in encontrados.items()))
            else:
                st.warning("Primero escribe cualquier mensaje a tu bot en Telegram y vuelve a pulsar este botón.")
        except Exception as ex:
            st.error(f"No se pudo consultar Telegram: {ex}")
    with st.expander("Cómo crear el bot (5 minutos)"):
        st.markdown(
            "1. En Telegram busca **@BotFather**, escribe `/newbot`, ponle un nombre (por ejemplo *Rodamientos ESPE*) y copia el **token**.\n"
            "2. Pega el token arriba y guarda.\n"
            "3. Busca tu bot por su nombre en Telegram y escríbele cualquier mensaje (por ejemplo *hola*).\n"
            "4. Pulsa **Buscar mi chat ID**, copia el número, pégalo en *Chat ID*, activa las alertas y guarda.\n"
            "5. Pulsa **Enviar mensaje de prueba**. Cada integrante puede repetir los pasos 3 y 4 y agregar su número separado por coma.")
    if alertas_cfg.get("historial"):
        st.markdown("**Historial de alertas enviadas**")
        st.dataframe(pd.DataFrame(alertas_cfg["historial"]), hide_index=True, width="stretch")

with st.sidebar:
    st.divider()
    st.markdown('<div class="lateral-titulo">Informe en Word</div>', unsafe_allow_html=True)
    if st.button("📄 Generar informe", key="inf_lateral", width="stretch"):
        try:
            with st.spinner("Generando informe..."):
                st.session_state["informe"] = generar_informe(dder, equipo, modelo_guardado, req_ir, tabla_ir, catalogo)
        except ImportError:
            st.error("Falta python-docx: python -m pip install python-docx matplotlib")
    if st.session_state.get("informe"):
        st.download_button("⬇️ Descargar informe", st.session_state["informe"],
                           f"Informe_rodamientos_{datetime.now():%Y%m%d_%H%M}.docx",
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           key="desc_lateral", width="stretch")

st.markdown("""<div class="pie"><b>Universidad de las Fuerzas Armadas ESPE – Sede Latacunga</b><br>
Departamento de Eléctrica y Electrónica | Carrera de Ingeniería Electromecánica</div>""", unsafe_allow_html=True)
