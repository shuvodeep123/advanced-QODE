import io
import math
import re
import os
import logging

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import matplotlib.image as mpimg
import pydot
from io import StringIO


# ---------------------------------------------------------------------------
# Original class — tool-to-tool dependency graph (Graphviz / pydot)
# ---------------------------------------------------------------------------

class Technology_Diagram:
    node_list = {}
    edge_list = []
    dot_graph = pydot.Dot(graph_type='digraph')

    def node_creation(self, distinct_tools):
        for tool in distinct_tools:
            temp_tool = tool.lower()
            temp_tool = re.sub(r'\W+', '', temp_tool)
            temp_node = pydot.Node(tool, fillcolor="#ADD8E6", style="filled")
            self.node_list[tool] = {"value": temp_node}
            self.dot_graph.add_node(temp_node)

    def check_edge_present(self, label, node_1, node_2):
        for edge in self.edge_list:
            if edge["head"] == node_1 and edge["tail"] == node_2:
                edge["label"] += f'  {label}'
                return
        self.edge_list.append({"head": node_1, "tail": node_2, "label": label})

    def edge_creation(self, label, node_1, node_2):
        temp_edge = pydot.Edge(
            node_1, node_2, arrowsize=0.5, color="#000000",
            penwidth=0.7, fontsize=8.0
        )
        temp_edge.set_label(label)
        self.dot_graph.add_edge(temp_edge)

    def isnan(self, value):
        try:
            return math.isnan(float(value))
        except Exception:
            return False

    def create_edge(self, final_df):
        pred_cols = [
            "Predecessor 1 (incl. INIT)",
            "Predecessor 2 (optional)",
            "Predecessor 3 (optional)",
            "Predecessor 4 (optional)",
            "Predecessor 5 (optional)",
        ]
        for i in range(final_df.shape[0]):
            current_tool = final_df.iat[i, 6]
            for j, col in enumerate(pred_cols):
                pred = final_df.iat[i, j + 1]
                if not self.isnan(pred) and pred != "INIT":
                    pred_tool = final_df.loc[
                        final_df['S#'] == pred, 'Automation tool'
                    ].iloc[0]
                    self.check_edge_present(
                        f'A{pred}',
                        self.node_list[pred_tool]["value"],
                        self.node_list[current_tool]["value"],
                    )
        for edge in self.edge_list:
            self.edge_creation(edge["label"], edge["head"], edge["tail"])

    def output(self):
        self.dot_graph.write_raw("Diagram_Technology")
        # self.dot_graph.write_png("Technology_Diagram.png")
        # self.dot_graph.write_svg("Technology_Diagram.svg")

    def create_technology_diagram(self, excel_path='QODE-Questionnaire.xlsm'):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logger.debug("creating_technology_diagram")

        data_read = pd.read_excel(excel_path, sheet_name="Q_Stories", header=3)[2:]
        logger.debug("data_read is done")
        logger.debug(data_read)

        Semi_Final_df = data_read[data_read['Yes / No'] == 'Yes']
        selected_columns = [
            "S#",
            "Predecessor 1 (incl. INIT)",
            "Predecessor 2 (optional)",
            "Predecessor 3 (optional)",
            "Predecessor 4 (optional)",
            "Predecessor 5 (optional)",
            "Automation tool",
        ]
        final_df = Semi_Final_df[selected_columns].copy()
        distinct_tools = final_df["Automation tool"].unique()
        self.node_creation(distinct_tools)
        self.create_edge(final_df)
        self.output()


# ---------------------------------------------------------------------------
# New class — Technology Usage Propensity Diagram (matplotlib, per SDLC epic)
# ---------------------------------------------------------------------------

class Technology_Propensity_Diagram:
    """
    Generates a Technology Usage Propensity diagram per SDLC epic.

    Propensity bands (from QODE_methodologies.md §14.2):
      Low    (0 – <1.5) : Documentation-based tools  (red zone)
      Medium (1.5 – <3.5): Configuration-centric tools (amber zone)
      High   (3.5 – 5.0): Coding-centric tools         (green zone)

    Each node is plotted at its average Tech usage score on the Y-axis,
    inside the column for its SDLC epic.  Nodes whose activities primarily
    produce Information (waste) outputs are highlighted with a red border.
    """

    # Band definitions: (label, y_centre, y_lo, y_hi, bg_color, node_color)
    BANDS = [
        ("Low\n(Documentation)", 0.75,  0.0,  1.5, "#FFDEDE", "#FF9999"),
        ("Medium\n(Configuration)", 2.5,  1.5,  3.5, "#FFF3CC", "#FFD966"),
        ("High\n(Coding-Centric)", 4.25, 3.5,  5.0, "#D9EAD3", "#93C47D"),
    ]

    EPIC_LABELS = {
        "SDLC - Requirements analysis": "Requirement Engineering",
        "SDLC - Coding":                "Code & Data Engineering",
        "SDLC - Testing":               "Quality Engineering",
        "SDLC - Build and package":     "Build & Package Engineering",
        "SDLC - Manage environment":    "Environment Engineering",
        "SDLC - Release and rollback":  "Release Engineering",
        "SDLC - SRE":                "Reliability Engineering",
        "SDLC - Operations":                "Service Ops and Monitoring",
        "SDLC - Ontology":                "Knowledge/Ontology Engineering",
    }

    def _propensity_band(self, score):
        if score < 1.5:
            return "Low", "#FF9999"
        if score < 3.5:
            return "Medium", "#FFD966"
        return "High", "#93C47D"

    def _load_data(self, excel_path):
        df = pd.read_excel(excel_path, sheet_name="Q_Stories", header=3)[2:]
        return df[df['Yes / No'] == 'Yes'].copy()

    def _aggregate(self, data):
        cols = [
            'Epic', 'Automation tool', 'Tool category',
            'Tech usage score', '%(time) of automation',
            'Practice type', 'Practice score',
            'Pipeline integration score', 'Output type',
        ]
        grp = (
            data[cols]
            .groupby(['Epic', 'Automation tool', 'Tool category'])
            .agg(
                tech_score=('Tech usage score',        'mean'),
                auto_pct=('%(time) of automation',     'mean'),
                practice_score=('Practice score',      'mean'),
                pipeline_score=('Pipeline integration score', 'mean'),
                info_count=('Output type', lambda x: (x == 'Information').sum()),
                mat_count=('Output type',  lambda x: (x == 'Material').sum()),
            )
            .reset_index()
        )
        grp['band'], grp['node_color'] = zip(
            *grp['tech_score'].map(self._propensity_band)
        )
        # waste flag: tool primarily produces Information outputs
        grp['waste'] = grp['info_count'] > grp['mat_count']
        return grp

    def _draw_epic_column(self, ax, epic, epic_data, col_idx):
        label = self.EPIC_LABELS.get(epic, epic.replace("SDLC - ", ""))
        ax.set_title(label, fontsize=9, fontweight='bold', pad=6)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 5.5)
        ax.set_xticks([])

        # Band backgrounds + Y-axis labels on first column only
        for band_label, y_ctr, y_lo, y_hi, bg, _ in self.BANDS:
            ax.axhspan(y_lo, y_hi, alpha=0.25, color=bg, zorder=0)
            if col_idx == 0:
                ax.set_yticks([b[1] for b in self.BANDS])
                ax.set_yticklabels(
                    [b[0] for b in self.BANDS], fontsize=7
                )
            else:
                ax.set_yticks([])

        # Horizontal band dividers
        ax.axhline(1.5, color='#BBBBBB', linewidth=0.6, linestyle='--', zorder=1)
        ax.axhline(3.5, color='#BBBBBB', linewidth=0.6, linestyle='--', zorder=1)

        # Scatter nodes with jitter when multiple tools share the same score
        tool_rows = epic_data.sort_values('tech_score').reset_index(drop=True)
        n = len(tool_rows)
        x_positions = [0.5] * n
        if n > 1:
            # spread evenly across 0.15–0.85 to avoid overlap
            x_positions = [0.15 + 0.7 * i / (n - 1) for i in range(n)]

        for xi, (_, row) in zip(x_positions, tool_rows.iterrows()):
            border_color = '#CC0000' if row['waste'] else '#333333'
            border_lw    = 2.2      if row['waste'] else 0.8

            ax.scatter(
                xi, row['tech_score'],
                s=320, c=row['node_color'],
                edgecolors=border_color, linewidths=border_lw,
                zorder=3,
            )

            short_label = (
                f"{row['Automation tool']}\n"
                f"{row['Practice type'][0]}·{row['auto_pct']:.0%}"
            )
            ax.annotate(
                short_label,
                (xi, row['tech_score']),
                textcoords='offset points',
                xytext=(7, 0),
                fontsize=6.5,
                va='center',
                zorder=4,
            )

    def create_propensity_diagram(
        self,
        excel_path='QODE-Questionnaire.xlsm',
        output_png='Technology_Propensity_Diagram.png',
        show=True,
    ):
        data = self._load_data(excel_path)
        grp  = self._aggregate(data)

        # Use a fixed epic order; skip epics not present in data
        ordered_epics = [e for e in self.EPIC_LABELS if e in grp['Epic'].unique()]
        # Append any unrecognised epics at the end
        for e in grp['Epic'].unique():
            if e not in ordered_epics:
                ordered_epics.append(e)

        n_cols = len(ordered_epics)
        fig, axes = plt.subplots(
            1, n_cols,
            figsize=(max(3.5 * n_cols, 14), 9),
            sharey=False,
        )
        if n_cols == 1:
            axes = [axes]

        fig.suptitle(
            'Technology Usage Propensity — As-Is\n(per SDLC Epic)',
            fontsize=13, fontweight='bold', y=0.99,
        )

        for col_idx, (ax, epic) in enumerate(zip(axes, ordered_epics)):
            epic_data = grp[grp['Epic'] == epic]
            self._draw_epic_column(ax, epic, epic_data, col_idx)

        # Legend
        legend_items = [
            mpatches.Patch(color='#FF9999', label='Low — Documentation-based'),
            mpatches.Patch(color='#FFD966', label='Medium — Configuration-centric'),
            mpatches.Patch(color='#93C47D', label='High — Coding-centric'),
            plt.Line2D(
                [0], [0], marker='o', color='w',
                markeredgecolor='#CC0000', markeredgewidth=2.2,
                markersize=9, label='⚠ Waste (primarily Information output)',
            ),
        ]
        fig.legend(
            handles=legend_items, loc='lower center',
            ncol=4, fontsize=8,
            bbox_to_anchor=(0.5, 0.01),
            frameon=True, edgecolor='#CCCCCC',
        )

        plt.tight_layout(rect=[0, 0.07, 1, 0.97])
        plt.savefig(output_png, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_png}")
        if show:
            plt.show()
        plt.close()


# ---------------------------------------------------------------------------
# Entry point — runs both diagrams
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    EXCEL = 'QODE-Questionnaire.xlsm'

    # 1. Original tool-dependency graph (Graphviz DOT output)
    print("Generating tool dependency graph (Diagram_Technology) …")
    tech_diag = Technology_Diagram()
    tech_diag.create_technology_diagram(excel_path=EXCEL)
    print("Done — raw DOT file written as 'Diagram_Technology'")

    # 2. New propensity diagram (matplotlib PNG)
    print("Generating technology usage propensity diagram …")
    prop_diag = Technology_Propensity_Diagram()
    prop_diag.create_propensity_diagram(excel_path=EXCEL)
