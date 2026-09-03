import numpy as np
from sklearn.linear_model import LinearRegression

def forecast_sentiment(trend_df, steps=3):
    trend_df["t"] = range(len(trend_df))
    X = trend_df[["t"]]
    y = trend_df["sentiment_score"]

    model = LinearRegression()
    model.fit(X, y)

    future_t = np.arange(len(trend_df), len(trend_df) + steps).reshape(-1, 1)
    preds = model.predict(future_t)

    return preds.tolist()
