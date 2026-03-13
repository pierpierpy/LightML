from math import comb
import numpy as np


def contingency_table(scores_a, scores_b):
    a = np.asarray(scores_a)
    b = np.asarray(scores_b)
    if len(a) != len(b):
        raise ValueError(
            f"Score vectors must have same length: {len(a)} vs {len(b)}"
        )

    both_correct = int(np.sum((a == 1) & (b == 1)))
    only_a = int(np.sum((a == 1) & (b == 0)))
    only_b = int(np.sum((a == 0) & (b == 1)))
    both_wrong = int(np.sum((a == 0) & (b == 0)))

    return {
        "both_correct": both_correct,
        "only_a": only_a,
        "only_b": only_b,
        "both_wrong": both_wrong,
        "n_discordant": only_a + only_b,
        "n_total": len(a),
    }



def bootstrap_ci(scores_a, scores_b, n_bootstrap=10000, confidence=0.95, seed=42):
    a = np.asarray(scores_a, dtype=np.float64)
    b = np.asarray(scores_b, dtype=np.float64)
    if len(a) != len(b):
        raise ValueError(
            f"Score vectors must have same length: {len(a)} vs {len(b)}"
        )

    n = len(a)
    observed_delta = a.mean() - b.mean()

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n, size=(n_bootstrap, n))
    means_a = a[indices].mean(axis=1)
    means_b = b[indices].mean(axis=1)
    deltas = np.sort(means_a - means_b)

    alpha = 1 - confidence
    lo = float(deltas[int(n_bootstrap * alpha / 2)])
    hi = float(deltas[int(n_bootstrap * (1 - alpha / 2))])

    return {
        "delta": float(observed_delta),
        "ci_lower": lo,
        "ci_upper": hi,
        "confidence": confidence,
    }
    

def mcnemar_test(scores_a, scores_b, table=None):
    if table is None:
        table = contingency_table(scores_a, scores_b)
    b = table["only_a"]
    c = table["only_b"]
    n = b + c

    if n == 0:
        return {"p_value": 1.0, "significant": False, "winner": None}

    k = min(b, c)
    p_value = 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    p_value = min(p_value, 1.0)

    winner = None
    if p_value < 0.05:
        winner = "a" if b > c else "b"

    return {
        "p_value": p_value,
        "significant": p_value < 0.05,
        "winner": winner,
    }



def compare_models_stats(scores_a, scores_b):
    a = np.asarray(scores_a, dtype=np.float64)
    b = np.asarray(scores_b, dtype=np.float64)

    table = contingency_table(a, b)
    mcnemar = mcnemar_test(a, b, table=table)
    ci = bootstrap_ci(a, b)

    return {
        "contingency": table,
        "mcnemar": mcnemar,
        "bootstrap": ci,
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
    }