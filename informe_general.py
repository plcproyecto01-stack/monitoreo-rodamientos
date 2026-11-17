# -*- coding: utf-8 -*-
"""Informe general detallado del sistema de monitoreo predictivo de la bomba Goulds 3642 (Word .docx)."""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

import nucleo as N

AZUL, MARINO, RAYO, ROJO, VERDE, NARANJA, GRIS = "#1F6FEB", "#0A1F44", "#F2B705", "#D64545", "#2E9E5B", "#F28C28", "#5A6B88"

DESC_VAR = {
    "estado_bomba": ("—", "1 = bomba funcionando, 0 = detenida"),
    "horas_trabajo_acum_h": ("h", "Horas de funcionamiento acumuladas con el rodamiento actual"),
    "nivel_tanque_mm": ("mm", "Altura del agua en el tanque de succión"),
    "caudal_L_h": ("L/h", "Cantidad de agua que entrega la bomba"),
    "presion_succion_PSI": ("psi", "Presión manométrica a la entrada de la bomba (negativa = vacío)"),
    "presion_descarga_PSI": ("psi", "Presión manométrica a la salida de la bomba"),
    "vibracion_succion_mm_s": ("mm/s RMS", "Vibración global de la carcasa, lado de entrada"),
    "vibracion_descarga_mm_s": ("mm/s RMS", "Vibración global de la carcasa, lado de salida"),
    "temperatura_motor_C": ("°C", "Temperatura de la tapa del rodamiento medida por el sensor infrarrojo"),
    "V_L1L2_V": ("V", "Voltaje entre las fases L1 y L2"), "V_L2L3_V": ("V", "Voltaje entre las fases L2 y L3"),
    "V_L3L1_V": ("V", "Voltaje entre las fases L3 y L1"), "I_L1_A": ("A", "Corriente de la fase L1"),
    "I_L2_A": ("A", "Corriente de la fase L2"), "I_L3_A": ("A", "Corriente de la fase L3"),
    "potencia_activa_kW": ("kW", "Potencia que el motor convierte en trabajo"),
    "potencia_reactiva_kVAr": ("kVAr", "Potencia que magnetiza el motor y no produce trabajo"),
}
SIGNIFICADO = {
    "NORMAL": "La bomba funciona bien: agua suficiente en la succión y rodamiento sano.",
    "CAVITACION_INCIPIENTE": "Empiezan a formarse burbujas de vapor en la entrada de la bomba porque llega poca presión.",
    "CAVITACION_SEVERA": "Las burbujas revientan dentro de la bomba: ruido de grava y daño al impulsor.",
    "DEGRADACION_RODAMIENTO": "El rodamiento empieza a desgastarse: suben su temperatura y la vibración.",
    "RODAMIENTO_CRITICO": "El rodamiento está en la etapa final antes de fallar.",
    "FALLA_COMBINADA": "Cavitación y rodamiento dañado al mismo tiempo.",
    "DETENIDA": "La bomba está apagada (paradas nocturnas u operativas).",
    "MANTENIMIENTO": "Parada programada para cambiar el rodamiento.",
}
SECCIONES_APP = [
    ("🏠 Inicio", "Ruta del proyecto en tres pasos y estado actual del equipo con semáforos."),
    ("➕ Registro de datos", "Pruebas ya llenas con los datos recolectados y formulario para registrar mediciones nuevas."),
    ("🔍 Modelo", "Correlaciones y ecuación matemática de la temperatura del rodamiento en °F y °C."),
    ("🧮 Calculadora de temperatura", "Temperatura esperada según la condición de trabajo; compara con la lectura del sensor IR."),
    ("🌡️ Transmisor IR", "Criterios, comparación de transmisores, selección, conexión al PLC e informe de selección."),
    ("📊 Gráficas", "Gráficas hidráulicas, térmicas, de vibración, eléctricas y mapas de calor, cada una explicada."),
    ("🩺 Diagnóstico", "Qué le pasa al equipo, por qué y qué hacer, para cualquier registro."),
    ("🧠 Estado y vida útil", "Estados de falla, red neuronal y vida útil restante del rodamiento."),
    ("⚙️ Rodamientos", "Frecuencias de falla de los rodamientos 6202 a 6208 y diagnóstico por vibración."),
    ("💧 Cavitación", "Frecuencia de paso de álabes, severidad de vibración y efecto de la altitud en el NPSH."),
    ("🛠️ Mantenimiento", "Vida útil restante, plan preventivo, horómetro e historial."),
    ("▶️ Simulación", "Reproduce los datos hora por hora como si llegaran del PLC, con alertas opcionales."),
    ("📋 Datos", "Tabla de los datos recolectados y de los registros nuevos (editables)."),
    ("🔔 Alertas", "Configuración del bot de Telegram y el historial de alertas enviadas."),
    ("⚙️ Configuración", "Datos del grupo y límites técnicos (alarmas, corriente, vibración, altitud)."),
    ("📄 Informe", "Genera este informe y el informe de selección del transmisor."),
    ("📖 Glosario", "Términos técnicos explicados en lenguaje sencillo."),
]


def num(x, nd=1):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        return f"{float(x):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(x)


def c2f(c):
    return c * 1.8 + 32


# =============================================================================
# Figuras
# =============================================================================
def _png(fig) -> bytes:
    import matplotlib.pyplot as plt
    b = BytesIO()
    fig.tight_layout()
    fig.savefig(b, format="png", dpi=165)
    plt.close(fig)
    return b.getvalue()


def figuras(d: pd.DataFrame, op: pd.DataFrame, eq: dict, modelos: dict, modelo: dict) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False})
    F = {}
    fechas = pd.to_datetime(op["timestamp"])
    estados_op = [e for e in N.ESTADOS if e in set(op["estado"])]

    def por_estado(ax, y, s=5):
        for e in estados_op:
            m = op["estado"] == e
            ax.scatter(fechas[m], op.loc[m, y], s=s, color=N.COLOR_ESTADO[e], label=N.NOMBRE_ESTADO[e], alpha=.8)

    # Curvas del fabricante
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    q = np.linspace(0, 80, 200)
    ax.plot(q, N.h_ref(q), color=MARINO, lw=2.3, label="Altura H (m)")
    ax.plot(N.CURVA["Q_gpm"], N.CURVA["NPSHr_m"], color=ROJO, lw=2, marker="o", ms=4, label="NPSH requerido (m)")
    a2 = ax.twinx()
    a2.plot(N.CURVA["Q_gpm"], N.CURVA["Eficiencia_pct"], color=AZUL, ls="--", lw=1.8, label="Eficiencia (%)")
    a2.set_ylabel("Eficiencia (%)"), a2.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="center left", fontsize=8)
    ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("m"), ax.grid(alpha=.3)
    ax.set_title("Curvas de referencia de la bomba Goulds 3642 (impulsor 3 5/8\", 3500 rpm)", fontsize=10.5)
    F["curvas"] = _png(fig)

    # Estados en el tiempo
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    orden = {e: i for i, e in enumerate(N.ESTADOS)}
    fd = pd.to_datetime(d["timestamp"])
    for e in N.ESTADOS:
        m = d["estado"] == e
        if m.any():
            ax.scatter(fd[m], [orden[e]] * int(m.sum()), marker="|", s=60, color=N.COLOR_ESTADO[e])
    ax.set_yticks(range(len(N.ESTADOS))), ax.set_yticklabels([N.NOMBRE_ESTADO[e] for e in N.ESTADOS], fontsize=8)
    ax.invert_yaxis(), ax.grid(alpha=.25, axis="x"), ax.set_title("Estado del equipo en cada hora de la recolección de datos", fontsize=10.5)
    F["linea_tiempo"] = _png(fig)

    # H-Q con puntos
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    q_lo, q_hi = op["caudal_GPM"].min() - 2, op["caudal_GPM"].max() + 2
    q = np.linspace(q_lo, q_hi, 100)
    for e in estados_op:
        m = op["estado"] == e
        ax.scatter(op.loc[m, "caudal_GPM"], op.loc[m, "head_total_m"], s=5, color=N.COLOR_ESTADO[e], label=N.NOMBRE_ESTADO[e], alpha=.7)
    ax.plot(q, N.h_ref(q), color=MARINO, lw=2.5, label="Curva del fabricante")
    ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("Altura (m)"), ax.grid(alpha=.3), ax.legend(fontsize=7, markerscale=3, frameon=False)
    ax.set_title("Puntos de operación sobre la curva H–Q del fabricante", fontsize=10.5)
    F["hq"] = _png(fig)

    # NPSH mar vs Latacunga
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.scatter(op["caudal_GPM"], op["NPSHa_m"], s=4, color=AZUL, alpha=.5, label="NPSH disponible – datos (nivel del mar)")
    ax.scatter(op["caudal_GPM"], op["NPSHa_lat_m"], s=4, color=NARANJA, alpha=.5, label=f"NPSH disponible – Latacunga ({N.p_atm_kpa(eq):.1f} kPa)")
    ax.plot(N.CURVA["Q_gpm"], N.CURVA["NPSHr_m"], color=ROJO, lw=2.3, label="NPSH requerido (fabricante)")
    ax.set_xlim(q_lo, q_hi), ax.set_xlabel("Caudal (GPM)"), ax.set_ylabel("NPSH (m)"), ax.grid(alpha=.3), ax.legend(fontsize=7.5, markerscale=3, frameon=False)
    ax.set_title("Efecto de la altitud de Latacunga en el NPSH disponible", fontsize=10.5)
    F["npsh"] = _png(fig)

    # Margen en el tiempo
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    por_estado(ax, "margen_NPSH_m", 4)
    ax.axhline(N.REGLAS["margen_incipiente"], color=RAYO, ls="--", lw=1.4), ax.axhline(N.REGLAS["margen_severa"], color=ROJO, ls="--", lw=1.4)
    ax.set_ylabel("Margen contra cavitación (m)"), ax.grid(alpha=.3), ax.legend(fontsize=6.5, markerscale=3, frameon=False, ncol=3)
    ax.set_title("Margen contra cavitación en el tiempo (líneas: 0,82 m incipiente y 0,107 m severa)", fontsize=10)
    F["margen"] = _png(fig)

    # Temperatura en el tiempo
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    por_estado(ax, "temperatura_motor_C", 4)
    ax.axhline(eq["alarma_C"], color=RAYO, ls="--", lw=1.4), ax.axhline(eq["disparo_C"], color=ROJO, ls="--", lw=1.4)
    ax.set_ylabel("°C"), ax.grid(alpha=.3), ax.legend(fontsize=6.5, markerscale=3, frameon=False, ncol=3, loc="upper left")
    ax.set_title("Temperatura del rodamiento en el tiempo, coloreada por estado", fontsize=10.5)
    F["temp_tiempo"] = _png(fig)

    # Boxplot temperatura
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    datos = [op.loc[op["estado"] == e, "temperatura_motor_C"].dropna().values for e in estados_op]
    bp = ax.boxplot(datos, patch_artist=True, showfliers=False, widths=.55)
    for p_, e in zip(bp["boxes"], estados_op):
        p_.set_facecolor(N.COLOR_ESTADO[e]), p_.set_alpha(.8)
    ax.set_xticks(range(1, len(estados_op) + 1))
    ax.set_xticklabels([N.NOMBRE_ESTADO[e].replace(" ", "\n", 1) for e in estados_op], fontsize=7.5)
    ax.axhline(eq["alarma_C"], color=RAYO, ls="--", lw=1.3), ax.set_ylabel("°C"), ax.grid(alpha=.3, axis="y")
    ax.set_title("Temperatura del rodamiento según el estado del equipo", fontsize=10.5)
    F["temp_box"] = _png(fig)

    # Vibración en el tiempo
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for y0, y1, c in ((0, eq["iso_A"], "#2E9E5B"), (eq["iso_A"], eq["iso_B"], "#F2B705"), (eq["iso_B"], eq["iso_C"], "#F28C28"), (eq["iso_C"], 9, "#D64545")):
        ax.axhspan(y0, y1, color=c, alpha=.10)
    ax.scatter(fechas, op["vibracion_succion_mm_s"], s=3, color=MARINO, alpha=.5, label="Succión")
    ax.scatter(fechas, op["vibracion_descarga_mm_s"], s=3, color=AZUL, alpha=.5, label="Descarga")
    ax.set_ylim(0, max(8, op["Vib_max"].max() * 1.05)), ax.set_ylabel("mm/s RMS"), ax.legend(fontsize=8, markerscale=4, frameon=False)
    ax.set_title("Vibración global sobre las zonas de severidad (normal, atención, alarma, crítico)", fontsize=10)
    F["vib"] = _png(fig)

    # Carga del motor
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    por_estado(ax, "carga_pct", 4)
    ax.axhline(100, color=RAYO, ls="--", lw=1.3), ax.set_ylabel("Carga (% de 3,0 A)"), ax.grid(alpha=.3)
    ax.legend(fontsize=6.5, markerscale=3, frameon=False, ncol=3)
    ax.set_title("Carga del motor (corriente medida / corriente nominal)", fontsize=10.5)
    F["carga"] = _png(fig)

    # Correlación
    vars_c = ["temperatura_motor_C", "vibracion_descarga_mm_s", "vibracion_succion_mm_s", "eta_global_pct", "nivel_tanque_mm", "I_prom_A",
              "potencia_activa_kW", "factor_potencia", "caudal_GPM", "head_total_m", "presion_succion_PSI", "margen_NPSH_m"]
    lab = ["Temperatura", "Vib. descarga", "Vib. succión", "Eficiencia", "Nivel tanque", "Corriente", "Potencia", "FP", "Caudal", "Altura",
           "P. succión", "Margen NPSH"]
    corr = op[vars_c].astype(float).corr()
    fig, ax = plt.subplots(figsize=(7.0, 6.0))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(lab))), ax.set_xticklabels(lab, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(lab))), ax.set_yticklabels(lab, fontsize=8)
    for i in range(len(lab)):
        for j in range(len(lab)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.3, color="white" if abs(v) > .6 else "#24324d")
    fig.colorbar(im, ax=ax, fraction=.04)
    for s_ in ax.spines.values():
        s_.set_visible(False)
    ax.set_title("Mapa de calor de correlación entre las variables", fontsize=10.5)
    F["corr"] = _png(fig)

    # Modelo: medido vs calculado y residuos
    X = N.matriz_terminos(op, modelo["terminos"])
    ok = X.notna().all(axis=1) & op["T_F"].notna()
    pred = modelo["intercepto"] + X[ok].values @ np.array(modelo["coeficientes"])
    real = op.loc[ok, "T_F"].values
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.4))
    lo, hi = min(real.min(), pred.min()), max(real.max(), pred.max())
    ax[0].scatter(real, pred, s=4, alpha=.35, color=AZUL), ax[0].plot([lo, hi], [lo, hi], color="gray", ls="--")
    ax[0].set_xlabel("Medida por el sensor (°F)"), ax[0].set_ylabel("Calculada por la ecuación (°F)"), ax[0].grid(alpha=.3)
    ax[0].set_title("Medida vs calculada", fontsize=10)
    ax[1].scatter(np.arange(len(real)), real - pred, s=3, alpha=.35, color=MARINO), ax[1].axhline(0, color=ROJO)
    ax[1].set_xlabel("Hora de operación (orden)"), ax[1].set_ylabel("Error (°F)"), ax[1].grid(alpha=.3), ax[1].set_title("Error de cada hora", fontsize=10)
    F["modelo"] = _png(fig)

    # Matriz de confusión
    cm = modelos["matriz"]
    et = [N.NOMBRE_ESTADO[c] for c in modelos["clases"]]
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(et))), ax.set_xticklabels(et, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(et))), ax.set_yticklabels(et, fontsize=8)
    for i in range(len(et)):
        for j in range(len(et)):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=9, color="white" if cm[i, j] > cm.max() / 2 else MARINO)
    ax.set_xlabel("Estado según la red neuronal"), ax.set_ylabel("Estado real")
    ax.set_title("Matriz de confusión (horas de prueba)", fontsize=10.5)
    F["confusion"] = _png(fig)

    # Índice de salud y vida útil
    hi_ = op[["horas_trabajo_acum_h", "health_index_rodamiento"]].dropna()
    cr = modelos["curva_rul"]
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.3))
    ax[0].plot(hi_["horas_trabajo_acum_h"], hi_["health_index_rodamiento"], color=MARINO, lw=1.4)
    ax[0].axhline(N.REGLAS["hi_degradacion"], color=NARANJA, ls="--", lw=1.2), ax[0].axhline(N.REGLAS["hi_critico"], color=ROJO, ls="--", lw=1.2)
    ax[0].set_xlabel("Horas de funcionamiento"), ax[0].set_ylabel("Índice de salud"), ax[0].grid(alpha=.3), ax[0].set_title("Desgaste del rodamiento", fontsize=10)
    ax[1].plot(cr["horas"], cr["RUL real"], color=NARANJA, lw=1.6, label="Real (recortada a 800 h)")
    ax[1].plot(cr["horas"], cr["RUL MLP"], color=AZUL, lw=1, alpha=.8, label="Calculada por la IA")
    ax[1].set_xlabel("Horas de funcionamiento"), ax[1].set_ylabel("Horas restantes"), ax[1].grid(alpha=.3), ax[1].legend(fontsize=7.5, frameon=False)
    ax[1].set_title("Vida útil restante", fontsize=10)
    F["rul"] = _png(fig)
    return F


# =============================================================================
# Documento
# =============================================================================
def generar(dbase: pd.DataFrame, dreg: pd.DataFrame, eq: dict, modelos: dict, modelo: dict, cat: list, req: dict,
            tabla_ir: pd.DataFrame, mant_estado: pd.DataFrame, base_dir: Path) -> bytes:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    op = dbase[dbase["estado_bomba"] == 1].copy()
    t = op["temperatura_motor_C"].dropna()
    F = figuras(dbase, op, eq, modelos, modelo)
    cap = base_dir / "capturas"
    sel = next((c for c in cat if c["Modelo"] == N.TX_COMPRA), None)
    alt_ = next((c for c in cat if c["Modelo"] == N.TX_ALTERNATIVA), None)
    patm = N.p_atm_kpa(eq)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    st_ = doc.styles["Normal"]
    st_.font.name, st_.font.size = "Calibri", Pt(11)
    st_.paragraph_format.space_after = Pt(6)
    for nivel, tam in ((1, 15), (2, 12.5)):
        h = doc.styles[f"Heading {nivel}"]
        h.font.name, h.font.size, h.font.color.rgb = "Calibri", Pt(tam), RGBColor(0x0A, 0x1F, 0x44)

    def sombrear(celda, color):
        tcPr = celda._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"), shd.set(qn("w:color"), "auto"), shd.set(qn("w:fill"), color)
        tcPr.append(shd)

    def P(texto, negrita=False, cursiva=False, centro=False, tam=None, color=None):
        p = doc.add_paragraph()
        for i, parte in enumerate(texto.split("**")):
            r = p.add_run(parte)
            r.bold = negrita or (i % 2 == 1)
            r.italic = cursiva
            if tam:
                r.font.size = Pt(tam)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if centro else WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    def B(texto):
        p = doc.add_paragraph(style="List Bullet")
        for i, parte in enumerate(texto.split("**")):
            p.add_run(parte).bold = (i % 2 == 1)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def NUM(items):
        for k, texto in enumerate(items, 1):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(0.9), Cm(-0.6)
            p.paragraph_format.space_after = Pt(3)
            p.add_run(f"{k}.  ").bold = True
            for i, parte in enumerate(texto.split("**")):
                p.add_run(parte).bold = (i % 2 == 1)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def EQ(texto):
        p = P(texto, negrita=True, centro=True)
        for r in p.runs:
            r.font.name = "Cambria Math"
        return p

    def H(texto, nivel=1):
        doc.add_heading(texto, level=nivel)

    n_fig, n_tab = [0], [0]

    def FIG(png, ancho_cm, pie):
        n_fig[0] += 1
        doc.add_picture(BytesIO(png) if isinstance(png, (bytes, bytearray)) else str(png), width=Cm(ancho_cm))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.paragraphs[-1].paragraph_format.keep_with_next = True
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f"Figura {n_fig[0]}. ")
        r.bold, r.font.size, r.font.color.rgb = True, Pt(9.5), RGBColor(0x0A, 0x1F, 0x44)
        r = p.add_run(pie)
        r.italic, r.font.size, r.font.color.rgb = True, Pt(9.5), RGBColor(0x5A, 0x6B, 0x88)

    def T(enc, filas, anchos=None, titulo=None, primera_col=False, tam=9.5):
        if titulo:
            n_tab[0] += 1
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(f"Tabla {n_tab[0]}. ")
            r.bold, r.font.size, r.font.color.rgb = True, Pt(9.5), RGBColor(0x0A, 0x1F, 0x44)
            r = p.add_run(titulo)
            r.italic, r.font.size, r.font.color.rgb = True, Pt(9.5), RGBColor(0x5A, 0x6B, 0x88)
            p.paragraph_format.keep_with_next = True
        tb = doc.add_table(rows=0, cols=len(enc) if enc else len(filas[0]))
        tb.style = "Table Grid"
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        if anchos:
            tb.autofit = False
        if enc:
            cs = tb.add_row().cells
            for i, v in enumerate(enc):
                cs[i].text = ""
                r = cs[i].paragraphs[0].add_run(str(v))
                r.bold, r.font.size, r.font.color.rgb = True, Pt(tam), RGBColor(0xFF, 0xFF, 0xFF)
                sombrear(cs[i], "0A1F44")
        for k, f in enumerate(filas):
            cs = tb.add_row().cells
            for i, v in enumerate(f):
                cs[i].text = ""
                r = cs[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(tam)
                if primera_col and i == 0:
                    r.bold = True
                    sombrear(cs[i], "E4ECF8")
                elif k % 2:
                    sombrear(cs[i], "F4F7FC")
        if anchos:
            for row in tb.rows:
                for i, w in enumerate(anchos):
                    row.cells[i].width = Cm(w)
        if enc:
            trPr = tb.rows[0]._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            th.set(qn("w:val"), "true")
            trPr.append(th)
        for row in tb.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        if len(tb.rows) <= 14:
            for row in tb.rows[:-1]:
                for cel in row.cells:
                    for par in cel.paragraphs:
                        par.paragraph_format.keep_with_next = True
        doc.add_paragraph()

    def salto():
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ============================ Portada ============================
    tl = doc.add_table(rows=1, cols=2)
    tl.autofit = False
    tl.cell(0, 0).width, tl.cell(0, 1).width = Cm(12.6), Cm(4)
    if (base_dir / "logo_espe.png").exists():
        tl.cell(0, 0).paragraphs[0].add_run().add_picture(str(base_dir / "logo_espe.png"), width=Cm(8))
    if (base_dir / "logo_em.png").exists():
        tl.cell(0, 1).paragraphs[0].add_run().add_picture(str(base_dir / "logo_em.png"), width=Cm(2.4))
        tl.cell(0, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    doc.add_paragraph()
    P("UNIVERSIDAD DE LAS FUERZAS ARMADAS ESPE – SEDE LATACUNGA", negrita=True, centro=True, tam=13, color="0A1F44")
    P("DEPARTAMENTO DE ELÉCTRICA Y ELECTRÓNICA", negrita=True, centro=True, tam=11)
    P("CARRERA DE INGENIERÍA ELECTROMECÁNICA", negrita=True, centro=True, tam=11)
    doc.add_paragraph()
    P("INFORME TÉCNICO", negrita=True, centro=True, tam=13, color="5A6B88")
    P("MANTENIMIENTO PREDICTIVO DE RODAMIENTOS DE LA BOMBA CENTRÍFUGA GOULDS 3642", negrita=True, centro=True, tam=17, color="0A1F44")
    P(eq.get("proyecto", ""), cursiva=True, centro=True, tam=11.5, color="5A6B88")
    doc.add_paragraph()
    T(None, [("Asignatura", N.ASIGNATURA), ("NRC", N.NRC), ("Período", N.PERIODO), ("Docente", N.DOCENTE),
             ("Integrantes", "\n".join(N.INTEGRANTES)), ("Equipo", f"Motor {eq['motor_marca']} {eq['motor_modelo']} + bomba {eq['bomba_marca']} {eq['bomba_modelo']}"),
             ("Fecha", datetime.now().strftime("%d/%m/%Y"))], anchos=[5, 11.5], primera_col=True, tam=10.5)
    salto()

    # ============================ Contenido ============================
    H("Contenido")
    temas = ["Introducción y objetivos", "Descripción del equipo", "Datos recolectados", "Variables calculadas", "Análisis hidráulico y cavitación",
             "Análisis térmico", "Análisis de vibraciones", "Análisis eléctrico", "Modelo matemático de la temperatura",
             "Estado de falla y vida útil del rodamiento", "Diagnóstico y soluciones", "Mantenimiento", "Transmisor de temperatura infrarrojo",
             "Aplicación de monitoreo"]
    if len(dreg):
        temas.append("Registros nuevos")
    temas += ["Conclusiones", "Recomendaciones", "Referencias"]
    for i, x in enumerate(temas, 1):
        P(f"{i}. {x}")
    salto()
    k = 0

    def SEC(titulo):
        nonlocal k
        k += 1
        H(f"{k}. {titulo}")
        return k

    # 1 Introducción
    s_ = SEC("Introducción y objetivos")
    P("Los rodamientos son el componente que más falla en los motores eléctricos pequeños. En una bomba centrífuga de montaje "
      "close-coupled, como la Goulds 3642, el impulsor va directamente sobre el eje del motor, de modo que los rodamientos del motor "
      "soportan además el empuje hidráulico de la bomba. Su desgaste aumenta la fricción, la temperatura y la vibración hasta que "
      "el rodamiento se traba. Además, el motor Emerson P55CST-1247 **no tiene protección térmica propia**, por lo que un sobrecalentamiento "
      "no detectado puede terminar en la falla del equipo.")
    P("El mantenimiento predictivo busca detectar ese deterioro antes de la falla, a partir de mediciones de operación. Este informe "
      "presenta el análisis de las mediciones recolectadas, el modelo matemático de la temperatura del rodamiento, la clasificación "
      "del estado de falla con inteligencia artificial, la vida útil restante del rodamiento, el diagnóstico con soluciones, la "
      "selección del transmisor de temperatura infrarrojo y la aplicación de monitoreo desarrollada.")
    H(f"{s_}.1 Objetivo general", 2)
    P("Desarrollar un sistema de monitoreo predictivo de los rodamientos del conjunto motor–bomba Goulds 3642 que, a partir de los datos "
      "de operación, estime la temperatura del rodamiento, identifique el estado de falla, calcule la vida útil restante y permita "
      "seleccionar el transmisor de temperatura infrarrojo adecuado.")
    H(f"{s_}.2 Objetivos específicos", 2)
    for x in ["Analizar las variables hidráulicas, térmicas, de vibración y eléctricas registradas en la recolección de datos.",
              "Obtener una ecuación matemática que estime la temperatura del rodamiento en °F y °C a partir de variables medibles.",
              "Clasificar el estado de falla y calcular la vida útil restante del rodamiento con una red neuronal.",
              "Proponer el diagnóstico, las soluciones y el plan de mantenimiento para cada estado de falla.",
              "Seleccionar el transmisor infrarrojo y definir su conexión al PLC S7-1200.",
              "Implementar una aplicación web, accesible desde el celular y la computadora, con alertas por Telegram."]:
        B(x)

    # 2 Equipo
    s_ = SEC("Descripción del equipo")
    T(["Parámetro", "Valor"], [
        ("Fabricante / modelo", f"{eq['motor_marca']} {eq['motor_modelo']}"), ("Potencia", f"{eq['motor_hp']} HP, trifásico, 60 Hz"),
        ("Voltaje / corriente nominal", f"208–230 / 460 V · {eq['motor_i']} A (a 230 V)"), ("Corriente con factor de servicio", f"{eq['motor_i_sf']} A (SF 1,5)"),
        ("Velocidad", f"{eq['motor_rpm']:.0f} rpm, {eq['motor_polos']} polos"), ("Aislamiento / ambiente máximo", "Clase B (130 °C) / 40 °C"),
        ("Protección", "IP22 abierto (ODP); protección térmica: ninguna"),
        ("Rodamientos", f"{eq['rod_DE']} lado bomba (DE) · {eq['rod_NDE']} lado ventilador (NDE)")],
      anchos=[5.5, 11], titulo="Datos del motor.", primera_col=True)
    T(["Parámetro", "Valor"], [
        ("Fabricante / modelo", f"{eq['bomba_marca']} {eq['bomba_modelo']} · index {eq['bomba_index']} · serie {eq['bomba_serie']}"),
        ("Tamaño / impulsor", f"{eq['bomba_tamano']} · impulsor de {eq['bomba_impulsor']} ({eq['bomba_alabes']} álabes)"),
        ("Configuración", "Centrífuga horizontal, monoetapa, close-coupled; succión 1 1/2\" NPT, descarga 1 1/4\" NPT"),
        ("Ubicación", f"{eq['ubicacion']}, {eq['altitud_m']:.0f} m s.n.m. (presión atmosférica {num(patm)} kPa)")],
      anchos=[5.5, 11], titulo="Datos de la bomba e instalación.", primera_col=True)
    FIG(F["curvas"], 15.5, "Curvas del fabricante: altura, eficiencia y NPSH requerido en función del caudal.")
    P("La curva H–Q indica la altura que entrega la bomba en buen estado para cada caudal; la de NPSH requerido, la presión mínima "
      "que necesita en la entrada para no cavitar. Ambas se usan como referencia para evaluar el desempeño y la cavitación.")

    # 3 Datos recolectados
    s_ = SEC("Datos recolectados")
    P(f"Se dispone de **{len(dbase)} registros horarios** entre el {dbase['timestamp'].min()[:10]} y el {dbase['timestamp'].max()[:10]} "
      f"({len(dbase) // 24} días). En **{len(op)} horas** la bomba estuvo funcionando; el resto corresponde a paradas nocturnas "
      "(23:00 a 04:59) y paradas operativas. Se midieron 17 variables:")
    T(["Variable", "Unidad", "Qué representa"], [(N.ETIQUETAS.get(k_, k_).split(" (")[0], u, dsc) for k_, (u, dsc) in DESC_VAR.items()],
      anchos=[5, 2.3, 9.2], titulo="Variables medidas en la recolección de datos.", tam=9)
    cnt = dbase["estado"].value_counts()
    T(["Estado", "Horas", "% del tiempo", "Qué significa"],
      [(N.NOMBRE_ESTADO[e], int(cnt.get(e, 0)), num(cnt.get(e, 0) / len(dbase) * 100), SIGNIFICADO[e]) for e in N.ESTADOS if cnt.get(e, 0)],
      anchos=[3.8, 1.6, 2, 9.1], titulo="Horas en cada estado del equipo.", primera_col=True, tam=9)
    FIG(F["linea_tiempo"], 16, "Línea de tiempo de los estados del equipo durante la recolección de datos.")
    ev = dbase[dbase["evento_mantenimiento"].notna()]
    if len(ev):
        P(f"**Evento de mantenimiento:** el {ev['timestamp'].iloc[0][:16]} se registró «{ev['evento_mantenimiento'].iloc[0]}» a las "
          f"{num(ev['horas_trabajo_acum_h'].iloc[0], 0)} h de funcionamiento. Antes del cambio, el rodamiento recorrió todas las etapas: "
          "normal, degradación y estado crítico. Después del cambio, el equipo volvió a operar normalmente.")

    # 4 Variables calculadas
    s_ = SEC("Variables calculadas")
    P("A partir de las mediciones, la aplicación calcula automáticamente las siguientes variables:")
    T(["Variable", "Fórmula", "Para qué sirve"], [
        ("Caudal", "Q (GPM) = Q (L/h) / 227,12", "Comparar con la curva del fabricante"),
        ("Altura total", "H = (P_desc − P_succ) × 0,703", "Energía entregada al agua (m)"),
        ("NPSH disponible", "NPSHa = (P_atm + P_succ − P_v)/(ρ·g) + v²/(2g)", "Presión disponible en la entrada (m)"),
        ("Margen contra cavitación", "Margen = NPSHa − NPSHr", "Sobre 0,82 m es seguro; bajo 0,107 m hay cavitación severa"),
        ("Presión atmosférica", "P_atm = 101,325·(1 − 2,25577×10⁻⁵·h)^5,25588", f"A {eq['altitud_m']:.0f} m: {num(patm)} kPa"),
        ("Potencia aparente / FP", "S = √(P² + Q²) · FP = P/S", "Carga eléctrica y aprovechamiento de la energía"),
        ("Carga del motor", "Carga = I_promedio / I_nominal × 100", f"Sobre 100 % el motor trabaja forzado (I_nominal = {eq['motor_i']} A)"),
        ("Desbalance", "Desb = (máximo − promedio) / promedio × 100", "Detecta problemas en las fases"),
        ("Eficiencia global", "η = ρ·g·Q·H / P_eléctrica × 100", "Rendimiento del conjunto motor–bomba"),
        ("Temperatura en °F", "T(°F) = 1,8·T(°C) + 32", "Unidad requerida para el modelo")],
      anchos=[3.5, 6.7, 6.3], titulo="Variables calculadas y sus fórmulas.", primera_col=True, tam=9)

    # 5 Hidráulico
    s_ = SEC("Análisis hidráulico y cavitación")
    eh = op["E_H_pct"].dropna()
    P(f"El caudal estuvo entre {num(op['caudal_GPM'].min())} y {num(op['caudal_GPM'].max())} GPM y la altura entre "
      f"{num(op['head_total_m'].min(), 2)} y {num(op['head_total_m'].max(), 2)} m. La Figura {n_fig[0] + 1} muestra que los puntos de operación "
      f"siguen la curva del fabricante (error medio de altura {num(eh.mean())} %): la bomba no presenta pérdida de desempeño importante.")
    FIG(F["hq"], 15.5, "Puntos de operación sobre la curva H–Q, coloreados por estado.")
    FIG(F["margen"], 15.5, "Margen contra cavitación en el tiempo y umbrales de los estados de cavitación.")
    cav = op[op["estado"].isin(["CAVITACION_INCIPIENTE", "CAVITACION_SEVERA", "FALLA_COMBINADA"])]
    nor = op[op["estado"] == "NORMAL"]
    P(f"Durante los episodios de cavitación el margen cae bruscamente (mediana {num(cav['margen_NPSH_m'].median(), 2)} m frente a "
      f"{num(nor['margen_NPSH_m'].median(), 2)} m en operación normal), junto con la presión de succión ({num(cav['presion_succion_PSI'].median(), 2)} psi "
      f"frente a {num(nor['presion_succion_PSI'].median(), 2)} psi). Estos episodios se deben a restricciones en la succión o nivel bajo del tanque.")
    H(f"{s_}.1 Efecto de la altitud de Latacunga", 2)
    P(f"Los datos recolectados calculan el NPSH a nivel del mar (101,3 kPa). En Latacunga, a {eq['altitud_m']:.0f} m, la presión atmosférica es "
      f"**{num(patm)} kPa**, por lo que el NPSH disponible baja en promedio **{num((op['margen_mar_m'] - op['margen_lat_m']).mean(), 2)} m**.")
    lat = pd.Series([N.estado_por_reglas(m, h, True) for m, h in zip(op["margen_lat_m"], op["health_index_rodamiento"])], index=op.index)
    pasan = int(((op["estado"] == "NORMAL") & (lat != "NORMAL")).sum())
    inc_sev = int(((op["estado"] == "CAVITACION_INCIPIENTE") & (lat == "CAVITACION_SEVERA")).sum())
    T(["Indicador", "Nivel del mar", "Latacunga"], [
        ("Presión atmosférica", "101,3 kPa", f"{num(patm)} kPa"),
        ("Margen contra cavitación medio", f"{num(op['margen_mar_m'].mean(), 2)} m", f"{num(op['margen_lat_m'].mean(), 2)} m"),
        ("Horas con margen bajo 0,82 m", int((op["margen_mar_m"] <= .82).sum()), int((op["margen_lat_m"] <= .82).sum())),
        ("Horas con margen bajo 0,107 m (severa)", int((op["margen_mar_m"] <= .107).sum()), int((op["margen_lat_m"] <= .107).sum()))],
      anchos=[7, 4, 4], titulo="Comparación del NPSH a nivel del mar y en Latacunga.", primera_col=True)
    FIG(F["npsh"], 15.5, "NPSH disponible a nivel del mar y en Latacunga frente al NPSH requerido.")
    P(f"**Interpretación:** con la presión real de Latacunga, {pasan} horas que eran «normales» pasarían a tener cavitación y {inc_sev} horas de "
      "cavitación incipiente pasarían a ser severas. Por eso las mediciones nuevas de la aplicación calculan el NPSH con la presión local, "
      "y la instalación real debe cuidar especialmente el nivel del tanque y la succión.")

    # 6 Térmico
    s_ = SEC("Análisis térmico")
    T(["Indicador", "°C", "°F"], [
        ("Mínima", num(t.min()), num(c2f(t.min()))), ("Mediana", num(t.median()), num(c2f(t.median()))),
        ("Percentil 95 %", num(t.quantile(.95)), num(c2f(t.quantile(.95)))), ("Máxima", num(t.max()), num(c2f(t.max()))),
        ("Alarma", num(eq["alarma_C"], 0), num(c2f(eq["alarma_C"]), 0)), ("Disparo", num(eq["disparo_C"], 0), num(c2f(eq["disparo_C"]), 0))],
      anchos=[6, 4, 4], titulo="Temperatura del rodamiento en operación.", primera_col=True)
    FIG(F["temp_tiempo"], 15.5, "Temperatura del rodamiento en el tiempo; líneas: alarma y disparo.")
    filas = []
    for e in N.ESTADOS:
        s2 = op.loc[op["estado"] == e, "temperatura_motor_C"].dropna()
        if len(s2):
            filas.append((N.NOMBRE_ESTADO[e], len(s2), num(s2.median()), num(c2f(s2.median())), num(s2.max()), num(c2f(s2.max()))))
    T(["Estado", "Horas", "Mediana °C", "Mediana °F", "Máxima °C", "Máxima °F"], filas, anchos=[4.6, 1.8, 2.5, 2.5, 2.5, 2.5],
      titulo="Temperatura del rodamiento según el estado.", primera_col=True, tam=9)
    FIG(F["temp_box"], 15, "Distribución de la temperatura del rodamiento en cada estado.")
    med_n = nor["temperatura_motor_C"].median()
    med_c = op.loc[op["estado"] == "RODAMIENTO_CRITICO", "temperatura_motor_C"].median()
    P(f"**Interpretación:** la temperatura sube de forma progresiva cuando el rodamiento se desgasta: de {num(med_n)} °C en operación normal a "
      f"{num(med_c)} °C en estado crítico (≈ {num(med_c - med_n, 0)} °C más). En cambio, la cavitación casi no cambia la temperatura. Esto "
      f"confirma que la temperatura de la tapa es un buen indicador del desgaste del rodamiento. La máxima registrada ({num(t.max())} °C) "
      f"estuvo cerca de la alarma de {num(eq['alarma_C'], 0)} °C justo antes del cambio de rodamiento.")

    # 7 Vibraciones
    s_ = SEC("Análisis de vibraciones")
    filas = []
    for col, nom in (("vibracion_succion_mm_s", "Succión"), ("vibracion_descarga_mm_s", "Descarga")):
        v = op[col]
        filas.append((nom, num(v.median(), 2), num(v.quantile(.95), 2), num(v.max(), 2), int((v > eq["iso_B"]).sum()), int((v > eq["iso_C"]).sum())))
    T(["Punto", "Mediana (mm/s)", "Percentil 95", "Máxima", f"Horas > {num(eq['iso_B'])}", f"Horas > {num(eq['iso_C'])}"], filas,
      anchos=[2.6, 2.8, 2.6, 2.4, 3, 3], titulo="Vibración global medida.", primera_col=True)
    FIG(F["vib"], 15.5, "Vibración global en succión y descarga sobre las zonas de severidad.")
    filas = []
    for e in N.ESTADOS:
        s2 = op.loc[op["estado"] == e]
        if len(s2):
            filas.append((N.NOMBRE_ESTADO[e], num(s2["vibracion_succion_mm_s"].median(), 2), num(s2["vibracion_descarga_mm_s"].median(), 2)))
    T(["Estado", "Vib. succión (mediana)", "Vib. descarga (mediana)"], filas, anchos=[5.5, 4.5, 4.5],
      titulo="Vibración según el estado del equipo (mm/s RMS).", primera_col=True)
    P("La vibración sube tanto con la cavitación (sobre todo en la succión) como con el desgaste del rodamiento (sobre todo en la descarga). "
      "Por eso, para distinguir la causa, se analizan las frecuencias características.")
    H(f"{s_}.1 Frecuencias de falla de los rodamientos", 2)
    P(f"Un daño localizado en un rodamiento genera vibración a frecuencias que dependen de su geometría y de la velocidad. A {eq['motor_rpm']:.0f} rpm "
      f"(frecuencia de giro fr = {num(eq['motor_rpm'] / 60, 2)} Hz):")
    filas = []
    for rod, lado in ((eq["rod_DE"], "DE"), (eq["rod_NDE"], "NDE")):
        a = N.analisis_rodamiento(rod, int(eq["motor_polos"]), 60.0, float(eq["motor_rpm"]), 60.0, None, None, None)
        g = a["geom"]
        hz = {r_["Falla"].split(" ")[0]: r_["Frecuencia (Hz)"] for r_ in a["tabla"].to_dict("records")}
        filas.append((f"{rod} ({lado})", f"{g['n']} / {g['d']} / {g['D']}", num(hz["FTF"], 1), num(hz["BPFO"], 1), num(hz["BPFI"], 1), num(hz["BSF"], 1)))
    T(["Rodamiento", "Bolas / d / D (mm)", "FTF jaula", "BPFO pista ext.", "BPFI pista int.", "BSF bolas"], filas,
      anchos=[3, 3.5, 2.4, 2.6, 2.6, 2.4], titulo="Frecuencias características de falla (Hz).", primera_col=True)
    P("Si el espectro de vibración muestra un pico que coincide (±2 %) con una de estas frecuencias, el daño está en esa parte del rodamiento. "
      "La sección «⚙️ Rodamientos» de la aplicación hace esta comparación automáticamente.")
    H(f"{s_}.2 Frecuencia de paso de álabes (cavitación)", 2)
    bpf = int(eq["bomba_alabes"]) * eq["motor_rpm"] / 60
    P(f"Con {eq['bomba_alabes']} álabes, la frecuencia de paso de álabes es BPF = Z × rpm / 60 = {eq['bomba_alabes']} × {eq['motor_rpm']:.0f} / 60 = "
      f"**{num(bpf)} Hz**. Un aumento de la amplitud en esa frecuencia (más de 25 % respecto a la condición normal) junto con vibración global "
      "alta indica cavitación probable, según el método de Sánchez, Carvajal, Poalacin y Salazar.")

    # 8 Eléctrico
    s_ = SEC("Análisis eléctrico")
    T(["Indicador", "Mediana", "Máximo"], [
        ("Corriente promedio (A)", num(op["I_prom_A"].median(), 2), num(op["I_prom_A"].max(), 2)),
        ("Carga del motor (%)", num(op["carga_pct"].median(), 0), num(op["carga_pct"].max(), 0)),
        ("Potencia activa (kW)", num(op["potencia_activa_kW"].median(), 3), num(op["potencia_activa_kW"].max(), 3)),
        ("Factor de potencia", num(op["factor_potencia"].median(), 3), num(op["factor_potencia"].max(), 3)),
        ("Desbalance de corriente (%)", num(op["desb_corriente_pct"].median(), 2), num(op["desb_corriente_pct"].max(), 2)),
        ("Desbalance de tensión (%)", num(op["desb_tension_pct"].median(), 2), num(op["desb_tension_pct"].max(), 2)),
        ("Eficiencia global (%)", num(op["eta_global_pct"].median()), num(op["eta_global_pct"].max()))],
      anchos=[6.5, 4, 4], titulo="Indicadores eléctricos en operación.", primera_col=True)
    FIG(F["carga"], 15.5, "Carga del motor en el tiempo, coloreada por estado.")
    P(f"El motor trabajó con una carga mediana de {num(op['carga_pct'].median(), 0)} % de su corriente nominal, sin sobrecargas. Los desbalances "
      "de corriente y tensión son bajos, por lo que la alimentación eléctrica no explica los calentamientos: estos se deben al desgaste del rodamiento.")

    # 9 Modelo
    s_ = SEC("Modelo matemático de la temperatura")
    P("El objetivo es una ecuación que calcule la temperatura del rodamiento a partir de variables que se miden en la bomba. Primero se "
      "identificaron las variables que más se relacionan con la temperatura mediante el coeficiente de correlación r (−1 a +1).")
    FIG(F["corr"], 13.5, "Mapa de calor de correlación entre las variables.")
    num_c = op[[c for c in N.CANDIDATAS if op[c].std() > 0] + ["T_F"]].astype(float).corr()["T_F"].drop("T_F")
    top = num_c.abs().sort_values(ascending=False).head(6)
    T(["Variable", "r", "Relación"], [(N.ETIQUETAS.get(v, v), num(num_c[v], 2),
                                      ("fuerte" if abs(num_c[v]) >= .7 else "moderada" if abs(num_c[v]) >= .4 else "débil") + (", directa" if num_c[v] > 0 else ", inversa"))
                                     for v in top.index], anchos=[8, 2, 5], titulo="Variables más relacionadas con la temperatura del rodamiento.", primera_col=True)
    P("Se eligieron las variables de mayor correlación que no repiten información entre sí (factor de inflación de la varianza menor a 5) y "
      "se ajustó una regresión lineal múltiple por mínimos cuadrados. La ecuación obtenida, en las dos unidades, es:")
    ef, ec = N.ecuaciones(modelo)
    EQ(ef)
    EQ(ec)
    P("Donde: " + N.leyenda_ecuacion(modelo) + ".", cursiva=True, tam=10)
    P(N.lectura_ecuacion(modelo, "°F"))
    T(["Indicador", "Valor", "Significado"], [
        ("R²", f"{num(modelo['r2'] * 100, 1)} %", "Porcentaje de los cambios de temperatura que explica la ecuación"),
        ("Error típico (RMSE)", f"±{num(modelo['rmse_F'], 2)} °F (±{num(modelo['rmse_F'] / 1.8, 2)} °C)", "Cuánto se equivoca en promedio"),
        ("Error con datos nuevos", f"±{num(modelo.get('rmse_validacion_F'), 2)} °F", "Entrenada con el 70 % de las horas y probada con el 30 % final"),
        ("Horas usadas", modelo["n"], "Horas de operación con todas las variables")],
      anchos=[4, 4.5, 8], titulo="Calidad del modelo matemático.", primera_col=True)
    FIG(F["modelo"], 16, "Temperatura medida frente a la calculada y error de cada hora.")
    P("**Interpretación:** la ecuación reproduce bien la temperatura en operación normal. El error con datos nuevos es mayor porque el desgaste "
      "del rodamiento ocurre al final del período y la ecuación no lo «vio» al ajustarse. En la práctica, si la lectura del transmisor supera a lo "
      f"calculado en más de dos errores típicos ({num(2 * modelo['rmse_F'], 1)} °F), hay que revisar el rodamiento o el sensor.")

    # 10 Estado y vida útil
    s_ = SEC("Estado de falla y vida útil del rodamiento")
    P("El estado del equipo se decide con dos indicadores: el margen contra cavitación y el índice de salud del rodamiento (1 = nuevo, 0 = fallado). "
      "Las reglas, obtenidas con un árbol de decisión, reproducen el 100 % de los estados registrados:")
    T(["Orden", "Condición", "Estado"], [
        (1, "Bomba detenida", "Detenida / Mantenimiento"),
        (2, f"Margen ≤ {N.REGLAS['margen_severa']} m e índice ≤ {N.REGLAS['hi_degradacion']}", "Falla combinada"),
        (3, f"Margen ≤ {N.REGLAS['margen_severa']} m", "Cavitación severa"), (4, f"Índice ≤ {N.REGLAS['hi_critico']}", "Rodamiento crítico"),
        (5, f"Margen ≤ {N.REGLAS['margen_incipiente']} m", "Cavitación incipiente"), (6, f"Índice ≤ {N.REGLAS['hi_degradacion']}", "Degradación de rodamiento"),
        (7, "Ninguna de las anteriores", "Normal")], anchos=[1.6, 9, 5.5], titulo="Reglas del estado de falla.")
    P("Como el índice de salud y el margen no se miden directamente en una planta real, se entrenó una **red neuronal (MLP)** que reconoce el "
      "estado a partir de 19 variables medibles (presiones, caudal, altura, nivel, vibraciones, temperatura, corrientes, voltajes, potencias, "
      "factor de potencia y desbalances), y otra que calcula la vida útil restante.")
    acc = float(np.trace(modelos["matriz"]) / modelos["matriz"].sum())
    T(["Indicador", "Resultado"], [
        ("Horas de entrenamiento / prueba", f"{modelos['n_train']} / {modelos['n_test']}"),
        ("Aciertos del estado en la prueba", f"{num(acc * 100, 1)} %"), ("F1 macro (promedio entre estados)", num(modelos["f1"], 3)),
        ("Error medio de la vida útil", f"±{num(modelos['mae'], 1)} h"), ("R² de la vida útil", num(modelos["r2"], 3))],
      anchos=[8, 6], titulo="Desempeño de la red neuronal.", primera_col=True)
    FIG(F["confusion"], 12.5, "Matriz de confusión: los números en la diagonal son aciertos.")
    FIG(F["rul"], 16, "Desgaste del rodamiento (índice de salud) y vida útil restante real y calculada.")
    P("**Interpretación:** mientras el rodamiento está sano solo se puede afirmar que le quedan «800 h o más». Unas 800–900 h antes de la falla "
      "el índice de salud empieza a bajar, suben la temperatura y la vibración, y la red neuronal puede calcular cuántas horas quedan. Esto da "
      "tiempo suficiente para programar el cambio del rodamiento.")
    T(["Modelo", "F1 (estado)", "Error vida útil (h)", "R² vida útil"], [
        ("MLP de referencia (TensorFlow)", "0,966", "15,4", "0,962"), ("LSTM de referencia (TensorFlow)", "0,646", "6,9", "0,993"),
        ("MLP de la aplicación (scikit-learn)", num(modelos["f1"], 3), num(modelos["mae"], 1), num(modelos["r2"], 3))],
      anchos=[6.5, 3, 3.5, 3], titulo="Comparación con los modelos de referencia.", primera_col=True)

    # 11 Diagnóstico
    s_ = SEC("Diagnóstico y soluciones")
    P("Para cada estado de falla, la aplicación muestra qué está pasando, las causas probables y las acciones recomendadas:")
    filas = []
    for e in ("CAVITACION_INCIPIENTE", "CAVITACION_SEVERA", "DEGRADACION_RODAMIENTO", "RODAMIENTO_CRITICO", "FALLA_COMBINADA"):
        sol = N.SOLUCIONES[e]
        filas.append((N.NOMBRE_ESTADO[e], "\n".join("• " + c for c in sol["causas"][:3]), "\n".join("• " + a for a in sol["acciones"][:3])))
    T(["Estado", "Causas probables", "Qué hacer"], filas, anchos=[3.2, 6.5, 6.8], titulo="Diagnóstico y soluciones por estado.", primera_col=True, tam=8.5)
    T(["Condición adicional", "Límite", "Acción principal"], [
        ("Temperatura del rodamiento", f"Alarma {num(eq['alarma_C'], 0)} °C · disparo {num(eq['disparo_C'], 0)} °C", "Vigilar; sobre el disparo, detener y dejar enfriar"),
        ("Vida útil restante baja", f"Menos de {num(eq['rul_aviso_h'], 0)} h", "Programar el cambio de rodamiento"),
        ("Vibración global", f"Alarma > {num(eq['iso_B'])} · crítico > {num(eq['iso_C'])} mm/s", "Analizar el espectro; reapretar anclajes"),
        ("Corriente del motor", f"Nominal {eq['motor_i']} A · servicio {eq['motor_i_sf']} A", "Medir voltajes; cerrar parcialmente la descarga"),
        ("Desbalance de corriente", "Más de 10 %", "Revisar tensiones y bornes")],
      anchos=[4, 5.5, 7], titulo="Otras condiciones que generan diagnóstico y alerta.", primera_col=True, tam=9)

    # 12 Mantenimiento
    s_ = SEC("Mantenimiento")
    u = op.sort_values("timestamp").iloc[-1]
    P(f"En el último registro (horas acumuladas {num(u['horas_trabajo_acum_h'], 0)} h) el equipo está en estado «{N.NOMBRE_ESTADO.get(u['estado'], u['estado'])}» "
      f"y el rodamiento nuevo tiene una vida útil restante de {num(u['RUL_h'], 0)} h. El cambio de rodamiento debe programarse cuando la vida útil "
      f"restante calculada baje de {num(eq['rul_aviso_h'], 0)} h. Además se propone el siguiente plan preventivo:")
    if len(mant_estado):
        T(["Tarea", "Frecuencia"], [(r_["Tarea"], r_["Frecuencia"]) for r_ in mant_estado.to_dict("records")],
          anchos=[11, 5], titulo="Plan de mantenimiento preventivo.", primera_col=True)

    # 13 Transmisor
    s_ = SEC("Transmisor de temperatura infrarrojo")
    if sel:
        cumplen = [x["Modelo"] for x in tabla_ir.to_dict("records") if x["Cumple todo"]]
        P(f"Se evaluaron {len(cat)} transmisores frente a criterios obtenidos de los datos (rango, óptica, tamaño del punto medido, respuesta, "
          f"temperatura ambiente, exactitud, salida, alimentación y protección). Cumplen todos: {', '.join(cumplen)}. Se seleccionó para la compra el "
          f"**{sel['Marca'].split(' (')[0]} {sel['Modelo']}** y como alternativa técnica el **{alt_['Marca']} {alt_['Modelo']}**." if alt_ else "")
        T(["Parámetro", sel["Modelo"]], [
            ("Rango", "0 a 100 °C"), ("Óptica", f"20:1 (a {req['distancia_mm']:.0f} mm mide {num(N.punto_medido(sel, req['distancia_mm']))} mm)"),
            ("Exactitud", "±2 °C o ±1,5 %"), ("Respuesta", "200 ms"), ("Salida / alimentación", "4–20 mA / 9–32 VDC"),
            ("Protección / ambiente", "IP65 / 0–60 °C"), ("Conexión al PLC", "Módulo SM 1231 AI4, canal 4..20 mA"),
            ("Escalado", "NORM_X (0–27648) → SCALE_X (0–100 °C)")], anchos=[5, 11], titulo="Resumen del transmisor seleccionado.", primera_col=True)
        P("El detalle completo de la selección, la instalación, la conexión y el escalado está en el **Informe de selección del transmisor IR**, "
          "que se genera desde la misma aplicación.")

    # 14 Aplicación
    s_ = SEC("Aplicación de monitoreo")
    P("Se desarrolló una aplicación web en Python (Streamlit) con la identidad de la ESPE Sede Latacunga y de la carrera de Ingeniería "
      "Electromecánica. Funciona desde el navegador del celular o de la computadora y puede instalarse como aplicación en la pantalla de inicio.")
    T(["Componente", "Función"], [
        ("Streamlit Community Cloud", "Publica la aplicación en internet (rodamientos-espe.streamlit.app)"),
        ("Supabase (base de datos)", "Guarda los registros y la configuración en la nube; celular y PC ven lo mismo"),
        ("GitHub", "Almacena el código; cada cambio se publica automáticamente"),
        ("Telegram", "Envía alertas al celular con la falla, la causa y la acción"),
        ("scikit-learn", "Entrena la red neuronal del estado de falla y la vida útil"),
        ("python-docx / matplotlib", "Generan los informes en Word con sus gráficas")],
      anchos=[5, 11], titulo="Componentes del sistema.", primera_col=True)
    T(["Sección", "Qué hace"], SECCIONES_APP, anchos=[4.5, 12], titulo="Secciones de la aplicación.", primera_col=True, tam=9)
    capturas = [("app_inicio.png", 15.5, "Pantalla de inicio: encabezado, integrantes, menú y ruta del proyecto."),
                ("app_registro.png", 13, "Registro de datos: prueba con datos recolectados, valores calculados y resultados."),
                ("app_diagnostico.png", 13.5, "Diagnóstico de un registro y horas en cada estado."),
                ("app_transmisor_evaluacion.png", 13.5, "Criterios de selección y evaluación de los transmisores."),
                ("app_transmisor_resultado.png", 13, "Resultado de la selección: transmisor para compra, alternativa y ficha técnica."),
                ("app_telegram.png", 7, "Alertas recibidas en el celular por Telegram (prueba, alerta y crítico).")]
    for arch, ancho, pie in capturas:
        if (cap / arch).exists():
            FIG(cap / arch, ancho, pie)
    P("Las alertas se envían cuando se guarda una medición con falla, durante la simulación (si se activa) y una vez al día si hay tareas de "
      "mantenimiento vencidas. Para que lleguen de forma automática, sin registro manual, se prevé leer el PLC S7-1200 desde la aplicación.")

    # Registros nuevos
    if len(dreg):
        s_ = SEC("Registros nuevos")
        P(f"Además de los datos recolectados, se ingresaron {len(dreg)} registros nuevos. Su estado se calculó con la red neuronal y el margen contra "
          "cavitación con la presión de Latacunga:")
        filas = []
        for r_ in dreg.sort_values("timestamp").to_dict("records")[-25:]:
            dg = N.diagnosticar(r_, eq)
            filas.append((str(r_["timestamp"])[:16], N.NOMBRE_ESTADO.get(r_["estado"], r_["estado"]), num(r_.get("temperatura_motor_C")),
                          num(r_.get("RUL_h"), 0), dg[0]["Acciones"][0] if dg else "Ninguna"))
        T(["Fecha", "Estado", "T (°C)", "Vida útil (h)", "Acción principal"], filas, anchos=[3, 3.3, 1.8, 2.3, 6.1],
          titulo="Registros nuevos (últimos 25).", tam=8.5)

    # Conclusiones
    SEC("Conclusiones")
    for x in [f"Se analizaron {len(dbase)} horas de datos ({len(op)} en operación) de la bomba Goulds 3642, que incluyen operación normal, "
              "episodios de cavitación y el ciclo completo de desgaste de un rodamiento hasta su cambio.",
              f"La temperatura de la tapa del rodamiento sube unos {num(med_c - med_n, 0)} °C entre la operación normal y el estado crítico, por lo que es un "
              "indicador confiable del desgaste y justifica el uso de un transmisor infrarrojo.",
              f"La ecuación obtenida estima la temperatura con R² = {num(modelo['r2'], 3)} y un error típico de ±{num(modelo['rmse_F'], 1)} °F "
              f"(±{num(modelo['rmse_F'] / 1.8, 1)} °C), y se presenta en °F y °C.",
              f"La red neuronal reconoce el estado del equipo con {num(acc * 100, 1)} % de aciertos y calcula la vida útil restante con un error medio de "
              f"±{num(modelos['mae'], 0)} h, lo que permite programar el cambio del rodamiento con anticipación.",
              f"La altitud de Latacunga reduce el NPSH disponible en unos {num((op['margen_mar_m'] - op['margen_lat_m']).mean(), 1)} m; con la presión local, "
              f"{pasan} horas normales pasarían a tener cavitación, por lo que la succión es un punto crítico en la instalación real.",
              (f"Se seleccionó el transmisor {sel['Marca'].split(' (')[0]} {sel['Modelo']}, que cumple todos los criterios técnicos, con el "
               f"{alt_['Marca']} {alt_['Modelo']} como alternativa." if sel and alt_ else "Se seleccionó el transmisor infrarrojo."),
              "La aplicación integra el registro, el análisis, el diagnóstico, el mantenimiento, la selección del transmisor y las alertas, y es "
              "accesible desde el celular y la computadora."]:
        B(x)

    SEC("Recomendaciones")
    for x in ["Validar el transmisor instalado con un termómetro de referencia (PT100 o IR portátil) y aplicar la corrección en el PLC si es necesario.",
              "Pegar cinta negra mate en el punto de medición y mantener siempre la misma distancia y el mismo punto.",
              "Mantener el nivel del tanque y limpiar periódicamente el colador de succión, debido al menor NPSH disponible en Latacunga.",
              "Volver a entrenar el modelo y la red neuronal cuando se disponga de datos reales del banco, incluyendo más de un ciclo de desgaste.",
              "Implementar la lectura automática del PLC para que el monitoreo y las alertas funcionen sin registro manual.",
              "Confirmar con el fabricante la designación de los rodamientos y el número de álabes del impulsor."]:
        B(x)

    SEC("Referencias")
    for x in ["Çengel, Y. A., & Cimbala, J. M. (2018). Mecánica de fluidos: fundamentos y aplicaciones (4.ª ed.). McGraw-Hill.",
              "Çengel, Y. A., & Ghajar, A. J. (2011). Transferencia de calor y masa (4.ª ed.). McGraw-Hill.",
              "Goulds Water Technology – Xylem. (s. f.). Models 3642/3742 technical brochure.",
              "Harris, T. A., & Kotzalas, M. N. (2006). Rolling bearing analysis (5.ª ed.). CRC Press.",
              "International Organization for Standardization. (1995). ISO 10816-1: Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts.",
              "Montgomery, D. C., Peck, E. A., & Vining, G. G. (2012). Introduction to linear regression analysis (5.ª ed.). Wiley.",
              "Pedregosa, F. et al. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825–2830.",
              "Sánchez, Carvajal, Poalacin y Salazar. (s. f.). Detection of cavitation in centrifugal pump for vibration analysis.",
              "BIEDAS. (s. f.). Operation manual of the fixed infrared thermometer BYDXAC/BC/CC/R4C/R2C.",
              "Siemens AG. (s. f.). SIMATIC S7-1200 Programmable controller: System manual."]:
        p = doc.add_paragraph(x)
        p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(1), Cm(-1)

    b = BytesIO()
    doc.save(b)
    return b.getvalue()
