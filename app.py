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


ACTIVE_COLOR = "#d32f2f"
INACTIVE_COLOR = "#9aa0a6"
EDGE_COLOR = "#8B0000"
MINE_COLOR = "#FFD700"


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
    df_mines=None,
    edge_base=0.6,
    edge_scale=0.7,
    edge_max_mult=6,
    opacity=0.5,
    inactive_radius=4,
    active_radius=6,
):
    m = folium.Map(
        location=[-9.19, -75.0152],
        zoom_start=6,
        tiles="CartoDB positron",
        control_scale=True
    )

    layer_all_towns = folium.FeatureGroup(name="All towns", show=True, control=False)
    layer_connections = folium.FeatureGroup(name="Connections", show=True, control=False)
    layer_active_towns = folium.FeatureGroup(name="Active towns", show=True, control=False)

    for town, c in coords.items():
        folium.CircleMarker(
            location=[c["lat"], c["lon"]],
            radius=inactive_radius,
            color=INACTIVE_COLOR,
            fill=True,
            fill_color=INACTIVE_COLOR,
            fill_opacity=0.8,
            opacity=0.8,
            tooltip=f"Inactive town: {town}"
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
                color=EDGE_COLOR,
                tooltip=f"{u} — {v} | Conflicts: {weight} | Mines: {mines}"
            ).add_to(layer_connections)

            active_bounds.extend(pts)

    for town in G.nodes:
        if town in coords:
            lat, lon = coords[town]["lat"], coords[town]["lon"]

            folium.CircleMarker(
                location=[lat, lon],
                radius=active_radius,
                color=ACTIVE_COLOR,
                fill=True,
                fill_color=ACTIVE_COLOR,
                fill_opacity=0.95,
                opacity=0.95,
                tooltip=f"Active town: {town}"
            ).add_to(layer_active_towns)

            active_bounds.append((lat, lon))

    if df_mines is not None:
        layer_mines = folium.FeatureGroup(name="Mines", show=True, control=False)

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
                border-top: {size * 1.5}px solid {MINE_COLOR};
            "></div>
            """

            folium.Marker(
                location=[lat, lon],
                icon=DivIcon(html=triangle_icon),
                popup=folium.Popup(popup_html, max_width=260),
                tooltip="Mine"
            ).add_to(layer_mines)

        layer_mines.add_to(m)

    layer_all_towns.add_to(m)
    layer_connections.add_to(m)
    layer_active_towns.add_to(m)

    if active_bounds:
        m.fit_bounds(active_bounds)

    return m


df, df_location, df_mines = load_data()
coords = get_coords(df_location)

st.title("Mining conflict map by semester")

st.sidebar.header("Filters")

semesters = sorted(df["Semestre"].dropna().astype(str).unique())

semester = st.sidebar.selectbox("Semester", semesters)

show_mines = st.sidebar.checkbox("Show mines", value=True)

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

st.sidebar.markdown("---")
st.sidebar.subheader("Legend")

st.sidebar.markdown(
    f"""
    <div style="font-size:15px; line-height:1.8;">
        <div>
            <span style="
                display:inline-block;
                width:12px;
                height:12px;
                border-radius:50%;
                background:{ACTIVE_COLOR};
                margin-right:8px;
            "></span>
            Active nodes: red circles
        </div>

        <div>
            <span style="
                display:inline-block;
                width:12px;
                height:12px;
                border-radius:50%;
                background:{INACTIVE_COLOR};
                margin-right:8px;
            "></span>
            Inactive nodes: gray circles
        </div>

        <div>
            <span style="
                display:inline-block;
                width:0;
                height:0;
                border-left:7px solid transparent;
                border-right:7px solid transparent;
                border-top:12px solid {MINE_COLOR};
                margin-right:8px;
            "></span>
            Mines: yellow triangles
        </div>

        <div>
            <span style="
                display:inline-block;
                width:22px;
                height:3px;
                background:{EDGE_COLOR};
                margin-right:8px;
                vertical-align:middle;
            "></span>
            Connections: red lines between towns that appear in the same conflict record
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

G, df_semester = graph_by_semester(df, semester)

m = make_map(
    G,
    coords,
    df_mines=df_mines if show_mines else None,
    edge_base=edge_base,
    edge_scale=edge_scale,
)

col1, col2, col3 = st.columns(3)

col1.metric("Active nodes", len(G.nodes))
col2.metric("Connections", len(G.edges))
col3.metric("Records in semester", len(df_semester))

st.subheader(f"Semester: {semester}")

st_folium(
    m,
    width=None,
    height=720
)
