import wandb
from wandb import util
from wandb.plots.utils import test_missing, test_types


chart_limit = wandb.Table.MAX_ROWS


def pr_curve(y_true=None, y_probas=None, labels=None, classes_to_plot=None):
    """
    Computes the tradeoff between precision and recall for different thresholds.
        A high area under the curve represents both high recall and high precision,
        where high precision relates to a low false positive rate, and high recall
        relates to a low false negative rate. High scores for both show that the
        classifier is returning accurate results (high precision), as well as
        returning a majority of all positive results (high recall).
        PR curve is useful when the classes are very imbalanced.

    Arguments:
    y_true (arr): Test set labels.
    y_probas (arr): Test set predicted probabilities.
    labels (list): Named labels for target varible (y). Makes plots easier to
      read by replacing target values with corresponding index.
      For example labels= ['dog', 'cat', 'owl'] all 0s are
      replaced by 'dog', 1s by 'cat'.

    Returns:
    Nothing. To see plots, go to your W&B run page then expand the 'media' tab
    under 'auto visualizations'.

    Example:
    wandb.log({'pr-curve': wandb.plot.pr_curve(y_true, y_probas, labels)})
    """
    np = util.get_module(
        "numpy",
        required="roc requires the numpy library, install with `pip install numpy`",
    )
    scikit = util.get_module(
        "sklearn",
        "roc requires the scikit library, install with `pip install scikit-learn`",
    )

    y_true = np.array(y_true)
    y_probas = np.array(y_probas)

    if test_missing(y_true=y_true, y_probas=y_probas) and test_types(
        y_true=y_true, y_probas=y_probas
    ):
        classes = np.unique(y_true)
        probas = y_probas

        if classes_to_plot is None:
            classes_to_plot = classes

        binarized_y_true = scikit.preprocessing.label_binarize(y_true, classes=classes)
        if len(classes) == 2:
            binarized_y_true = np.hstack((1 - binarized_y_true, binarized_y_true))

        pr_curves = {}
        indices_to_plot = np.in1d(classes, classes_to_plot)
        for i, to_plot in enumerate(indices_to_plot):
            if to_plot:
                precision, recall, _ = scikit.metrics.precision_recall_curve(
                    y_true, probas[:, i], pos_label=classes[i]
                )

                samples = 20
                sample_precision = []
                sample_recall = []
                for k in range(samples):
                    sample_precision.append(
                        precision[int(len(precision) * k / samples)]
                    )
                    sample_recall.append(recall[int(len(recall) * k / samples)])

                pr_curves[classes[i]] = (sample_precision, sample_recall)

        data = []
        count = 0
        for class_name in pr_curves:
            precision, recall = pr_curves[class_name]
            for p, r in zip(precision, recall):
                # if class_names are ints and labels are set
                if labels is not None and isinstance(
                    class_name, (int, np.integer)
                ):
                    class_name = labels[class_name]
                # if class_names are ints and labels are not set
                # or, if class_names have something other than ints
                # (string, float, date) - user class_names
                data.append([class_name, round(p, 3), round(r, 3)])
                count += 1
                if count >= chart_limit:
                    wandb.termwarn(
                        "wandb uses only the first %d datapoints to create the plots."
                        % wandb.Table.MAX_ROWS
                    )
                    break
        table = wandb.Table(columns=["class", "precision", "recall"], data=data)
        return wandb.plot_table(
            "wandb/area-under-curve/v0",
            table,
            {"x": "recall", "y": "precision", "class": "class"},
            {"title": "Precision v. Recall"},
        )
