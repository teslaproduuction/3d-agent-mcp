"""
Analytics handler — builds Plotly charts and summary stats from the metrics DB.
"""
import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def _load_df() -> pd.DataFrame:
    try:
        from utils.metrics_collector import load_records_df
        return load_records_df()
    except Exception as e:
        logger.warning(f"Could not load metrics: {e}")
        return pd.DataFrame()


def _empty_fig(msg: str = "Нет данных"):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, showarrow=False,
                       xref="paper", yref="paper", font=dict(size=16))
    fig.update_layout(xaxis_visible=False, yaxis_visible=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(t=20, b=20, l=20, r=20))
    return fig


class AnalyticsMixin:

    # ── Main refresh ───────────────────────────────────────────────────────

    def handle_refresh_analytics(self):
        """Return all analytics outputs in one call."""
        df = _load_df()

        if df.empty:
            empty = _empty_fig()
            return (
                "Нет данных", "—", "—", "—", "—", "—",
                empty, empty, empty, empty, empty, empty,
                pd.DataFrame(),
            )

        summary    = self._build_summary(df)
        fig_time   = self._fig_time_breakdown(df)
        fig_hist   = self._fig_time_history(df)
        fig_res    = self._fig_resources(df)
        fig_gci    = self._fig_gci_distribution(df)
        fig_models = self._fig_models_comparison(df)
        fig_corr   = self._fig_gci_vs_time(df)
        table      = self._build_table(df)

        return (
            summary["total"],
            summary["avg_time"],
            summary["avg_vram"],
            summary["avg_faces"],
            summary["avg_gci"],
            summary["success_rate"],
            fig_time,
            fig_hist,
            fig_res,
            fig_gci,
            fig_models,
            fig_corr,
            table,
        )

    # ── Summary cards ──────────────────────────────────────────────────────

    def _build_summary(self, df: pd.DataFrame) -> dict:
        total = len(df)
        avg_time = df["time_3d_gen"].dropna().mean()
        avg_vram = df["peak_vram_gb"].dropna().mean()
        avg_faces = df["face_count"].dropna().mean()
        avg_gci = df["gci_total"].dropna().mean()
        has_time = df["time_3d_gen"].notna().sum()
        return {
            "total":       f"{total}",
            "avg_time":    f"{avg_time:.1f} сек" if not pd.isna(avg_time) else "—",
            "avg_vram":    f"{avg_vram:.1f} GB"  if not pd.isna(avg_vram) else "—",
            "avg_faces":   f"{int(avg_faces):,}" if not pd.isna(avg_faces) else "—",
            "avg_gci":     f"{avg_gci:.3f}"      if not pd.isna(avg_gci)  else "—",
            "success_rate": f"{has_time}/{total}",
        }

    # ── Chart: time breakdown (stacked bar per model) ──────────────────────

    def _fig_time_breakdown(self, df: pd.DataFrame):
        import plotly.graph_objects as go

        cols = {
            "time_image_gen":  "Генерация изображения",
            "time_3d_gen":     "Генерация 3D",
            "time_postprocess":"Постобработка",
        }
        df2 = df[["model_name"] + list(cols.keys())].copy()
        df2 = df2.dropna(subset=["time_3d_gen"])

        if df2.empty:
            return _empty_fig("Нет данных о времени")

        # Clamp negatives to 0 (can appear from clock skew or unset fields)
        for col in cols:
            df2[col] = df2[col].clip(lower=0)

        # Average per model
        grp = df2.groupby("model_name")[list(cols.keys())].mean().reset_index()

        colors = ["#4C78A8", "#F58518", "#E45756"]
        fig = go.Figure()
        for (col, label), color in zip(cols.items(), colors):
            vals = grp[col].fillna(0).clip(lower=0)
            # Skip bars that are all zero (not measured)
            if vals.sum() == 0:
                continue
            fig.add_trace(go.Bar(
                name=label,
                x=grp["model_name"],
                y=vals,
                marker_color=color,
            ))
        fig.update_layout(
            barmode="stack",
            title="Среднее время по этапам (сек)",
            xaxis_title="Модель",
            yaxis_title="Время (сек)",
            yaxis=dict(rangemode="nonnegative"),
            legend=dict(orientation="h", y=-0.25),
            margin=dict(t=40, b=80, l=50, r=20),
        )
        return fig

    # ── Chart: generation time history ────────────────────────────────────

    def _fig_time_history(self, df: pd.DataFrame):
        import plotly.graph_objects as go

        df2 = df[["timestamp", "time_3d_gen", "model_name"]].dropna(subset=["time_3d_gen"]).copy()
        if df2.empty:
            return _empty_fig("Нет данных о времени")

        df2 = df2.sort_values("timestamp")
        fig = go.Figure()

        for model in df2["model_name"].unique():
            sub = df2[df2["model_name"] == model]
            fig.add_trace(go.Scatter(
                x=sub["timestamp"],
                y=sub["time_3d_gen"],
                mode="lines+markers",
                name=model,
            ))

        fig.update_layout(
            title="История времени генерации 3D (сек)",
            xaxis_title="Время",
            yaxis_title="Секунды",
            legend=dict(orientation="h", y=-0.3),
            margin=dict(t=40, b=80, l=50, r=20),
        )
        return fig

    # ── Chart: peak resource usage per model ──────────────────────────────

    def _fig_resources(self, df: pd.DataFrame):
        import plotly.graph_objects as go

        df2 = df[["model_name", "peak_vram_gb", "peak_cpu_pct", "peak_ram_gb"]].copy()
        df2 = df2.dropna(subset=["model_name"])
        grp = df2.groupby("model_name").mean().reset_index()

        if grp.empty:
            return _empty_fig("Нет данных о ресурсах")

        fig = go.Figure()
        fig.add_trace(go.Bar(name="Пиковый VRAM (GB)", x=grp["model_name"],
                             y=grp["peak_vram_gb"].fillna(0), marker_color="#72B7B2"))
        fig.add_trace(go.Bar(name="Пиковый RAM (GB)", x=grp["model_name"],
                             y=grp["peak_ram_gb"].fillna(0), marker_color="#54A24B"))
        fig.add_trace(go.Bar(name="Пиковый CPU (%)", x=grp["model_name"],
                             y=grp["peak_cpu_pct"].fillna(0) / 10,  # scale for visibility
                             marker_color="#EECA3B",
                             customdata=grp["peak_cpu_pct"].fillna(0),
                             hovertemplate="CPU: %{customdata:.1f}%<extra></extra>"))
        fig.update_layout(
            barmode="group",
            title="Среднее пиковое потребление ресурсов",
            xaxis_title="Модель",
            yaxis_title="GB / (CPU%/10)",
            legend=dict(orientation="h", y=-0.3),
            margin=dict(t=40, b=80, l=50, r=20),
        )
        return fig

    # ── Chart: GCI distribution (histogram) ───────────────────────────────

    def _fig_gci_distribution(self, df: pd.DataFrame):
        import plotly.graph_objects as go

        gci_vals = df["gci_total"].dropna()
        if gci_vals.empty:
            return _empty_fig("GCI не вычислен")

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=gci_vals,
            nbinsx=20,
            marker_color="#4C78A8",
            opacity=0.75,
            name="GCI",
        ))

        # Threshold lines
        for val, color, label in [
            (0.5, "green",  "Простая < 0.5"),
            (0.8, "orange", "Средняя < 0.8"),
        ]:
            fig.add_vline(x=val, line_dash="dash", line_color=color,
                          annotation_text=label, annotation_position="top right")

        fig.update_layout(
            title="Распределение GCI сгенерированных моделей",
            xaxis_title="GCI (Индекс геометрической сложности)",
            yaxis_title="Количество моделей",
            margin=dict(t=40, b=50, l=50, r=20),
        )
        return fig

    # ── Chart: model comparison (face count + GCI) ────────────────────────

    def _fig_models_comparison(self, df: pd.DataFrame):
        import plotly.graph_objects as go

        df2 = df[["model_name", "face_count", "gci_total", "time_3d_gen"]].dropna(subset=["model_name"]).copy()
        grp = df2.groupby("model_name").agg(
            face_count=("face_count", "mean"),
            gci_total=("gci_total", "mean"),
            time_3d_gen=("time_3d_gen", "mean"),
            count=("model_name", "count"),
        ).reset_index()

        if grp.empty:
            return _empty_fig("Нет данных для сравнения")

        fig = go.Figure()

        # Bubble chart: x=model, y=faces, size=time, color=GCI
        gci_vals = grp["gci_total"].fillna(0)
        sizes = grp["time_3d_gen"].fillna(30).clip(5, 600)

        fig.add_trace(go.Scatter(
            x=grp["model_name"],
            y=grp["face_count"].fillna(0),
            mode="markers+text",
            marker=dict(
                size=(sizes / sizes.max() * 60 + 10).tolist(),
                color=gci_vals,
                colorscale="RdYlGn_r",
                showscale=True,
                colorbar=dict(title="GCI"),
                cmin=0, cmax=1,
            ),
            text=[f"N={int(c)}" for c in grp["count"]],
            textposition="top center",
            customdata=grp[["gci_total", "time_3d_gen"]].fillna(0).values,
            hovertemplate="<b>%{x}</b><br>Полигонов: %{y:,.0f}<br>GCI: %{customdata[0]:.3f}<br>Время: %{customdata[1]:.1f}с<extra></extra>",
        ))

        fig.update_layout(
            title="Сравнение моделей (пузырьки = время, цвет = GCI)",
            xaxis_title="Модель",
            yaxis_title="Среднее кол-во полигонов",
            margin=dict(t=40, b=60, l=60, r=20),
        )
        return fig

    # ── Chart: GCI vs generation time (scatter with regression) ──────────

    def _fig_gci_vs_time(self, df: pd.DataFrame):
        import plotly.graph_objects as go
        import numpy as np

        df2 = df[["gci_total", "time_3d_gen", "model_name"]].dropna()
        if df2.empty:
            return _empty_fig("Нет данных GCI / время")

        colors_map = {}
        palette = ["#4C78A8", "#F58518", "#E45756", "#72B7B2", "#54A24B"]
        for i, m in enumerate(df2["model_name"].unique()):
            colors_map[m] = palette[i % len(palette)]

        fig = go.Figure()
        for model, sub in df2.groupby("model_name"):
            fig.add_trace(go.Scatter(
                x=sub["gci_total"],
                y=sub["time_3d_gen"],
                mode="markers",
                name=model,
                marker=dict(color=colors_map[model], size=8, opacity=0.7),
            ))

        # Regression line if enough points
        if len(df2) >= 3:
            x = df2["gci_total"].values
            y = df2["time_3d_gen"].values
            try:
                coef = np.polyfit(x, y, 1)
                x_line = np.linspace(x.min(), x.max(), 50)
                y_line = np.polyval(coef, x_line)
                fig.add_trace(go.Scatter(
                    x=x_line, y=y_line,
                    mode="lines",
                    name=f"Тренд (y={coef[0]:.1f}x+{coef[1]:.1f})",
                    line=dict(color="black", dash="dash", width=1),
                ))
            except Exception:
                pass

        fig.update_layout(
            title="GCI vs Время генерации",
            xaxis_title="GCI (геометрическая сложность)",
            yaxis_title="Время генерации 3D (сек)",
            legend=dict(orientation="h", y=-0.3),
            margin=dict(t=40, b=80, l=60, r=20),
        )
        return fig

    # ── Table ──────────────────────────────────────────────────────────────

    def _build_table(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = {
            "timestamp":        "Время",
            "model_name":       "Модель",
            "face_count":       "Полигонов",
            "gci_total":        "GCI",
            "time_3d_gen":      "Время 3D (с)",
            "time_total":       "Всего (с)",
            "peak_vram_gb":     "VRAM GB",
            "peak_cpu_pct":     "CPU %",
            "is_manifold":      "Manifold",
            "predicted_mae_mm": "MAE прогноз",
        }

        df2 = df.copy()

        # Add predicted MAE from GCI
        if "gci_total" in df2.columns:
            from utils.mesh_analyzer import predicted_mae
            df2["predicted_mae_mm"] = df2["gci_total"].apply(
                lambda g: f"{predicted_mae(g):.3f}" if pd.notna(g) else "—"
            )
        else:
            df2["predicted_mae_mm"] = "—"

        available = [c for c in cols if c in df2.columns]
        out = df2[available].copy().rename(columns=cols).head(50)

        # Format
        if "Время" in out:
            out["Время"] = pd.to_datetime(out["Время"]).dt.strftime("%d.%m %H:%M")
        if "GCI" in out:
            out["GCI"] = out["GCI"].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "—")
        if "Полигонов" in out:
            out["Полигонов"] = out["Полигонов"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
        if "Время 3D (с)" in out:
            out["Время 3D (с)"] = out["Время 3D (с)"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
        if "Всего (с)" in out:
            out["Всего (с)"] = out["Всего (с)"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
        if "VRAM GB" in out:
            out["VRAM GB"] = out["VRAM GB"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
        if "CPU %" in out:
            out["CPU %"] = out["CPU %"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
        if "Manifold" in out:
            out["Manifold"] = out["Manifold"].apply(lambda x: "✅" if x else "❌")

        return out
