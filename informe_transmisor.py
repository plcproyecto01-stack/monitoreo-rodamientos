# -*- coding: utf-8 -*-
"""Informe detallado de selección del transmisor de temperatura infrarrojo (Word .docx)."""
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

import nucleo as N

AZUL, MARINO, RAYO, ROJO, VERDE, GRIS = "#1F6FEB", "#0A1F44", "#F2B705", "#D64545", "#2E9E5B", "#5A6B88"


def c2f(c):
    return c * 1.8 + 32


def num(x, nd=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:.{nd}f}".replace(".", ",")


def escalado(t_min: float, t_max: float, modo: str) -> pd.DataFrame:
    """Tabla corriente → valor digital del PLC → temperatura. modo: '4-20' (SM 1231 configurado 4–20 mA) o '0-20'."""
    filas = []
    for ma in (4, 8, 12, 16, 20):
        raw = (ma - 4) / 16 * 27648 if modo == "4-20" else ma / 20 * 27648
        t = t_min + (ma - 4) / 16 * (t_max - t_min)
        filas.append({"Corriente (mA)": ma, "Valor en el PLC": int(round(raw)), "Temperatura (°C)": t, "Temperatura (°F)": c2f(t)})
    return pd.DataFrame(filas)


# -----------------------------------------------------------------------------
# Figuras
# -----------------------------------------------------------------------------
def _fig_png(fig) -> bytes:
    import matplotlib.pyplot as plt
    b = BytesIO()
    fig.tight_layout()
    fig.savefig(b, format="png", dpi=170)
    plt.close(fig)
    return b.getvalue()


def figuras(op: pd.DataFrame, eq: dict, cat: list, req: dict, sel: dict, alt_: dict) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False})
    F = {}
    t = op["temperatura_motor_C"].dropna()

    # 1. Histograma con límites y rango del sensor
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    ax.axvspan(sel["T_min_C"], sel["T_max_C"], color=AZUL, alpha=.07, label=f"Rango del {sel['Modelo']} ({sel['T_min_C']}–{sel['T_max_C']} °C)")
    ax.hist(t, bins=34, color=AZUL, alpha=.9)
    ax.axvline(eq["alarma_C"], color=RAYO, lw=2, ls="--", label=f"Alarma {eq['alarma_C']:.0f} °C")
    ax.axvline(eq["disparo_C"], color=ROJO, lw=2, ls="--", label=f"Disparo {eq['disparo_C']:.0f} °C")
    ax.axvline(t.max(), color=MARINO, lw=1.4, ls=":", label=f"Máxima medida {t.max():.1f} °C")
    ax.set_xlim(30, 105), ax.set_xlabel("Temperatura del rodamiento (°C)"), ax.set_ylabel("Horas de operación")
    ax.legend(frameon=False, fontsize=8), ax.grid(alpha=.3)
    ax.set_title("Temperaturas registradas frente al rango del transmisor", fontsize=11)
    F["hist"] = _fig_png(fig)

    # 2. Temperatura por estado
    orden = [e for e in N.ESTADOS if e in set(op["estado"])]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    datos = [op.loc[op["estado"] == e, "temperatura_motor_C"].dropna().values for e in orden]
    bp = ax.boxplot(datos, patch_artist=True, showfliers=False, widths=.55)
    for p_, e in zip(bp["boxes"], orden):
        p_.set_facecolor(N.COLOR_ESTADO[e]), p_.set_alpha(.8)
    ax.set_xticks(range(1, len(orden) + 1))
    ax.set_xticklabels([N.NOMBRE_ESTADO[e].replace(" de ", "\nde ").replace(" ", "\n", 1) if len(N.NOMBRE_ESTADO[e]) > 12 else N.NOMBRE_ESTADO[e] for e in orden], fontsize=8)
    ax.axhline(eq["alarma_C"], color=RAYO, ls="--", lw=1.5), ax.axhline(eq["disparo_C"], color=ROJO, ls="--", lw=1.5)
    ax.set_ylabel("°C"), ax.grid(alpha=.3, axis="y"), ax.set_title("Temperatura del rodamiento en cada estado del equipo", fontsize=11)
    F["estados"] = _fig_png(fig)

    # 3. Punto medido vs distancia
    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    L = np.linspace(0, 400, 200)
    for c, col, ls in ((sel, AZUL, "-"), (alt_, VERDE, "-"), (next(x for x in cat if x["Modelo"] == "SA-80T-2A"), GRIS, "--")):
        ax.plot(L, [N.punto_medido(c, x) for x in L], color=col, lw=2.2, ls=ls, label=f"{c['Modelo']} (D:S {c['DS']:g}:1)")
    if sel.get("Spot_D_mm"):
        ax.plot(sel["Spot_D_mm"][:3], sel["Spot_S_mm"][:3], "o", color=AZUL, ms=5, label="Datos del fabricante BIEDAS")
    ax.axhline(req["spot_max_mm"], color=ROJO, ls="--", lw=1.5, label=f"Punto máximo admisible ({req['spot_max_mm']:.0f} mm)")
    ax.axhline(eq["ir_d_objetivo_mm"], color=RAYO, ls=":", lw=1.5, label=f"Diámetro útil de la tapa ({eq['ir_d_objetivo_mm']:.0f} mm)")
    ax.axvline(req["distancia_mm"], color="gray", ls=":", lw=1.2)
    ax.text(req["distancia_mm"] + 5, 2, f"Montaje a {req['distancia_mm']:.0f} mm", fontsize=8, color="#444")
    ax.set_xlim(0, 400), ax.set_ylim(0, 70), ax.set_xlabel("Distancia sensor–tapa (mm)"), ax.set_ylabel("Diámetro del punto medido (mm)")
    ax.legend(frameon=False, fontsize=7.6, loc="upper left"), ax.grid(alpha=.3)
    ax.set_title("Tamaño del círculo que mide cada sensor según la distancia", fontsize=11)
    F["spot"] = _fig_png(fig)

    # 4. Diagrama de conexión
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    ax.axis("off"), ax.set_xlim(0, 100), ax.set_ylim(0, 54)

    def caja(x, y, w, h, txt, fc):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5", fc=fc, ec=MARINO, lw=1.2))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", color="white", fontsize=8.6)

    caja(3, 36, 18, 12, "Fuente\n24 VDC\n(+)   (−)", MARINO)
    caja(3, 6, 20, 17, f"Transmisor IR\n{sel['Modelo']}\n0–100 °C\n4–20 mA", AZUL)
    caja(73, 6, 24, 42, "PLC S7-1200\nCPU 1214C\n+\nmódulo\nSM 1231 AI4\n\ncanal 0\nrango 4..20 mA", MARINO)

    def cable(xs, ys, col, txt=None, tx=0, ty=0, lw=2.2):
        ax.plot(xs, ys, color=col, lw=lw, solid_capstyle="round")
        if txt:
            ax.text(tx, ty, txt, fontsize=8, color=col, fontweight="bold")
    cable([9, 9, 9], [35.4, 30, 23.6], "#D64545", "Rojo: +24 V", 10.2, 28.5)
    cable([16, 16], [35.4, 23.6], "#222222", "Negro: 0 V", 17.2, 31)
    cable([23.6, 72.4], [17, 17], "#1F6FEB", "Azul: señal 4–20 mA (+)  →  AI0+", 30, 18.2)
    cable([23.6, 72.4], [12, 12], "#E07B14", "Naranja: señal 4–20 mA (−)  →  AI0−", 30, 13.2)
    cable([23.6, 50, 50], [8, 8, 2.5], "#8A96A3", "Plateado: pantalla", 30, 4.4)
    ax.plot([47, 53], [2.5, 2.5], color="#444", lw=1.6), ax.plot([48.3, 51.7], [1.5, 1.5], color="#444", lw=1.4), ax.plot([49.4, 50.6], [.6, .6], color="#444", lw=1.2)
    ax.text(54, 1.3, "Tierra (PE)", fontsize=8, color="#444")
    cable([21.6, 72.4], [44, 44], "#D64545", lw=1.2)
    cable([21.6, 72.4], [40, 40], "#222222", lw=1.2)
    ax.text(25, 45.2, "+24 V y 0 V también alimentan el módulo (L+ / M)", fontsize=7.6, color="#555")
    ax.set_title("Conexión a 4 hilos del BYD10AS al PLC (colores según el manual del fabricante)", fontsize=10.5)
    F["conexion"] = _fig_png(fig)

    # 5. Recta de escalado
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ma = np.linspace(4, 20, 50)
    tt = sel["T_min_C"] + (ma - 4) / 16 * (sel["T_max_C"] - sel["T_min_C"])
    ax.plot(ma, tt, color=AZUL, lw=2.4)
    for m_ in (4, 8, 12, 16, 20):
        v = sel["T_min_C"] + (m_ - 4) / 16 * (sel["T_max_C"] - sel["T_min_C"])
        ax.plot(m_, v, "o", color=MARINO), ax.text(m_ + .2, v - 6, f"{v:.0f} °C\n({c2f(v):.0f} °F)", fontsize=7.5)
    ax.axhline(eq["alarma_C"], color=RAYO, ls="--", lw=1.3), ax.axhline(eq["disparo_C"], color=ROJO, ls="--", lw=1.3)
    ax.set_xlabel("Corriente del lazo (mA)"), ax.set_ylabel("Temperatura (°C)"), ax.grid(alpha=.3)
    ax.set_title(f"Recta de conversión del {sel['Modelo']}: 4–20 mA → {sel['T_min_C']}–{sel['T_max_C']} °C", fontsize=11)
    F["escala"] = _fig_png(fig)

    # 6. Puntaje
    return F


# -----------------------------------------------------------------------------
# Documento
# -----------------------------------------------------------------------------
def generar(dbase: pd.DataFrame, eq: dict, cat: list, req: dict, tabla: pd.DataFrame, base_dir: Path) -> bytes:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    sel = next(c for c in cat if c["Modelo"] == N.TX_COMPRA)
    alt_ = next((c for c in cat if c["Modelo"] == N.TX_ALTERNATIVA), None) or next(c for c in cat if c["Modelo"] != N.TX_COMPRA)
    op = dbase[dbase["estado_bomba"] == 1].copy()
    t = op["temperatura_motor_C"].dropna()
    F = figuras(op, eq, cat, req, sel, alt_)
    cat_dir = base_dir / "catalogos"

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
        partes = texto.split("**")
        for i, parte in enumerate(partes):
            r = p.add_run(parte)
            r.bold = negrita or (i % 2 == 1)
            r.italic = cursiva
            if tam:
                r.font.size = Pt(tam)
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
        if centro:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    def B(texto, estilo="List Bullet"):
        p = doc.add_paragraph(style=estilo)
        for i, parte in enumerate(texto.split("**")):
            p.add_run(parte).bold = (i % 2 == 1)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    def NUM(items):
        """Lista numerada que siempre empieza en 1."""
        for k, texto in enumerate(items, 1):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(0.9), Cm(-0.6)
            p.paragraph_format.space_after = Pt(3)
            p.add_run(f"{k}.  ").bold = True
            for i, parte in enumerate(texto.split("**")):
                p.add_run(parte).bold = (i % 2 == 1)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def H(texto, nivel=1):
        doc.add_heading(texto, level=nivel)

    n_fig = [0]
    n_tab = [0]

    def FIG(png: bytes | Path, ancho_cm: float, pie: str):
        n_fig[0] += 1
        doc.add_picture(BytesIO(png) if isinstance(png, (bytes, bytearray)) else str(png), width=Cm(ancho_cm))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
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
        if anchos:
            tb.autofit = False
        tb.style = "Table Grid"
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
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
                txt = str(v)
                r = cs[i].paragraphs[0].add_run(txt)
                r.font.size = Pt(tam)
                if primera_col and i == 0:
                    r.bold = True
                    sombrear(cs[i], "E4ECF8")
                elif k % 2:
                    sombrear(cs[i], "F4F7FC")
                if txt == "✔":
                    r.font.color.rgb = RGBColor(0x2E, 0x9E, 0x5B)
                elif txt == "✘":
                    r.font.color.rgb = RGBColor(0xD6, 0x45, 0x45)
        if anchos:
            for row in tb.rows:
                for i, w in enumerate(anchos):
                    row.cells[i].width = Cm(w)
        if enc:  # repetir la cabecera si la tabla pasa de página
            trPr = tb.rows[0]._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            th.set(qn("w:val"), "true")
            trPr.append(th)
        for row in tb.rows:  # no partir una fila entre páginas
            trPr = row._tr.get_or_add_trPr()
            cs_ = OxmlElement("w:cantSplit")
            trPr.append(cs_)
        if len(tb.rows) <= 14:  # mantener juntas las tablas cortas
            for row in tb.rows[:-1]:
                for cel in row.cells:
                    for par in cel.paragraphs:
                        par.paragraph_format.keep_with_next = True
        doc.add_paragraph()
        return tb

    def salto():
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ========================= Portada =========================
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
    P("INFORME DE SELECCIÓN DEL TRANSMISOR DE TEMPERATURA INFRARROJO", negrita=True, centro=True, tam=17, color="0A1F44")
    P("Monitoreo de la temperatura de los rodamientos del motor Emerson P55CST-1247 acoplado a la bomba centrífuga Goulds 3642",
      cursiva=True, centro=True, tam=11.5, color="5A6B88")
    doc.add_paragraph()
    T(None, [("Asignatura", N.ASIGNATURA), ("NRC", N.NRC), ("Período", N.PERIODO), ("Docente", N.DOCENTE),
             ("Integrantes", "\n".join(N.INTEGRANTES)), ("Transmisor seleccionado", f"{sel['Marca']} {sel['Modelo']}"),
             ("Fecha", datetime.now().strftime("%d/%m/%Y"))], anchos=[5, 11.5], primera_col=True, tam=10.5)
    P("Nota: la selección es técnica. El costo no se incluye porque las cotizaciones aún no están disponibles.", cursiva=True, centro=True, tam=9, color="5A6B88")
    salto()

    # ========================= Contenido =========================
    H("Contenido")
    for i, x in enumerate(["Objetivos", "Equipo y punto de medición", "Condiciones del proceso", "Criterios de selección",
                           "Transmisores evaluados", "Evaluación criterio por criterio", "Cálculo del punto de medición",
                           "Transmisor seleccionado: BIEDAS BYD10AS", "Alternativa técnica: Optris CT LT22", "Instalación mecánica",
                           "Conexión eléctrica al PLC", "Escalado de la señal en TIA Portal", "Validación y calibración",
                           "Mantenimiento del sensor", "Lista de materiales", "Conclusiones", "Referencias"], 1):
        P(f"{i}. {x}")
    salto()

    # 1
    H("1. Objetivos")
    H("1.1 Objetivo general", 2)
    P("Seleccionar el transmisor de temperatura infrarrojo más adecuado para vigilar, sin contacto, la temperatura de los "
      "rodamientos del conjunto motor–bomba, a partir de las temperaturas registradas en la recolección de datos y de las "
      "condiciones reales de instalación.")
    H("1.2 Objetivos específicos", 2)
    for x in ["Caracterizar el rango de temperaturas del rodamiento en cada estado de operación del equipo.",
              "Definir y justificar cuantitativamente los criterios técnicos que debe cumplir el transmisor.",
              f"Comparar {len(cat)} transmisores de diferentes fabricantes frente a esos criterios.",
              "Elegir el transmisor a adquirir y una alternativa técnica, explicando las razones.",
              "Establecer la instalación mecánica, la conexión eléctrica al PLC S7-1200 y el escalado de la señal en TIA Portal."]:
        B(x)

    # 2
    H("2. Equipo y punto de medición")
    T(["Elemento", "Datos"], [
        ("Motor", f"{eq['motor_marca']} {eq['motor_modelo']}, {eq['motor_hp']} HP, trifásico, {eq['motor_rpm']:.0f} rpm, 2 polos, aislamiento clase B, IP22 abierto (ODP), ambiente máximo 40 °C, protección térmica: ninguna"),
        ("Bomba", f"{eq['bomba_marca']} {eq['bomba_modelo']}, tamaño {eq['bomba_tamano']}, impulsor {eq['bomba_impulsor']}, montaje close-coupled (el impulsor va en el eje del motor)"),
        ("Rodamientos vigilados", f"{eq['rod_DE']} en el lado de la bomba (DE) y {eq['rod_NDE']} en el lado del ventilador (NDE)"),
        ("Superficie medida", f"Tapa (escudo) del rodamiento; diámetro útil ≈ {eq['ir_d_objetivo_mm']:.0f} mm"),
        ("Distancia de montaje prevista", f"{eq['ir_distancia_mm']:.0f} mm entre la lente del sensor y la tapa"),
        ("Controlador", "PLC Siemens S7-1200, CPU 1214C DC/DC/DC (entradas analógicas integradas 0–10 V)")],
      anchos=[4.5, 12], titulo="Datos del equipo y del punto de medición.", primera_col=True)
    P("El sensor infrarrojo no mide el interior del rodamiento sino la temperatura de la superficie de su tapa. Como el motor no "
      "tiene protección térmica propia, esta medición es la única vigilancia térmica del conjunto. En una bomba close-coupled "
      "los rodamientos del motor soportan también el empuje del impulsor, por lo que el lado de la bomba (DE) es el punto prioritario.")

    # 3
    H("3. Condiciones del proceso")
    P(f"Se analizaron **{len(op)} horas de operación** de la recolección de datos (del {op['timestamp'].min()[:10]} al "
      f"{op['timestamp'].max()[:10]}). La Tabla {n_tab[0] + 1} resume las temperaturas registradas en la tapa del rodamiento.")
    T(["Indicador", "°C", "°F"], [
        ("Mínima", num(t.min()), num(c2f(t.min()))), ("Percentil 5 %", num(t.quantile(.05)), num(c2f(t.quantile(.05)))),
        ("Mediana", num(t.median()), num(c2f(t.median()))), ("Percentil 95 %", num(t.quantile(.95)), num(c2f(t.quantile(.95)))),
        ("Máxima", num(t.max()), num(c2f(t.max()))), ("Límite de alarma", num(eq["alarma_C"], 0), num(c2f(eq["alarma_C"]), 0)),
        ("Límite de disparo (parada)", num(eq["disparo_C"], 0), num(c2f(eq["disparo_C"]), 0))],
      anchos=[6, 4, 4], titulo="Temperaturas del rodamiento registradas en operación.", primera_col=True)
    FIG(F["hist"], 15.5, "Distribución de las temperaturas registradas, límites de operación y rango del transmisor seleccionado.")
    filas = []
    for e in N.ESTADOS:
        s = op.loc[op["estado"] == e, "temperatura_motor_C"].dropna()
        if len(s):
            filas.append((N.NOMBRE_ESTADO[e], len(s), num(s.median()), num(s.max()), num(c2f(s.max()))))
    T(["Estado", "Horas", "Mediana (°C)", "Máxima (°C)", "Máxima (°F)"], filas, anchos=[5.5, 2.2, 2.8, 2.8, 2.8],
      titulo="Temperatura del rodamiento según el estado del equipo.", primera_col=True)
    FIG(F["estados"], 15.5, "Temperatura del rodamiento en cada estado: sube claramente cuando el rodamiento se degrada.")
    med_n = op.loc[op["estado"] == "NORMAL", "temperatura_motor_C"].median()
    med_c = op.loc[op["estado"] == "RODAMIENTO_CRITICO", "temperatura_motor_C"].median()
    P(f"**Interpretación.** En operación normal la mediana es {num(med_n)} °C, mientras que con el rodamiento en estado crítico "
      f"sube a {num(med_c)} °C: una diferencia de unos {num(med_c - med_n, 0)} °C. Esto confirma que la temperatura de la tapa es un "
      "indicador útil del desgaste del rodamiento y fija el orden de magnitud de la exactitud necesaria: el sensor debe "
      "equivocarse mucho menos que esa diferencia.")

    # 4
    H("4. Criterios de selección")
    P("Cada criterio se obtuvo de los datos registrados, de la geometría de la instalación o de las condiciones del motor. "
      "La Tabla siguiente resume el valor exigido y su justificación.")
    T(["Criterio", "Valor exigido", "Justificación"], [
        ("Rango de medición", f"{req['rango_min_C']:.0f} a {req['rango_max_C']:.0f} °C",
         f"La máxima registrada fue {num(req['t_max_obs_C'])} °C y el disparo está en {eq['disparo_C']:.0f} °C; el rango debe cubrir ambos."),
        ("Relación óptica D:S", f"≥ {req['ds_req']:g}:1", "La tapa es pequeña; una óptica fina evita medir el fondo o el ambiente."),
        ("Punto medido", f"≤ {req['spot_max_mm']:.1f} mm a {req['distancia_mm']:.0f} mm",
         f"Regla práctica: el círculo medido debe ocupar como máximo 2/3 de la tapa ({eq['ir_d_objetivo_mm']:.0f} mm × 2/3)."),
        ("Tiempo de respuesta", f"≤ {req['resp_ms']:.0f} ms", "El rodamiento se calienta en minutos; un segundo es miles de veces más rápido que el proceso."),
        ("Temperatura ambiente del sensor", f"≥ {req['cabezal_C']:.0f} °C", "El motor está diseñado para 40 °C de ambiente; se añaden 10 °C de margen por el aire del motor."),
        ("Exactitud", f"±{req['exactitud_C']:.0f} °C", "Mucho menor que la diferencia de temperatura entre operación normal y rodamiento crítico."),
        ("Salida", req["salida"], "Señal industrial inmune a la caída de tensión del cable y que permite detectar un cable roto."),
        ("Alimentación", f"{req['alim_V']:.0f} VDC", "Fuente disponible en el tablero del PLC."),
        ("Protección", f"≥ IP{req['ip_min']}", "Instalación junto a una bomba de agua: polvo y salpicaduras.")],
      anchos=[3.8, 3.3, 9.4], titulo="Criterios de selección y su justificación.", primera_col=True, tam=9)
    H("4.1 Cálculo del punto medido y de la relación D:S", 2)
    P(f"El diámetro máximo admisible del círculo medido es S_max = (2/3) × {eq['ir_d_objetivo_mm']:.0f} mm = **{req['spot_max_mm']:.1f} mm**. "
      f"Para un sensor ideal, el círculo medido a una distancia D es S = D / (D:S); por tanto la relación mínima por geometría es "
      f"D:S ≥ {req['distancia_mm']:.0f} / {req['spot_max_mm']:.1f} = {req['ds_geo']:.1f}:1. Se adopta un valor más exigente, **{req['ds_req']:g}:1**, "
      "para tener margen frente a desalineaciones y porque la lente real no converge en un punto (ver sección 7).")
    H("4.2 Exactitud efectiva", 2)
    P(f"Los fabricantes expresan la exactitud como «el mayor entre ±X °C y ±Y % de la lectura». Se evalúa en la temperatura de "
      f"disparo ({eq['disparo_C']:.0f} °C), que es donde importa no equivocarse. Por ejemplo, para ±2 °C o ±1,5 %: "
      f"1,5 % × {eq['disparo_C']:.0f} = {0.015 * eq['disparo_C']:.2f} °C, de modo que manda el valor de ±2 °C.")

    # 5
    H("5. Transmisores evaluados")
    P("Se compararon transmisores de tres fabricantes, con datos tomados de sus hojas técnicas y catálogos.")
    filas = []
    for c in cat:
        emis = f"{c['Emis_min']:g} fija" if c["Emis_max"] == c["Emis_min"] else f"{c['Emis_min']:g}–{c['Emis_max']:g}"
        filas.append((f"{c['Marca'].split(' (')[0]} {c['Modelo']}", f"{c['T_min_C']} a {c['T_max_C']}", f"{c['DS']:g}:1", c["Resp_ms"],
                      f"±{c['Exact_C']:g} °C" + (f" / ±{c['Exact_pct']:g} %" if c.get("Exact_pct") else ""), emis,
                      c["Salidas"].split(";")[0] + (" y otras" if ";" in c["Salidas"] else ""), c.get("Tcab_C"), f"IP{int(c['IP'])}" if c.get("IP") else "n. i."))
    T(["Transmisor", "Rango (°C)", "D:S", "Resp. (ms)", "Exactitud", "Emisividad", "Salida", "T. amb. (°C)", "IP"], filas,
      anchos=[3.6, 1.8, 1.2, 1.3, 2.4, 1.6, 2.3, 1.4, 1.0], titulo="Especificaciones de los transmisores evaluados.", tam=8)
    P("n. i.: no indicado en el catálogo consultado.", cursiva=True, tam=8.5, color="5A6B88")

    # 6
    H("6. Evaluación criterio por criterio")
    cols = N.CRITERIOS_IR
    T(["Transmisor"] + cols + ["¿Cumple?"], [[x["Modelo"]] + [x[c] for c in cols] + ["Sí" if x["Cumple todo"] else "No"] for x in tabla.to_dict("records")],
      anchos=[2.6] + [1.25] * len(cols) + [1.3], titulo="Cumplimiento de cada criterio (✔ cumple · ✘ no cumple).", tam=8)
    H("6.1 Razones de descarte", 2)
    for c in cat:
        f_ = N.explicar_fallas(c, req)
        if f_:
            B(f"**{c['Marca'].split(' (')[0]} {c['Modelo']}:** " + " ".join(f_))
    cumplen = [x["Modelo"] for x in tabla.to_dict("records") if x["Cumple todo"]]
    P(f"Cumplen todos los criterios: **{', '.join(cumplen)}**.")
    H("6.2 Puntaje técnico de desempate", 2)
    P("Entre los que cumplen, se asignó un puntaje técnico (máximo 100): exactitud 30, holgura de la óptica 25, emisividad ajustable 15, "
      "grado de protección 10, resolución de la señal 10 (un rango más ajustado al proceso reparte los 16 mA en menos grados) y "
      "accesorios de montaje incluidos 10. El costo no se considera porque aún no hay cotizaciones.")
    T(["Transmisor", "Cumple todo", "Exactitud efectiva (°C)", "Punto medido (mm)", "Puntaje"],
      [(x["Modelo"], "Sí" if x["Cumple todo"] else "No", num(x["Exactitud (°C)"]), num(x["Punto medido (mm)"]), num(x["Puntaje"], 1)) for x in tabla.to_dict("records")],
      anchos=[4.5, 2.5, 3.5, 3.2, 2.5], titulo="Puntaje técnico de los transmisores.", primera_col=True)

    # 7
    H("7. Cálculo del punto de medición")
    P("La fórmula S = D/(D:S) supone que el haz nace en un punto. En realidad la lente tiene un diámetro propio, por lo que a "
      "distancias cortas el círculo medido es mayor. Para el BIEDAS se usa la tabla óptica del fabricante (Figura siguiente).")
    if (cat_dir / "BYD_optica.png").exists():
        FIG(cat_dir / "BYD_optica.png", 15, "Diagrama óptico del BIEDAS serie BYD (D:S = 20:1). Fuente: BIEDAS.")
    filas = [(d_, num(N.punto_medido(sel, d_)), num(N.punto_medido(alt_, d_)), "✔" if N.punto_medido(sel, d_) <= req["spot_max_mm"] else "✘")
             for d_ in (50, 100, 120, 150, 200, 300)]
    T(["Distancia (mm)", f"Punto {sel['Modelo']} (mm)", f"Punto {alt_['Modelo']} (mm)", f"{sel['Modelo']} ≤ {req['spot_max_mm']:.0f} mm"], filas,
      anchos=[3.2, 4, 4, 4], titulo="Diámetro del círculo medido según la distancia de montaje.")
    FIG(F["spot"], 15.5, "Diámetro del círculo medido en función de la distancia para tres transmisores.")
    d_lim = float(np.interp(req["spot_max_mm"], sel["Spot_S_mm"], sel["Spot_D_mm"])) if sel.get("Spot_S_mm") else req["spot_max_mm"] * sel["DS"]
    P(f"A la distancia prevista de {req['distancia_mm']:.0f} mm, el {sel['Modelo']} mide un círculo de **{num(N.punto_medido(sel, req['distancia_mm']))} mm**, "
      f"menor que el máximo de {req['spot_max_mm']:.0f} mm y dentro de la tapa de {eq['ir_d_objetivo_mm']:.0f} mm. Podría montarse hasta "
      f"unos **{d_lim:.0f} mm** sin superar ese límite.")

    # 8
    H(f"8. Transmisor seleccionado: {sel['Marca'].split(' (')[0]} {sel['Modelo']}")
    if (cat_dir / "BYD_producto.jpg").exists():
        FIG(cat_dir / "BYD_producto.jpg", 9.5, "Termómetro infrarrojo fijo BIEDAS con soporte en L. Fuente: página del fabricante.")
    H("8.1 Código de pedido", 2)
    T(["Parte", "Significado"], [("BYD", "Marca BIEDAS, serie de termómetros infrarrojos fijos"),
                                 ("10", "Rango de medición 0 a 100 °C"), ("A", "Salida analógica 4–20 mA"),
                                 ("S", "Versión de cuerpo corto: 71 mm de largo, rosca M18×1 de 32,85 mm")],
      anchos=[3, 13.5], titulo="Interpretación del código BYD10AS.", primera_col=True)
    H("8.2 Especificaciones", 2)
    T(["Parámetro", "Valor"], [
        ("Fabricante", "Wuxi Baiyida Electromechanical Technology Co., Ltd. (marca BIEDAS), China"),
        ("Principio", "Termopila con filtro de 8–14 µm (infrarrojo de onda larga)"),
        ("Rango", "0 a 100 °C (32 a 212 °F)"), ("Relación óptica", "20:1"),
        ("Exactitud", "±1,5 % de la lectura o ±2 °C (el mayor)"), ("Repetibilidad", "±0,5 % o ±1 °C (el mayor)"),
        ("Tiempo de respuesta", "200 ms al 95 % (configurable de fábrica entre 50 ms y 5 s)"), ("Emisividad", "0,95 fija"),
        ("Salida", "4–20 mA (2, 3 o 4 hilos)"), ("Alimentación", "9 a 32 VDC"),
        ("Temperatura ambiente", "0 a 60 °C (almacenamiento −20 a 80 °C), humedad 10–95 % sin condensación"),
        ("Protección", "IP65 (NEMA-4)"), ("Cuerpo", "Acero inoxidable, M18×1, 71 mm de largo"),
        ("Cable", "Apantallado, 2 m (longitud a pedido)"), ("Accesorios incluidos", "2 tuercas de fijación y soporte en L"),
        ("Garantía", "12 meses")], anchos=[4.5, 12], titulo="Especificaciones del BIEDAS BYD10AS.", primera_col=True)
    H("8.3 Razones de la selección", 2)
    for x in ["**Cumple los nueve criterios** de la sección 4.",
              f"**Rango ajustado al proceso (0–100 °C):** cubre la máxima registrada ({num(t.max())} °C) y el disparo ({eq['disparo_C']:.0f} °C). "
              "Al ser un rango corto, cada miliamperio equivale a 6,25 °C, lo que da mejor resolución que un sensor de 0–150 °C o más.",
              f"**Óptica 20:1:** a {req['distancia_mm']:.0f} mm mide un círculo de {num(N.punto_medido(sel, req['distancia_mm']))} mm, bien dentro de la tapa.",
              "**Salida 4–20 mA:** inmune a la caída de tensión del cable y al ruido eléctrico del motor; una corriente menor a 4 mA revela un cable roto.",
              "**Instalación sencilla:** trae soporte en L, tuercas y cable apantallado; cuerpo compacto de 71 mm en acero inoxidable con IP65."]:
        B(x)
    H("8.4 Limitaciones y cómo manejarlas", 2)
    T(["Limitación", "Consecuencia", "Medida"], [
        ("Rango hasta 100 °C", "Sobre 100 °C la señal se satura en 20 mA", f"El disparo está en {eq['disparo_C']:.0f} °C: una lectura de 100 °C ya indica parar la bomba."),
        ("Emisividad fija 0,95", "En metal brillante la lectura sería muy baja", "Pegar cinta negra mate (ε ≈ 0,95) en el punto de medición."),
        ("Exactitud ±2 °C", "Error posible de ±2 °C (±3,6 °F)", "Es menor que la diferencia entre estados; validar con un PT100 al instalar."),
        ("Ambiente máximo 60 °C", "Error o daño si se calienta", "No montarlo frente a la salida de aire del ventilador del motor."),
        ("Importación", "Tiempo de entrega", "Confirmar plazo y el largo de 71 mm con el vendedor antes de comprar.")],
      anchos=[3.8, 5, 7.7], titulo="Limitaciones del transmisor seleccionado.", primera_col=True, tam=9)

    # 9
    H(f"9. Alternativa técnica: {alt_['Marca']} {alt_['Modelo']}")
    P(f"El {alt_['Modelo']} también cumple todos los criterios y tiene **mejor exactitud (±1 °C)**, **óptica {alt_['DS']:g}:1**, "
      "**emisividad ajustable (0,1–1,1)**, display, salida de alarma y cabezal que soporta 180 °C. Su desventaja es que usa cabezal "
      "más caja electrónica, por lo que la instalación es más compleja, y su rango (−50 a 975 °C) es mucho más amplio de lo "
      "necesario, aunque la salida puede programarse a 0–100 °C.")
    P("**Conviene elegirlo** si no se puede pegar cinta mate en el punto de medición (emisividad ajustable), si se necesita una "
      "exactitud mejor que ±2 °C o si el sensor debe instalarse en un lugar con más de 60 °C de ambiente.")

    # 10
    H("10. Instalación mecánica")
    if (cat_dir / "BYD_soporte.png").exists():
        FIG(cat_dir / "BYD_soporte.png", 11, "Dimensiones del soporte en L incluido (41,8 × 43,7 mm, agujero de 18,2 mm). Fuente: BIEDAS.")
    NUM([f"Fijar el soporte en L a una base rígida (no al motor si vibra demasiado) de modo que la lente quede a **{req['distancia_mm']:.0f} mm** de la tapa del rodamiento.",
              "Pasar el cuerpo roscado M18 por el agujero del soporte y asegurarlo con las **dos tuercas**.",
              "Orientar el sensor **perpendicular** a la superficie de la tapa y apuntar siempre al **mismo punto**.",
              "Pegar en ese punto un trozo de **cinta negra mate** de al menos 25 mm, más grande que el círculo medido.",
              "Verificar que el camino óptico esté libre: sin cables, polvo, vapor ni salpicaduras entre la lente y la tapa.",
              "Evitar que el sensor apunte o reciba reflejos del sol o de superficies calientes.",
              "No ubicarlo frente a la salida de aire del ventilador del motor, para no superar 60 °C de ambiente."])

    # 11
    H("11. Conexión eléctrica al PLC")
    P("La CPU 1214C solo tiene entradas analógicas de 0–10 V, por lo que la señal de 4–20 mA se conecta a un módulo de entradas "
      "analógicas **SM 1231 AI4** (4 canales, admite 4–20 mA). Se usa la conexión a 4 hilos indicada por el fabricante.")
    T(["Color del cable", "Función", "Conexión"], [
        ("Rojo", "+ alimentación 9–32 VDC", "+24 VDC de la fuente"), ("Negro", "− alimentación", "0 V (M) de la fuente"),
        ("Azul", "Señal 4–20 mA (+)", "Entrada AI0+ del SM 1231"), ("Naranja", "Señal 4–20 mA (−)", "Entrada AI0− del SM 1231"),
        ("Plateado", "Pantalla del cable", "Tierra (PE) en un solo extremo, del lado del tablero")],
      anchos=[3.5, 5, 8], titulo="Colores de los cables del BYD10AS y su conexión.", primera_col=True)
    FIG(F["conexion"], 16, "Diagrama de conexión del transmisor al PLC.")
    P("**Otras formas de conexión permitidas por el fabricante:** a 3 hilos (rojo +24 V, azul 4–20 mA +, negro y naranja juntos como común) "
      "o a 2 hilos (rojo +24 V y azul 4–20 mA +; los demás cables se aíslan). Recomendaciones: llevar el cable apantallado separado "
      "de los cables de potencia del motor y conectar la pantalla a tierra.")
    H("11.1 Configuración del canal en TIA Portal", 2)
    NUM(["En la vista de dispositivos, agregar el módulo **SM 1231 AI4** junto a la CPU 1214C.",
              "En las propiedades del canal 0: **Tipo de medición: Intensidad**, **Rango: 4..20 mA**.",
              "Activar el diagnóstico de **rotura de hilo** y de **rebase por defecto**.",
              "Anotar la dirección asignada (por ejemplo, %IW96) y crear la variable «T_ROD_DE_RAW» de tipo Int."])

    # 12
    H("12. Escalado de la señal en TIA Portal")
    P("El PLC entrega un número entero proporcional a la corriente. Con el canal en el rango **4..20 mA**, 4 mA corresponde a **0** "
      "y 20 mA a **27648**. La temperatura se obtiene con la recta:")
    P("T(°C) = T_mín + (Valor / 27648) × (T_máx − T_mín) = 0 + (Valor / 27648) × 100", centro=True, negrita=True)
    P("T(°F) = 1,8 × T(°C) + 32", centro=True, negrita=True)
    P("En lenguaje KOP se usan dos instrucciones en cadena: **NORM_X** (MIN = 0, VALUE = T_ROD_DE_RAW, MAX = 27648, salida Real de 0 a 1) "
      "y **SCALE_X** (MIN = 0,0, VALUE = salida de NORM_X, MAX = 100,0, salida T_ROD_DE_C en °C). Luego se multiplica por 1,8 y se suma 32 "
      "para obtener °F.")
    tb4 = escalado(sel["T_min_C"], sel["T_max_C"], "4-20")
    T(list(tb4.columns), [(r["Corriente (mA)"], r["Valor en el PLC"], num(r["Temperatura (°C)"]), num(r["Temperatura (°F)"])) for r in tb4.to_dict("records")],
      anchos=[3.5, 3.5, 3.5, 3.5], titulo="Equivalencias con el canal configurado en 4..20 mA (SM 1231).")
    tb0 = escalado(sel["T_min_C"], sel["T_max_C"], "0-20")
    T(list(tb0.columns), [(r["Corriente (mA)"], r["Valor en el PLC"], num(r["Temperatura (°C)"]), num(r["Temperatura (°F)"])) for r in tb0.to_dict("records")],
      anchos=[3.5, 3.5, 3.5, 3.5], titulo="Equivalencias si el canal se configura en 0..20 mA (por ejemplo, con SB 1231).")
    P("Con un canal de 0..20 mA, 4 mA equivale a 5530; en ese caso NORM_X usa MIN = 5530.", cursiva=True, tam=9.5)
    FIG(F["escala"], 15, "Recta de conversión de la corriente del transmisor a temperatura.")
    H("12.1 Detección de fallas de la señal", 2)
    for x in ["**Cable roto o sensor sin alimentación:** la corriente cae bajo 4 mA; el valor queda negativo (rango 4..20 mA) o bajo 5530 (rango 0..20 mA). "
              "Con el diagnóstico de rotura de hilo activo, el módulo entrega 32767. Programar una alarma «Falla del sensor».",
              "**Temperatura sobre 100 °C:** la señal se satura en 20 mA (27648). Tratar ese valor como disparo y detener la bomba.",
              f"**Alarmas de proceso:** comparar T_ROD_DE_C con {eq['alarma_C']:.0f} °C (alarma) y {eq['disparo_C']:.0f} °C (disparo)."]:
        B(x)

    # 13
    H("13. Validación y calibración")
    NUM(["Con el motor frío y apagado, comparar la lectura del transmisor con un termómetro de referencia (PT100 de contacto o termómetro IR portátil) en el mismo punto con cinta mate.",
              "Arrancar la bomba y registrar ambas lecturas cada 5 minutos hasta que la temperatura se estabilice.",
              "Calcular la diferencia promedio. Si es mayor que ±2 °C, revisar la cinta, la alineación y la limpieza de la lente.",
              "Si la diferencia es constante, aplicar una corrección (offset) en el PLC sumándola al valor de SCALE_X.",
              "Registrar la validación (fecha, lecturas, corrección aplicada) en el historial de mantenimiento."])

    # 14
    H("14. Mantenimiento del sensor")
    T(["Tarea", "Frecuencia", "Detalle"], [
        ("Limpieza de la lente", "Cada 3 meses", "Hisopo o papel de lente con alcohol anhidro; nunca abrasivos."),
        ("Revisión de la cinta mate", "Cada 3 meses", "Reemplazar si está despegada, sucia o quemada."),
        ("Revisión de conexiones y pantalla", "Cada 6 meses", "Reapretar bornes y verificar la tierra de la pantalla."),
        ("Comparación con referencia", "Cada 6 meses", "Repetir la validación de la sección 13."),
        ("Verificación de la fijación", "Cada 6 meses", "Comprobar que el soporte y las tuercas no se aflojaron por la vibración.")],
      anchos=[4.5, 3, 9], titulo="Plan de mantenimiento del transmisor.", primera_col=True)

    # 15
    H("15. Lista de materiales")
    T(["N.º", "Material", "Cantidad", "Observación"], [
        (1, f"Transmisor IR {sel['Marca'].split(' (')[0]} {sel['Modelo']} (0–100 °C, 4–20 mA, 71 mm)", "1 por rodamiento vigilado", "Incluye soporte en L, tuercas y cable de 2 m"),
        (2, "Módulo de entradas analógicas Siemens SM 1231 AI4", "1", "4 canales, admite 4–20 mA"),
        (3, "Fuente de alimentación 24 VDC", "1", "Puede ser la del tablero del PLC"),
        (4, "Cable apantallado 2 × 0,5 mm² (extensión)", "Según distancia", "Si el cable de 2 m no alcanza"),
        (5, "Cinta negra mate de alta emisividad", "1 rollo", "ε ≈ 0,95, resistente a la temperatura"),
        (6, "Termómetro de referencia (PT100 o IR portátil)", "1", "Para la validación"),
        (7, "Borneras, canaleta y terminales", "Varios", "Montaje en tablero")],
      anchos=[1.2, 7.3, 3.3, 4.7], titulo="Materiales para la implementación (sin precios).")

    # 16
    H("16. Conclusiones")
    for x in [f"En {len(op)} horas de operación la temperatura de la tapa del rodamiento estuvo entre {num(t.min())} y {num(t.max())} °C, y subió "
              f"unos {num(med_c - med_n, 0)} °C entre la operación normal y el rodamiento crítico, lo que valida la medición infrarroja como indicador de desgaste.",
              f"Los criterios de selección se justificaron con los datos y la instalación: rango 0–{req['rango_max_C']:.0f} °C, óptica ≥ {req['ds_req']:g}:1, "
              f"punto ≤ {req['spot_max_mm']:.0f} mm, respuesta ≤ {req['resp_ms']:.0f} ms, ambiente ≥ {req['cabezal_C']:.0f} °C, ±{req['exactitud_C']:.0f} °C, 4–20 mA e IP ≥ {req['ip_min']}.",
              f"De {len(cat)} transmisores evaluados, {len(cumplen)} cumplen todos los criterios: {', '.join(cumplen)}.",
              f"Se selecciona el **{sel['Marca'].split(' (')[0]} {sel['Modelo']}** para la compra por cumplir todos los criterios, tener un rango ajustado al proceso, "
              "óptica 20:1, salida 4–20 mA robusta e incluir los accesorios de montaje.",
              f"El **{alt_['Marca']} {alt_['Modelo']}** queda como alternativa técnica si se requiere mejor exactitud o emisividad ajustable.",
              "La señal se integra al S7-1200 mediante un módulo SM 1231 AI4 y se escala con NORM_X y SCALE_X de 0–27648 a 0–100 °C."]:
        B(x)

    # 17
    H("17. Referencias")
    for x in ["BIEDAS. (s. f.). BYD10AS Infrared Thermometer [Página de producto]. Wuxi Baiyida Electromechanical Technology Co., Ltd.",
              "BIEDAS. (s. f.). Operation manual of the fixed infrared thermometer BYDXAC/BC/CC/R4C/R2C. Wuxi Baiyida Electromechanical Technology Co., Ltd.",
              "Optris GmbH. (2018). optris CT LT: Technical data [Hoja de datos].",
              "Optris GmbH. (s. f.). Infrared thermometers and thermal imaging cameras [Folleto de productos].",
              "OPTEX FA Co., Ltd. (s. f.). SA-80 Series M18 cylindrical thermometers [Hoja de datos].",
              "Siemens AG. (s. f.). SIMATIC S7-1200 Programmable controller: System manual.",
              "Çengel, Y. A., & Ghajar, A. J. (2011). Transferencia de calor y masa (4.ª ed.). McGraw-Hill."]:
        p = doc.add_paragraph(x)
        p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(1), Cm(-1)

    b = BytesIO()
    doc.save(b)
    return b.getvalue()
