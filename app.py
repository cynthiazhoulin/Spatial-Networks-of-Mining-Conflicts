import ast
import pandas as pd
import networkx as nx
import folium
import streamlit as st
from folium.features import DivIcon
from streamlit_folium import st_folium


st.set_page_config(
    page_title="Mining Conflict Map",
    layout="wide"
)


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


@st.cache_data
def load_data():
    df = pd.read_csv("df_mapa.csv")
    df_location = pd.read_csv("df_localizacion.csv")

    try:
        df_mines = pd.read_csv("minas_light.csv")
    except Exception:
        df_mines = None

    return df, df_location, df_mines


def get_coords(df_location):
    base = df_location.dropna(subset=["lat", "lon"]).copy()
    base = base.drop_duplicates(subset=["Pueblos_actualizados"], keep="first")

    return base.set_index("Pueblos_actualizados")[["lat", "lon"]].to_dict("index")


def graph_by_semester(df, semester):
    use = df.copy()
    use["Pueblos_actualizados"] = use["Pueblos_actualizados"].apply(to_list)
    use = use[use["Semestre"].astype(str) == str(semester)].reset_index(drop=True)

    G = nx.Graph()

    for _, row in use.iterrows():
        towns = row["Pueblos_actualizados"]
        mine = str(row.get("Minas", "Unknown"))

        for town in towns:
            G.add_node(town, type="town")

        for i in range(len(towns)):
            for j in range(i + 1, len(towns)):
                u, v = towns[i], towns[j]

                if G.has_edge(u, v):
                    G[u][v]["weight"] += 1
                    G[u][v]["mines"].add(mine)
                else:
                    G.add_edge(u, v, weight=1, mines={mine})

    return G, use


def make_map(
    G,
    coords,
    title="Mining conflict network",
    df_mines=None,
    edge_base=0.6,
    edge_scale=0.7,
    edge_max_mult=6,
    edge_color="#8B0000",
    opacity=0.5,
    active_color="#d32f2f",
    inactive_color="#9aa0a6",
    inactive_radius=4,
    active_radius=6,
):
    m = folium.Map(
        location=[-9.19, -75.0152],
        zoom_start=6,
        tiles="CartoDB positron"
    )

    layer_all_towns = folium.FeatureGroup(
        name="All towns with coordinates",
        show=True
    )

    layer_active_towns = folium.FeatureGroup(
        name="Towns in selected semester",
        show=True
    )

    layer_connections = folium.FeatureGroup(
        name="Connections in selected semester",
        show=True
    )

    for town, c in coords.items():
        folium.CircleMarker(
            location=[c["lat"], c["lon"]],
            radius=inactive_radius,
            color=inactive_color,
            fill=True,
            fill_color=inactive_color,
            fill_opacity=0.8,
            opacity=0.8,
            tooltip=town
        ).add_to(layer_all_towns)

    active_bounds = []

    for u, v, data in G.edges(data=True):
        if u in coords and v in coords:
            pts = [
                (coords[u]["lat"], coords[u]["lon"]),
                (coords[v]["lat"], coords[v]["lon"])
            ]

            weight = data.get("weight", 1)
            mines = ", ".join(sorted(map(str, data.get("mines", []))))

            folium.PolyLine(
                pts,
                weight=edge_base + edge_scale * min(weight, edge_max_mult),
                opacity=opacity,
                color=edge_color,
                tooltip=f"{u} — {v} | Conflicts: {weight} | Mines: {mines}"
            ).add_to(layer_connections)

            active_bounds.extend(pts)

    for town in G.nodes:
        if town in coords:
            lat, lon = coords[town]["lat"], coords[town]["lon"]

            folium.CircleMarker(
                location=[lat, lon],
                radius=active_radius,
                color=active_color,
                fill=True,
                fill_color=active_color,
                fill_opacity=0.95,
                opacity=0.95,
                tooltip=f"{town} (active)"
            ).add_to(layer_active_towns)

            active_bounds.append((lat, lon))

    if df_mines is not None:
        layer_mines = folium.FeatureGroup(
            name="Mines",
            show=True
        )

        for _, row in df_mines.dropna(subset=["lat", "lon"]).iterrows():
            lat = row["lat"]
            lon = row["lon"]
            size = int(row.get("radius", 10))

            popup_html = f"""
            <b>Project:</b> {row.get("PROYECTO", "N/A")}<br>
            <b>Company:</b> {row.get("EMPRESA", "N/A")}<br>
            <b>Area (km²):</b> {row.get("AREAKM2", "N/A")}<br>
            <b>Has:</b> {row.get("HAS", "N/A")}<br>
            <b>Zone:</b> {row.get("ZONA", "N/A")}<br>
            <b>ID:</b> {row.get("ID", "N/A")}<br>
            <b>Layer:</b> {row.get("CAPA", "N/A")}
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
                popup=folium.Popup(popup_html, max_width=260),
            ).add_to(layer_mines)

        layer_mines.add_to(m)

    layer_all_towns.add_to(m)
    layer_connections.add_to(m)
    layer_active_towns.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 18px;
        right: 18px;
        z-index: 9999;
        background: rgba(255,255,255,0.95);
        padding: 12px;
        border: 1px solid #ccc;
        border-radius: 10px;
        font-size: 13px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        pointer-events: none;
    ">
      <div style="font-weight:700; margin-bottom:6px">
        Legend
      </div>

      <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
        <span style="width:10px; height:10px; background:{inactive_color}; border-radius:50%; display:inline-block;"></span>
        <span>All towns</span>
      </div>

      <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
        <span style="width:10px; height:10px; background:{active_color}; border-radius:50%; display:inline-block;"></span>
        <span>Active towns</span>
      </div>

      <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
        <span style="width:20px; height:2px; background:{edge_color}; display:inline-block;"></span>
        <span>Connections</span>
      </div>

      <div style="display:flex; align-items:center; gap:8px;">
        <span style="
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 10px solid #FFD700;
            display:inline-block;
        "></span>
        <span>Mines</span>
      </div>
    </div>
    """

    folium.map.Marker(
        [-17.8, -81.3],
        icon=DivIcon(
            icon_size=(0, 0),
            icon_anchor=(0, 0),
            html=legend_html
        )
    ).add_to(m)

    if active_bounds:
        m.fit_bounds(active_bounds)

    return m


df, df_location, df_mines = load_data()
coords = get_coords(df_location)

st.title("Mining conflict map by semester")

st.sidebar.header("Filters")

semesters = sorted(df["Semestre"].dropna().astype(str).unique())

semester = st.sidebar.selectbox(
    "Semester",
    semesters
)

show_mines = st.sidebar.checkbox(
    "Show mines",
    value=True
)

edge_base = st.sidebar.slider(
    "Base thickness",
    min_value=0.1,
    max_value=2.0,
    value=0.6,
    step=0.1
)

edge_scale = st.sidebar.slider(
    "Weight scale",
    min_value=0.1,
    max_value=2.0,
    value=0.7,
    step=0.1
)

G, df_semester = graph_by_semester(df, semester)

m = make_map(
    G,
    coords,
    title=f"Network by semester: {semester}",
    df_mines=df_mines if show_mines else None,
    edge_base=edge_base,
    edge_scale=edge_scale,
)

col1, col2, col3 = st.columns(3)

col1.metric("Active towns", len(G.nodes))
col2.metric("Connections", len(G.edges))
col3.metric("Records in semester", len(df_semester))

st.subheader(f"Semester: {semester}")

st_folium(
    m,
    width=None,
    height=720
)
