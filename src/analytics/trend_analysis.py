import pandas as pd

def analyze_trends(df: pd.DataFrame):
    mapping = {"positive": 1, "neutral": 0, "negative": -1}
    df["sentiment_score"] = df["sentiment"].map(mapping)
    df["date"] = pd.to_datetime(df["date"])
    return (
        df.groupby(df["date"].dt.to_period("M"))["sentiment_score"]
        .mean()
        .reset_index()
    )
