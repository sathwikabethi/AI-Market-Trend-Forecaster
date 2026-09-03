import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report
import pandas as pd

def plot_confusion_matrix(y_true, y_pred, path):
    labels = ["NEGATIVE", "POSITIVE"]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    sns.heatmap(cm, annot=True, fmt="d",
                xticklabels=labels, yticklabels=labels)
    plt.savefig(path)
    plt.close()

def plot_metrics(y_true, y_pred, path):
    report = classification_report(y_true, y_pred, output_dict=True)
    df = pd.DataFrame(report).transpose().iloc[:2][["precision","recall","f1-score"]]
    df.plot(kind="bar")
    plt.ylim(0,1)
    plt.savefig(path)
    plt.close()
