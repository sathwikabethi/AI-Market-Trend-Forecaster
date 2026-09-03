def prepare_eval_data(texts, labels, predictor):
    y_true, y_pred = [], []
    for t, l in zip(texts, labels):
        y_true.append(l.upper())
        y_pred.append(predictor(t)["label"])
    return y_true, y_pred
