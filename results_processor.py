import json
import os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go


class ResultsProcessor:
    def __init__(self, results_dir: str):
        self.results_dir = results_dir

    def load_results(self) -> pd.DataFrame:
        records = []

        for filename in os.listdir(self.results_dir):
            if filename.startswith("results_") and filename.endswith(".json"):
                with open(os.path.join(self.results_dir, filename), "r") as f:
                    result = json.load(f)
                    region = result["region"]
                    timestamp = result["timestamp"]
                    for exchange, metrics in result["exchanges"].items():
                        record = {
                            "region": region,
                            "timestamp": datetime.fromtimestamp(timestamp),
                            "exchange": exchange,
                            "avg_public_latency": metrics.get(
                                "avg_public_latency", None
                            ),
                            "avg_private_latency": metrics.get(
                                "avg_private_latency", None
                            ),
                        }
                        if record["avg_public_latency"] is not None:
                            record["avg_public_latency"] *= 1000
                        if record["avg_private_latency"] is not None:
                            record["avg_private_latency"] *= 1000
                        records.append(record)

        return pd.DataFrame(records)

    def generate_summary_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        summary = (
            df.groupby(["exchange", "region"])
            .agg({"avg_public_latency": "mean", "avg_private_latency": "mean"})
            .round(1)
        )
        summary.columns = ["Public API Latency (ms)", "Private API Latency (ms)"]
        return summary

    def create_heatmap(self, df: pd.DataFrame, latency_type: str) -> go.Figure:
        heatmap_data = df.pivot_table(
            values=f"avg_{latency_type}_latency",
            index="exchange",
            columns="region",
            aggfunc="mean",
        ).round(1)

        fig = go.Figure(
            data=go.Heatmap(
                z=heatmap_data.values,
                x=heatmap_data.columns,
                y=heatmap_data.index,
                text=heatmap_data.values.round(1),
                texttemplate="%{text} ms",
                textfont={"size": 10},
                colorscale="RdYlGn_r",
                showscale=True,
                colorbar_title="Latency (ms)",
            )
        )

        fig.update_layout(
            title=f"{latency_type.title()} API",
            xaxis_title="AWS Region",
            yaxis_title="Exchange",
            height=400,
            margin=dict(t=30, b=30),
        )

        return fig

    def generate_report(self) -> None:
        df = self.load_results()
        summary_stats = self.generate_summary_stats(df)
        public_heatmap = self.create_heatmap(df, "public")
        private_heatmap = self.create_heatmap(df, "private")

        html_content = f"""
        <html>
        <head>
            <title>Exchange Latency Analysis</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .stats-table {{
                    border-collapse: collapse;
                    width: 100%;
                    font-size: 13px;
                    margin: 10px 0;
                }}
                .stats-table th, .stats-table td {{
                    border: 1px solid #ddd;
                    padding: 6px 8px;
                }}
                .stats-table th {{
                    background-color: #f5f5f5;
                    font-weight: 600;
                    text-align: left;
                }}
                .stats-table td {{
                    text-align: right;
                }}
                .stats-table tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .section {{
                    margin: 20px 0;
                    padding: 15px;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #333;
                    border-bottom: 2px solid #eee;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                }}
                .heatmaps {{
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <h1>Exchange Latency Analysis</h1>
            
            <div class="section">
                <div class="heatmaps">
                    {public_heatmap.to_html(full_html=False, include_plotlyjs='cdn')}
                    {private_heatmap.to_html(full_html=False, include_plotlyjs='cdn')}
                </div>
            </div>
            
            <div class="section">
                <h2>Detailed Statistics</h2>
                {summary_stats.to_html(classes='stats-table')}
            </div>
            
            <footer>
                <p>Report created on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <a href="https://vanderwalt.de/blog/exchange-latency-explorer">vanderwalt.de</a>
            </footer>
        </body>
        </html>
        """

        with open(os.path.join(self.results_dir, "analysis.html"), "w") as f:
            f.write(html_content)


def main():
    processor = ResultsProcessor("./results")
    processor.generate_report()


if __name__ == "__main__":
    main()
