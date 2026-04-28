import ast
import math
import pandas as pd
import numpy as np
import networkx as nx
import folium
import streamlit as st
from folium.features import DivIcon
from streamlit_folium import st_folium

# opcional si usarás gpkg
import geopandas as gpd


st.set_page_config(page_title="Mapa de conflictos mineros", layout="wide")


@st.cache_data
def cargar_datos():
    df = pd.read_csv("df_mapa.csv")

    df["Pueblos_actualizados"] = df["Pueblos_actualizados"].apply(to_list)

    df_localizacion = pd.read_csv("df_localizacion.csv")

    mines_4326 = None
    try:
        mines_gdf = gpd.read_file("mapa_minas.gpkg", layer="Mina")
        mines_4326 = mines_gdf.to_crs(epsg=4326).copy()
        centroids = mines_4326.geometry.centroid
        mines_4326["lat"] = centroids.y
        mines_4326["lon"] = centroids.x
        mines_4326["radius"] = mines_4326["AREAKM2"].apply(calc_radius)
    except Exception:
        pass

    return df, df_localizacion, mines_4326


def to_list(x):
    if isinstance(x, list):
        return [str(s).strip() for s in x if str(s).strip()]

    if isinstance(x, str):
        x = x.strip()
        try:
            parsed = ast.literal_eval(x)
            if isinstance(parsed, (list, tuple)):
                return [str(s).strip() for s in parsed if str(s).strip()]
        except Exception:
            pass
        return [s.strip() for s in x.split(",") if s.strip()]

    return []


def calc_radius(area):
    try:
        a = float(str(area).replace(",", ""))
    except Exception:
        return 10
    return 8 + 2 * np.log1p(max(a, 0))


def coords_dict(df_localizacion):
    base = df_localizacion.dropna(subset=["lat", "lon"]).copy()
    base = base.drop_duplicates(subset=["Pueblos_actualizados"], keep="first")
    return base.set_index("Pueblos_actualizados")[["lat", "lon"]].to_dict("index")


def grafo_por_semestre(df, semestre):
    use = df.copy()
    use["Pueblos_actualizados"] = use["Pueblos_actualizados"].apply(to_list)
    use = use[use["Semestre"].astype(str) == str(semestre)].reset_index(drop=True)

    G = nx.Graph()

    for _, row in use.iterrows():
        pueblos = row["Pueblos_actualizados"]
        mina = str(row.get("Minas", "Desconocida"))

        for p in pueblos:
            G.add_node(p, tipo="pueblo_actualizado")

        for i in range(len(pueblos)):
            for j in range(i + 1, len(pueblos)):
                u, v = pueblos[i], pueblos[j]

                if G.has_edge(u, v):
                    G[u][v]["peso"] += 1
                    G[u][v]["minas"].add(mina)
                else:
                    G.add_edge(u, v, peso=1, minas={mina})

    return G, use


def mapa_grafo(
    G,
    coords,
    titulo,
    mines_4326=None,
    edge_base=0.6,
    edge_scale=0.7,
    edge_max_mult=6,
    edge_color="#8B0000",
    opacity=0.5,
    color_activo="#d32f2f",
    color_inactivo="#9aa0a6",
    radio_inactivo=4,
    radio_activo=6,
):
    m = folium.Map(location=[-9.19, -75.0152], zoom_start=6, tiles="CartoDB positron")

    layer_base = folium.FeatureGroup(name="Todos los pueblos", show=True)
    layer_activos = folium.FeatureGroup(name="Pueblos del semestre", show=True)
    layer_aristas = folium.FeatureGroup(name="Conexiones", show=True)

    for n, c in coords.items():
        folium.CircleMarker(
            location=[c["lat"], c["lon"]],
            radius=radio_inactivo,
            color=color_inactivo,
            fill=True,
            fill_color=color_inactivo,
            fill_opacity=0.8,
            tooltip=n,
        ).add_to(layer_base)

    bounds = []

    for u, v, data in G.edges(data=True):
        if u in coords and v in coords:
            pts = [
                (coords[u]["lat"], coords[u]["lon"]),
                (coords[v]["lat"], coords[v]["lon"]),
            ]
            peso = data.get("peso", 1)
            minas = ", ".join(sorted(map(str, data.get("minas", []))))

            folium.PolyLine(
                pts,
                weight=edge_base + edge_scale * min(peso, edge_max_mult),
                opacity=opacity,
                color=edge_color,
                tooltip=f"{u} — {v} | Conflictos: {peso} | Minas: {minas}",
            ).add_to(layer_aristas)

            bounds.extend(pts)

    for n in G.nodes:
        if n in coords:
            la, lo = coords[n]["lat"], coords[n]["lon"]
            folium.CircleMarker(
                location=[la, lo],
                radius=radio_activo,
                color=color_activo,
                fill=True,
                fill_color=color_activo,
                fill_opacity=0.95,
                tooltip=f"{n} activo",
            ).add_to(layer_activos)
            bounds.append((la, lo))

    if mines_4326 is not None:
        layer_minas = folium.FeatureGroup(name="Minas", show=True)

        for _, row in mines_4326.iterrows():
            lat = row["lat"]
            lon = row["lon"]
            size = int(row["radius"])

            popup_html = f"""
            <b>Proyecto:</b> {row.get("PROYECTO", "N/A")}<br>
            <b>Empresa:</b> {row.get("EMPRESA", "N/A")}<br>
            <b>Área km²:</b> {row.get("AREAKM2", "N/A")}<br>
            <b>Zona:</b> {row.get("ZONA", "N/A")}
            """

            triangle_icon = f"""
            <div style="
                width: 0;
                height: 0;
                border-left: {size}px solid transparent;
                border-right: {size}px solid transparent;
                border-top: {size * 1.5}px solid #FFD700;
            "></div>
            """

            folium.Marker(
                location=[lat, lon],
                icon=DivIcon(html=triangle_icon),
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(layer_minas)

        layer_minas.add_to(m)

    layer_base.add_to(m)
    layer_aristas.add_to(m)
    layer_activos.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    if bounds:
        m.fit_bounds(bounds)

    return m


df, df_localizacion, mines_4326 = cargar_datos()
coords = coords_dict(df_localizacion)

st.title("Mapa de conflictos mineros por semestre")

semestres = sorted(df["Semestre"].dropna().astype(str).unique())
semestre = st.sidebar.selectbox("Semestre", semestres)

mostrar_minas = st.sidebar.checkbox("Mostrar capa de minas", value=True)

G, df_sem = grafo_por_semestre(df, semestre)

m = mapa_grafo(
    G,
    coords,
    titulo=f"Red por semestre: {semestre}",
    mines_4326=mines_4326 if mostrar_minas else None,
)

st.subheader(f"Semestre: {semestre}")
st_folium(m, width=None, height=720)

st.caption(f"{len(G.nodes)} pueblos activos | {len(G.edges)} conexiones")